from __future__ import annotations

from typing import Any
from urllib.parse import quote

from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.discovery.openapi import (
    OpenApiOperation,
)
from crxzipple.shared.access import CredentialProvider
from .openapi_remote_security import build_security_query_items


def build_request(
    operation: OpenApiOperation,
    arguments: dict[str, Any],
    *,
    credential_provider: CredentialProvider,
) -> tuple[
    str,
    list[tuple[str, str]],
    dict[str, str],
    dict[str, Any] | list[Any] | None,
]:
    path = operation.path_template
    for parameter_name in operation.path_parameters:
        if parameter_name not in arguments:
            raise ToolValidationError(
                f"Remote OpenAPI tool '{operation.tool_id}' requires path parameter '{parameter_name}'.",
            )
        path = path.replace(
            "{" + parameter_name + "}",
            quote(str(arguments.pop(parameter_name)), safe=""),
        )

    query_items: list[tuple[str, str]] = []
    for parameter_name in operation.query_parameters:
        value = arguments.pop(parameter_name, None)
        if value is None:
            continue
        value = _normalize_openapi_argument(operation, parameter_name, value)
        if isinstance(value, (list, tuple)):
            query_items.extend(
                (parameter_name, _serialize_scalar(item)) for item in value
            )
        else:
            query_items.append((parameter_name, _serialize_scalar(value)))

    body = arguments.pop("body", None)
    if operation.body_required and body is None:
        raise ToolValidationError(
            f"Remote OpenAPI tool '{operation.tool_id}' requires a JSON body payload.",
        )

    headers = {"Accept": "application/json"}
    cookies: list[str] = []
    query_items.extend(
        build_security_query_items(
            operation,
            credential_provider=credential_provider,
            headers=headers,
            cookies=cookies,
        ),
    )
    if cookies:
        headers["Cookie"] = "; ".join(cookies)

    json_body: dict[str, Any] | list[Any] | None = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        json_body = body

    return _build_url(operation.base_url, path), query_items, headers, json_body


def _normalize_openapi_argument(
    operation: OpenApiOperation,
    parameter_name: str,
    value: Any,
) -> Any:
    if isinstance(value, list):
        return [
            _normalize_openapi_argument(operation, parameter_name, item)
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            _normalize_openapi_argument(operation, parameter_name, item)
            for item in value
        )
    if not isinstance(value, str):
        return value

    normalized = _normalize_known_openapi_alias(operation, parameter_name, value)
    schema = _parameter_schema(operation, parameter_name)
    enum_values = _schema_enum(schema)
    if not enum_values:
        return normalized
    if normalized in enum_values:
        return normalized

    lower_matches = {
        str(candidate).lower(): str(candidate)
        for candidate in enum_values
        if isinstance(candidate, str)
    }
    lower_normalized = normalized.lower()
    if lower_normalized in lower_matches:
        return lower_matches[lower_normalized]

    raise ToolValidationError(
        "Remote OpenAPI tool "
        f"'{operation.tool_id}' parameter '{parameter_name}' must be one of: "
        f"{', '.join(str(item) for item in enum_values)}.",
    )


def _normalize_known_openapi_alias(
    operation: OpenApiOperation,
    parameter_name: str,
    value: str,
) -> str:
    normalized = value.strip()
    alias_key = (operation.provider_name, parameter_name)
    aliases = _OPENAPI_PARAMETER_ALIASES.get(alias_key, {})
    return aliases.get(normalized.lower(), normalized)


def _parameter_schema(
    operation: OpenApiOperation,
    parameter_name: str,
) -> dict[str, Any]:
    for parameter in operation.parameters:
        if parameter.name == parameter_name and parameter.json_schema is not None:
            return parameter.json_schema
    return {}


def _schema_enum(schema: dict[str, Any]) -> tuple[Any, ...]:
    raw = schema.get("enum")
    if not isinstance(raw, list):
        return ()
    return tuple(raw)


def _build_url(
    base_url: str,
    path: str,
) -> str:
    base = base_url.rstrip("/")
    path_value = path if path.startswith("/") else f"/{path}"
    return f"{base}{path_value}"


def _serialize_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


_OPENAPI_PARAMETER_ALIASES: dict[tuple[str, str], dict[str, str]] = {
    ("brave_search", "search_lang"): {
        "zh": "zh-hans",
        "zh-cn": "zh-hans",
        "zh_cn": "zh-hans",
        "zh-hans-cn": "zh-hans",
        "zh-tw": "zh-hant",
        "zh_tw": "zh-hant",
        "zh-hant-tw": "zh-hant",
    },
    ("brave_search", "ui_lang"): {
        "zh": "zh-CN",
        "zh-cn": "zh-CN",
        "zh_cn": "zh-CN",
        "zh-hans": "zh-CN",
        "zh-hant": "zh-TW",
        "zh-tw": "zh-TW",
        "zh_tw": "zh-TW",
        "en": "en-US",
    },
}


__all__ = ["build_request"]
