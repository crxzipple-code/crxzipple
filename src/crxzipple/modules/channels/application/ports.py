from __future__ import annotations

from collections.abc import Callable
from threading import Event as ThreadEvent
from typing import TYPE_CHECKING, Any, Protocol

from crxzipple.modules.channels.domain import (
    ChannelInteractionRegistry,
    ChannelRuntimeRegistry,
    ChannelSystemConfig,
)
from crxzipple.modules.daemon.domain import DaemonServiceSpec
from crxzipple.modules.events.domain import (
    EventCursor,
    EventTopicRecord,
    EventTopicWatch,
)
from crxzipple.shared.domain.events import Event

if TYPE_CHECKING:
    from pathlib import Path

    from crxzipple.modules.agent.domain.entities import AgentProfile
    from crxzipple.modules.artifacts.domain import Artifact, ArtifactVariant


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


class ChannelAccessReadinessPort(Protocol):
    def check_requirements(self, requirements: tuple[str, ...]) -> tuple[Any, ...]:
        ...


class ChannelAgentProfilePort(Protocol):
    def get_profile(self, profile_id: str) -> "AgentProfile":
        ...

    def list_profiles(self) -> list["AgentProfile"]:
        ...


class ChannelResolvedArtifactVariantPort(Protocol):
    path: "Path"
    artifact: Any


class ChannelArtifactReadPort(Protocol):
    def get_artifact(self, artifact_id: str) -> "Artifact":
        ...

    def resolve_variant(
        self,
        artifact_id: str,
        *,
        variant: "ArtifactVariant",
    ) -> ChannelResolvedArtifactVariantPort:
        ...


class ChannelEventStreamPort(Protocol):
    def publish(self, event: Event) -> None:
        ...

    def snapshot_event_topic(self, topic: str) -> EventCursor:
        ...

    def read_event_topic(
        self,
        topic: str,
        *,
        after_cursor: EventCursor | None = None,
        limit: int = 100,
    ) -> tuple[EventTopicRecord, ...]:
        ...

    def wait_for_event_topics(
        self,
        watches: tuple[EventTopicWatch, ...],
        *,
        timeout_seconds: float,
        stop_event: ThreadEvent | None = None,
    ) -> EventTopicWatch | None:
        ...


class ChannelDaemonSpecRegistryPort(Protocol):
    def register_service_spec(self, spec: DaemonServiceSpec) -> DaemonServiceSpec:
        ...

    def remove_service_specs(
        self,
        predicate: Callable[[DaemonServiceSpec], bool],
    ) -> tuple[str, ...]:
        ...
