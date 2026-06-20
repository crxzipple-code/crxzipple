"""Tool discovery exports."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    "LocalToolHandler": (
        "crxzipple.modules.tool.infrastructure.discovery.local_runtime_registry",
        "LocalToolHandler",
    ),
    "LocalToolRuntimeRegistry": (
        "crxzipple.modules.tool.infrastructure.discovery.local_runtime_registry",
        "LocalToolRuntimeRegistry",
    ),
    "McpDiscoveryProvider": (
        "crxzipple.modules.tool.infrastructure.discovery.mcp",
        "McpDiscoveryProvider",
    ),
    "McpToolDefinition": (
        "crxzipple.modules.tool.infrastructure.discovery.mcp",
        "McpToolDefinition",
    ),
    "OpenApiDiscoveryProvider": (
        "crxzipple.modules.tool.infrastructure.discovery.openapi",
        "OpenApiDiscoveryProvider",
    ),
    "OpenApiOperation": (
        "crxzipple.modules.tool.infrastructure.discovery.openapi",
        "OpenApiOperation",
    ),
    "ToolDiscoveryProvider": (
        "crxzipple.modules.tool.infrastructure.discovery.providers",
        "ToolDiscoveryProvider",
    ),
    "ToolDiscoveryRegistry": (
        "crxzipple.modules.tool.infrastructure.discovery.providers",
        "ToolDiscoveryRegistry",
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
