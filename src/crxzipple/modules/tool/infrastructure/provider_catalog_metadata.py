from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.tool.application.catalog_models import ToolFunctionCatalogRecord
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.discovery.mcp import McpToolDefinition
from crxzipple.modules.tool.infrastructure.discovery.openapi import (
    OpenApiOperation,
    OpenApiSecurityRequirement,
    OpenApiSecurityScheme,
)
from crxzipple.modules.tool.infrastructure.provider_catalog_config import (
    credential_binding_from_payload,
    optional_text,
    positive_int,
    required_text,
    text_tuple,
)


def openapi_operation_from_function(
    function: ToolFunctionCatalogRecord,
) -> OpenApiOperation:
    payload = function.metadata.get("openapi_operation")
    if not isinstance(payload, Mapping):
        raise ToolValidationError(
            f"Tool function '{function.function_id}' is missing persisted OpenAPI operation metadata.",
        )
    return OpenApiOperation(
        provider_name=required_text(
            payload.get("provider_name"),
            source=None,
            field_name="openapi_operation.provider_name",
        ),
        tool_id=function.function_id,
        runtime_key=function.handler_ref,
        name=function.name,
        description=function.description,
        method=required_text(
            payload.get("method"),
            source=None,
            field_name="openapi_operation.method",
        ),
        path_template=required_text(
            payload.get("path_template"),
            source=None,
            field_name="openapi_operation.path_template",
        ),
        base_url=required_text(
            payload.get("base_url"),
            source=None,
            field_name="openapi_operation.base_url",
        ),
        timeout_seconds=positive_int(payload.get("timeout_seconds"), default=30),
        path_parameters=text_tuple(payload.get("path_parameters")),
        query_parameters=text_tuple(payload.get("query_parameters")),
        body_required=bool(payload.get("body_required", False)),
        tags=text_tuple(payload.get("tags")),
        parameters=(),
        security_schemes=tuple(
            _openapi_security_scheme_from_payload(item)
            for item in _mapping_tuple_payload(payload.get("security_schemes"))
        ),
        security_requirements=tuple(
            _openapi_security_requirement_from_payload(item)
            for item in _mapping_tuple_payload(payload.get("security_requirements"))
        ),
        credential_bindings=tuple(
            credential_binding_from_payload(item)
            for item in _mapping_tuple_payload(payload.get("credential_bindings"))
        ),
        required_effect_ids=text_tuple(payload.get("required_effect_ids")),
        capability_ids=function.capabilities,
    )


def mcp_definition_from_function(
    function: ToolFunctionCatalogRecord,
) -> McpToolDefinition:
    payload = function.metadata.get("mcp_definition")
    if not isinstance(payload, Mapping):
        raise ToolValidationError(
            f"Tool function '{function.function_id}' is missing persisted MCP definition metadata.",
        )
    return McpToolDefinition(
        provider_name=required_text(
            payload.get("provider_name"),
            source=None,
            field_name="mcp_definition.provider_name",
        ),
        tool_name=required_text(
            payload.get("tool_name"),
            source=None,
            field_name="mcp_definition.tool_name",
        ),
        tool_id=function.function_id,
        runtime_key=function.handler_ref,
        name=function.name,
        description=function.description,
        tags=text_tuple(payload.get("tags")),
        parameters=(),
        timeout_seconds=positive_int(payload.get("timeout_seconds"), default=30),
        mutates_state=bool(payload.get("mutates_state", False)),
        required_effect_ids=text_tuple(payload.get("required_effect_ids")),
    )


def openapi_operation_payload(operation: OpenApiOperation) -> dict[str, Any]:
    return {
        "provider_name": operation.provider_name,
        "tool_id": operation.tool_id,
        "runtime_key": operation.runtime_key,
        "name": operation.name,
        "description": operation.description,
        "method": operation.method,
        "path_template": operation.path_template,
        "base_url": operation.base_url,
        "timeout_seconds": operation.timeout_seconds,
        "path_parameters": operation.path_parameters,
        "query_parameters": operation.query_parameters,
        "body_required": operation.body_required,
        "tags": operation.tags,
        "security_schemes": operation.security_schemes,
        "security_requirements": operation.security_requirements,
        "credential_bindings": operation.credential_bindings,
        "required_effect_ids": operation.required_effect_ids,
        "capability_ids": operation.capability_ids,
    }


def mcp_definition_payload(definition: McpToolDefinition) -> dict[str, Any]:
    return {
        "provider_name": definition.provider_name,
        "tool_name": definition.tool_name,
        "tool_id": definition.tool_id,
        "runtime_key": definition.runtime_key,
        "name": definition.name,
        "description": definition.description,
        "tags": definition.tags,
        "timeout_seconds": definition.timeout_seconds,
        "mutates_state": definition.mutates_state,
        "required_effect_ids": definition.required_effect_ids,
    }


def _openapi_security_scheme_from_payload(
    payload: Mapping[str, Any],
) -> OpenApiSecurityScheme:
    return OpenApiSecurityScheme(
        name=required_text(
            payload.get("name"),
            source=None,
            field_name="security_scheme.name",
        ),
        scheme_type=required_text(
            payload.get("scheme_type"),
            source=None,
            field_name="security_scheme.scheme_type",
        ),
        parameter_name=optional_text(payload.get("parameter_name")),
        location=optional_text(payload.get("location")),
        http_scheme=optional_text(payload.get("http_scheme")),
        metadata=dict(payload.get("metadata")) if isinstance(payload.get("metadata"), Mapping) else {},
    )


def _openapi_security_requirement_from_payload(
    payload: Mapping[str, Any],
) -> OpenApiSecurityRequirement:
    raw_scopes = payload.get("scopes_by_scheme")
    scopes_by_scheme: dict[str, tuple[str, ...]] = {}
    if isinstance(raw_scopes, Mapping):
        scopes_by_scheme = {
            str(scheme): text_tuple(scopes)
            for scheme, scopes in raw_scopes.items()
        }
    return OpenApiSecurityRequirement(
        scheme_names=text_tuple(payload.get("scheme_names")),
        scopes_by_scheme=scopes_by_scheme,
    )


def _mapping_tuple_payload(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))
