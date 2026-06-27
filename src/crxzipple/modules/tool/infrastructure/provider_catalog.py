from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

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
    OpenApiDiscoveryProvider,
)
from crxzipple.modules.tool.infrastructure.mcp_client import build_mcp_client
from crxzipple.modules.tool.infrastructure.cli_source import (
    discover_cli_source,
    register_cli_guided_handlers,
)
from crxzipple.modules.tool.infrastructure.provider_catalog_config import (
    configured_mcp_source_id,
    configured_openapi_source_id,
    mcp_provider_settings_from_source,
    openapi_provider_settings_from_source,
    tool_source_records_from_configured_providers,
)
from crxzipple.modules.tool.infrastructure.provider_catalog_metadata import (
    mcp_definition_from_function,
    mcp_definition_payload,
    openapi_operation_from_function,
    openapi_operation_payload,
)
from crxzipple.modules.tool.infrastructure.runtimes import (
    register_mcp_remote_handlers,
    register_openapi_remote_handlers,
)

__all__ = [
    "ToolConfiguredProviderDiscoveryAdapter",
    "activate_configured_provider_runtimes",
    "configured_mcp_source_id",
    "configured_openapi_source_id",
    "tool_source_records_from_configured_providers",
]


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
            provider = openapi_provider_settings_from_source(source)
            operations = tuple(
                openapi_operation_from_function(function)
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
            provider = mcp_provider_settings_from_source(source)
            definitions = tuple(
                mcp_definition_from_function(function)
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


def _discover_openapi_source(
    source: ToolSourceCatalogRecord,
) -> ToolSourceDiscoveryResult:
    provider = openapi_provider_settings_from_source(source)
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
                        "openapi_operation": openapi_operation_payload(operation),
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
    provider = mcp_provider_settings_from_source(source)
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


def _active_source_functions(
    functions: tuple[ToolFunctionCatalogRecord, ...],
) -> tuple[ToolFunctionCatalogRecord, ...]:
    return tuple(
        function
        for function in functions
        if function.status is ToolFunctionStatus.ACTIVE and function.enabled
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
            "mcp_definition": mcp_definition_payload(definition),
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
