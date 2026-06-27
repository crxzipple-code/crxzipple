from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from crxzipple.modules.tool.domain.exceptions import ToolValidationError


def optional_manifest_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def parse_string_list(
    raw_values: object,
    field_name: str,
    manifest_path: Path,
) -> tuple[str, ...]:
    if not isinstance(raw_values, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field '{field_name}' must be a list.",
        )
    return tuple(
        str(item).strip()
        for item in raw_values
        if str(item).strip()
    )


def parse_string_sets(
    raw_values: object,
    field_name: str,
    manifest_path: Path,
) -> tuple[tuple[str, ...], ...]:
    if not isinstance(raw_values, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field '{field_name}' must be a list.",
        )
    return tuple(
        parse_string_list(item, field_name, manifest_path)
        for item in raw_values
    )


def mapping_payload(raw_value: object) -> dict[str, object]:
    return dict(raw_value) if isinstance(raw_value, dict) else {}


def optional_mapping_payload(raw_value: object) -> dict[str, object] | None:
    return dict(raw_value) if isinstance(raw_value, dict) else None


def stable_payload(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: stable_payload(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {
            str(key): stable_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple | list):
        return [stable_payload(item) for item in value]
    return value


def parse_enum_list(
    raw_values: object,
    *,
    enum_type,
    field_name: str,
    manifest_path: Path,
) -> tuple[Any, ...]:
    if not isinstance(raw_values, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field '{field_name}' must be a list.",
        )
    return tuple(
        parse_enum(
            value,
            enum_type=enum_type,
            field_name=field_name,
            manifest_path=manifest_path,
        )
        for value in raw_values
    )


def parse_enum(
    raw_value: object,
    *,
    enum_type,
    field_name: str,
    manifest_path: Path,
):
    try:
        return enum_type(str(raw_value).strip())
    except ValueError as exc:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field '{field_name}' "
            f"declares unsupported value '{raw_value}'.",
        ) from exc


def required_string(
    payload: dict[str, Any],
    field_name: str,
    manifest_path: Path,
) -> str:
    value = str(payload.get(field_name, "")).strip()
    if not value:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' must define non-empty '{field_name}'.",
        )
    return value


__all__ = [
    "mapping_payload",
    "optional_manifest_text",
    "optional_mapping_payload",
    "parse_enum",
    "parse_enum_list",
    "parse_string_list",
    "parse_string_sets",
    "required_string",
    "stable_payload",
]
