from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace
from typing import Any

from crxzipple.core.config import (
    McpProviderSettings,
    OpenApiCredentialBinding,
    OpenApiProviderSettings,
)
from crxzipple.modules.tool.application.catalog_models import (
    ToolFunctionCandidate,
    ToolFunctionCatalogRecord,
    ToolFunctionRuntimeKind,
    ToolFunctionStatus,
    ToolSourceCatalogKind,
    ToolSourceCatalogRecord,
    ToolSourceDiscoveryResult,
)
from crxzipple.modules.tool.application.discovery import ToolDiscoveryAdapter
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.discovery.mcp import McpDiscoveryProvider
from crxzipple.modules.tool.infrastructure.discovery.mcp import McpToolDefinition
from crxzipple.modules.tool.infrastructure.discovery.openapi import (
    OpenApiOperation,
    OpenApiDiscoveryProvider,
    OpenApiSecurityRequirement,
    OpenApiSecurityScheme,
)
from crxzipple.modules.tool.infrastructure.mcp_client import build_mcp_client
from crxzipple.modules.tool.infrastructure.cli_source import (
    discover_cli_source,
    register_cli_guided_handlers,
)
from crxzipple.modules.tool.infrastructure.runtimes import (
    register_mcp_remote_handlers,
    register_openapi_remote_handlers,
)


CONFIGURED_PROVIDER_SOURCE_PREFIX = "configured"


class ToolConfiguredProviderDiscoveryAdapter(ToolDiscoveryAdapter):
    def discover(self, source: ToolSourceCatalogRecord) -> ToolSourceDiscoveryResult:
        if source.kind is ToolSourceCatalogKind.MCP:
            return _discover_mcp_source(source)
        if source.kind is ToolSourceCatalogKind.OPENAPI:
            return _discover_openapi_source(source)
        if source.kind is ToolSourceCatalogKind.CLI:
            return _discover_cli_source(source)
        raise ToolValidationError(
            f"Configured provider source '{source.source_id}' kind '{source.kind.value}' is not supported.",
        )


def tool_source_records_from_configured_providers(
    *,
    openapi_providers: tuple[OpenApiProviderSettings, ...] = (),
    mcp_providers: tuple[McpProviderSettings, ...] = (),
) -> tuple[ToolSourceCatalogRecord, ...]:
    records: list[ToolSourceCatalogRecord] = []
    records.extend(_openapi_source_record(provider) for provider in openapi_providers)
    records.extend(_mcp_source_record(provider) for provider in mcp_providers)
    return tuple(records)


def activate_configured_provider_runtimes(
    *,
    sources: tuple[ToolSourceCatalogRecord, ...],
    functions_by_source: Mapping[str, tuple[ToolFunctionCatalogRecord, ...]],
    remote_runtime_registry: Any,
    credential_provider: Any,
    events_service: Any | None = None,
    process_service: Any | None = None,
    default_max_concurrency: int,
    add_cleanup_callback: Any | None = None,
    replace_existing: bool = False,
) -> None:
    for source in sources:
        if source.config.get("source") != "configured_tool_provider":
            continue
        if source.kind is ToolSourceCatalogKind.OPENAPI:
            provider = _openapi_provider_settings_from_source(source)
            operations = tuple(
                _openapi_operation_from_function(function)
                for function in _active_source_functions(
                    functions_by_source.get(source.source_id, ()),
                )
            )
            if not operations:
                continue
            register_openapi_remote_handlers(
                remote_runtime_registry,
                operations,
                credential_provider=credential_provider,
                max_concurrency=(
                    provider.max_concurrency or default_max_concurrency
                ),
                replace=replace_existing,
            )
            continue
        if source.kind is ToolSourceCatalogKind.MCP:
            provider = _mcp_provider_settings_from_source(source)
            definitions = tuple(
                _mcp_definition_from_function(function)
                for function in _active_source_functions(
                    functions_by_source.get(source.source_id, ()),
                )
            )
            if not definitions:
                continue
            client = build_mcp_client(provider)
            try:
                register_mcp_remote_handlers(
                    remote_runtime_registry,
                    definitions,
                    client=client,
                    max_concurrency=(
                        provider.max_concurrency or default_max_concurrency
                    ),
                    replace=replace_existing,
                )
            except Exception:
                client.close()
                raise
            if add_cleanup_callback is not None:
                add_cleanup_callback(source, client.close)
            continue
        if source.kind is ToolSourceCatalogKind.CLI:
            if process_service is None:
                raise ToolValidationError(
                    f"Configured CLI source '{source.source_id}' requires process_service.",
                )
            register_cli_guided_handlers(
                remote_runtime_registry,
                source=source,
                functions=_active_source_functions(
                    functions_by_source.get(source.source_id, ()),
                ),
                process_service=process_service,
                credential_provider=credential_provider,
                events_service=events_service,
                max_concurrency=default_max_concurrency,
                replace=replace_existing,
            )


def configured_openapi_source_id(provider: OpenApiProviderSettings) -> str:
    return f"{CONFIGURED_PROVIDER_SOURCE_PREFIX}.openapi.{provider.name}"


def configured_mcp_source_id(provider: McpProviderSettings) -> str:
    return f"{CONFIGURED_PROVIDER_SOURCE_PREFIX}.mcp.{provider.name}"


def _discover_openapi_source(
    source: ToolSourceCatalogRecord,
) -> ToolSourceDiscoveryResult:
    provider = _openapi_provider_settings_from_source(source)
    discovery = OpenApiDiscoveryProvider(provider)
    operations = discovery.operations()
    return ToolSourceDiscoveryResult.completed(
        source_id=source.source_id,
        candidates=tuple(
            _with_source_runtime_requirements(
                ToolFunctionCandidate.from_tool_spec(
                    operation.to_tool_spec(),
                    source_id=source.source_id,
                    runtime_kind=ToolFunctionRuntimeKind.OPENAPI,
                    metadata={
                        "source": "configured_tool_provider",
                        "package_kind": "openapi",
                        "provider_name": provider.name,
                        "openapi_operation": _openapi_operation_payload(operation),
                    },
                ),
                source=source,
            )
            for operation in operations
        ),
        metadata={
            "source": "configured_tool_provider",
            "package_kind": "openapi",
            "provider_name": provider.name,
        },
    )


def _discover_mcp_source(source: ToolSourceCatalogRecord) -> ToolSourceDiscoveryResult:
    provider = _mcp_provider_settings_from_source(source)
    client = build_mcp_client(provider)
    try:
        discovery = McpDiscoveryProvider(provider, client=client)
        definitions = discovery.definitions()
        return ToolSourceDiscoveryResult.completed(
            source_id=source.source_id,
            candidates=tuple(
                _mcp_candidate_from_definition(
                    definition,
                    source=source,
                    provider_name=provider.name,
                )
                for definition in definitions
            ),
            metadata={
                "source": "configured_tool_provider",
                "package_kind": "mcp",
                "provider_name": provider.name,
            },
        )
    finally:
        client.close()


def _discover_cli_source(source: ToolSourceCatalogRecord) -> ToolSourceDiscoveryResult:
    return discover_cli_source(source)


def _openapi_source_record(
    provider: OpenApiProviderSettings,
) -> ToolSourceCatalogRecord:
    return ToolSourceCatalogRecord(
        source_id=configured_openapi_source_id(provider),
        kind=ToolSourceCatalogKind.OPENAPI,
        display_name=provider.description or provider.name,
        description=(
            provider.description
            or f"Configured OpenAPI tool provider '{provider.name}'."
        ),
        config={
            "source": "configured_tool_provider",
            "package_kind": "openapi",
            "provider": _provider_payload(provider),
        },
        runtime_requirements=provider.runtime_requirements,
    )


def _mcp_source_record(provider: McpProviderSettings) -> ToolSourceCatalogRecord:
    return ToolSourceCatalogRecord(
        source_id=configured_mcp_source_id(provider),
        kind=ToolSourceCatalogKind.MCP,
        display_name=provider.description or provider.name,
        description=provider.description or f"Configured MCP tool provider '{provider.name}'.",
        config={
            "source": "configured_tool_provider",
            "package_kind": "mcp",
            "provider": _provider_payload(provider),
        },
        runtime_requirements=provider.runtime_requirements,
    )


def _openapi_provider_settings_from_source(
    source: ToolSourceCatalogRecord,
) -> OpenApiProviderSettings:
    payload = _provider_config(source)
    return OpenApiProviderSettings(
        name=_required_text(payload.get("name"), source=source, field_name="name"),
        spec_location=_required_text(
            payload.get("spec_location"),
            source=source,
            field_name="spec_location",
        ),
        base_url=_optional_text(payload.get("base_url")),
        description=str(payload.get("description") or ""),
        timeout_seconds=_positive_int(payload.get("timeout_seconds"), default=30),
        max_concurrency=_optional_positive_int(payload.get("max_concurrency")),
        credential_bindings=tuple(
            _credential_binding_from_payload(item)
            for item in payload.get("credential_bindings", ())
            if isinstance(item, Mapping)
        ),
        default_effect_ids=_text_tuple(payload.get("default_effect_ids")),
        runtime_requirements=_text_tuple(payload.get("runtime_requirements")),
    )


def _mcp_provider_settings_from_source(
    source: ToolSourceCatalogRecord,
) -> McpProviderSettings:
    payload = _provider_config(source)
    return McpProviderSettings(
        name=_required_text(payload.get("name"), source=source, field_name="name"),
        command=_text_tuple(payload.get("command")),
        transport=str(payload.get("transport") or "stdio"),
        endpoint_url=_optional_text(payload.get("endpoint_url")),
        description=str(payload.get("description") or ""),
        timeout_seconds=_positive_int(payload.get("timeout_seconds"), default=30),
        max_concurrency=_optional_positive_int(payload.get("max_concurrency")),
        default_effect_ids=_text_tuple(payload.get("default_effect_ids")),
        runtime_requirements=_text_tuple(payload.get("runtime_requirements")),
    )


def _provider_config(source: ToolSourceCatalogRecord) -> Mapping[str, Any]:
    provider = source.config.get("provider")
    if not isinstance(provider, Mapping):
        raise ToolValidationError(
            f"Configured provider source '{source.source_id}' config.provider must be an object.",
        )
    return provider


def _active_source_functions(
    functions: tuple[ToolFunctionCatalogRecord, ...],
) -> tuple[ToolFunctionCatalogRecord, ...]:
    return tuple(
        function
        for function in functions
        if function.status is ToolFunctionStatus.ACTIVE and function.enabled
    )


def _openapi_operation_from_function(
    function: ToolFunctionCatalogRecord,
) -> OpenApiOperation:
    payload = function.metadata.get("openapi_operation")
    if not isinstance(payload, Mapping):
        raise ToolValidationError(
            f"Tool function '{function.function_id}' is missing persisted OpenAPI operation metadata.",
        )
    return OpenApiOperation(
        provider_name=_required_text(
            payload.get("provider_name"),
            source=None,
            field_name="openapi_operation.provider_name",
        ),
        tool_id=function.function_id,
        runtime_key=function.handler_ref,
        name=function.name,
        description=function.description,
        method=_required_text(
            payload.get("method"),
            source=None,
            field_name="openapi_operation.method",
        ),
        path_template=_required_text(
            payload.get("path_template"),
            source=None,
            field_name="openapi_operation.path_template",
        ),
        base_url=_required_text(
            payload.get("base_url"),
            source=None,
            field_name="openapi_operation.base_url",
        ),
        timeout_seconds=_positive_int(payload.get("timeout_seconds"), default=30),
        path_parameters=_text_tuple(payload.get("path_parameters")),
        query_parameters=_text_tuple(payload.get("query_parameters")),
        body_required=bool(payload.get("body_required", False)),
        tags=_text_tuple(payload.get("tags")),
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
            _credential_binding_from_payload(item)
            for item in _mapping_tuple_payload(payload.get("credential_bindings"))
        ),
        required_effect_ids=_text_tuple(payload.get("required_effect_ids")),
        capability_ids=function.capabilities,
    )


def _mcp_definition_from_function(
    function: ToolFunctionCatalogRecord,
) -> McpToolDefinition:
    payload = function.metadata.get("mcp_definition")
    if not isinstance(payload, Mapping):
        raise ToolValidationError(
            f"Tool function '{function.function_id}' is missing persisted MCP definition metadata.",
        )
    return McpToolDefinition(
        provider_name=_required_text(
            payload.get("provider_name"),
            source=None,
            field_name="mcp_definition.provider_name",
        ),
        tool_name=_required_text(
            payload.get("tool_name"),
            source=None,
            field_name="mcp_definition.tool_name",
        ),
        tool_id=function.function_id,
        runtime_key=function.handler_ref,
        name=function.name,
        description=function.description,
        tags=_text_tuple(payload.get("tags")),
        parameters=(),
        timeout_seconds=_positive_int(payload.get("timeout_seconds"), default=30),
        mutates_state=bool(payload.get("mutates_state", False)),
        required_effect_ids=_text_tuple(payload.get("required_effect_ids")),
    )


def _mcp_candidate_from_definition(
    definition: McpToolDefinition,
    *,
    source: ToolSourceCatalogRecord,
    provider_name: str,
) -> ToolFunctionCandidate:
    candidate = ToolFunctionCandidate.from_tool_spec(
        definition.to_tool_spec(),
        source_id=source.source_id,
        runtime_kind=ToolFunctionRuntimeKind.MCP,
        metadata={
            "source": "configured_tool_provider",
            "package_kind": "mcp",
            "provider_name": provider_name,
            "mcp_definition": _mcp_definition_payload(definition),
        },
    )
    return _with_source_runtime_requirements(candidate, source=source)


def _with_source_runtime_requirements(
    candidate: ToolFunctionCandidate,
    *,
    source: ToolSourceCatalogRecord,
) -> ToolFunctionCandidate:
    if not source.runtime_requirements:
        return candidate
    return replace(
        candidate,
        requirements=replace(
            candidate.requirements,
            runtime_requirement_sets=(
                *candidate.requirements.runtime_requirement_sets,
                tuple(source.runtime_requirements),
            ),
        ),
    )


def _openapi_operation_payload(operation: OpenApiOperation) -> dict[str, Any]:
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


def _mcp_definition_payload(definition: McpToolDefinition) -> dict[str, Any]:
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
        name=_required_text(
            payload.get("name"),
            source=None,
            field_name="security_scheme.name",
        ),
        scheme_type=_required_text(
            payload.get("scheme_type"),
            source=None,
            field_name="security_scheme.scheme_type",
        ),
        parameter_name=_optional_text(payload.get("parameter_name")),
        location=_optional_text(payload.get("location")),
        http_scheme=_optional_text(payload.get("http_scheme")),
        metadata=dict(payload.get("metadata")) if isinstance(payload.get("metadata"), Mapping) else {},
    )


def _openapi_security_requirement_from_payload(
    payload: Mapping[str, Any],
) -> OpenApiSecurityRequirement:
    raw_scopes = payload.get("scopes_by_scheme")
    scopes_by_scheme: dict[str, tuple[str, ...]] = {}
    if isinstance(raw_scopes, Mapping):
        scopes_by_scheme = {
            str(scheme): _text_tuple(scopes)
            for scheme, scopes in raw_scopes.items()
        }
    return OpenApiSecurityRequirement(
        scheme_names=_text_tuple(payload.get("scheme_names")),
        scopes_by_scheme=scopes_by_scheme,
    )


def _mapping_tuple_payload(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _credential_binding_from_payload(
    payload: Mapping[str, Any],
) -> OpenApiCredentialBinding:
    return OpenApiCredentialBinding(
        scheme_name=_required_text(
            payload.get("scheme_name"),
            source=None,
            field_name="scheme_name",
        ),
        credential_binding_id=_optional_text(payload.get("credential_binding_id")),
        username_binding_id=_optional_text(payload.get("username_binding_id")),
        password_binding_id=_optional_text(payload.get("password_binding_id")),
    )


def _provider_payload(provider: OpenApiProviderSettings | McpProviderSettings) -> dict[str, Any]:
    return _stable_payload(provider)


def _stable_payload(value: Any) -> Any:
    if is_dataclass(value):
        return {
            field.name: _stable_payload(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _stable_payload(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple | list):
        return [_stable_payload(item) for item in value]
    return value


def _required_text(
    value: object,
    *,
    source: ToolSourceCatalogRecord | None,
    field_name: str,
) -> str:
    text = str(value or "").strip()
    if not text:
        prefix = (
            f"Configured provider source '{source.source_id}' "
            if source is not None
            else ""
        )
        raise ToolValidationError(f"{prefix}{field_name} cannot be empty.")
    return text


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _text_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(
        dict.fromkeys(
            str(item).strip()
            for item in value
            if str(item).strip()
        ),
    )


def _positive_int(value: object, *, default: int) -> int:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        resolved = default
    return max(resolved, 1)


def _optional_positive_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return None
    return max(resolved, 1)
