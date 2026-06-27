from __future__ import annotations

from typing import Any

from crxzipple.modules.tool.domain.value_objects import ToolParameter


def parameter_to_tool_parameter(parameter: dict[str, Any]) -> ToolParameter:
    schema = parameter.get("schema") if isinstance(parameter.get("schema"), dict) else {}
    description = str(parameter.get("description", "")).strip()
    return ToolParameter(
        name=str(parameter["name"]),
        data_type=schema_type(schema),
        description=description,
        required=bool(parameter.get("required", False)),
        json_schema=tool_parameter_json_schema(schema, description=description),
    )


def json_body_tool_parameter(
    request_body_schema: dict[str, Any],
    *,
    required: bool,
) -> ToolParameter:
    description = "JSON request body payload."
    return ToolParameter(
        name="body",
        data_type=schema_type(request_body_schema),
        description=description,
        required=required,
        json_schema=tool_parameter_json_schema(
            request_body_schema,
            description=description,
        ),
    )


def tool_parameter_json_schema(
    schema: dict[str, Any],
    *,
    description: str,
) -> dict[str, Any]:
    payload = dict(schema)
    if not payload:
        payload["type"] = schema_type(schema)
    if description and not payload.get("description"):
        payload["description"] = description
    return payload


def schema_type(schema: dict[str, Any]) -> str:
    schema_type_value = str(schema.get("type", "")).strip().lower()
    if schema_type_value == "array":
        items = schema.get("items") if isinstance(schema.get("items"), dict) else {}
        item_type = schema_type(items)
        return f"array[{item_type}]"
    if schema_type_value:
        return schema_type_value
    if "properties" in schema:
        return "object"
    return "string"


def supports_json_request_body(request_body: dict[str, Any]) -> bool:
    content = request_body.get("content")
    if not isinstance(content, dict):
        return False
    return "application/json" in content


def request_body_schema(request_body: dict[str, Any]) -> dict[str, Any]:
    content = request_body.get("content")
    if not isinstance(content, dict):
        return {"type": "object"}
    media = content.get("application/json")
    if not isinstance(media, dict):
        return {"type": "object"}
    schema = media.get("schema") if isinstance(media.get("schema"), dict) else {}
    return schema or {"type": "object"}


__all__ = [
    "json_body_tool_parameter",
    "parameter_to_tool_parameter",
    "request_body_schema",
    "schema_type",
    "supports_json_request_body",
    "tool_parameter_json_schema",
]
