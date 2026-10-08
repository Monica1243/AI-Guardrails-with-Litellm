"""
PII detection and redaction.

Detection: Microsoft Presidio Analyzer
Redaction: Microsoft Presidio Anonymizer

Supported actions:
    - warn
    - redact
    - block
"""

from typing import Any

from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from core.types import (
    ValidationAction,
    ValidationOutcome,
    ValidationStage,
    ValidatorRequest,
    ValidatorResponse,
)


class PIIValidator:

    name = "pii"
    stage = ValidationStage.PREBUILT

    def __init__(
        self,
        analyzer: AnalyzerEngine | None = None,
        anonymizer: AnonymizerEngine | None = None,
    ) -> None:
        self.analyzer = analyzer or AnalyzerEngine()
        self.anonymizer = anonymizer or AnonymizerEngine()
        self.default_language = "en"
        self.default_replacement = "<REDACTED>"

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def validate(self, request: ValidatorRequest) -> ValidatorResponse:
        text = request.input
        config = request.config
        options = config.options

        language = self._get_language(options)
        entities = self._get_entities(options)
        replacement = self._get_replacement(options)

        results = self._analyze(text, language, entities)

        if not results:
            return ValidatorResponse(
                validator=self.name,
                stage=self.stage,
                action=config.action,
                outcome=ValidationOutcome.ALLOWED,
                output=text,
                metadata={
                    "detected_entities": [],
                    "detection_count": 0,
                },
            )

        detected_entities = self._get_detected_entities(results)
        metadata: dict[str, Any] = {
            "detected_entities": detected_entities,
            "detection_count": len(results),
        }

        if config.action == ValidationAction.WARN:
            return ValidatorResponse(
                validator=self.name,
                stage=self.stage,
                action=config.action,
                outcome=ValidationOutcome.WARNED,
                output=text,
                reason="PII detected",
                metadata=metadata,
            )

        if config.action == ValidationAction.BLOCK:
            return ValidatorResponse(
                validator=self.name,
                stage=self.stage,
                action=config.action,
                outcome=ValidationOutcome.BLOCKED,
                output=text,
                reason="PII detected",
                metadata=metadata,
            )

        if config.action == ValidationAction.REDACT:
            redacted_text = self._redact(text, results, replacement)

            return ValidatorResponse(
                validator=self.name,
                stage=self.stage,
                action=config.action,
                outcome=ValidationOutcome.REDACTED,
                output=redacted_text,
                reason="PII detected and redacted",
                metadata=metadata,
            )

        raise ValueError(f"Unsupported validation action: {config.action}")

    # ------------------------------------------------------------------
    # Detection and redaction
    # ------------------------------------------------------------------

    def _analyze(
        self,
        text: str,
        language: str,
        entities: list[str] | None,
    ) -> list[RecognizerResult]:
        return self.analyzer.analyze(
            text=text,
            language=language,
            entities=entities,
        )

    def _redact(
        self,
        text: str,
        results: list[RecognizerResult],
        replacement: str,
    ) -> str:
        operators = {
            "DEFAULT": OperatorConfig("replace", {"new_value": replacement})
        }

        anonymized = self.anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=operators,
        )

        return anonymized.text

    def _get_detected_entities(self, results: list[RecognizerResult]) -> list[str]:
        return sorted({result.entity_type for result in results})

    # ------------------------------------------------------------------
    # Options parsing
    # ------------------------------------------------------------------

    def _get_language(self, options: dict[str, Any]) -> str:
        language = options.get("language", self.default_language)

        if not isinstance(language, str) or not language.strip():
            raise ValueError(
                "PII validator option 'language' must be a non-empty string"
            )

        return language

    def _get_entities(self, options: dict[str, Any]) -> list[str] | None:
        entities = options.get("entities")

        if entities is None:
            return None

        if not isinstance(entities, list):
            raise ValueError("PII validator option 'entities' must be a list")

        if not all(isinstance(e, str) for e in entities):
            raise ValueError(
                "PII validator option 'entities' must contain only strings"
            )

        return entities

    def _get_replacement(self, options: dict[str, Any]) -> str:
        replacement = options.get("replacement", self.default_replacement)

        if not isinstance(replacement, str) or not replacement.strip():
            raise ValueError(
                "PII validator option 'replacement' must be a non-empty string"
            )

        return replacement
