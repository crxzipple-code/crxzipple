from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    truncate_text,
)
from crxzipple.modules.tool.domain import ToolRun
from crxzipple.shared.time import format_datetime_utc


def invocation_context_items(run: ToolRun) -> tuple[OperationsKeyValueItemModel, ...]:
    payload = run.invocation_context_payload
    if not isinstance(payload, dict) or not payload:
        return ()
    return tuple(
        OperationsKeyValueItemModel(
            label=str(key),
            value=detail_value(value),
        )
        for key, value in sorted(payload.items(), key=lambda item: str(item[0]))
    )


def detail_value(value: Any) -> str:
    if isinstance(value, str):
        return truncate_text(value, 160)
    return truncate_text(
        json.dumps(json_safe_payload(value), ensure_ascii=False, sort_keys=True),
        160,
    )


def json_safe_payload(value: Any, *, depth: int = 0) -> Any:
    if depth >= 6:
        return truncate_text(str(value), 240)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return format_datetime_utc(value)
    if isinstance(value, dict):
        return {
            str(key): json_safe_payload(item, depth=depth + 1)
            for key, item in list(value.items())[:80]
        }
    if isinstance(value, (list, tuple, set)):
        return [
            json_safe_payload(item, depth=depth + 1)
            for item in list(value)[:80]
        ]
    return truncate_text(str(value), 240)
