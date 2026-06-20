from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from crxzipple.modules.workbench.application import (
    ApprovalRequestDetail,
    ArtifactPreview,
    RunMetrics,
    RunStatusStrip,
    RuntimeRef,
    StatusBadgeModel,
    TurnStepView,
    TurnSummary,
    WorkbenchAction,
    WorkbenchConnectionState,
    WorkbenchFilterSummary,
    WorkbenchHomeView,
    WorkbenchInspectorView,
    WorkbenchKeyValueItem,
    WorkbenchKeyValueSection,
    WorkbenchLinkedEntity,
    WorkbenchLinkedEntityDetail,
    WorkbenchRunView,
    WorkbenchTimelineItem,
    WorkbenchThreadSummary,
)
from crxzipple.modules.events.application.read_models import (
    TraceEventView,
    TraceSummaryView,
)
from crxzipple.shared.runtime_console import ConsoleSection, TraceContext


class TraceContextResponse(BaseModel):
    trace_id: str
    correlation_id: str | None = None
    source_event_id: str | None = None
    source_owner: str | None = None
    source_surface_id: str | None = None
    source_event_name: str | None = None
    observed_event_id: str | None = None
    observed_event_name: str | None = None
    session_key: str | None = None
    session_id: str | None = None
    turn_id: str | None = None
    run_id: str | None = None
    step_id: str | None = None
    execution_item_id: str | None = None
    tool_run_id: str | None = None
    tool_call_id: str | None = None
    llm_invocation_id: str | None = None
    llm_response_item_id: str | None = None
    request_render_snapshot_id: str | None = None
    session_item_id: str | None = None
    continuation_decision_id: str | None = None
    artifact_id: str | None = None
    approval_request_id: str | None = None

    @classmethod
    def from_value(cls, value: TraceContext) -> "TraceContextResponse":
        return cls(**value.to_payload())


class ConsoleSectionErrorResponse(BaseModel):
    code: str
    message: str
    retryable: bool
    trace_id: str | None = None


class ConsoleSectionResponse(BaseModel):
    id: str
    owner: str
    status: str
    updated_at: str | None
    data: dict[str, Any] | None = None
    error: ConsoleSectionErrorResponse | None = None

    @classmethod
    def from_value(cls, value: ConsoleSection) -> "ConsoleSectionResponse":
        return cls(
            id=value.id,
            owner=value.owner,
            status=value.status,
            updated_at=value.updated_at,
            data=value.data if isinstance(value.data, dict) else None,
            error=(
                ConsoleSectionErrorResponse(
                    code=value.error.code,
                    message=value.error.message,
                    retryable=value.error.retryable,
                    trace_id=value.error.trace_id,
                )
                if value.error is not None
                else None
            ),
        )


class UiBootstrapResponse(BaseModel):
    version: int
    app_name: str
    environment: str
    default_locale: str = "zh-CN"
    routes: list[str] = Field(default_factory=list)
    sections: list[ConsoleSectionResponse] = Field(default_factory=list)


class RuntimeRefResponse(BaseModel):
    id: str
    name: str

    @classmethod
    def from_value(cls, value: RuntimeRef) -> "RuntimeRefResponse":
        return cls(id=value.id, name=value.name)


class RunMetricsResponse(BaseModel):
    tool_calls: int
    llm_calls: int
    tokens: int
    estimated_cost_usd: float | None

    @classmethod
    def from_value(cls, value: RunMetrics) -> "RunMetricsResponse":
        return cls(
            tool_calls=value.tool_calls,
            llm_calls=value.llm_calls,
            tokens=value.tokens,
            estimated_cost_usd=value.estimated_cost_usd,
        )


class TurnSummaryResponse(BaseModel):
    turn_id: str
    ordinal: int
    status: str
    duration_ms: int | None

    @classmethod
    def from_value(cls, value: TurnSummary) -> "TurnSummaryResponse":
        return cls(
            turn_id=value.turn_id,
            ordinal=value.ordinal,
            status=value.status,
            duration_ms=value.duration_ms,
        )


class RunStatusStripResponse(BaseModel):
    label: str
    eta_ms: int | None
    queue_wait_ms: int

    @classmethod
    def from_value(cls, value: RunStatusStrip) -> "RunStatusStripResponse":
        return cls(
            label=value.label,
            eta_ms=value.eta_ms,
            queue_wait_ms=value.queue_wait_ms,
        )


class ArtifactPreviewResponse(BaseModel):
    artifact_id: str
    name: str
    kind: str
    size_bytes: int | None = None
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    preview_url: str | None = None
    download_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_value(cls, value: ArtifactPreview) -> "ArtifactPreviewResponse":
        return cls(
            artifact_id=value.artifact_id,
            name=value.name,
            kind=value.kind,
            size_bytes=value.size_bytes,
            mime_type=value.mime_type,
            width=value.width,
            height=value.height,
            preview_url=value.preview_url,
            download_url=value.download_url,
            metadata=dict(value.metadata),
        )


class StatusBadgeResponse(BaseModel):
    label: str
    tone: str = "neutral"

    @classmethod
    def from_value(cls, value: StatusBadgeModel) -> "StatusBadgeResponse":
        return cls(label=value.label, tone=value.tone)


class WorkbenchLinkedEntityResponse(BaseModel):
    type: str
    id: str
    label: str | None = None
    owner: str | None = None
    route: str | None = None
    copy_value: str | None = None
    trace: TraceContextResponse | None = None

    @classmethod
    def from_value(
        cls,
        value: WorkbenchLinkedEntity,
    ) -> "WorkbenchLinkedEntityResponse":
        return cls(
            type=value.type,
            id=value.id,
            label=value.label,
            owner=value.owner,
            route=value.route,
            copy_value=value.copy_value,
            trace=(
                TraceContextResponse.from_value(value.trace)
                if value.trace is not None
                else None
            ),
        )


class WorkbenchLinkedEntityDetailResponse(BaseModel):
    type: str
    id: str
    owner: str
    label: str
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_view(
        cls,
        value: WorkbenchLinkedEntityDetail,
    ) -> "WorkbenchLinkedEntityDetailResponse":
        return cls(
            type=value.type,
            id=value.id,
            owner=value.owner,
            label=value.label,
            summary=value.summary,
            payload=dict(value.payload),
        )


class WorkbenchActionResponse(BaseModel):
    id: str
    label: str
    owner: str
    risk: str = "normal"
    allowed: bool = True
    disabled_reason: str | None = None
    requires_confirmation: bool = False
    reason_required: bool = False
    method: str | None = None
    endpoint: str | None = None
    target: WorkbenchLinkedEntityResponse | None = None
    trace: TraceContextResponse | None = None

    @classmethod
    def from_value(cls, value: WorkbenchAction) -> "WorkbenchActionResponse":
        return cls(
            id=value.id,
            label=value.label,
            owner=value.owner,
            risk=value.risk,
            allowed=value.allowed,
            disabled_reason=value.disabled_reason,
            requires_confirmation=value.requires_confirmation,
            reason_required=value.reason_required,
            method=value.method,
            endpoint=value.endpoint,
            target=(
                WorkbenchLinkedEntityResponse.from_value(value.target)
                if value.target is not None
                else None
            ),
            trace=(
                TraceContextResponse.from_value(value.trace)
                if value.trace is not None
                else None
            ),
        )


class WorkbenchKeyValueItemResponse(BaseModel):
    label: str
    value: str
    tone: str = "neutral"
    route: str | None = None
    copy_value: str | None = None

    @classmethod
    def from_value(
        cls,
        value: WorkbenchKeyValueItem,
    ) -> "WorkbenchKeyValueItemResponse":
        return cls(
            label=value.label,
            value=value.value,
            tone=value.tone,
            route=value.route,
            copy_value=value.copy_value,
        )


class WorkbenchKeyValueSectionResponse(BaseModel):
    id: str
    title: str
    items: list[WorkbenchKeyValueItemResponse]
    actions: list[WorkbenchActionResponse] = Field(default_factory=list)

    @classmethod
    def from_value(
        cls,
        value: WorkbenchKeyValueSection,
    ) -> "WorkbenchKeyValueSectionResponse":
        return cls(
            id=value.id,
            title=value.title,
            items=[WorkbenchKeyValueItemResponse.from_value(item) for item in value.items],
            actions=[WorkbenchActionResponse.from_value(item) for item in value.actions],
        )


class WorkbenchInspectorResponse(BaseModel):
    tabs: list[str]
    active_tab: str
    overview: list[WorkbenchKeyValueSectionResponse]
    debug: list[WorkbenchKeyValueSectionResponse]
    memory: list[WorkbenchKeyValueSectionResponse]
    agent: list[WorkbenchKeyValueSectionResponse]
    current_turn_summary: str | None = None
    linked_assets: list[WorkbenchLinkedEntityResponse] = Field(default_factory=list)
    quick_actions: list[WorkbenchActionResponse] = Field(default_factory=list)

    @classmethod
    def from_value(
        cls,
        value: WorkbenchInspectorView,
    ) -> "WorkbenchInspectorResponse":
        return cls(
            tabs=list(value.tabs),
            active_tab=value.active_tab,
            overview=[
                WorkbenchKeyValueSectionResponse.from_value(item)
                for item in value.overview
            ],
            debug=[
                WorkbenchKeyValueSectionResponse.from_value(item)
                for item in value.debug
            ],
            memory=[
                WorkbenchKeyValueSectionResponse.from_value(item)
                for item in value.memory
            ],
            agent=[
                WorkbenchKeyValueSectionResponse.from_value(item)
                for item in value.agent
            ],
            current_turn_summary=value.current_turn_summary,
            linked_assets=[
                WorkbenchLinkedEntityResponse.from_value(item)
                for item in value.linked_assets
            ],
            quick_actions=[
                WorkbenchActionResponse.from_value(item)
                for item in value.quick_actions
            ],
        )


class UiConnectionStateResponse(BaseModel):
    status: str
    label: str
    updated_at: str | None
    details: str | None = None

    @classmethod
    def from_value(
        cls,
        value: WorkbenchConnectionState,
    ) -> "UiConnectionStateResponse":
        return cls(
            status=value.status,
            label=value.label,
            updated_at=value.updated_at,
            details=value.details,
        )


class WorkbenchFilterResponse(BaseModel):
    id: str
    label: str
    count: int

    @classmethod
    def from_value(
        cls,
        value: WorkbenchFilterSummary,
    ) -> "WorkbenchFilterResponse":
        return cls(id=value.id, label=value.label, count=value.count)


class WorkbenchThreadSummaryResponse(BaseModel):
    id: str
    run_id: str | None = None
    session_key: str
    title: str
    agent: str
    status: str
    current_activity: str
    updated_at: str
    starred: bool = False
    trace: TraceContextResponse | None = None

    @classmethod
    def from_value(
        cls,
        value: WorkbenchThreadSummary,
    ) -> "WorkbenchThreadSummaryResponse":
        return cls(
            id=value.id,
            run_id=value.run_id,
            session_key=value.session_key,
            title=value.title,
            agent=value.agent,
            status=value.status,
            current_activity=value.current_activity,
            updated_at=value.updated_at,
            starred=value.starred,
            trace=(
                TraceContextResponse.from_value(value.trace)
                if value.trace is not None
                else None
            ),
        )


class WorkbenchHomeResponse(BaseModel):
    connection: UiConnectionStateResponse
    filters: list[WorkbenchFilterResponse]
    threads: list[WorkbenchThreadSummaryResponse]
    active_thread_id: str | None
    active_run_id: str | None
    actions: list[dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def from_view(cls, view: WorkbenchHomeView) -> "WorkbenchHomeResponse":
        return cls(
            connection=UiConnectionStateResponse.from_value(view.connection),
            filters=[WorkbenchFilterResponse.from_value(item) for item in view.filters],
            threads=[
                WorkbenchThreadSummaryResponse.from_value(item)
                for item in view.threads
            ],
            active_thread_id=view.active_thread_id,
            active_run_id=view.active_run_id,
            actions=[dict(item) for item in view.actions],
        )


class WorkbenchRunResponse(BaseModel):
    run_id: str
    session_key: str
    title: str
    status: str
    agent: RuntimeRefResponse
    model: RuntimeRefResponse
    started_at: str | None
    completed_at: str | None
    duration_ms: int | None
    metrics: RunMetricsResponse
    turns: list[TurnSummaryResponse]
    current_turn_id: str | None
    status_strip: RunStatusStripResponse | None
    cover_artifact: ArtifactPreviewResponse | None = None
    timeline: list[WorkbenchTimelineItemResponse] = Field(default_factory=list)
    actions: list[WorkbenchActionResponse] = Field(default_factory=list)
    inspector: WorkbenchInspectorResponse
    trace: TraceContextResponse

    @classmethod
    def from_view(cls, view: WorkbenchRunView) -> "WorkbenchRunResponse":
        return cls(
            run_id=view.run_id,
            session_key=view.session_key,
            title=view.title,
            status=view.status,
            agent=RuntimeRefResponse.from_value(view.agent),
            model=RuntimeRefResponse.from_value(view.model),
            started_at=view.started_at,
            completed_at=view.completed_at,
            duration_ms=view.duration_ms,
            metrics=RunMetricsResponse.from_value(view.metrics),
            turns=[TurnSummaryResponse.from_value(item) for item in view.turns],
            current_turn_id=view.current_turn_id,
            status_strip=(
                RunStatusStripResponse.from_value(view.status_strip)
                if view.status_strip is not None
                else None
            ),
            cover_artifact=(
                ArtifactPreviewResponse.from_value(view.cover_artifact)
                if view.cover_artifact is not None
                else None
            ),
            timeline=[
                WorkbenchTimelineItemResponse.from_value(item)
                for item in view.timeline
            ],
            actions=[WorkbenchActionResponse.from_value(item) for item in view.actions],
            inspector=WorkbenchInspectorResponse.from_value(view.inspector),
            trace=TraceContextResponse.from_value(view.trace),
        )


class WorkbenchTimelineItemResponse(BaseModel):
    id: str
    turn_id: str
    run_id: str
    kind: str
    status: str
    title: str
    content: dict[str, Any] = Field(default_factory=dict)
    phase: str | None = None
    source_refs: dict[str, str] = Field(default_factory=dict)
    started_at: str | None = None
    completed_at: str | None = None
    trace: TraceContextResponse

    @classmethod
    def from_value(
        cls,
        value: WorkbenchTimelineItem,
    ) -> "WorkbenchTimelineItemResponse":
        return cls(
            id=value.id,
            turn_id=value.turn_id,
            run_id=value.run_id,
            kind=value.kind,
            status=value.status,
            title=value.title,
            content=dict(value.content),
            phase=value.phase,
            source_refs=dict(value.source_refs),
            started_at=value.started_at,
            completed_at=value.completed_at,
            trace=TraceContextResponse.from_value(value.trace),
        )


class ApprovalRequestDetailResponse(BaseModel):
    request_id: str
    effect_id: str
    label: str
    reason: str
    tool_name: str | None = None
    tool_ids: list[str] = Field(default_factory=list)
    tool_arguments: dict[str, Any] = Field(default_factory=dict)
    execution_mode: str | None = None
    execution_strategy: str | None = None
    execution_environment: str | None = None
    draft_id: str | None = None

    @classmethod
    def from_value(
        cls,
        value: ApprovalRequestDetail,
    ) -> "ApprovalRequestDetailResponse":
        return cls(
            request_id=value.request_id,
            effect_id=value.effect_id,
            label=value.label,
            reason=value.reason,
            tool_name=value.tool_name,
            tool_ids=list(value.tool_ids),
            tool_arguments=dict(value.tool_arguments),
            execution_mode=value.execution_mode,
            execution_strategy=value.execution_strategy,
            execution_environment=value.execution_environment,
            draft_id=value.draft_id,
        )


class TurnStepResponse(BaseModel):
    step_id: str
    turn_id: str
    run_id: str
    type: str
    status: str
    title: str
    summary: str
    markdown: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    artifacts: list[ArtifactPreviewResponse] = Field(default_factory=list)
    badges: list[StatusBadgeResponse] = Field(default_factory=list)
    linked_entities: list[WorkbenchLinkedEntityResponse] = Field(default_factory=list)
    actions: list[WorkbenchActionResponse] = Field(default_factory=list)
    approval: ApprovalRequestDetailResponse | None = None
    details_available: bool
    trace: TraceContextResponse

    @classmethod
    def from_view(cls, view: TurnStepView) -> "TurnStepResponse":
        return cls(
            step_id=view.step_id,
            turn_id=view.turn_id,
            run_id=view.run_id,
            type=view.type,
            status=view.status,
            title=view.title,
            summary=view.summary,
            markdown=view.markdown,
            started_at=view.started_at,
            completed_at=view.completed_at,
            duration_ms=view.duration_ms,
            artifacts=[ArtifactPreviewResponse.from_value(item) for item in view.artifacts],
            badges=[StatusBadgeResponse.from_value(item) for item in view.badges],
            linked_entities=[
                WorkbenchLinkedEntityResponse.from_value(item)
                for item in view.linked_entities
            ],
            actions=[WorkbenchActionResponse.from_value(item) for item in view.actions],
            approval=(
                ApprovalRequestDetailResponse.from_value(view.approval)
                if view.approval is not None
                else None
            ),
            details_available=view.details_available,
            trace=TraceContextResponse.from_value(view.trace),
        )


class TraceLinkedEntityResponse(BaseModel):
    type: str
    id: str


class TraceSummaryResponse(BaseModel):
    trace_id: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    event_count: int
    key_event_count: int
    owners: list[str] = Field(default_factory=list)
    linked_entities: list[TraceLinkedEntityResponse] = Field(default_factory=list)

    @classmethod
    def from_view(cls, view: TraceSummaryView) -> "TraceSummaryResponse":
        return cls(
            trace_id=view.trace_id,
            status=view.status,
            started_at=view.started_at,
            completed_at=view.completed_at,
            duration_ms=view.duration_ms,
            event_count=view.event_count,
            key_event_count=view.key_event_count,
            owners=list(view.owners),
            linked_entities=[
                TraceLinkedEntityResponse(type=item.type, id=item.id)
                for item in view.linked_entities
            ],
        )


class TraceEventResponse(BaseModel):
    event_id: str
    name: str
    family: str
    owner: str
    status: str
    timestamp: str
    relative_ms: int
    summary: str
    key_event: bool
    linked_entities: list[TraceLinkedEntityResponse] = Field(default_factory=list)
    trace: TraceContextResponse
    topic: str
    cursor: str
    payload: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_view(cls, view: TraceEventView) -> "TraceEventResponse":
        return cls(
            event_id=view.event_id,
            name=view.name,
            family=view.family,
            owner=view.owner,
            status=view.status,
            timestamp=view.timestamp,
            relative_ms=view.relative_ms,
            summary=view.summary,
            key_event=view.key_event,
            linked_entities=[
                TraceLinkedEntityResponse(type=item.type, id=item.id)
                for item in view.linked_entities
            ],
            trace=TraceContextResponse.from_value(view.trace),
            topic=view.topic,
            cursor=view.cursor,
            payload=dict(view.payload),
        )
