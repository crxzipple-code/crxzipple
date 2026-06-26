from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
import json
from typing import Any

from crxzipple.modules.tool.application.catalog_model_types import (
    ToolFunctionRuntimeKind,
    ToolSourceCatalogKind,
)
from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.value_objects import ToolEnvironment, ToolKind


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if not normalized:
        raise ToolValidationError(f"Tool catalog {field_name} cannot be empty.")
    return normalized


def normalize_text_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip()
        ),
    )


def normalize_mapping(value: Mapping[str, Any], *, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ToolValidationError(f"Tool catalog {field_name} must be a mapping.")
    normalized = stable_payload(value)
    assert isinstance(normalized, dict)
    return normalized


def runtime_kind_from_tool_spec(spec: ToolSpec) -> ToolFunctionRuntimeKind:
    runtime_key = spec.runtime_key or ""
    runtime_prefix = runtime_key.split(".", 1)[0]
    if runtime_prefix in {kind.value for kind in ToolFunctionRuntimeKind}:
        return ToolFunctionRuntimeKind(runtime_prefix)
    if spec.kind is ToolKind.MCP:
        return ToolFunctionRuntimeKind.MCP
    if ToolEnvironment.SANDBOX in spec.execution_support.supported_environments:
        return ToolFunctionRuntimeKind.SANDBOX
    if ToolEnvironment.REMOTE in spec.execution_support.supported_environments:
        return ToolFunctionRuntimeKind.REMOTE
    return ToolFunctionRuntimeKind.LOCAL


def stable_key_from_tool_spec(
    spec: ToolSpec,
    *,
    source_id: str,
    runtime_kind: ToolFunctionRuntimeKind,
) -> str:
    runtime_key = spec.runtime_key or ""
    runtime_prefix = runtime_key.split(".", 1)[0]
    if runtime_prefix in {
        ToolFunctionRuntimeKind.MCP.value,
        ToolFunctionRuntimeKind.OPENAPI.value,
        ToolFunctionRuntimeKind.CLI.value,
        ToolFunctionRuntimeKind.PROVIDER_BACKEND.value,
    }:
        return runtime_key
    source_prefix = (
        ToolSourceCatalogKind.LOCAL_PACKAGE.value
        if runtime_kind is ToolFunctionRuntimeKind.LOCAL
        else runtime_kind.value
    )
    return f"{source_prefix}.{source_id}.{spec.id}"


def input_schema_from_tool_spec(spec: ToolSpec) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for parameter in spec.parameters:
        parameter_schema = _json_schema_for_tool_parameter(parameter)
        if parameter.description:
            parameter_schema.setdefault("description", parameter.description)
        properties[parameter.name] = parameter_schema
        if parameter.required:
            required.append(parameter.name)
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def hash_payload(payload: Mapping[str, Any]) -> str:
    digest = sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def canonical_json(payload: Any) -> str:
    return json.dumps(
        stable_payload(payload),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def stable_payload(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field_info.name: stable_payload(getattr(value, field_info.name))
            for field_info in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): stable_payload(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, tuple | list):
        return [stable_payload(item) for item in value]
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)


def _json_schema_for_tool_parameter(parameter: Any) -> dict[str, Any]:
    if parameter.json_schema is None:
        return _json_schema_for_data_type(parameter.data_type)
    schema = deepcopy(parameter.json_schema)
    if not schema:
        return _json_schema_for_data_type(parameter.data_type)
    if (
        "type" not in schema
        and "properties" not in schema
        and "items" not in schema
        and "enum" not in schema
        and "oneOf" not in schema
        and "anyOf" not in schema
        and "allOf" not in schema
        and "$ref" not in schema
    ):
        schema["type"] = parameter.data_type.strip().lower() or "string"
    return schema


def _json_schema_for_data_type(data_type: str) -> dict[str, Any]:
    normalized = data_type.strip().lower()
    if normalized.startswith("array[") and normalized.endswith("]"):
        item_type = normalized.removeprefix("array[").removesuffix("]")
        return {
            "type": "array",
            "items": _json_schema_for_data_type(item_type),
        }
    if normalized in {"string", "integer", "number", "boolean", "object", "array"}:
        return {"type": normalized}
    return {"type": "string", "x-crxzipple-data-type": data_type}
