from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.llm.domain import (
    LlmContinuationSignal,
    LlmResponseItem,
)


def response_items_from_completed_payload(
    payload: Mapping[str, Any],
) -> tuple[LlmResponseItem, ...]:
    raw_items = payload.get("response_items")
    if not isinstance(raw_items, (list, tuple)):
        return ()
    items: list[LlmResponseItem] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        items.append(LlmResponseItem.from_payload(raw_item))
    return tuple(items)


def continuation_from_completed_payload(
    payload: Mapping[str, Any],
) -> LlmContinuationSignal | None:
    raw_continuation = payload.get("continuation")
    if not isinstance(raw_continuation, dict):
        return None
    return LlmContinuationSignal.from_payload(raw_continuation)


__all__ = [
    "continuation_from_completed_payload",
    "response_items_from_completed_payload",
]
