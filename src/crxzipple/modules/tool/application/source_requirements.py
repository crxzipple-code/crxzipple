from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.tool.application.credential_requirement_payloads import (
    credential_requirement_sets_from_payload,
)


def runtime_requirement_sets_from_payload(
    payload: tuple[Mapping[str, Any], ...],
) -> tuple[tuple[str, ...], ...]:
    requirement_sets: list[tuple[str, ...]] = []
    for item in payload:
        raw = item.get("requirements")
        if not isinstance(raw, list | tuple):
            raw = (item.get("requirement"),)
        values = tuple(str(value).strip() for value in raw if str(value).strip())
        if values:
            requirement_sets.append(values)
    return tuple(requirement_sets)


__all__ = [
    "credential_requirement_sets_from_payload",
    "runtime_requirement_sets_from_payload",
]
