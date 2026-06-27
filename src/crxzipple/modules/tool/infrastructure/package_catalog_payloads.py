from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from crxzipple.modules.tool.application.activation import ToolDependencyRequirement


def dependency_payload(dependency: ToolDependencyRequirement) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": dependency.id,
        "kind": dependency.kind,
        "required": dependency.required,
    }
    if dependency.description:
        payload["description"] = dependency.description
    if dependency.metadata:
        payload["metadata"] = dict(dependency.metadata)
    return payload


def stable_payload(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: stable_payload(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): stable_payload(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple | list):
        return [stable_payload(item) for item in value]
    return value


def sequence(value: object) -> tuple[object, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple | list):
        return tuple(value)
    return (value,)


__all__ = ["dependency_payload", "sequence", "stable_payload"]
