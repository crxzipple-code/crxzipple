from __future__ import annotations

from dataclasses import dataclass, field
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
    from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
        RuntimeLlmRequestDraft,
    )
    from crxzipple.modules.orchestration.domain.entities import OrchestrationRun
    from crxzipple.modules.session.domain.entities import Session
    from crxzipple.modules.session.domain.value_objects import SessionItem
    from crxzipple.modules.session.application.services import (
        AppendSessionItemInput,
        AppendSessionItemsInput,
        CompactSessionSegmentInput,
        CompactSessionSegmentResult,
        GetSessionItemBySourceInput,
        ListSessionItemsInput,
        MergeSessionItemMetadataInput,
        SessionItemsBundle,
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
    def get_session_with_items(
        self,
        data: "ListSessionItemsInput",
    ) -> "SessionItemsBundle":
        ...

    def list_items(
        self,
        data: "ListSessionItemsInput",
    ) -> list["SessionItem"]:
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


class SessionItemAppendPort(Protocol):
    def append_item(self, data: "AppendSessionItemInput") -> "SessionItem":
        ...


class SessionItemBulkAppendPort(Protocol):
    def append_items(
        self,
        data: "AppendSessionItemsInput",
    ) -> tuple[object, ...]:
        ...


class SessionItemSourceLookupPort(Protocol):
    def get_item_by_source(
        self,
        data: "GetSessionItemBySourceInput",
    ) -> "SessionItem | None":
        ...


class SessionRecorderPort(
    SessionItemBulkAppendPort,
    SessionItemSourceLookupPort,
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


class SessionMaintenancePort(Protocol):
    def get_item(self, item_id: str) -> "SessionItem":
        ...

    def list_items(
        self,
        data: "ListSessionItemsInput",
    ) -> list["SessionItem"]:
        ...

    def merge_item_metadata(
        self,
        data: "MergeSessionItemMetadataInput",
    ) -> "SessionItem":
        ...

    def compact_active_segment(
        self,
        data: "CompactSessionSegmentInput",
    ) -> "CompactSessionSegmentResult":
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
class RequestRenderSnapshotRecord:
    snapshot_id: str
    estimate: dict[str, object] | None = None
    included_node_ids: tuple[str, ...] = ()
    mirrored_node_ids: tuple[str, ...] = ()
    included_refs: tuple[dict[str, object], ...] = ()
    collapsed_refs: tuple[dict[str, object], ...] = ()
    protocol_required_refs: tuple[dict[str, object], ...] = ()
    input_item_refs: tuple[dict[str, object], ...] = ()
    projected_input_items: tuple[dict[str, object], ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)
    tool_schemas: tuple["ToolSchema", ...] | None = None
    tool_schema_refs: tuple[dict[str, object], ...] = ()
    tool_schema_mirror_available: bool = False
    artifact_content_blocks: tuple[dict[str, object], ...] = ()
    parent_snapshot_id: str | None = None
    parent_tree_revision: int | None = None


class RequestRenderSnapshotPort(Protocol):
    def get_recorded_run_request_render_snapshot(
        self,
        *,
        run: "OrchestrationRun",
        draft: "RuntimeLlmRequestDraft",
    ) -> RequestRenderSnapshotRecord | None:
        ...

    def preview_run_request_render_snapshot(
        self,
        *,
        run: "OrchestrationRun",
        draft: "RuntimeLlmRequestDraft",
    ) -> RequestRenderSnapshotRecord | None:
        ...

    def record_run_request_render_snapshot(
        self,
        *,
        run: "OrchestrationRun",
        draft: "RuntimeLlmRequestDraft",
    ) -> RequestRenderSnapshotRecord | None:
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
