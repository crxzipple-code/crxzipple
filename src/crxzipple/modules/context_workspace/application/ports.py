from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from crxzipple.modules.context_workspace.application.models import (
    BuildContextControlSliceInput,
    BuildContextObservationSliceInput,
    ContextControlSlice,
    ContextSlice,
)
from crxzipple.modules.context_workspace.domain import (
    ContextNode,
    ContextNodeSeed,
    ContextWorkspace,
)


@dataclass(frozen=True, slots=True)
class ContextChildrenRequest:
    workspace: ContextWorkspace
    node: ContextNode


class ContextNodeProvider(Protocol):
    owner: str

    def children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        ...


class ContextSliceBuilder(Protocol):
    def build_slice(
        self,
        *,
        session_key: str = "",
        run_id: str = "",
        audience: str = "llm_request",
        provider_profile: str | None = None,
        data: BuildContextObservationSliceInput | None = None,
    ) -> ContextSlice:
        ...


class ContextControlSliceBuilder(Protocol):
    def build_control_slice(
        self,
        *,
        session_key: str = "",
        run_id: str = "",
        audience: str = "llm_request",
        provider_profile: str | None = None,
        data: BuildContextControlSliceInput | None = None,
    ) -> ContextControlSlice:
        ...


class ContextOwnerRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ContextNodeProvider] = {}

    def register(self, provider: ContextNodeProvider) -> None:
        owner = provider.owner.strip()
        if not owner:
            raise ValueError("context node provider owner cannot be blank.")
        self._providers[owner] = provider

    def get(self, owner: str) -> ContextNodeProvider | None:
        return self._providers.get(owner.strip())

    @property
    def owners(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))


__all__ = [
    "ContextChildrenRequest",
    "ContextControlSliceBuilder",
    "ContextNodeProvider",
    "ContextOwnerRegistry",
    "ContextSliceBuilder",
]
