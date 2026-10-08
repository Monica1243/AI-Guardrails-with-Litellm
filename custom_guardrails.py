"""
LiteLLM Proxy callback that executes the internal GuardrailsFramework before an LLM request is sent upstream.
"""

from __future__ import annotations

import uuid
from typing import Any

from litellm.integrations.custom_logger import CustomLogger

from core.framework import GuardrailsFramework
from core.types import (
    GuardrailsRequest,
    ValidationOutcome,
)


class GuardrailsCallback(CustomLogger):

    def __init__(self) -> None:
        super().__init__()
        self._framework = GuardrailsFramework.from_yaml(config_path="config.yml")

    async def async_pre_call_hook(
        self,
        user_api_key_dict: Any,
        cache: Any,
        data: dict[str, Any],
        call_type: str,
    ) -> dict[str, Any]:

        if call_type not in {"completion", "acompletion", "text_completion"}:
            return data

        messages = data.get("messages")

        if not isinstance(messages, list) or not messages:
            return data

        user_message_index = self._find_latest_user_message(messages)

        if user_message_index is None:
            return data

        content = messages[user_message_index].get("content")

        if not isinstance(content, str):
            return data

        request = GuardrailsRequest(
            request_id=self._get_request_id(data),
            model=data.get("model", "unknown"),
            input=content,
            user=data.get("user"),
            metadata={"call_type": call_type},
        )

        result = await self._framework.validate(request)

        if result.outcome == ValidationOutcome.BLOCKED:
            raise ValueError(result.reason or "Request blocked by guardrails")

        if result.output != content:
            messages[user_message_index]["content"] = result.output

        return data

    def _find_latest_user_message(self, messages: list[dict[str, Any]]) -> int | None:
        for index in range(len(messages) - 1, -1, -1):
            if messages[index].get("role") == "user":
                return index

        return None

    def _get_request_id(self, data: dict[str, Any]) -> str:
        request_id = data.get("request_id")

        if isinstance(request_id, str) and request_id:
            return request_id

        return str(uuid.uuid4())


guardrails_callback = GuardrailsCallback()
