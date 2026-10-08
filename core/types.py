from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ValidationOutcome(str, Enum):
    ALLOWED = "allowed"
    WARNED = "warned"
    REDACTED = "redacted"
    BLOCKED = "blocked"


class ValidationAction(str, Enum):
    WARN = "warn"
    REDACT = "redact"
    BLOCK = "block"


class ValidationStage(str, Enum):
    PREBUILT = "prebuilt"
    AI = "ai"


class ValidationFailureMode(str, Enum):
    FAIL_OPEN = "open"
    FAIL_CLOSED = "closed"


class GuardrailsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    model: str
    input: str
    user: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GuardrailsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    outcome: ValidationOutcome
    output: str
    validator: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidatorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    action: ValidationAction
    timeout: int = Field(default=1000, gt=0)
    options: dict[str, Any] = Field(default_factory=dict)


class ValidatorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: str
    config: ValidatorConfig


class ValidatorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    validator: str
    stage: ValidationStage
    action: ValidationAction
    outcome: ValidationOutcome
    output: str
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GuardrailsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_mode: ValidationFailureMode = (
        ValidationFailureMode.FAIL_CLOSED
    )

    prebuilt_validators: list[ValidatorConfig] = Field(
        default_factory=list
    )

    ai_validators: list[ValidatorConfig] = Field(
        default_factory=list
    )