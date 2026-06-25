from __future__ import annotations

import json
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
)


def columns(*pairs: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(OperationsTableColumnModel(key=key, label=label) for key, label in pairs)


def enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    if raw is None:
        return "-"
    normalized = str(raw).strip()
    return normalized or "-"


def json_preview(value: Any) -> str:
    try:
        return truncate(
            json.dumps(sanitize_payload(value), ensure_ascii=False, sort_keys=True),
            240,
        )
    except TypeError:
        return truncate(value, 240)


def text(value: Any) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def sanitize_payload(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return truncate(value, 240)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return truncate(value, 512)
    if isinstance(value, dict):
        return {
            str(key): sanitize_payload(item, depth=depth + 1)
            for key, item in list(value.items())[:40]
            if isinstance(key, str)
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_payload(item, depth=depth + 1) for item in list(value)[:40]]
    return truncate(value, 240)


def truncate(value: Any, limit: int = 160) -> str:
    rendered = str(value)
    if len(rendered) <= limit:
        return rendered
    return rendered[: max(limit - 1, 0)] + "…"
