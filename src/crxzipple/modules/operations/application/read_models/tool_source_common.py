from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    display_value,
)
from crxzipple.shared.time import format_datetime_utc


def record_value(record: Any | None, field_name: str) -> str:
    if record is None:
        return ""
    value = getattr(record, field_name, None)
    if value is None:
        return ""
    raw = getattr(value, "value", value)
    return str(raw).strip()


def record_text(record: Any | None, field_name: str) -> str:
    return record_value(record, field_name)


def record_datetime_label(record: Any | None, field_name: str) -> str:
    value = getattr(record, field_name, None) if record is not None else None
    if isinstance(value, datetime):
        return format_datetime_utc(value)
    return display_value(value)


def columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(
        OperationsTableColumnModel(key=key, label=label) for key, label in items
    )


def sequence(value: object) -> tuple[object, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple | list):
        return tuple(value)
    return (value,)
