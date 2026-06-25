from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.tool.application.catalog_models import (
    ToolFunctionCatalogRecord,
    ToolSourceCatalogRecord,
    ToolSourceDiscoveryResult,
)
from crxzipple.modules.tool.application.reconcile_service import (
    ToolCatalogReconcileResult,
)


@dataclass(frozen=True, slots=True)
class ToolSourceCommandResult:
    source: ToolSourceCatalogRecord
    changed: bool


@dataclass(frozen=True, slots=True)
class ToolFunctionCommandResult:
    function: ToolFunctionCatalogRecord
    changed: bool


@dataclass(frozen=True, slots=True)
class ToolSourceSyncResult:
    source: ToolSourceCatalogRecord
    discovery: ToolSourceDiscoveryResult | None = None
    reconcile: ToolCatalogReconcileResult | None = None
    skipped: bool = False
    error_message: str | None = None

    @property
    def changed(self) -> bool:
        return bool(
            self.reconcile is not None and self.reconcile.changed,
        )


@dataclass(frozen=True, slots=True)
class ToolSourceCatalogSyncResult:
    results: tuple[ToolSourceSyncResult, ...]

    @property
    def source_count(self) -> int:
        return len(self.results)

    @property
    def function_count(self) -> int:
        return sum(
            len(result.discovery.candidates)
            for result in self.results
            if result.discovery is not None
        )

    @property
    def changed_count(self) -> int:
        return sum(
            len(result.reconcile.changed)
            for result in self.results
            if result.reconcile is not None
        )

    @property
    def error_count(self) -> int:
        return sum(1 for result in self.results if result.error_message)


__all__ = [
    "ToolFunctionCommandResult",
    "ToolSourceCatalogSyncResult",
    "ToolSourceCommandResult",
    "ToolSourceSyncResult",
]
