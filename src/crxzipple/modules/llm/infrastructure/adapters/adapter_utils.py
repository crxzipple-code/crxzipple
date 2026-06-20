from __future__ import annotations

import json
from typing import Any

from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain.value_objects import (
    LlmCapability,
    LlmMessage,
)
from crxzipple.shared.content_blocks import (
    describe_content_for_text_fallback,
    has_image_content_blocks,
)


def coerce_text_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    return describe_content_for_text_fallback(value)


def parse_json_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}
        if isinstance(payload, dict):
            return payload
        return {"value": payload}
    return {}


def default_base_url(profile: LlmProfile, fallback: str) -> str:
    return profile.base_url or fallback


def ensure_image_input_supported(
    profile: LlmProfile,
    messages: tuple[LlmMessage, ...],
) -> None:
    if not any(has_image_content_blocks(message.content) for message in messages):
        return
    if LlmCapability.VISION_INPUT not in profile.capabilities:
        raise RuntimeError(
            f"LLM profile '{profile.id}' does not support vision input.",
        )
