"""Tool infrastructure exports.

Exports are lazy so schema/query-only entrypoints do not import every execution
backend, package synchronizer, or provider runtime.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    "DEFAULT_TOOL_ROOT": (
        "crxzipple.modules.tool.infrastructure.tool_packages",
        "DEFAULT_TOOL_ROOT",
    ),
    "DockerSandboxBackend": (
        "crxzipple.modules.tool.infrastructure.runtimes",
        "DockerSandboxBackend",
    ),
    "InMemoryToolRunAssignmentRepository": (
        "crxzipple.modules.tool.infrastructure.in_memory_repository",
        "InMemoryToolRunAssignmentRepository",
    ),
    "InMemoryToolRunRepository": (
        "crxzipple.modules.tool.infrastructure.in_memory_repository",
        "InMemoryToolRunRepository",
    ),
    "InMemoryToolWorkerRepository": (
        "crxzipple.modules.tool.infrastructure.in_memory_repository",
        "InMemoryToolWorkerRepository",
    ),
    "LocalAsyncToolExecutor": (
        "crxzipple.modules.tool.infrastructure.executors",
        "LocalAsyncToolExecutor",
    ),
    "LocalToolBinding": (
        "crxzipple.modules.tool.infrastructure.tool_packages",
        "LocalToolBinding",
    ),
    "LocalToolRuntimeRegistry": (
        "crxzipple.modules.tool.infrastructure.discovery",
        "LocalToolRuntimeRegistry",
    ),
    "McpClient": ("crxzipple.modules.tool.infrastructure.mcp_client", "McpClient"),
    "McpDiscoveryProvider": (
        "crxzipple.modules.tool.infrastructure.discovery",
        "McpDiscoveryProvider",
    ),
    "McpHttpClient": (
        "crxzipple.modules.tool.infrastructure.mcp_client",
        "McpHttpClient",
    ),
    "McpStdioClient": (
        "crxzipple.modules.tool.infrastructure.mcp_client",
        "McpStdioClient",
    ),
    "McpToolDefinition": (
        "crxzipple.modules.tool.infrastructure.discovery",
        "McpToolDefinition",
    ),
    "OpenApiDiscoveryProvider": (
        "crxzipple.modules.tool.infrastructure.discovery",
        "OpenApiDiscoveryProvider",
    ),
    "OpenApiOperation": (
        "crxzipple.modules.tool.infrastructure.discovery",
        "OpenApiOperation",
    ),
    "RemoteAsyncToolExecutor": (
        "crxzipple.modules.tool.infrastructure.runtimes",
        "RemoteAsyncToolExecutor",
    ),
    "ResolvedToolHandlerActivation": (
        "crxzipple.modules.tool.infrastructure.tool_packages",
        "ResolvedToolHandlerActivation",
    ),
    "ResolvedToolPackageActivation": (
        "crxzipple.modules.tool.infrastructure.tool_packages",
        "ResolvedToolPackageActivation",
    ),
    "ResolvedToolRuntimeActivation": (
        "crxzipple.modules.tool.infrastructure.tool_packages",
        "ResolvedToolRuntimeActivation",
    ),
    "RuntimeToolBinding": (
        "crxzipple.modules.tool.infrastructure.tool_packages",
        "RuntimeToolBinding",
    ),
    "SandboxAsyncToolExecutor": (
        "crxzipple.modules.tool.infrastructure.runtimes",
        "SandboxAsyncToolExecutor",
    ),
    "SqlAlchemyToolFunctionCatalogRepository": (
        "crxzipple.modules.tool.infrastructure.persistence",
        "SqlAlchemyToolFunctionCatalogRepository",
    ),
    "SqlAlchemyToolFunctionRepository": (
        "crxzipple.modules.tool.infrastructure.persistence",
        "SqlAlchemyToolFunctionRepository",
    ),
    "SqlAlchemyToolProviderBackendRepository": (
        "crxzipple.modules.tool.infrastructure.persistence",
        "SqlAlchemyToolProviderBackendRepository",
    ),
    "SqlAlchemyToolRunAssignmentRepository": (
        "crxzipple.modules.tool.infrastructure.persistence",
        "SqlAlchemyToolRunAssignmentRepository",
    ),
    "SqlAlchemyToolRunRepository": (
        "crxzipple.modules.tool.infrastructure.persistence",
        "SqlAlchemyToolRunRepository",
    ),
    "SqlAlchemyToolSourceDiscoveryRunRepository": (
        "crxzipple.modules.tool.infrastructure.persistence",
        "SqlAlchemyToolSourceDiscoveryRunRepository",
    ),
    "SqlAlchemyToolSourceRepository": (
        "crxzipple.modules.tool.infrastructure.persistence",
        "SqlAlchemyToolSourceRepository",
    ),
    "SqlAlchemyToolSurfaceRepository": (
        "crxzipple.modules.tool.infrastructure.persistence",
        "SqlAlchemyToolSurfaceRepository",
    ),
    "SqlAlchemyToolWorkerRepository": (
        "crxzipple.modules.tool.infrastructure.persistence",
        "SqlAlchemyToolWorkerRepository",
    ),
    "SubprocessSandboxBackend": (
        "crxzipple.modules.tool.infrastructure.runtimes",
        "SubprocessSandboxBackend",
    ),
    "ToolConfiguredProviderDiscoveryAdapter": (
        "crxzipple.modules.tool.infrastructure.provider_catalog",
        "ToolConfiguredProviderDiscoveryAdapter",
    ),
    "ToolDependencyBinding": (
        "crxzipple.modules.tool.infrastructure.tool_packages",
        "ToolDependencyBinding",
    ),
    "ToolDependencyRequirement": (
        "crxzipple.modules.tool.infrastructure.tool_packages",
        "ToolDependencyRequirement",
    ),
    "ToolDiscoveryProvider": (
        "crxzipple.modules.tool.infrastructure.discovery",
        "ToolDiscoveryProvider",
    ),
    "ToolDiscoveryRegistry": (
        "crxzipple.modules.tool.infrastructure.discovery",
        "ToolDiscoveryRegistry",
    ),
    "ToolHandlerPlan": (
        "crxzipple.modules.tool.infrastructure.tool_packages",
        "ToolHandlerPlan",
    ),
    "ToolHandlerRegistration": (
        "crxzipple.modules.tool.infrastructure.tool_packages",
        "ToolHandlerRegistration",
    ),
    "ToolNamespaceDefinition": (
        "crxzipple.modules.tool.infrastructure.tool_packages",
        "ToolNamespaceDefinition",
    ),
    "ToolOpenApiPlan": (
        "crxzipple.modules.tool.infrastructure.tool_packages",
        "ToolOpenApiPlan",
    ),
    "ToolPackageApplyContext": (
        "crxzipple.modules.tool.infrastructure.tool_packages",
        "ToolPackageApplyContext",
    ),
    "ToolPackageApplyResult": (
        "crxzipple.modules.tool.infrastructure.tool_packages",
        "ToolPackageApplyResult",
    ),
    "ToolPackageDiscoveryAdapter": (
        "crxzipple.modules.tool.infrastructure.package_catalog",
        "ToolPackageDiscoveryAdapter",
    ),
    "ToolPackagePlan": (
        "crxzipple.modules.tool.infrastructure.tool_packages",
        "ToolPackagePlan",
    ),
    "ToolRuntimePlan": (
        "crxzipple.modules.tool.infrastructure.tool_packages",
        "ToolRuntimePlan",
    ),
    "ToolRuntimeRegistration": (
        "crxzipple.modules.tool.infrastructure.runtimes",
        "ToolRuntimeRegistration",
    ),
    "ToolRuntimeRegistry": (
        "crxzipple.modules.tool.infrastructure.runtimes",
        "ToolRuntimeRegistry",
    ),
    "ToolRuntimeRouter": (
        "crxzipple.modules.tool.infrastructure.runtimes",
        "ToolRuntimeRouter",
    ),
    "activate_configured_provider_runtimes": (
        "crxzipple.modules.tool.infrastructure.provider_catalog",
        "activate_configured_provider_runtimes",
    ),
    "apply_tool_package_plans": (
        "crxzipple.modules.tool.infrastructure.tool_packages",
        "apply_tool_package_plans",
    ),
    "build_mcp_client": (
        "crxzipple.modules.tool.infrastructure.mcp_client",
        "build_mcp_client",
    ),
    "build_sandbox_backend": (
        "crxzipple.modules.tool.infrastructure.runtimes",
        "build_sandbox_backend",
    ),
    "configured_mcp_source_id": (
        "crxzipple.modules.tool.infrastructure.provider_catalog",
        "configured_mcp_source_id",
    ),
    "configured_openapi_source_id": (
        "crxzipple.modules.tool.infrastructure.provider_catalog",
        "configured_openapi_source_id",
    ),
    "discover_tool_namespaces": (
        "crxzipple.modules.tool.infrastructure.tool_packages",
        "discover_tool_namespaces",
    ),
    "discover_tool_package_plans": (
        "crxzipple.modules.tool.infrastructure.tool_packages",
        "discover_tool_package_plans",
    ),
    "load_tool_package_plan": (
        "crxzipple.modules.tool.infrastructure.tool_packages",
        "load_tool_package_plan",
    ),
    "register_mcp_remote_handlers": (
        "crxzipple.modules.tool.infrastructure.runtimes",
        "register_mcp_remote_handlers",
    ),
    "register_openapi_remote_handlers": (
        "crxzipple.modules.tool.infrastructure.runtimes",
        "register_openapi_remote_handlers",
    ),
    "resolve_tool_package_activations": (
        "crxzipple.modules.tool.infrastructure.tool_packages",
        "resolve_tool_package_activations",
    ),
    "tool_package_source_id": (
        "crxzipple.modules.tool.infrastructure.package_catalog",
        "tool_package_source_id",
    ),
    "tool_source_records_from_configured_providers": (
        "crxzipple.modules.tool.infrastructure.provider_catalog",
        "tool_source_records_from_configured_providers",
    ),
    "tool_source_records_from_package_plans": (
        "crxzipple.modules.tool.infrastructure.package_catalog",
        "tool_source_records_from_package_plans",
    ),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
