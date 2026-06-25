from __future__ import annotations

import hashlib
import json
from typing import Any


def openai_response_input_fingerprints(
    payloads: list[dict[str, Any]],
) -> tuple[str, ...]:
    return tuple(openai_provider_payload_fingerprint(payload) for payload in payloads)


def openai_provider_payload_fingerprint(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def safe_preview_value(value: object, *, depth: int = 0) -> object:
    if depth >= 5:
        return truncate_preview(value, 240)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return truncate_preview(value, 512)
    if isinstance(value, dict):
        return {
            str(key): safe_preview_value(item, depth=depth + 1)
            for key, item in list(value.items())[:60]
        }
    if isinstance(value, (list, tuple)):
        return [safe_preview_value(item, depth=depth + 1) for item in value[:80]]
    return truncate_preview(value, 240)


def payload_item_type(item: object) -> str:
    if isinstance(item, dict):
        item_type = item.get("type")
        if item_type is not None:
            return str(item_type)
        role = item.get("role")
        if role is not None:
            return str(role)
    return type(item).__name__


def payload_fingerprint_or_none(payload: Any) -> str | None:
    if payload is None:
        return None
    return openai_provider_payload_fingerprint(payload)


def truncate_preview(value: object, limit: int) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)] + "..."
