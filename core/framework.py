"""
Main guardrails orchestration engine.

Execution order:
    1. Prebuilt validators
    2. AI validators

Pipeline behavior:
    allowed  -> continue
    warned   -> continue with original output
    redacted -> continue with modified output
    blocked  -> stop immediately

Validator registration is handled by config.py.
Validator execution is controlled by config.yml.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from config import VALIDATOR_REGISTRY
from core.config_loader import ConfigLoader
from core.types import (
    GuardrailsConfig,
    GuardrailsRequest,
    GuardrailsResponse,
    ValidationFailureMode,
    ValidationOutcome,
    ValidationStage,
    ValidatorConfig,
    ValidatorRequest,
    ValidatorResponse,
)

logger = logging.getLogger(__name__)

ValidatorInstance = Any
ValidatorClass = Callable[[], ValidatorInstance]


class GuardrailsFramework:

    def __init__(
        self,
        config: GuardrailsConfig,
        validator_registry: dict[str, ValidatorClass] | None = None,
    ) -> None:
        self._config = config
        self._registry = validator_registry if validator_registry is not None else VALIDATOR_REGISTRY
        self._validators: dict[str, ValidatorInstance] = {}

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def validate(self, request: GuardrailsRequest) -> GuardrailsResponse:
        current_input = request.input

        logger.info(
            "Starting guardrails validation",
            extra={"request_id": request.request_id, "model": request.model},
        )

        # Stage 1: prebuilt validators
        prebuilt_result = await self._run_stage(
            request=request,
            input_text=current_input,
            configs=self._config.prebuilt_validators,
            expected_stage=ValidationStage.PREBUILT,
        )

        if prebuilt_result is not None:
            if prebuilt_result.outcome == ValidationOutcome.BLOCKED:
                return self._build_response(request, prebuilt_result)
            current_input = prebuilt_result.output

        # Stage 2: AI validators
        ai_result = await self._run_stage(
            request=request,
            input_text=current_input,
            configs=self._config.ai_validators,
            expected_stage=ValidationStage.AI,
        )

        if ai_result is not None:
            if ai_result.outcome == ValidationOutcome.BLOCKED:
                return self._build_response(request, ai_result)
            current_input = ai_result.output

        logger.info(
            "Guardrails validation completed",
            extra={"request_id": request.request_id, "outcome": ValidationOutcome.ALLOWED.value},
        )

        return GuardrailsResponse(
            request_id=request.request_id,
            outcome=ValidationOutcome.ALLOWED,
            output=current_input,
            metadata={"model": request.model},
        )

    # ------------------------------------------------------------------
    # Stage execution
    # ------------------------------------------------------------------

    async def _run_stage(
        self,
        request: GuardrailsRequest,
        input_text: str,
        configs: list[ValidatorConfig],
        expected_stage: ValidationStage,
    ) -> ValidatorResponse | None:
        current_input = input_text
        last_result: ValidatorResponse | None = None

        for config in configs:
            validator = self._get_validator(config.name)
            self._validate_stage(validator, expected_stage)

            result = await self._execute_validator(
                validator=validator,
                request=ValidatorRequest(input=current_input, config=config),
            )

            last_result = result

            logger.info(
                "Validator completed",
                extra={
                    "request_id": request.request_id,
                    "validator": result.validator,
                    "stage": result.stage.value,
                    "outcome": result.outcome.value,
                },
            )

            if result.outcome == ValidationOutcome.BLOCKED:
                logger.warning(
                    "Request blocked by validator",
                    extra={
                        "request_id": request.request_id,
                        "validator": result.validator,
                        "stage": result.stage.value,
                        "reason": result.reason,
                    },
                )
                return result

            if result.outcome in {
                ValidationOutcome.REDACTED,
                ValidationOutcome.WARNED,
                ValidationOutcome.ALLOWED,
            }:
                current_input = result.output
                continue

            raise RuntimeError(
                f"Validator '{result.validator}' returned unsupported outcome '{result.outcome}'"
            )

        return last_result

    # ------------------------------------------------------------------
    # Validator execution
    # ------------------------------------------------------------------

    async def _execute_validator(
        self, validator: Any, request: ValidatorRequest
    ) -> ValidatorResponse:
        timeout_seconds = request.config.timeout / 1000

        try:
            if asyncio.iscoroutinefunction(validator.validate):
                # Async validator — call and await with timeout
                response = await asyncio.wait_for(
                    validator.validate(request),
                    timeout=timeout_seconds,
                )
            else:
                # Sync validator — run in a thread so it doesn't block the event
                # loop, and still enforce the configured timeout
                loop = asyncio.get_running_loop()
                with ThreadPoolExecutor(max_workers=1) as pool:
                    response = await asyncio.wait_for(
                        loop.run_in_executor(pool, validator.validate, request),
                        timeout=timeout_seconds,
                    )

        except asyncio.TimeoutError:
            return self._handle_failure(
                request,
                TimeoutError(
                    f"Validator '{request.config.name}' timed out after {request.config.timeout}ms"
                ),
            )

        except Exception as exc:
            return self._handle_failure(request, exc)

        if not isinstance(response, ValidatorResponse):
            return self._handle_failure(
                request,
                TypeError(
                    f"Validator '{request.config.name}' must return ValidatorResponse, "
                    f"got {type(response).__name__}"
                ),
            )

        return response

    def _handle_failure(self, request: ValidatorRequest, error: Exception) -> ValidatorResponse:
        logger.exception(
            "Validator execution failed",
            extra={
                "validator": request.config.name,
                "timeout_ms": request.config.timeout,
                "failure_mode": self._config.failure_mode.value,
            },
        )

        outcome = (
            ValidationOutcome.BLOCKED
            if self._config.failure_mode == ValidationFailureMode.FAIL_CLOSED
            else ValidationOutcome.WARNED
        )

        return ValidatorResponse(
            validator=request.config.name,
            stage=self._get_validator_stage(request.config.name),
            action=request.config.action,
            outcome=outcome,
            output=request.input,
            reason=f"Validator execution failed: {type(error).__name__}",
            metadata={"failure": True, "error_type": type(error).__name__},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_validator(self, validator_name: str) -> ValidatorInstance:
        if validator_name not in self._registry:
            raise ValueError(f"Validator '{validator_name}' is not registered")

        if validator_name not in self._validators:
            try:
                self._validators[validator_name] = self._registry[validator_name]()
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to initialize validator '{validator_name}'"
                ) from exc

        return self._validators[validator_name]

    def _get_validator_stage(self, validator_name: str) -> ValidationStage:
        validator = self._get_validator(validator_name)
        stage = getattr(validator, "stage", None)

        if not isinstance(stage, ValidationStage):
            raise ValueError(f"Validator '{validator_name}' has an invalid stage")

        return stage

    def _validate_stage(self, validator: ValidatorInstance, expected_stage: ValidationStage) -> None:
        actual_stage = getattr(validator, "stage", None)

        if actual_stage != expected_stage:
            validator_name = getattr(validator, "name", validator.__class__.__name__)
            raise ValueError(
                f"Validator '{validator_name}' is registered in the wrong stage. "
                f"Expected '{expected_stage.value}', got '{actual_stage.value if actual_stage else actual_stage}'."
            )

    def _build_response(self, request: GuardrailsRequest, result: ValidatorResponse) -> GuardrailsResponse:
        return GuardrailsResponse(
            request_id=request.request_id,
            outcome=result.outcome,
            output=result.output,
            validator=result.validator,
            reason=result.reason,
            metadata={
                "model": request.model,
                "stage": result.stage.value,
                **result.metadata,
            },
        )

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_yaml(
        cls,
        config_path: str | Path = "config.yml",
        validator_registry: dict[str, ValidatorClass] | None = None,
    ) -> "GuardrailsFramework":
        config = ConfigLoader(config_path=config_path).load()
        return cls(config=config, validator_registry=validator_registry)
