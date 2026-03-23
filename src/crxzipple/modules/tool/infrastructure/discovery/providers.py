from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.modules.tool.application import ToolDiscoveryProviderDescriptor
from crxzipple.modules.tool.domain import ToolSourceKind
from crxzipple.modules.tool.infrastructure.discovery.local_catalog import LocalToolCatalog


class ToolDiscoveryProvider(Protocol):
    name: str
    description: str
    source_kind: ToolSourceKind

    def discover_specs(self) -> list[ToolSpec]:
        ...


class ToolDiscoveryRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ToolDiscoveryProvider] = {}

    def register(self, provider: ToolDiscoveryProvider) -> None:
        self._providers[provider.name] = provider

    def list_providers(self) -> list[ToolDiscoveryProviderDescriptor]:
        return [
            ToolDiscoveryProviderDescriptor(
                name=provider.name,
                description=provider.description,
                source_kind=provider.source_kind,
            )
            for provider in sorted(self._providers.values(), key=lambda item: item.name)
        ]

    def get(self, provider_name: str) -> ToolDiscoveryProvider | None:
        return self._providers.get(provider_name)

    def discover(self, *, provider_name: str | None = None) -> list[ToolSpec]:
        if provider_name is not None:
            provider = self.get(provider_name)
            if provider is None:
                return []
            return provider.discover_specs()

        specs: list[ToolSpec] = []
        for provider in sorted(self._providers.values(), key=lambda item: item.name):
            specs.extend(provider.discover_specs())
        return specs


@dataclass(slots=True)
class LocalCatalogDiscoveryProvider:
    catalog: LocalToolCatalog
    name: str = "local_builtin"
    description: str = "Discovers local built-in tools from the in-process catalog."
    source_kind: ToolSourceKind = ToolSourceKind.LOCAL_DISCOVERY

    def discover_specs(self) -> list[ToolSpec]:
        return [
            ToolSpec.from_tool(tool, provider_name=self.name)
            for tool in self.catalog.list_local_tools(provider_name=self.name)
        ]
