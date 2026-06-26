from __future__ import annotations

from enum import StrEnum
from typing import Any

from crxzipple.modules.tool.domain.exceptions import ToolValidationError


def normalize_access_requirement_sets(
    values: tuple[tuple[str, ...], ...],
    *,
    fallback_requirements: tuple[str, ...],
) -> tuple[tuple[str, ...], ...]:
    resolved: list[tuple[str, ...]] = []
    for value in values:
        requirement_set = tuple(
            dict.fromkeys(
                requirement.strip()
                for requirement in value
                if requirement is not None and requirement.strip()
            ),
        )
        if requirement_set not in resolved:
            resolved.append(requirement_set)
    if not resolved and fallback_requirements:
        resolved.append(fallback_requirements)
    return tuple(resolved)


def coerce_str_enum(
    enum_type: type[StrEnum],
    value: StrEnum | str,
    *,
    field_name: str,
) -> StrEnum:
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ToolValidationError(
            f"Unsupported {field_name}: {value!s}.",
        ) from exc


def normalize_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ToolValidationError(f"{field_name} cannot be empty.")
    return normalized


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def normalize_text_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip()
        ),
    )


def normalize_json_mapping(value: dict[str, Any]) -> dict[str, Any]:
    return dict(value)


def normalize_json_mapping_tuple(
    values: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    return tuple(dict(value) for value in values)
