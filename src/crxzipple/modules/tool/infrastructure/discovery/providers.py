from __future__ import annotations

from typing import Protocol

from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.modules.tool.domain import ToolDefinitionOrigin


class ToolDiscoveryProvider(Protocol):
    name: str
    description: str
    definition_origin: ToolDefinitionOrigin

    def discover_specs(self) -> list[ToolSpec]:
        ...


class ToolDiscoveryRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ToolDiscoveryProvider] = {}

    def register(self, provider: ToolDiscoveryProvider) -> None:
        if provider.name in self._providers:
            raise ValueError(
                f"Tool discovery provider '{provider.name}' is already registered.",
            )
        self._providers[provider.name] = provider

    def get(self, provider_name: str) -> ToolDiscoveryProvider | None:
        return self._providers.get(provider_name)
