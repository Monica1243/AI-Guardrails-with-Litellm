"""
Loads and validates guardrails configuration from a YAML file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from core.types import GuardrailsConfig


class ConfigLoader:

    def __init__(self, config_path: str | Path = "config.yml") -> None:
        self._config_path = Path(config_path)

    def load(self) -> GuardrailsConfig:
        raw = self._read_yaml()

        guardrails_config = raw.get("pipeline")

        if guardrails_config is None:
            raise ValueError(
                "Missing required 'pipeline' section in configuration"
            )

        if not isinstance(guardrails_config, dict):
            raise ValueError("'pipeline' configuration must be a mapping")

        try:
            return GuardrailsConfig.model_validate(guardrails_config)
        except Exception as exc:
            raise ValueError("Invalid guardrails configuration") from exc

    def _read_yaml(self) -> dict[str, Any]:
        if not self._config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self._config_path}"
            )

        if not self._config_path.is_file():
            raise ValueError(
                f"Configuration path is not a file: {self._config_path}"
            )

        try:
            with self._config_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ValueError(
                f"Invalid YAML configuration: {self._config_path}"
            ) from exc

        if data is None:
            raise ValueError("Configuration file is empty")

        if not isinstance(data, dict):
            raise ValueError("Root configuration must be a mapping")

        return data
