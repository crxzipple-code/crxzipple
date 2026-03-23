from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.modules.tool.domain import ToolSourceKind


@dataclass(frozen=True, slots=True)
class ToolDiscoveryProviderDescriptor:
    name: str
    description: str
    source_kind: ToolSourceKind


class ToolDiscoveryGateway(Protocol):
    def list_providers(self) -> list[ToolDiscoveryProviderDescriptor]:
        ...

    def discover(self, *, provider_name: str | None = None) -> list[ToolSpec]:
        ...
