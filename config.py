from prebuilt_validators.pii_validator import PIIValidator
from ai_validators.prompt_injection_validator import PromptInjectionValidator


VALIDATOR_REGISTRY = {
    PIIValidator.name: PIIValidator,
    PromptInjectionValidator.name: PromptInjectionValidator,
}