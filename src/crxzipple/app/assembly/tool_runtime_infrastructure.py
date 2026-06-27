"""Tool runtime infrastructure assembly helpers."""

from __future__ import annotations

from typing import Any

from crxzipple.app.keys import AppKey
from crxzipple.app.assembly.tool_packages import validate_tool_package_plans
from crxzipple.app.assembly.tool_runtime import ToolCleanupCallbacks
from crxzipple.modules.tool.infrastructure import (
    LocalAsyncToolExecutor,
    LocalToolRuntimeRegistry,
    RemoteAsyncToolExecutor,
    SandboxAsyncToolExecutor,
    ToolDiscoveryRegistry,
    ToolRuntimeRegistry,
    ToolRuntimeRouter,
    build_sandbox_backend,
    discover_tool_package_plans,
)


def build_tool_runtime_infrastructure(ctx) -> dict[str, Any]:
    settings = ctx.require(AppKey.CORE_SETTINGS)
    runtime_parts = _build_runtime_parts(settings)
    package_plans = discover_tool_package_plans()

    validate_tool_package_plans(package_plans)

    return {
        AppKey.TOOL_PACKAGE_PLANS: package_plans,
        AppKey.TOOL_LOCAL_RUNTIME_REGISTRY: runtime_parts["local_runtime_registry"],
        AppKey.TOOL_DISCOVERY_REGISTRY: runtime_parts["discovery_registry"],
        AppKey.TOOL_REMOTE_RUNTIME_REGISTRY: runtime_parts["remote_runtime_registry"],
        AppKey.TOOL_SANDBOX_RUNTIME_REGISTRY: runtime_parts["sandbox_runtime_registry"],
        AppKey.TOOL_RUNTIME_GATEWAY: runtime_parts["runtime_gateway"],
        AppKey.TOOL_CLEANUP_CALLBACKS: (ToolCleanupCallbacks(),),
    }


def build_tool_request_preview_runtime_infrastructure(ctx) -> dict[str, Any]:
    settings = ctx.require(AppKey.CORE_SETTINGS)
    runtime_parts = _build_runtime_parts(settings)

    return {
        AppKey.TOOL_PACKAGE_PLANS: (),
        AppKey.TOOL_LOCAL_RUNTIME_REGISTRY: runtime_parts["local_runtime_registry"],
        AppKey.TOOL_DISCOVERY_REGISTRY: runtime_parts["discovery_registry"],
        AppKey.TOOL_REMOTE_RUNTIME_REGISTRY: runtime_parts["remote_runtime_registry"],
        AppKey.TOOL_SANDBOX_RUNTIME_REGISTRY: runtime_parts["sandbox_runtime_registry"],
        AppKey.TOOL_RUNTIME_GATEWAY: runtime_parts["runtime_gateway"],
        AppKey.TOOL_CLEANUP_CALLBACKS: (),
    }


def _build_runtime_parts(settings) -> dict[str, Any]:
    local_runtime_registry = LocalToolRuntimeRegistry()
    discovery_registry = ToolDiscoveryRegistry()
    sandbox_runtime_registry = ToolRuntimeRegistry()
    remote_runtime_registry = ToolRuntimeRegistry()
    runtime_gateway = ToolRuntimeRouter(
        LocalAsyncToolExecutor(local_runtime_registry),
        SandboxAsyncToolExecutor(
            sandbox_runtime_registry,
            build_sandbox_backend(settings),
        ),
        RemoteAsyncToolExecutor(remote_runtime_registry),
    )
    return {
        "local_runtime_registry": local_runtime_registry,
        "discovery_registry": discovery_registry,
        "sandbox_runtime_registry": sandbox_runtime_registry,
        "remote_runtime_registry": remote_runtime_registry,
        "runtime_gateway": runtime_gateway,
    }
