from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock

from crxzipple.modules.channels.application.ports import (
    ChannelInteractionRegistryStore,
    ChannelRuntimeRegistryStore,
    ChannelSystemConfigStore,
)
from crxzipple.modules.channels.application.migrations import (
    normalize_channel_interaction_delivery_state,
)
from crxzipple.modules.channels.domain import (
    ChannelInteractionRegistry,
    ChannelRuntimeRegistry,
    ChannelSystemConfig,
)
from crxzipple.modules.channels.infrastructure.state_root import (
    ChannelStateRoot,
    bootstrap_channel_state_root,
    load_channel_interaction_registry,
    ensure_channel_state_root,
    load_channel_runtime_registry,
    load_channel_system_config,
    persist_channel_interaction_registry,
    persist_channel_runtime_registry,
    persist_channel_system_config,
    update_channel_interaction_registry,
    update_channel_runtime_registry,
    update_channel_system_config,
)


@dataclass(slots=True)
class InMemoryChannelSystemConfigStore(ChannelSystemConfigStore):
    config: ChannelSystemConfig = field(default_factory=ChannelSystemConfig)
    _lock: RLock = field(default_factory=RLock)

    def load(self) -> ChannelSystemConfig:
        with self._lock:
            return self.config

    def save(self, config: ChannelSystemConfig) -> ChannelSystemConfig:
        with self._lock:
            self.config = config
            return self.config

    def update(
        self,
        mutator: Callable[[ChannelSystemConfig], ChannelSystemConfig],
    ) -> ChannelSystemConfig:
        with self._lock:
            updated = mutator(self.config)
            self.config = updated
            return self.config


@dataclass(slots=True)
class FileBackedChannelSystemConfigStore(ChannelSystemConfigStore):
    root_dir: Path | str
    bootstrap_config: ChannelSystemConfig | None = None
    state_root: ChannelStateRoot = field(init=False)
    _lock: RLock = field(default_factory=RLock, init=False)

    def __post_init__(self) -> None:
        if self.bootstrap_config is None:
            self.state_root = ensure_channel_state_root(self.root_dir)
        else:
            self.state_root = bootstrap_channel_state_root(
                self.root_dir,
                system_config=self.bootstrap_config,
            )

    def load(self) -> ChannelSystemConfig:
        with self._lock:
            config = load_channel_system_config(self.state_root)
            persist_channel_system_config(self.state_root, system_config=config)
            return config

    def save(self, config: ChannelSystemConfig) -> ChannelSystemConfig:
        with self._lock:
            persist_channel_system_config(self.state_root, system_config=config)
            return self.load()

    def update(
        self,
        mutator: Callable[[ChannelSystemConfig], ChannelSystemConfig],
    ) -> ChannelSystemConfig:
        with self._lock:
            return update_channel_system_config(self.state_root, mutator)


@dataclass(slots=True)
class InMemoryChannelRuntimeRegistryStore(ChannelRuntimeRegistryStore):
    registry: ChannelRuntimeRegistry = field(default_factory=ChannelRuntimeRegistry)
    _lock: RLock = field(default_factory=RLock)

    def load(self) -> ChannelRuntimeRegistry:
        with self._lock:
            return self.registry

    def save(self, registry: ChannelRuntimeRegistry) -> ChannelRuntimeRegistry:
        with self._lock:
            self.registry = registry
            return self.registry

    def update(
        self,
        mutator: Callable[[ChannelRuntimeRegistry], ChannelRuntimeRegistry],
    ) -> ChannelRuntimeRegistry:
        with self._lock:
            updated = mutator(self.registry)
            self.registry = updated
            return self.registry


@dataclass(slots=True)
class FileBackedChannelRuntimeRegistryStore(ChannelRuntimeRegistryStore):
    root_dir: Path | str
    bootstrap_registry: ChannelRuntimeRegistry | None = None
    state_root: ChannelStateRoot = field(init=False)
    _lock: RLock = field(default_factory=RLock, init=False)

    def __post_init__(self) -> None:
        if self.bootstrap_registry is None:
            self.state_root = ensure_channel_state_root(self.root_dir)
        else:
            self.state_root = bootstrap_channel_state_root(
                self.root_dir,
                runtime_registry=self.bootstrap_registry,
            )

    def load(self) -> ChannelRuntimeRegistry:
        with self._lock:
            registry = load_channel_runtime_registry(self.state_root)
            persist_channel_runtime_registry(self.state_root, registry=registry)
            return registry

    def save(self, registry: ChannelRuntimeRegistry) -> ChannelRuntimeRegistry:
        with self._lock:
            persist_channel_runtime_registry(self.state_root, registry=registry)
            return self.load()

    def update(
        self,
        mutator: Callable[[ChannelRuntimeRegistry], ChannelRuntimeRegistry],
    ) -> ChannelRuntimeRegistry:
        with self._lock:
            return update_channel_runtime_registry(self.state_root, mutator)


@dataclass(slots=True)
class InMemoryChannelInteractionRegistryStore(ChannelInteractionRegistryStore):
    registry: ChannelInteractionRegistry = field(default_factory=ChannelInteractionRegistry)
    _lock: RLock = field(default_factory=RLock)

    def load(self) -> ChannelInteractionRegistry:
        with self._lock:
            self.registry = normalize_channel_interaction_delivery_state(self.registry)
            return self.registry

    def save(self, registry: ChannelInteractionRegistry) -> ChannelInteractionRegistry:
        with self._lock:
            self.registry = normalize_channel_interaction_delivery_state(registry)
            return self.registry

    def update(
        self,
        mutator: Callable[[ChannelInteractionRegistry], ChannelInteractionRegistry],
    ) -> ChannelInteractionRegistry:
        with self._lock:
            updated = mutator(normalize_channel_interaction_delivery_state(self.registry))
            self.registry = normalize_channel_interaction_delivery_state(updated)
            return self.registry


@dataclass(slots=True)
class FileBackedChannelInteractionRegistryStore(ChannelInteractionRegistryStore):
    root_dir: Path | str
    bootstrap_registry: ChannelInteractionRegistry | None = None
    state_root: ChannelStateRoot = field(init=False)
    _lock: RLock = field(default_factory=RLock, init=False)

    def __post_init__(self) -> None:
        if self.bootstrap_registry is None:
            self.state_root = ensure_channel_state_root(self.root_dir)
        else:
            self.state_root = bootstrap_channel_state_root(
                self.root_dir,
                interaction_registry=self.bootstrap_registry,
            )

    def load(self) -> ChannelInteractionRegistry:
        with self._lock:
            registry = load_channel_interaction_registry(self.state_root)
            normalized = normalize_channel_interaction_delivery_state(registry)
            persist_channel_interaction_registry(self.state_root, registry=normalized)
            return normalized

    def save(self, registry: ChannelInteractionRegistry) -> ChannelInteractionRegistry:
        with self._lock:
            persist_channel_interaction_registry(
                self.state_root,
                registry=normalize_channel_interaction_delivery_state(registry),
            )
            return self.load()

    def update(
        self,
        mutator: Callable[[ChannelInteractionRegistry], ChannelInteractionRegistry],
    ) -> ChannelInteractionRegistry:
        with self._lock:
            return update_channel_interaction_registry(
                self.state_root,
                lambda registry: normalize_channel_interaction_delivery_state(
                    mutator(normalize_channel_interaction_delivery_state(registry)),
                ),
            )
