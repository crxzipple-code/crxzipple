from __future__ import annotations

from crxzipple.core.config import PROJECT_ROOT, OpenApiProviderSettings
from crxzipple.modules.tool.application.activation import (
    ToolHandlerPlan,
    ToolPackagePlan,
    ToolRuntimePlan,
)


DEFAULT_TOOL_ROOT = PROJECT_ROOT / "tools"

LocalToolBinding = ToolHandlerPlan
RuntimeToolBinding = ToolRuntimePlan


class ToolNamespaceDefinition(ToolPackagePlan):
    @property
    def name(self) -> str:
        return self.namespace

    @property
    def kind(self) -> str:
        return self.package_kind

    @property
    def local_bindings(self) -> tuple[ToolHandlerPlan, ...]:
        return self.local_handlers

    @property
    def remote_bindings(self) -> tuple[ToolRuntimePlan, ...]:
        return self.remote_runtimes

    @property
    def sandbox_bindings(self) -> tuple[ToolRuntimePlan, ...]:
        return self.sandbox_runtimes

    @property
    def openapi_provider(self) -> OpenApiProviderSettings | None:
        return self.openapi.provider if self.openapi is not None else None


__all__ = [
    "DEFAULT_TOOL_ROOT",
    "LocalToolBinding",
    "RuntimeToolBinding",
    "ToolNamespaceDefinition",
]
