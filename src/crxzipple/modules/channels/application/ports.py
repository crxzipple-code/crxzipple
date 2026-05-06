from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from crxzipple.modules.channels.domain import (
    ChannelInteractionRegistry,
    ChannelRuntimeRegistry,
    ChannelSystemConfig,
)


class ChannelSystemConfigStore(Protocol):
    def load(self) -> ChannelSystemConfig:
        ...

    def save(self, config: ChannelSystemConfig) -> ChannelSystemConfig:
        ...

    def update(
        self,
        mutator: Callable[[ChannelSystemConfig], ChannelSystemConfig],
    ) -> ChannelSystemConfig:
        ...


class ChannelRuntimeRegistryStore(Protocol):
    def load(self) -> ChannelRuntimeRegistry:
        ...

    def save(self, registry: ChannelRuntimeRegistry) -> ChannelRuntimeRegistry:
        ...

    def update(
        self,
        mutator: Callable[[ChannelRuntimeRegistry], ChannelRuntimeRegistry],
    ) -> ChannelRuntimeRegistry:
        ...


class ChannelInteractionRegistryStore(Protocol):
    def load(self) -> ChannelInteractionRegistry:
        ...

    def save(self, registry: ChannelInteractionRegistry) -> ChannelInteractionRegistry:
        ...

    def update(
        self,
        mutator: Callable[[ChannelInteractionRegistry], ChannelInteractionRegistry],
    ) -> ChannelInteractionRegistry:
        ...
