"""
AI-based prompt injection validator.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx

from core.types import (
    ValidationAction,
    ValidationOutcome,
    ValidationStage,
    ValidatorRequest,
    ValidatorResponse,
)

logger = logging.getLogger(__name__)


class PromptInjectionValidator:

    name = "prompt_injection"
    stage = ValidationStage.AI

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._ollama_host = self._get_ollama_host()
        self._ollama_model = self._get_ollama_model()
        self._prompt_template = self._load_prompt()

    async def validate(self, request: ValidatorRequest) -> ValidatorResponse:
        config = request.config
        text = request.input

        prompt = self._prompt_template.replace("{{ user_input }}", text)

        result = await self._classify(prompt, config.timeout)

        is_injection = result["is_prompt_injection"]
        metadata: dict[str, Any] = {
            "confidence": result["confidence"],
            "categories": result["categories"],
            "model": self._ollama_model,
        }

        if not is_injection:
            return ValidatorResponse(
                validator=self.name,
                stage=self.stage,
                action=config.action,
                outcome=ValidationOutcome.ALLOWED,
                output=text,
                metadata=metadata,
            )

        if config.action == ValidationAction.WARN:
            return ValidatorResponse(
                validator=self.name,
                stage=self.stage,
                action=config.action,
                outcome=ValidationOutcome.WARNED,
                output=text,
                reason=result["reason"],
                metadata=metadata,
            )

        if config.action == ValidationAction.BLOCK:
            return ValidatorResponse(
                validator=self.name,
                stage=self.stage,
                action=config.action,
                outcome=ValidationOutcome.BLOCKED,
                output=text,
                reason=result["reason"],
                metadata=metadata,
            )

        if config.action == ValidationAction.REDACT:
            return ValidatorResponse(
                validator=self.name,
                stage=self.stage,
                action=config.action,
                outcome=ValidationOutcome.REDACTED,
                output="<REDACTED>",
                reason=result["reason"],
                metadata=metadata,
            )

        raise ValueError(f"Unsupported validation action: {config.action}")

    # ------------------------------------------------------------------
    # Invoking Ollama Model to identify prompt injection
    # ------------------------------------------------------------------

    async def _classify(self, prompt: str, timeout: int) -> dict[str, Any]:
        client = self._client or httpx.AsyncClient()

        try:
            response = await client.post(
                f"{self._ollama_host}/api/generate",
                json={
                    "model": self._ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
                timeout=timeout / 1000,
            )

            response.raise_for_status()

            payload = response.json()
            raw_response = payload.get("response")

            if not isinstance(raw_response, str):
                raise ValueError(
                    "Ollama response does not contain a valid 'response' field"
                )

            logger.debug("Ollama raw response: %r", raw_response)

            return self._parse_response(raw_response)

        except httpx.TimeoutException as exc:
            raise TimeoutError(
                f"Ollama validation timed out after {timeout}ms"
            ) from exc

        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Ollama validation request failed: {exc}"
            ) from exc

        finally:
            if self._client is None:
                await client.aclose()

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _get_ollama_host(self) -> str:
        host = os.getenv("OLLAMA_HOST", "http://ollama:11434")

        if not host or not host.strip():
            raise ValueError(
                "Environment variable OLLAMA_HOST must be a non-empty string"
            )

        return host.rstrip("/")

    def _get_ollama_model(self) -> str:
        model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

        if not model or not model.strip():
            raise ValueError(
                "Environment variable OLLAMA_MODEL must be a non-empty string"
            )

        return model.strip()

    def _load_prompt(self) -> str:
        prompt_file = Path(__file__).parent / "prompts" / "prompt_injection.poml"

        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

        return prompt_file.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(self, raw_response: str) -> dict[str, Any]:
        try:
            result = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise ValueError("Ollama returned invalid JSON") from exc

        if not isinstance(result, dict):
            raise ValueError("Ollama response must be a JSON object")

        is_prompt_injection = result.get("is_prompt_injection")
        confidence = result.get("confidence")
        reason = result.get("reason")
        categories = result.get("categories")

        # Coerce string booleans — small models sometimes return "true"/"false"
        if isinstance(is_prompt_injection, str):
            if is_prompt_injection.lower() == "true":
                is_prompt_injection = True
            elif is_prompt_injection.lower() == "false":
                is_prompt_injection = False

        if not isinstance(is_prompt_injection, bool):
            raise ValueError("'is_prompt_injection' must be a boolean")

        # Coerce string numbers
        if isinstance(confidence, str):
            try:
                confidence = float(confidence)
            except (ValueError, TypeError):
                pass

        if (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0.0 <= float(confidence) <= 1.0
        ):
            raise ValueError("'confidence' must be a number between 0.0 and 1.0")

        if not isinstance(reason, str):
            raise ValueError("'reason' must be a string")

        if not isinstance(categories, list) or not all(
            isinstance(c, str) for c in categories
        ):
            raise ValueError("'categories' must be a list of strings")

        return {
            "is_prompt_injection": is_prompt_injection,
            "confidence": float(confidence),
            "reason": reason,
            "categories": categories,
        }
