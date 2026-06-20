"""Tool runtime backend exports."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    "DockerSandboxBackend": (
        "crxzipple.modules.tool.infrastructure.runtimes.sandbox_backends",
        "DockerSandboxBackend",
    ),
    "RemoteAsyncToolExecutor": (
        "crxzipple.modules.tool.infrastructure.runtimes.remote",
        "RemoteAsyncToolExecutor",
    ),
    "SandboxAsyncToolExecutor": (
        "crxzipple.modules.tool.infrastructure.runtimes.sandbox",
        "SandboxAsyncToolExecutor",
    ),
    "SubprocessSandboxBackend": (
        "crxzipple.modules.tool.infrastructure.runtimes.sandbox_backends",
        "SubprocessSandboxBackend",
    ),
    "ToolRuntimeRegistration": (
        "crxzipple.modules.tool.infrastructure.runtimes.registry",
        "ToolRuntimeRegistration",
    ),
    "ToolRuntimeRegistry": (
        "crxzipple.modules.tool.infrastructure.runtimes.registry",
        "ToolRuntimeRegistry",
    ),
    "ToolRuntimeRouter": (
        "crxzipple.modules.tool.infrastructure.runtimes.router",
        "ToolRuntimeRouter",
    ),
    "build_sandbox_backend": (
        "crxzipple.modules.tool.infrastructure.runtimes.sandbox_backends",
        "build_sandbox_backend",
    ),
    "register_mcp_remote_handlers": (
        "crxzipple.modules.tool.infrastructure.runtimes.mcp_remote",
        "register_mcp_remote_handlers",
    ),
    "register_openapi_remote_handlers": (
        "crxzipple.modules.tool.infrastructure.runtimes.openapi_remote",
        "register_openapi_remote_handlers",
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
