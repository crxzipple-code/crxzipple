from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return json_ready(asdict(value))
    if isinstance(value, datetime):
        return format_datetime_utc(coerce_utc_datetime(value))
    if isinstance(value, Enum):
        return json_ready(value.value)
    if isinstance(value, Mapping):
        return {
            str(key): json_ready(item)
            for key, item in value.items()
            if isinstance(key, str | int | float | bool)
        }
    if isinstance(value, tuple | list | set | frozenset):
        return [json_ready(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    raw_value = getattr(value, "value", None)
    if isinstance(raw_value, str | int | float | bool):
        return raw_value
    return str(value)


def int_value(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0
