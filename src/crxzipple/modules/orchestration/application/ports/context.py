from __future__ import annotations

from dataclasses import dataclass
from threading import Event as ThreadEvent
from typing import TYPE_CHECKING, Protocol

from crxzipple.modules.events.domain import EventCursor, EventTopicWatch
from crxzipple.modules.events.domain import EventSubscriptionCursor, EventTopicRecord
from crxzipple.shared.domain.events import Event

if TYPE_CHECKING:
    from pathlib import Path

    from crxzipple.modules.agent.domain.entities import AgentProfile
    from crxzipple.modules.artifacts.domain.entities import ArtifactVariant
    from crxzipple.modules.llm.domain import ToolSchema
    from crxzipple.modules.orchestration.application.prompt_surface import (
        PromptSurface,
    )
    from crxzipple.modules.orchestration.domain.entities import OrchestrationRun
    from crxzipple.modules.session.domain.entities import Session
    from crxzipple.modules.session.domain.value_objects import SessionMessage
    from crxzipple.modules.session.application.services import (
        AppendSessionMessageInput,
        AppendSessionMessagesInput,
        ArchiveSessionMessagesInput,
        ListSessionMessagesInput,
        MergeSessionMessageMetadataInput,
        SessionMessagesBundle,
    )
    from crxzipple.modules.session.application.resolution import (
        ResolveSessionInput,
        ResolvedSessionBundle,
    )


class AgentProfileCatalogPort(Protocol):
    def get_profile(self, profile_id: str) -> "AgentProfile":
        ...

    def list_profiles(self) -> list["AgentProfile"]:
        ...


class SessionTranscriptPort(Protocol):
    def get_session_with_messages(
        self,
        data: "ListSessionMessagesInput",
    ) -> "SessionMessagesBundle":
        ...


class SessionResolutionPort(Protocol):
    def resolve(self, data: "ResolveSessionInput") -> "ResolvedSessionBundle":
        ...


class SessionLookupPort(Protocol):
    def get_session(self, session_key: str) -> "Session":
        ...


class SessionCatalogPort(SessionLookupPort, Protocol):
    def list_sessions(self, *, agent_id: str | None = None) -> list["Session"]:
        ...


class SessionMessageAppendPort(Protocol):
    def append_message(self, data: "AppendSessionMessageInput") -> "SessionMessage":
        ...


class SessionMessageBulkAppendPort(SessionMessageAppendPort, Protocol):
    def append_messages(
        self,
        data: "AppendSessionMessagesInput",
    ) -> tuple["SessionMessage", ...]:
        ...


class SessionMessageSourceLookupPort(Protocol):
    def get_message_by_source(
        self,
        *,
        session_key: str,
        session_id: str,
        source_kind: str,
        source_id: str,
    ) -> "SessionMessage | None":
        ...


class SessionMessageListPort(Protocol):
    def list_messages(
        self,
        data: "ListSessionMessagesInput",
    ) -> list["SessionMessage"]:
        ...


class SessionRecorderPort(
    SessionMessageBulkAppendPort,
    SessionMessageSourceLookupPort,
    Protocol,
):
    pass


class SessionCompactionStatePort(SessionCatalogPort, Protocol):
    def merge_session_metadata(
        self,
        session_key: str,
        *,
        metadata: dict[str, object],
        touch_activity: bool = True,
    ) -> "Session":
        ...


class SessionMaintenancePort(
    SessionMessageSourceLookupPort,
    SessionMessageListPort,
    Protocol,
):
    def get_message(self, message_id: str) -> "SessionMessage":
        ...

    def merge_message_metadata(
        self,
        data: "MergeSessionMessageMetadataInput",
    ) -> "SessionMessage":
        ...

    def archive_messages(self, data: "ArchiveSessionMessagesInput") -> int:
        ...

    def merge_session_metadata(
        self,
        session_key: str,
        *,
        metadata: dict[str, object],
        touch_activity: bool = True,
    ) -> "Session":
        ...


class OrchestrationSessionPort(
    SessionCompactionStatePort,
    SessionMaintenancePort,
    SessionRecorderPort,
    Protocol,
):
    pass


class ResolvedArtifactVariantPort(Protocol):
    path: "Path"


class ArtifactVariantReadPort(Protocol):
    def resolve_variant(
        self,
        artifact_id: str,
        *,
        variant: "ArtifactVariant",
    ) -> ResolvedArtifactVariantPort:
        ...


@dataclass(frozen=True, slots=True)
class ContextRenderSnapshotRecord:
    snapshot_id: str
    prompt_body: str | None = None
    estimate: dict[str, object] | None = None
    included_node_ids: tuple[str, ...] = ()
    mirrored_node_ids: tuple[str, ...] = ()
    tool_schemas: tuple["ToolSchema", ...] | None = None
    tool_schema_mirror_available: bool = False
    artifact_content_blocks: tuple[dict[str, object], ...] = ()


class ContextRenderSnapshotPort(Protocol):
    def preview_run_prompt_snapshot(
        self,
        *,
        run: "OrchestrationRun",
        prompt: "PromptSurface",
    ) -> ContextRenderSnapshotRecord | None:
        ...

    def record_run_prompt_snapshot(
        self,
        *,
        run: "OrchestrationRun",
        prompt: "PromptSurface",
    ) -> ContextRenderSnapshotRecord | None:
        ...


class EventPublishPort(Protocol):
    def publish(self, event: Event) -> None:
        ...


class EventPublishManyPort(EventPublishPort, Protocol):
    def publish_many(self, events: tuple[Event, ...]) -> None:
        ...


class EventTopicWaitPort(Protocol):
    def snapshot_event_topic(self, topic: str) -> EventCursor:
        ...

    def wait_for_event_topics(
        self,
        watches: tuple[EventTopicWatch, ...],
        *,
        timeout_seconds: float,
        stop_event: ThreadEvent | None = None,
    ) -> EventTopicWatch | None:
        ...


class EventBusPort(EventPublishManyPort, EventTopicWaitPort, Protocol):
    pass


class EventSubscriptionStreamPort(EventTopicWaitPort, Protocol):
    def get_subscription_cursor(
        self,
        subscription_id: str,
        *,
        source_topic: str | None = None,
    ) -> EventSubscriptionCursor | None:
        ...

    def set_subscription_cursor(
        self,
        subscription_id: str,
        *,
        source_topic: str,
        cursor: EventCursor,
    ) -> EventSubscriptionCursor:
        ...

    def read_event_topic(
        self,
        topic: str,
        *,
        after_cursor: EventCursor | None = None,
        limit: int = 100,
    ) -> tuple[EventTopicRecord, ...]:
        ...
