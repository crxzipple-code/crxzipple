from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from crxzipple.modules.tool.application.catalog_models import (
    ToolSourceCatalogKind,
    ToolSourceCatalogRecord,
    ToolSourceDiscoveryResult,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError


class ToolDiscoveryAdapter(Protocol):
    def discover(self, source: ToolSourceCatalogRecord) -> ToolSourceDiscoveryResult:
        ...


class ToolDiscoveryAdapterRegistry:
    def __init__(
        self,
        adapters: Mapping[ToolSourceCatalogKind | str, ToolDiscoveryAdapter] | None = None,
    ) -> None:
        self._adapters: dict[ToolSourceCatalogKind, ToolDiscoveryAdapter] = {}
        for kind, adapter in dict(adapters or {}).items():
            self.register(kind, adapter)

    def register(
        self,
        kind: ToolSourceCatalogKind | str,
        adapter: ToolDiscoveryAdapter,
    ) -> None:
        self._adapters[ToolSourceCatalogKind(str(kind))] = adapter

    def adapter_for(
        self,
        kind: ToolSourceCatalogKind | str,
    ) -> ToolDiscoveryAdapter:
        source_kind = ToolSourceCatalogKind(str(kind))
        adapter = self._adapters.get(source_kind)
        if adapter is None:
            raise ToolValidationError(
                f"Tool discovery adapter for source kind '{source_kind.value}' is not configured.",
            )
        return adapter


class ToolDiscoveryService:
    def __init__(self, adapters: ToolDiscoveryAdapterRegistry) -> None:
        self._adapters = adapters

    def discover(self, source: ToolSourceCatalogRecord) -> ToolSourceDiscoveryResult:
        return self._adapters.adapter_for(source.kind).discover(source)
