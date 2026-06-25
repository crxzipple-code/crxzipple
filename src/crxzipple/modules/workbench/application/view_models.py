from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.workbench.application.projection_diagnostics import (
    WorkbenchOwnerFactSource,
)
from crxzipple.shared.runtime_console import TraceContext


@dataclass(frozen=True, slots=True)
class RuntimeRef:
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class RunMetrics:
    tool_calls: int
    llm_calls: int
    tokens: int
    estimated_cost_usd: float | None


@dataclass(frozen=True, slots=True)
class WorkbenchProjectionDiagnostics:
    owner_sources: tuple[WorkbenchOwnerFactSource, ...]
    owner_call_sources: tuple[str, ...]
    owner_call_count: int
    processed_item_count: int
    timeline_item_count: int
    elapsed_ms: float


@dataclass(frozen=True, slots=True)
class TurnSummary:
    turn_id: str
    ordinal: int
    status: str
    duration_ms: int | None


@dataclass(frozen=True, slots=True)
class RunStatusStrip:
    label: str
    eta_ms: int | None
    queue_wait_ms: int


@dataclass(frozen=True, slots=True)
class ArtifactPreview:
    artifact_id: str
    name: str
    kind: str
    size_bytes: int | None = None
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    preview_url: str | None = None
    download_url: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StatusBadgeModel:
    label: str
    tone: str = "neutral"


@dataclass(frozen=True, slots=True)
class WorkbenchLinkedEntity:
    type: str
    id: str
    label: str | None = None
    owner: str | None = None
    route: str | None = None
    copy_value: str | None = None
    trace: TraceContext | None = None


@dataclass(frozen=True, slots=True)
class ApprovalRequestDetail:
    request_id: str
    effect_id: str
    label: str
    reason: str
    tool_name: str | None
    tool_ids: tuple[str, ...]
    tool_arguments: dict[str, object]
    execution_mode: str | None = None
    execution_strategy: str | None = None
    execution_environment: str | None = None
    draft_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorkbenchAction:
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
    target: WorkbenchLinkedEntity | None = None
    trace: TraceContext | None = None


@dataclass(frozen=True, slots=True)
class WorkbenchKeyValueItem:
    label: str
    value: str
    tone: str = "neutral"
    route: str | None = None
    copy_value: str | None = None


@dataclass(frozen=True, slots=True)
class WorkbenchKeyValueSection:
    id: str
    title: str
    items: tuple[WorkbenchKeyValueItem, ...]
    actions: tuple[WorkbenchAction, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkbenchInspectorView:
    tabs: tuple[str, ...]
    active_tab: str
    overview: tuple[WorkbenchKeyValueSection, ...]
    debug: tuple[WorkbenchKeyValueSection, ...]
    memory: tuple[WorkbenchKeyValueSection, ...]
    agent: tuple[WorkbenchKeyValueSection, ...]
    current_turn_summary: str | None
    linked_assets: tuple[WorkbenchLinkedEntity, ...]
    quick_actions: tuple[WorkbenchAction, ...]


@dataclass(frozen=True, slots=True)
class WorkbenchConnectionState:
    status: str
    label: str
    updated_at: str | None
    details: str | None = None


@dataclass(frozen=True, slots=True)
class WorkbenchFilterSummary:
    id: str
    label: str
    count: int


@dataclass(frozen=True, slots=True)
class WorkbenchThreadSummary:
    id: str
    session_key: str
    run_id: str | None
    title: str
    agent: str
    status: str
    current_activity: str
    updated_at: str
    starred: bool = False
    trace: TraceContext | None = None


@dataclass(frozen=True, slots=True)
class WorkbenchHomeView:
    connection: WorkbenchConnectionState
    filters: tuple[WorkbenchFilterSummary, ...]
    threads: tuple[WorkbenchThreadSummary, ...]
    active_thread_id: str | None
    active_run_id: str | None
    actions: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class WorkbenchRunView:
    run_id: str
    session_key: str
    title: str
    status: str
    agent: RuntimeRef
    model: RuntimeRef
    started_at: str | None
    completed_at: str | None
    duration_ms: int | None
    metrics: RunMetrics
    turns: tuple[TurnSummary, ...]
    current_turn_id: str | None
    status_strip: RunStatusStrip | None
    cover_artifact: ArtifactPreview | None
    timeline: tuple[WorkbenchTimelineItem, ...]
    actions: tuple[WorkbenchAction, ...]
    inspector: WorkbenchInspectorView
    trace: TraceContext
    projection_diagnostics: WorkbenchProjectionDiagnostics


@dataclass(frozen=True, slots=True)
class WorkbenchTimelineItem:
    id: str
    turn_id: str
    run_id: str
    kind: str
    status: str
    title: str
    content: dict[str, Any]
    phase: str | None
    source_refs: dict[str, str]
    started_at: str | None
    completed_at: str | None
    trace: TraceContext


@dataclass(frozen=True, slots=True)
class TurnStepView:
    step_id: str
    turn_id: str
    run_id: str
    type: str
    status: str
    title: str
    summary: str
    markdown: str | None
    started_at: str | None
    completed_at: str | None
    duration_ms: int | None
    artifacts: tuple[ArtifactPreview, ...]
    badges: tuple[StatusBadgeModel, ...]
    linked_entities: tuple[WorkbenchLinkedEntity, ...]
    actions: tuple[WorkbenchAction, ...]
    approval: ApprovalRequestDetail | None
    details_available: bool
    trace: TraceContext
