from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.tool.domain.exceptions import ToolValidationError


def safe_tool_id(value: str) -> str:
    normalized = "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_")
    normalized = "_".join(part for part in normalized.split("_") if part)
    if len(normalized) <= 56:
        return normalized or "cli_source"
    return normalized[:56].rstrip("_")


def text_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(
        dict.fromkeys(
            str(item).strip()
            for item in value
            if str(item).strip()
        ),
    )


def argv_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise ToolValidationError(f"CLI source field '{field_name}' must be a list.")
    resolved: list[str] = []
    for index, item in enumerate(value):
        text = str(item).strip()
        if not text:
            raise ToolValidationError(
                f"CLI source field '{field_name}[{index}]' cannot be empty.",
            )
        resolved.append(text)
    return tuple(resolved)


def mapping_tuple(value: object, *, field_name: str) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise ToolValidationError(f"CLI source field '{field_name}' must be a list.")
    items: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ToolValidationError(
                f"CLI source field '{field_name}[{index}]' must be an object.",
            )
        items.append(item)
    return tuple(items)


def bool_value(value: object, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ToolValidationError("CLI source boolean policy values must be booleans.")


def optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def required_text(value: object, *, field_name: str) -> str:
    normalized = optional_text(value)
    if normalized is None:
        raise ToolValidationError(f"CLI source field '{field_name}' is required.")
    return normalized


def positive_int(value: object, *, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        resolved = int(value)
    except (TypeError, ValueError) as exc:
        raise ToolValidationError("CLI source numeric policy values must be integers.") from exc
    if resolved < 1:
        raise ToolValidationError("CLI source numeric policy values must be positive.")
    return resolved


def optional_positive_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return positive_int(value, default=1)


def non_negative_int(value: object) -> int:
    if value is None or value == "":
        return 0
    try:
        resolved = int(value)
    except (TypeError, ValueError) as exc:
        raise ToolValidationError("CLI source offsets must be integers.") from exc
    if resolved < 0:
        raise ToolValidationError("CLI source offsets cannot be negative.")
    return resolved


__all__ = [
    "argv_tuple",
    "bool_value",
    "mapping_tuple",
    "non_negative_int",
    "optional_positive_int",
    "optional_text",
    "positive_int",
    "required_text",
    "safe_tool_id",
    "text_tuple",
]
