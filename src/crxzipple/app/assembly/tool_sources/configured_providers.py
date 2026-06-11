"""Configured Tool source/provider assembly helpers."""

from __future__ import annotations

from crxzipple.app.assembly.tool_packages import activate_bundled_openapi_packages
from crxzipple.app.assembly.tool_runtime import (
    ToolConfiguredRuntimeActivator,
    tool_cleanup_callbacks,
)
from crxzipple.app.keys import AppKey
from crxzipple.modules.tool.application import (
    ToolDiscoveryAdapterRegistry,
    ToolDiscoveryService,
    ToolSourceCatalogKind,
)
from crxzipple.modules.tool.infrastructure import (
    ToolConfiguredProviderDiscoveryAdapter,
    ToolPackageDiscoveryAdapter,
    tool_source_records_from_configured_providers,
    tool_source_records_from_package_plans,
)


class ToolSourceDiscoveryRoutingAdapter:
    def __init__(
        self,
        *,
        package_adapter: ToolPackageDiscoveryAdapter,
        configured_adapter: ToolConfiguredProviderDiscoveryAdapter,
    ) -> None:
        self._package_adapter = package_adapter
        self._configured_adapter = configured_adapter

    def discover(self, source):
        source_kind = source.config.get("source")
        if source_kind == "bundled_tool_package":
            return self._package_adapter.discover(source)
        if source_kind == "configured_tool_provider":
            return self._configured_adapter.discover(source)
        raise ValueError(
            f"Tool source '{source.source_id}' has unsupported source marker '{source_kind}'.",
        )


def build_tool_source_discovery_service(ctx) -> ToolDiscoveryService:
    adapter = ToolSourceDiscoveryRoutingAdapter(
        package_adapter=ToolPackageDiscoveryAdapter(
            ctx.require(AppKey.TOOL_PACKAGE_PLANS),
        ),
        configured_adapter=ToolConfiguredProviderDiscoveryAdapter(),
    )
    return ToolDiscoveryService(
        ToolDiscoveryAdapterRegistry(
            {
                ToolSourceCatalogKind.LOCAL_PACKAGE: adapter,
                ToolSourceCatalogKind.OPENAPI: adapter,
                ToolSourceCatalogKind.MCP: adapter,
                ToolSourceCatalogKind.CLI: adapter,
            },
        ),
    )


def build_tool_configured_runtime_activator(ctx) -> ToolConfiguredRuntimeActivator:
    return ToolConfiguredRuntimeActivator(
        remote_default_max_concurrency=(
            ctx.require(AppKey.RUNTIME_BOOTSTRAP_CONFIG).tool_remote_default_max_concurrency
        ),
        source_query=ctx.require(AppKey.TOOL_SOURCE_QUERY_SERVICE),
        uow_factory=ctx.require(AppKey.UNIT_OF_WORK_FACTORY),
        remote_runtime_registry=ctx.require(AppKey.TOOL_REMOTE_RUNTIME_REGISTRY),
        credential_provider=ctx.require(AppKey.ACCESS_SERVICE),
        events_service=ctx.require(AppKey.EVENTS_SERVICE),
        process_service=ctx.require(AppKey.PROCESS_SERVICE),
        cleanup_callbacks=tool_cleanup_callbacks(ctx),
    )


def sync_bundled_tool_source_catalog(ctx) -> None:
    package_plans = ctx.require(AppKey.TOOL_PACKAGE_PLANS)
    sources = tool_source_records_from_package_plans(
        package_plans,
        include_openapi=activate_bundled_openapi_packages(),
    )
    if not sources:
        return
    ctx.require(AppKey.TOOL_SOURCE_COMMAND_SERVICE).sync_sources(
        sources,
        discovery_service=ctx.require(AppKey.TOOL_SOURCE_DISCOVERY_SERVICE),
    )


def sync_configured_tool_provider_source_catalog(ctx) -> None:
    bootstrap_config = ctx.require(AppKey.TOOL_BOOTSTRAP_CONFIG)
    sources = tool_source_records_from_configured_providers(
        openapi_providers=bootstrap_config.openapi_providers,
        mcp_providers=bootstrap_config.mcp_providers,
    )
    if not sources:
        return
    ctx.require(AppKey.TOOL_SOURCE_COMMAND_SERVICE).sync_sources(
        sources,
        discovery_service=ctx.require(AppKey.TOOL_SOURCE_DISCOVERY_SERVICE),
    )


def activate_configured_tool_provider_runtimes(ctx) -> None:
    ctx.require(AppKey.TOOL_CONFIGURED_RUNTIME_ACTIVATOR).activate_all()
