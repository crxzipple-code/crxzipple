from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from typing import Any, Protocol

from crxzipple.modules.orchestration.application.ports import OrchestrationRunQueryPort
from crxzipple.modules.orchestration.domain import (
    ExecutionStep,
    ExecutionStepItem,
    OrchestrationRun,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionStepItemKind,
    ExecutionStepItemStatus,
    ExecutionStepKind,
    ExecutionStepStatus,
    OrchestrationRunStage,
    OrchestrationRunStatus,
)
from crxzipple.modules.tool.domain import ToolRun
from crxzipple.modules.tool.domain.value_objects import ToolRunStatus
from crxzipple.shared.content_blocks import (
    content_blocks_from_payload,
    describe_content_for_text_fallback,
    extract_text_content,
)
from crxzipple.shared.runtime_console import TraceContext
from crxzipple.shared.time import (
    coerce_utc_datetime,
    format_optional_datetime_utc,
)


class WorkbenchToolRunQueryPort(Protocol):
    def list_tool_runs(self, *, tool_id: str | None = None) -> list[ToolRun]:
        ...


class WorkbenchArtifactQueryPort(Protocol):
    def get_artifact(self, artifact_id: str) -> Any:
        ...


class WorkbenchLlmQueryPort(Protocol):
    def get_profile(self, llm_id: str) -> Any:
        ...

    def get_invocation(self, invocation_id: str) -> Any:
        ...

    def list_invocations(self, *, llm_id: str | None = None) -> list[Any]:
        ...


class WorkbenchAgentQueryPort(Protocol):
    def get_profile(self, profile_id: str) -> Any:
        ...


class WorkbenchSessionQueryPort(Protocol):
    def get_item(self, item_id: str) -> Any:
        ...


@dataclass(frozen=True, slots=True)
class _DisplayToolRun:
    source_run: OrchestrationRun
    tool_run: ToolRun


@dataclass(frozen=True, slots=True)
class _ExecutionStepBundle:
    step: ExecutionStep
    items: tuple[ExecutionStepItem, ...]


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


@dataclass(slots=True)
class WorkbenchReadModelProvider:
    run_query: OrchestrationRunQueryPort
    tool_query: WorkbenchToolRunQueryPort | None = None
    artifact_query: WorkbenchArtifactQueryPort | None = None
    llm_query: WorkbenchLlmQueryPort | None = None
    agent_query: WorkbenchAgentQueryPort | None = None
    session_query: WorkbenchSessionQueryPort | None = None

    def get_home_view(
        self,
        *,
        run_id: str | None = None,
        session_key: str | None = None,
    ) -> WorkbenchHomeView:
        latest_runs = _latest_runs_by_session(self.run_query.list_runs())
        threads = tuple(
            _thread_summary(run)
            for run in sorted(
                latest_runs.values(),
                key=lambda item: item.updated_at,
                reverse=True,
            )
        )
        active_run_id = _active_run_id(
            threads,
            requested_run_id=run_id,
            requested_session_key=session_key,
        )
        fallback_thread_id = (
            None
            if run_id is not None or session_key is not None
            else threads[0].id if threads else None
        )
        active_thread_id = next(
            (
                thread.id
                for thread in threads
                if thread.run_id == active_run_id
                or (
                    session_key is not None
                    and thread.session_key == session_key.strip()
                )
            ),
            fallback_thread_id,
        )
        latest_updated_at = threads[0].updated_at if threads else None
        return WorkbenchHomeView(
            connection=WorkbenchConnectionState(
                status="connected",
                label="Connected",
                updated_at=latest_updated_at,
                details="Workbench read model is using orchestration state.",
            ),
            filters=_thread_filters(threads),
            threads=threads,
            active_thread_id=active_thread_id,
            active_run_id=active_run_id,
            actions=(
                {
                    "id": "new_task",
                    "label": "New task",
                    "owner": "orchestration",
                    "risk": "normal",
                    "allowed": True,
                    "requires_confirmation": False,
                    "reason_required": False,
                    "method": "POST",
                    "endpoint": "/turns",
                },
            ),
        )

    def get_run_view(self, run_id: str) -> WorkbenchRunView:
        run = self.run_query.get_run(run_id)
        candidate_runs = _safe_list_runs(self.run_query)
        tool_runs = _safe_list_tool_runs(self.tool_query)
        session_runs = _session_runs_for_run(
            self.run_query,
            run,
            candidate_runs=candidate_runs,
        )
        turn_id = _turn_id(run)
        session_display_tool_runs = tuple(
            display_tool_run
            for session_run in session_runs
            for display_tool_run in _display_tool_runs(
                self.run_query,
                self.tool_query,
                session_run,
                candidate_runs=candidate_runs,
                tool_runs=tool_runs,
            )
        )
        llm_invocations = _llm_invocations_for_runs(
            self.run_query,
            self.llm_query,
            session_runs,
        )
        trace = _trace_for_run(run, turn_id=turn_id)
        agent_ref = _agent_ref(run, self.agent_query)
        model_ref = _llm_ref(run, self.llm_query, run_query=self.run_query)
        cover_artifact = _cover_artifact(
            tuple(
                display_tool_run.tool_run
                for display_tool_run in session_display_tool_runs
            ),
            artifact_query=self.artifact_query,
        )
        actions = _run_actions(run, trace=trace)
        timeline_steps: list[TurnStepView] = []
        for session_run in session_runs:
            timeline_steps.extend(
                self._list_step_views_for_run(
                    session_run,
                    candidate_runs=candidate_runs,
                    tool_runs=tool_runs,
                ),
            )
        timeline = _timeline_items_from_steps(
            tuple(timeline_steps),
            llm_invocations_by_id={
                invocation_id: invocation
                for invocation in llm_invocations
                if (invocation_id := _optional_text(getattr(invocation, "id", None)))
                is not None
            },
        )
        timeline = _timeline_items_with_tool_lifecycle(
            timeline,
            run_query=self.run_query,
            runs=session_runs,
        )
        timeline = _timeline_items_with_evidence_frontier(
            timeline,
            runs=session_runs,
            turn_id=turn_id,
            trace=trace,
        )
        metrics = _metrics_for_runs(
            session_runs,
            related_tool_runs=tuple(
                display_tool_run.tool_run
                for display_tool_run in session_display_tool_runs
            ),
            llm_invocations=llm_invocations,
            timeline=timeline,
        )
        inspector = _inspector_for_run(
            run,
            session_runs=session_runs,
            display_tool_runs=session_display_tool_runs,
            llm_invocations=llm_invocations,
            metrics=metrics,
            cover_artifact=cover_artifact,
            agent_ref=agent_ref,
            model_ref=model_ref,
            trace=trace,
            agent_query=self.agent_query,
            timeline=timeline,
        )
        return WorkbenchRunView(
            run_id=run.id,
            session_key=run.session_key or "",
            title=_run_title(run),
            status=run.status.value,
            agent=agent_ref,
            model=model_ref,
            started_at=format_optional_datetime_utc(run.started_at),
            completed_at=format_optional_datetime_utc(run.completed_at),
            duration_ms=_duration_ms(run),
            metrics=metrics,
            turns=_turn_summaries(session_runs),
            current_turn_id=turn_id,
            status_strip=_status_strip(run),
            cover_artifact=cover_artifact,
            timeline=timeline,
            actions=actions,
            inspector=inspector,
            trace=trace,
        )

    def list_step_views(self, run_id: str) -> tuple[TurnStepView, ...]:
        run = self.run_query.get_run(run_id)
        candidate_runs = _safe_list_runs(self.run_query)
        tool_runs = _safe_list_tool_runs(self.tool_query)
        steps: list[TurnStepView] = []
        for session_run in _session_runs_for_run(
            self.run_query,
            run,
            candidate_runs=candidate_runs,
        ):
            steps.extend(
                self._list_step_views_for_run(
                    session_run,
                    candidate_runs=candidate_runs,
                    tool_runs=tool_runs,
                ),
            )
        return tuple(steps)

    def _list_step_views_for_run(
        self,
        run: OrchestrationRun,
        *,
        candidate_runs: list[OrchestrationRun] | None = None,
        tool_runs: list[ToolRun] | None = None,
    ) -> tuple[TurnStepView, ...]:
        turn_id = _turn_id(run)
        display_tool_runs = _display_tool_runs(
            self.run_query,
            self.tool_query,
            run,
            candidate_runs=candidate_runs,
            tool_runs=tool_runs,
        )
        direct_tool_runs = tuple(
            display_tool_run.tool_run
            for display_tool_run in display_tool_runs
            if display_tool_run.source_run.id == run.id
        )
        chain_steps = _chain_step_views_for_run(
            self.run_query,
            self.llm_query,
            self.artifact_query,
            self.session_query,
            run,
            turn_id=turn_id,
            display_tool_runs=display_tool_runs,
        )
        if chain_steps:
            return chain_steps

        pending_tool_run_ids = set(run.pending_tool_run_ids)
        llm_invocation = _llm_invocation_for_run(
            self.run_query,
            self.llm_query,
            run,
        )
        steps: list[TurnStepView] = [
            _step(
                run=run,
                turn_id=turn_id,
                step_id="user_input",
                step_type="user_input",
                status="success",
                title="User Input",
                summary=_instruction_summary(run),
                started_at=run.created_at,
                completed_at=run.created_at,
            ),
        ]

        if run.status is OrchestrationRunStatus.QUEUED:
            steps.append(
                _step(
                    run=run,
                    turn_id=turn_id,
                    step_id="queued",
                    step_type="agent_thinking",
                    status="queued",
                    title="Queued",
                    summary=run.waiting_reason or "Run is waiting for scheduler admission.",
                    started_at=run.queued_at or run.created_at,
                    completed_at=None,
                ),
            )

        if run.started_at is not None or run.current_step > 0:
            steps.append(
                _step(
                    run=run,
                    turn_id=turn_id,
                    step_id=f"llm_{max(run.current_step, 1)}",
                    step_type="llm",
                    status=_llm_step_status(run),
                    title="LLM Thinking",
                    summary=_llm_summary(run, llm_invocation=llm_invocation),
                    started_at=_llm_started_at(run, llm_invocation),
                    completed_at=(
                        _llm_completed_at(run, llm_invocation)
                        if run.stage
                        not in {
                            OrchestrationRunStage.LLM,
                            OrchestrationRunStage.RUNNING,
                        }
                        else None
                    ),
                    badges=(
                        StatusBadgeModel(
                            label=(
                                _llm_invocation_llm_id(llm_invocation)
                                or _llm_id(run)
                                or "Auto"
                            ),
                            tone="info",
                        ),
                    ),
                    llm_invocation_id=_optional_text(
                        getattr(llm_invocation, "id", None),
                    ),
                ),
            )

        if run.pending_tool_run_ids:
            pending_tool_run = direct_tool_runs[0] if direct_tool_runs else None
            steps.append(
                _step(
                    run=run,
                    turn_id=turn_id,
                    step_id="tool_wait",
                    step_type="tool_call",
                    status="waiting" if run.status is OrchestrationRunStatus.WAITING else "running",
                    title="Tool Execution",
                    summary=(
                        _tool_call_summary(pending_tool_run)
                        if pending_tool_run is not None
                        else run.waiting_reason or "Waiting for pending tool runs to finish."
                    ),
                    started_at=run.updated_at,
                    completed_at=None,
                    badges=(
                        StatusBadgeModel(
                            label=pending_tool_run.tool_id if pending_tool_run is not None else "Tool Call",
                            tone="info",
                        ),
                    ),
                    tool_run_id=run.pending_tool_run_ids[0],
                ),
            )

        for display_tool_run in display_tool_runs:
            source_run = display_tool_run.source_run
            tool_run = display_tool_run.tool_run
            if source_run.id == run.id and tool_run.id in pending_tool_run_ids:
                continue
            tool_status = _tool_status(tool_run)
            artifacts = (
                _tool_artifacts(tool_run, artifact_query=self.artifact_query)
                if tool_run.status in _TERMINAL_TOOL_RUN_STATUSES
                else ()
            )
            steps.append(
                _step(
                    run=source_run,
                    turn_id=turn_id,
                    step_id=f"tool_{tool_run.id}",
                    step_type=(
                        "error"
                        if tool_run.status in _FAILED_TOOL_RUN_STATUSES
                        else "tool_call"
                    ),
                    status=tool_status,
                    title=(
                        "Tool Failed"
                        if tool_run.status in _FAILED_TOOL_RUN_STATUSES
                        else "Tool Call"
                    ),
                    summary=_tool_step_summary(tool_run),
                    started_at=tool_run.created_at,
                    completed_at=(
                        tool_run.completed_at
                        if tool_run.status in _TERMINAL_TOOL_RUN_STATUSES
                        else None
                    ),
                    artifacts=artifacts,
                    badges=(StatusBadgeModel(label=tool_run.tool_id, tone=_tool_badge_tone(tool_run)),),
                    tool_run_id=tool_run.id,
                    artifact_id=artifacts[0].artifact_id if artifacts else None,
                ),
            )

        access_payload = _missing_access_payload(run)
        if access_payload is not None:
            steps.append(
                _step(
                    run=run,
                    turn_id=turn_id,
                    step_id="missing_access",
                    step_type="missing_access",
                    status=(
                        "waiting"
                        if run.status is OrchestrationRunStatus.WAITING
                        else "failed"
                    ),
                    title="External Access Required",
                    summary=_missing_access_summary(access_payload),
                    started_at=run.completed_at or run.updated_at,
                    completed_at=run.completed_at,
                    badges=(StatusBadgeModel(label="Access", tone="warning"),),
                    linked_entities=_missing_access_entities(access_payload),
                ),
            )

        approval = _pending_approval(run)
        if approval is not None:
            request_id = str(approval.get("request_id") or approval.get("id") or "")
            approval_detail = _approval_detail(approval)
            steps.append(
                _step(
                    run=run,
                    turn_id=turn_id,
                    step_id=f"approval_{request_id or 'pending'}",
                    step_type="approval_required",
                    status="waiting",
                    title="Approval Required",
                    summary=_approval_summary(approval),
                    started_at=run.updated_at,
                    completed_at=None,
                    badges=(StatusBadgeModel(label="Authorization", tone="warning"),),
                    linked_entities=_approval_entities(approval_detail),
                    approval=approval_detail,
                    approval_request_id=request_id or None,
                ),
            )

        if run.status is OrchestrationRunStatus.COMPLETED:
            output_text = _output_text(run)
            steps.append(
                _step(
                    run=run,
                    turn_id=turn_id,
                    step_id="final_response",
                    step_type="final_response",
                    status="success",
                    title="Final Response",
                    summary=output_text or "Run completed.",
                    markdown=output_text,
                    started_at=run.completed_at or run.updated_at,
                    completed_at=run.completed_at or run.updated_at,
                ),
            )
        elif run.status is OrchestrationRunStatus.FAILED and access_payload is None:
            steps.append(
                _step(
                    run=run,
                    turn_id=turn_id,
                    step_id="error",
                    step_type="error",
                    status="failed",
                    title="Run Failed",
                    summary=run.error.message if run.error is not None else "Run failed.",
                    started_at=run.completed_at or run.updated_at,
                    completed_at=run.completed_at or run.updated_at,
                    badges=(
                        StatusBadgeModel(
                            label=run.error.code if run.error is not None else "error",
                            tone="danger",
                        ),
                    ),
                ),
            )

        return tuple(steps)


def _session_runs_for_run(
    run_query: OrchestrationRunQueryPort,
    run: OrchestrationRun,
    *,
    candidate_runs: list[OrchestrationRun] | None = None,
) -> tuple[OrchestrationRun, ...]:
    session_key = _optional_text(run.session_key)
    if session_key is None:
        return (run,)
    runs = candidate_runs
    if runs is None:
        try:
            runs = run_query.list_runs()
        except Exception:
            return (run,)
    session_runs = [
        item
        for item in runs
        if _optional_text(item.session_key) == session_key
    ]
    if not any(item.id == run.id for item in session_runs):
        session_runs.append(run)
    return tuple(
        sorted(
            session_runs,
            key=lambda item: (item.created_at, item.id),
        ),
    )


def _turn_summaries(runs: tuple[OrchestrationRun, ...]) -> tuple[TurnSummary, ...]:
    return tuple(
        TurnSummary(
            turn_id=_turn_id(run),
            ordinal=index,
            status=run.status.value,
            duration_ms=_duration_ms(run),
        )
        for index, run in enumerate(runs, start=1)
    )


def _safe_list_runs(run_query: OrchestrationRunQueryPort) -> list[OrchestrationRun] | None:
    try:
        return run_query.list_runs()
    except Exception:
        return None


def _safe_list_tool_runs(
    tool_query: WorkbenchToolRunQueryPort | None,
) -> list[ToolRun] | None:
    if tool_query is None:
        return []
    try:
        return tool_query.list_tool_runs()
    except Exception:
        return None


def _latest_runs_by_session(
    runs: list[OrchestrationRun],
) -> dict[str, OrchestrationRun]:
    latest: dict[str, OrchestrationRun] = {}
    for run in sorted(runs, key=lambda item: item.updated_at, reverse=True):
        session_key = _optional_text(run.session_key)
        if session_key is None or session_key in latest:
            continue
        latest[session_key] = run
    return latest


def _thread_summary(run: OrchestrationRun) -> WorkbenchThreadSummary:
    session_key = _optional_text(run.session_key) or run.id
    turn_id = _turn_id(run)
    return WorkbenchThreadSummary(
        id=session_key,
        session_key=session_key,
        run_id=run.id,
        title=_run_title(run),
        agent=run.agent_id or "Unknown Agent",
        status=run.status.value,
        current_activity=_thread_activity(run),
        updated_at=format_optional_datetime_utc(run.updated_at) or "",
        starred=bool(run.metadata.get("starred")),
        trace=_trace_for_run(run, turn_id=turn_id),
    )


def _active_run_id(
    threads: tuple[WorkbenchThreadSummary, ...],
    *,
    requested_run_id: str | None,
    requested_session_key: str | None,
) -> str | None:
    normalized_run_id = _optional_text(requested_run_id)
    if normalized_run_id is not None:
        if any(thread.run_id == normalized_run_id for thread in threads):
            return normalized_run_id
        return normalized_run_id
    normalized_session_key = _optional_text(requested_session_key)
    if normalized_session_key is not None:
        for thread in threads:
            if thread.session_key == normalized_session_key:
                return thread.run_id
    return threads[0].run_id if threads else None


def _thread_filters(
    threads: tuple[WorkbenchThreadSummary, ...],
) -> tuple[WorkbenchFilterSummary, ...]:
    running_statuses = {"accepted", "queued", "running", "waiting"}
    completed_statuses = {"completed", "success"}
    failed_statuses = {"failed", "cancelled"}
    return (
        WorkbenchFilterSummary(id="all", label="All", count=len(threads)),
        WorkbenchFilterSummary(
            id="running",
            label="Running",
            count=sum(1 for thread in threads if thread.status in running_statuses),
        ),
        WorkbenchFilterSummary(
            id="completed",
            label="Completed",
            count=sum(1 for thread in threads if thread.status in completed_statuses),
        ),
        WorkbenchFilterSummary(
            id="failed",
            label="Failed",
            count=sum(1 for thread in threads if thread.status in failed_statuses),
        ),
    )


def _thread_activity(run: OrchestrationRun) -> str:
    if run.status is OrchestrationRunStatus.WAITING:
        return _truncate(run.waiting_reason or "Waiting", limit=120)
    if run.status is OrchestrationRunStatus.QUEUED:
        return _truncate(run.waiting_reason or "Queued for execution", limit=120)
    if run.status is OrchestrationRunStatus.RUNNING:
        return f"Running: {run.stage.value}"
    if run.status is OrchestrationRunStatus.ACCEPTED:
        return "Accepted"
    if run.status is OrchestrationRunStatus.COMPLETED:
        return _truncate(_output_text(run) or "Completed", limit=120)
    if run.status is OrchestrationRunStatus.FAILED:
        if run.error is not None and run.error.message:
            return _truncate(run.error.message, limit=120)
        return "Failed"
    if run.status is OrchestrationRunStatus.CANCELLED:
        return "Cancelled"
    return run.status.value


def _trace_for_run(
    run: OrchestrationRun,
    *,
    turn_id: str,
    step_id: str | None = None,
    tool_run_id: str | None = None,
    llm_invocation_id: str | None = None,
    context_render_snapshot_id: str | None = None,
    session_item_id: str | None = None,
    artifact_id: str | None = None,
    approval_request_id: str | None = None,
    source_owner: str | None = None,
    source_event_id: str | None = None,
    source_event_name: str | None = None,
) -> TraceContext:
    trace_id = _metadata_str(run, "trace_id") or run.id
    return TraceContext(
        trace_id=trace_id,
        correlation_id=_metadata_str(run, "correlation_id"),
        session_key=run.session_key,
        session_id=run.active_session_id,
        turn_id=turn_id,
        run_id=run.id,
        step_id=step_id,
        tool_run_id=tool_run_id,
        llm_invocation_id=llm_invocation_id,
        context_render_snapshot_id=context_render_snapshot_id,
        session_item_id=session_item_id,
        artifact_id=artifact_id,
        approval_request_id=approval_request_id,
        source_owner=source_owner,
        source_event_id=source_event_id,
        source_event_name=source_event_name,
    )


def _step(
    *,
    run: OrchestrationRun,
    turn_id: str,
    step_id: str,
    step_type: str,
    status: str,
    title: str,
    summary: str,
    started_at: datetime | None,
    completed_at: datetime | None,
    markdown: str | None = None,
    artifacts: tuple[ArtifactPreview, ...] = (),
    badges: tuple[StatusBadgeModel, ...] = (),
    linked_entities: tuple[WorkbenchLinkedEntity, ...] = (),
    actions: tuple[WorkbenchAction, ...] = (),
    approval: ApprovalRequestDetail | None = None,
    tool_run_id: str | None = None,
    llm_invocation_id: str | None = None,
    context_render_snapshot_id: str | None = None,
    session_item_id: str | None = None,
    artifact_id: str | None = None,
    approval_request_id: str | None = None,
    trace_step_id: str | None = None,
    source_owner: str | None = None,
    source_event_id: str | None = None,
    source_event_name: str | None = None,
) -> TurnStepView:
    stable_step_id = f"{run.id}:{step_id}"
    trace = _trace_for_run(
        run,
        turn_id=turn_id,
        step_id=trace_step_id or stable_step_id,
        tool_run_id=tool_run_id,
        llm_invocation_id=llm_invocation_id,
        context_render_snapshot_id=context_render_snapshot_id,
        session_item_id=session_item_id,
        artifact_id=artifact_id,
        approval_request_id=approval_request_id,
        source_owner=source_owner,
        source_event_id=source_event_id,
        source_event_name=source_event_name,
    )
    resolved_linked_entities = _dedupe_linked_entities(
        (
            *_linked_entities_for_trace(trace, artifacts=artifacts),
            *linked_entities,
        ),
    )
    resolved_actions = actions or _step_actions(
        run,
        trace=trace,
        step_type=step_type,
        status=status,
        artifacts=artifacts,
    )
    return TurnStepView(
        step_id=stable_step_id,
        turn_id=turn_id,
        run_id=run.id,
        type=step_type,
        status=status,
        title=title,
        summary=summary,
        markdown=markdown,
        started_at=format_optional_datetime_utc(started_at),
        completed_at=format_optional_datetime_utc(completed_at),
        duration_ms=_span_ms(started_at, completed_at),
        artifacts=artifacts,
        badges=badges,
        linked_entities=resolved_linked_entities,
        actions=resolved_actions,
        approval=approval,
        details_available=True,
        trace=trace,
    )


def _timeline_items_from_steps(
    steps: tuple[TurnStepView, ...],
    *,
    llm_invocations_by_id: dict[str, Any] | None = None,
) -> tuple[WorkbenchTimelineItem, ...]:
    invocations_by_id = llm_invocations_by_id or {}
    items: list[WorkbenchTimelineItem] = []
    for index, step in enumerate(steps):
        llm_invocation_id = step.trace.llm_invocation_id
        invocation = (
            invocations_by_id.get(llm_invocation_id)
            if llm_invocation_id is not None
            else None
        )
        if step.type == "llm" and invocation is not None:
            response_items = tuple(getattr(invocation, "response_items", ()) or ())
            if response_items:
                items.extend(
                    _timeline_items_from_llm_response_items(
                        step,
                        response_items=response_items,
                        base_index=index,
                    ),
                )
                continue
        if not _step_should_be_visible_in_timeline(step):
            continue
        items.append(_timeline_item_from_step(step, index=index))
    return _deduplicate_timeline_items(tuple(items))


def _step_should_be_visible_in_timeline(step: TurnStepView) -> bool:
    if step.type != "continuation_decision":
        return True
    return _continuation_decision_is_actionable(step)


def _continuation_decision_is_actionable(step: TurnStepView) -> bool:
    if step.status not in {"success", "completed"}:
        return True
    summary = (step.summary or "").strip().lower()
    if not summary:
        return False
    parts = [part.strip() for part in summary.split(";")]
    reason = parts[0] if parts else ""
    has_follow_up = "follow_up=true" in summary
    continues_turn = "end_turn=false" in summary
    if has_follow_up or continues_turn:
        return True
    return reason not in {"none", "unknown", ""}


def _deduplicate_timeline_items(
    items: tuple[WorkbenchTimelineItem, ...],
) -> tuple[WorkbenchTimelineItem, ...]:
    response_final_turns = {
        item.turn_id
        for item in items
        if item.kind == "final_answer"
        and item.source_refs.get("llm_response_item_id")
    }
    if not response_final_turns:
        return items
    return tuple(
        item
        for item in items
        if not (
            item.kind == "final_answer"
            and item.turn_id in response_final_turns
            and not item.source_refs.get("llm_response_item_id")
        )
    )


def _timeline_items_with_tool_lifecycle(
    timeline: tuple[WorkbenchTimelineItem, ...],
    *,
    run_query: OrchestrationRunQueryPort,
    runs: tuple[OrchestrationRun, ...],
) -> tuple[WorkbenchTimelineItem, ...]:
    lifecycle_items: list[WorkbenchTimelineItem] = []
    replaced_tool_run_item_ids: set[str] = set()
    replaced_tool_run_ids: set[str] = set()
    for run in runs:
        turn_id = _turn_id(run)
        for bundle in _execution_step_bundles(run_query, run.id):
            if bundle.step.kind is not ExecutionStepKind.TOOL_BATCH:
                continue
            for item in bundle.items:
                if item.kind not in {
                    ExecutionStepItemKind.TOOL_CALL,
                    ExecutionStepItemKind.TOOL_RUN,
                    ExecutionStepItemKind.TOOL_RESULT,
                }:
                    continue
                lifecycle_item = _timeline_item_from_tool_execution_item(
                    run,
                    turn_id=turn_id,
                    bundle=bundle,
                    item=item,
                )
                lifecycle_items.append(lifecycle_item)
                if item.kind is ExecutionStepItemKind.TOOL_RUN:
                    replaced_tool_run_item_ids.add(item.id)
                    tool_run_id = lifecycle_item.source_refs.get("tool_run_id")
                    if tool_run_id:
                        replaced_tool_run_ids.add(tool_run_id)
    if not lifecycle_items:
        return _suppress_loop_control_timeline_items(timeline)
    retained = tuple(
        item
        for item in timeline
        if not (
            item.kind == "tool_run"
            and (
                item.source_refs.get("execution_item_id") in replaced_tool_run_item_ids
                or _timeline_ref(item, "tool_run_id") in replaced_tool_run_ids
            )
        )
    )
    merged = _merge_tool_interaction_timeline_items(
        tuple(
            sorted(
                (*retained, *lifecycle_items),
                key=_timeline_sort_key,
            ),
        ),
    )
    return _suppress_loop_control_timeline_items(merged)


def _timeline_items_with_evidence_frontier(
    timeline: tuple[WorkbenchTimelineItem, ...],
    *,
    runs: tuple[OrchestrationRun, ...],
    turn_id: str,
    trace: TraceContext,
) -> tuple[WorkbenchTimelineItem, ...]:
    evidence_items = _run_evidence_frontier_items(runs)
    if not evidence_items:
        return timeline
    verified_facts = [
        str(item["summary"])
        for item in evidence_items
        if item.get("status") in {"verified", "success"}
    ]
    remaining_gaps = [
        str(item["summary"])
        for item in evidence_items
        if item.get("status") in {"open", "gap", "unknown"}
    ]
    failed_paths = [
        str(item["summary"])
        for item in evidence_items
        if item.get("status") in {"failed", "blocked"}
    ]
    latest_run = max(runs, key=lambda run: run.updated_at)
    item = WorkbenchTimelineItem(
        id=f"timeline:{latest_run.id}:evidence_frontier",
        turn_id=turn_id,
        run_id=latest_run.id,
        kind="evidence_frontier",
        status="success" if verified_facts else "running",
        title="Evidence Frontier",
        content={
            "text": _evidence_frontier_summary(
                verified_count=len(verified_facts),
                gap_count=len(remaining_gaps),
                failed_count=len(failed_paths),
            ),
            "verified_facts": verified_facts,
            "remaining_gaps": remaining_gaps,
            "failed_evidence_paths": failed_paths,
            "items": evidence_items,
        },
        phase="evidence",
        source_refs={"run_id": latest_run.id},
        started_at=format_optional_datetime_utc(latest_run.updated_at),
        completed_at=format_optional_datetime_utc(latest_run.updated_at),
        trace=trace,
    )
    return _deduplicate_timeline_items((*timeline, item))


def _run_evidence_frontier_items(
    runs: tuple[OrchestrationRun, ...],
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for run in runs:
        raw_items = run.metadata.get("evidence_frontier")
        if not isinstance(raw_items, list | tuple):
            continue
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            summary = _optional_text(raw_item.get("summary"))
            if summary is None:
                continue
            item = dict(raw_item)
            item["summary"] = summary
            item_id = _optional_text(item.get("id")) or f"{run.id}:{len(items) + 1}"
            if item_id in seen_ids:
                continue
            item["id"] = item_id
            items.append(item)
            seen_ids.add(item_id)
    return items


def _evidence_frontier_summary(
    *,
    verified_count: int,
    gap_count: int,
    failed_count: int,
) -> str:
    parts = [f"verified facts: {verified_count}"]
    if gap_count:
        parts.append(f"remaining gaps: {gap_count}")
    if failed_count:
        parts.append(f"failed evidence paths: {failed_count}")
    return "; ".join(parts)


def _timeline_ref(item: WorkbenchTimelineItem, key: str) -> str | None:
    if key == "tool_call_id":
        return (
            item.source_refs.get("tool_call_id")
            or item.source_refs.get("call_id")
            or getattr(item.trace, "tool_call_id", None)
        )
    return item.source_refs.get(key) or getattr(item.trace, key, None)


def _suppress_loop_control_timeline_items(
    items: tuple[WorkbenchTimelineItem, ...],
) -> tuple[WorkbenchTimelineItem, ...]:
    return tuple(
        item
        for item in items
        if not _timeline_item_is_debug_only_continuation(item)
    )


def _timeline_item_is_debug_only_continuation(item: WorkbenchTimelineItem) -> bool:
    if item.kind != "continuation":
        return False
    text = str(item.content.get("text") or item.content.get("summary") or "").strip()
    if not text:
        text = item.title.strip()
    normalized = text.lower()
    return normalized.startswith("none;") or normalized.startswith("tool_call;")


def _merge_tool_interaction_timeline_items(
    items: tuple[WorkbenchTimelineItem, ...],
) -> tuple[WorkbenchTimelineItem, ...]:
    groups: dict[str, list[WorkbenchTimelineItem]] = {}
    ungrouped: list[WorkbenchTimelineItem] = []
    for item in items:
        tool_call_id = _timeline_ref(item, "tool_call_id")
        if item.kind in {"tool_call", "tool_run", "tool_result"} and tool_call_id:
            groups.setdefault(tool_call_id, []).append(item)
        else:
            ungrouped.append(item)

    merged: list[WorkbenchTimelineItem] = []
    for tool_call_id, group_items in groups.items():
        if len(group_items) <= 1:
            merged.extend(group_items)
            continue
        merged.append(
            _merge_tool_interaction_group(
                tool_call_id=tool_call_id,
                items=tuple(sorted(group_items, key=_timeline_sort_key)),
            ),
        )
    return tuple(
        sorted(
            (*ungrouped, *merged),
            key=_timeline_sort_key,
        ),
    )


def _merge_tool_interaction_group(
    *,
    tool_call_id: str,
    items: tuple[WorkbenchTimelineItem, ...],
) -> WorkbenchTimelineItem:
    primary = _primary_tool_interaction_item(items)
    source_refs = dict(primary.source_refs)
    for item in items:
        for key, value in item.source_refs.items():
            source_refs.setdefault(key, value)
    source_refs["tool_call_id"] = tool_call_id
    tool_name = _tool_interaction_name(items)
    lifecycle = tuple(_tool_interaction_lifecycle_entry(item) for item in items)
    content = dict(primary.content)
    content.update(
        {
            "tool_name": tool_name,
            "text": _tool_interaction_text(items, tool_name=tool_name),
            "lifecycle": list(lifecycle),
            "lifecycle_item_count": len(lifecycle),
        },
    )
    tool_execution_plan = _tool_interaction_plan(items)
    if tool_execution_plan is not None:
        content["tool_execution_plan"] = tool_execution_plan
    return WorkbenchTimelineItem(
        id=f"timeline:{primary.run_id}:tool-interaction:{tool_call_id}",
        turn_id=primary.turn_id,
        run_id=primary.run_id,
        kind="tool_call",
        status=_tool_interaction_status(items),
        title=f"Tool Interaction: {tool_name}",
        content=content,
        phase=primary.phase,
        source_refs=source_refs,
        started_at=_first_timeline_timestamp(items),
        completed_at=_last_timeline_timestamp(items),
        trace=primary.trace,
    )


def _primary_tool_interaction_item(
    items: tuple[WorkbenchTimelineItem, ...],
) -> WorkbenchTimelineItem:
    for item in items:
        if item.kind == "tool_call" and item.source_refs.get("llm_response_item_id"):
            return item
    for item in items:
        if item.kind == "tool_call":
            return item
    return items[0]


def _tool_interaction_name(items: tuple[WorkbenchTimelineItem, ...]) -> str:
    for item in items:
        name = item.content.get("tool_name") or item.source_refs.get("tool_id")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return "tool"


def _tool_interaction_plan(
    items: tuple[WorkbenchTimelineItem, ...],
) -> dict[str, Any] | None:
    for item in items:
        plan = item.content.get("tool_execution_plan")
        if isinstance(plan, dict) and plan:
            return dict(plan)
    return None


def _tool_interaction_status(items: tuple[WorkbenchTimelineItem, ...]) -> str:
    statuses = {item.status for item in items}
    if statuses & {"failed", "error", "cancelled"}:
        return "failed"
    if statuses & {"waiting", "running", "queued"}:
        return "running"
    if "success" in statuses or "completed" in statuses:
        return "success"
    return items[-1].status


def _tool_interaction_text(
    items: tuple[WorkbenchTimelineItem, ...],
    *,
    tool_name: str,
) -> str:
    status = _tool_interaction_status(items)
    if status == "failed":
        return f"Tool interaction failed: {tool_name}."
    if status == "running":
        return f"Tool interaction running: {tool_name}."
    return f"Tool interaction completed: {tool_name}."


def _tool_interaction_lifecycle_entry(
    item: WorkbenchTimelineItem,
) -> dict[str, Any]:
    return {
        "id": item.id,
        "kind": item.kind,
        "status": item.status,
        "title": item.title,
        "source_refs": dict(item.source_refs),
        "started_at": item.started_at,
        "completed_at": item.completed_at,
        "content": dict(item.content),
    }


def _first_timeline_timestamp(items: tuple[WorkbenchTimelineItem, ...]) -> str | None:
    for item in items:
        if item.started_at:
            return item.started_at
    return None


def _last_timeline_timestamp(items: tuple[WorkbenchTimelineItem, ...]) -> str | None:
    for item in reversed(items):
        if item.completed_at or item.started_at:
            return item.completed_at or item.started_at
    return None


def _timeline_item_from_tool_execution_item(
    run: OrchestrationRun,
    *,
    turn_id: str,
    bundle: _ExecutionStepBundle,
    item: ExecutionStepItem,
) -> WorkbenchTimelineItem:
    summary = _execution_item_summary(item)
    context_render_snapshot_id = _context_render_snapshot_id(run, summary=summary)
    tool_run_id = _summary_text(summary, "tool_run_id")
    tool_call_id = _summary_text(summary, "tool_call_id") or item.correlation_key
    result_session_item_id = _summary_text(summary, "result_session_item_id")
    session_item_ids = _summary_text_list(summary, "session_item_ids")
    session_item_id = result_session_item_id or (
        session_item_ids[0] if session_item_ids else None
    )
    tool_name = (
        _summary_text(summary, "tool_name")
        or _summary_text(summary, "tool_id")
        or "tool"
    )
    source_refs = {
        "run_id": run.id,
        "turn_id": turn_id,
        "execution_step_id": bundle.step.id,
        "execution_item_id": item.id,
    }
    if tool_call_id:
        source_refs["tool_call_id"] = tool_call_id
    if tool_run_id:
        source_refs["tool_run_id"] = tool_run_id
    if session_item_id:
        source_refs["session_item_id"] = session_item_id
    if context_render_snapshot_id:
        source_refs["context_render_snapshot_id"] = context_render_snapshot_id
    tool_id = _summary_text(summary, "tool_id")
    if tool_id:
        source_refs["tool_id"] = tool_id
    trace = _trace_for_run(
        run,
        turn_id=turn_id,
        step_id=bundle.step.id,
        tool_run_id=tool_run_id,
        context_render_snapshot_id=context_render_snapshot_id,
        session_item_id=session_item_id,
        source_owner=item.owner.owner_kind if item.owner is not None else None,
        source_event_id=item.owner.owner_id if item.owner is not None else item.id,
        source_event_name=item.kind.value,
    )
    return WorkbenchTimelineItem(
        id=f"timeline:{run.id}:execution:{bundle.step.id}:{item.id}",
        turn_id=turn_id,
        run_id=run.id,
        kind=_timeline_kind_for_tool_execution_item(item),
        status=_execution_item_view_status(item),
        title=_timeline_title_for_tool_execution_item(item, tool_name=tool_name),
        content=_timeline_content_for_tool_execution_item(
            item,
            summary=summary,
            tool_name=tool_name,
        ),
        phase=None,
        source_refs=source_refs,
        started_at=format_optional_datetime_utc(item.created_at),
        completed_at=format_optional_datetime_utc(item.completed_at),
        trace=trace,
    )


def _timeline_kind_for_tool_execution_item(item: ExecutionStepItem) -> str:
    if item.kind is ExecutionStepItemKind.TOOL_CALL:
        return "tool_call"
    if item.kind is ExecutionStepItemKind.TOOL_RESULT:
        return "tool_result"
    return "tool_run"


def _timeline_title_for_tool_execution_item(
    item: ExecutionStepItem,
    *,
    tool_name: str,
) -> str:
    if item.kind is ExecutionStepItemKind.TOOL_CALL:
        return f"Tool Call: {tool_name}"
    if item.kind is ExecutionStepItemKind.TOOL_RESULT:
        return f"Tool Result: {tool_name}"
    return f"Tool Run: {tool_name}"


def _timeline_content_for_tool_execution_item(
    item: ExecutionStepItem,
    *,
    summary: dict[str, object],
    tool_name: str,
) -> dict[str, Any]:
    content: dict[str, Any] = {
        "tool_name": tool_name,
        "payload": dict(summary),
    }
    tool_execution_plan = summary.get("tool_execution_plan")
    if isinstance(tool_execution_plan, dict) and tool_execution_plan:
        content["tool_execution_plan"] = dict(tool_execution_plan)
    if item.kind is ExecutionStepItemKind.TOOL_CALL:
        content["text"] = f"Tool call requested: {tool_name}."
    elif item.kind is ExecutionStepItemKind.TOOL_RESULT:
        result_session_item_id = _summary_text(summary, "result_session_item_id")
        if result_session_item_id:
            suffix = f" Result item: {result_session_item_id}."
        else:
            suffix = ""
        content["text"] = f"Tool result recorded for {tool_name}.{suffix}"
    else:
        status = _summary_text(summary, "status") or _execution_item_view_status(item)
        content["text"] = f"Tool run {status}: {tool_name}."
    return content


def _timeline_sort_key(item: WorkbenchTimelineItem) -> tuple[str, str, str]:
    return (
        item.started_at or "",
        item.source_refs.get("execution_step_id", ""),
        item.id,
    )


def _timeline_items_from_llm_response_items(
    step: TurnStepView,
    *,
    response_items: tuple[Any, ...],
    base_index: int,
) -> tuple[WorkbenchTimelineItem, ...]:
    items: list[WorkbenchTimelineItem] = []
    for item_index, response_item in enumerate(response_items):
        update_plan_progress = _timeline_item_from_update_plan_response_item(
            step,
            response_item=response_item,
            base_index=base_index,
            item_index=item_index,
        )
        if update_plan_progress is not None:
            items.append(update_plan_progress)
            continue
        content = _timeline_content_from_response_item(response_item)
        if not _response_item_has_timeline_content(response_item, content):
            continue
        source_refs = _timeline_source_refs(step)
        response_item_id = _optional_text(getattr(response_item, "id", None))
        provider_item_id = _optional_text(getattr(response_item, "provider_item_id", None))
        call_id = _optional_text(getattr(response_item, "call_id", None))
        if response_item_id is not None:
            source_refs["llm_response_item_id"] = response_item_id
        if provider_item_id is not None:
            source_refs["provider_item_id"] = provider_item_id
        if call_id is not None:
            source_refs["call_id"] = call_id
        items.append(
            WorkbenchTimelineItem(
                id=f"timeline:{step.step_id}:response:{base_index}:{item_index}",
                turn_id=step.turn_id,
                run_id=step.run_id,
                kind=_timeline_kind_for_response_item(response_item),
                status="success" if getattr(response_item, "completed_at", None) else step.status,
                title=_timeline_title_for_response_item(response_item),
                content=content,
                phase=_enum_value(getattr(response_item, "phase", None)),
                source_refs=source_refs,
                started_at=format_optional_datetime_utc(
                    getattr(response_item, "created_at", None),
                ),
                completed_at=format_optional_datetime_utc(
                    getattr(response_item, "completed_at", None),
                ),
                trace=step.trace,
            ),
        )
    return tuple(items)


def _timeline_item_from_update_plan_response_item(
    step: TurnStepView,
    *,
    response_item: Any,
    base_index: int,
    item_index: int,
) -> WorkbenchTimelineItem | None:
    if not _response_item_is_update_plan_call(response_item):
        return None
    payload = dict(getattr(response_item, "content_payload", {}) or {})
    arguments = payload.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}
    text = _update_plan_progress_text(arguments)
    if text is None:
        return None
    source_refs = _timeline_source_refs(step)
    response_item_id = _optional_text(getattr(response_item, "id", None))
    provider_item_id = _optional_text(getattr(response_item, "provider_item_id", None))
    call_id = _optional_text(getattr(response_item, "call_id", None))
    if response_item_id is not None:
        source_refs["llm_response_item_id"] = response_item_id
    if provider_item_id is not None:
        source_refs["provider_item_id"] = provider_item_id
    if call_id is not None:
        source_refs["call_id"] = call_id
        source_refs["tool_call_id"] = call_id
    source_refs["tool_id"] = "context_tree.update_plan"
    return WorkbenchTimelineItem(
        id=f"timeline:{step.step_id}:response:{base_index}:{item_index}:progress",
        turn_id=step.turn_id,
        run_id=step.run_id,
        kind="agent_progress",
        status="success" if getattr(response_item, "completed_at", None) else step.status,
        title="Agent Progress",
        content={
            "text": text,
            "payload": {
                "tool_name": "context_tree.update_plan",
                "arguments": arguments,
            },
            "tool_name": "context_tree.update_plan",
            "call_id": call_id,
        },
        phase=_enum_value(getattr(response_item, "phase", None)),
        source_refs=source_refs,
        started_at=format_optional_datetime_utc(
            getattr(response_item, "created_at", None),
        ),
        completed_at=format_optional_datetime_utc(
            getattr(response_item, "completed_at", None),
        ),
        trace=step.trace,
    )


def _response_item_is_update_plan_call(response_item: Any) -> bool:
    if _enum_value(getattr(response_item, "kind", None)) != "tool_call":
        return False
    tool_name = _optional_text(getattr(response_item, "tool_name", None))
    return tool_name == "context_tree.update_plan"


def _update_plan_progress_text(arguments: dict[str, object]) -> str | None:
    objective = _optional_text(arguments.get("objective"))
    status = _optional_text(arguments.get("status"))
    current_step = _optional_text(arguments.get("current_step"))
    next_steps = _optional_text(arguments.get("next_steps"))
    parts: list[str] = []
    if objective:
        parts.append(f"目标：{objective}")
    if status or current_step:
        current = current_step or status
        if current:
            parts.append(f"当前：{current}")
    if next_steps:
        parts.append(f"下一步：{next_steps}")
    return "\n".join(parts) if parts else None


def _timeline_content_from_response_item(response_item: Any) -> dict[str, Any]:
    kind = _enum_value(getattr(response_item, "kind", None))
    if kind == "reasoning" and not bool(getattr(response_item, "user_visible", False)):
        return {
            "reasoning_present": True,
            "reasoning_item_count": 1,
            "reasoning_hidden": True,
            "hidden_reason": "policy",
        }
    payload = dict(getattr(response_item, "content_payload", {}) or {})
    content: dict[str, Any] = {}
    text = _optional_text(payload.get("text")) or _optional_text(payload.get("summary"))
    if text is not None:
        content["text"] = text
    if payload:
        content["payload"] = payload
    tool_name = _optional_text(getattr(response_item, "tool_name", None))
    call_id = _optional_text(getattr(response_item, "call_id", None))
    if tool_name is not None:
        content["tool_name"] = tool_name
    if call_id is not None:
        content["call_id"] = call_id
    return content


def _response_item_has_timeline_content(
    response_item: Any,
    content: dict[str, Any],
) -> bool:
    kind = _enum_value(getattr(response_item, "kind", None))
    if kind == "reasoning":
        if bool(content.get("reasoning_hidden")):
            return True
        return _timeline_content_has_visible_value(content)
    if kind != "assistant_message":
        return True
    text = _optional_text(content.get("text"))
    markdown = _optional_text(content.get("markdown"))
    payload = content.get("payload")
    return bool(text or markdown or _payload_has_visible_value(payload))


def _timeline_content_has_visible_value(content: dict[str, Any]) -> bool:
    if _optional_text(content.get("text")) is not None:
        return True
    if _optional_text(content.get("markdown")) is not None:
        return True
    return _payload_has_visible_value(content.get("payload"))


def _payload_has_visible_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, bool | int | float):
        return True
    if isinstance(value, dict):
        return any(_payload_has_visible_value(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_payload_has_visible_value(item) for item in value)
    return True


def _timeline_kind_for_response_item(response_item: Any) -> str:
    kind = _enum_value(getattr(response_item, "kind", None))
    phase = _enum_value(getattr(response_item, "phase", None))
    if kind == "assistant_message":
        return "final_answer" if phase == "final_answer" else "assistant_commentary"
    if kind == "reasoning":
        return "reasoning_summary"
    if kind == "provider_external_item":
        return "provider_external_item"
    if kind == "structured_output":
        return "structured_output"
    if kind == "compaction":
        return "compaction"
    return kind or "unknown"


def _timeline_title_for_response_item(response_item: Any) -> str:
    kind = _timeline_kind_for_response_item(response_item)
    if kind == "assistant_commentary":
        return "Agent Progress"
    if kind == "final_answer":
        return "Final Response"
    if kind == "reasoning_summary":
        return "Reasoning Summary"
    if kind == "tool_call":
        tool_name = _optional_text(getattr(response_item, "tool_name", None))
        return f"Tool Call: {tool_name}" if tool_name else "Tool Call"
    if kind == "tool_result":
        return "Tool Result"
    if kind == "provider_external_item":
        provider_type = _optional_text(getattr(response_item, "provider_item_type", None))
        return f"Provider Item: {provider_type}" if provider_type else "Provider Item"
    return kind.replace("_", " ").title()


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value
    text = str(value).strip()
    return text or None


def _timeline_item_from_step(
    step: TurnStepView,
    *,
    index: int,
) -> WorkbenchTimelineItem:
    content: dict[str, Any] = {}
    if step.markdown:
        content["markdown"] = step.markdown
    if step.summary:
        content["text"] = step.summary
    source_refs = _timeline_source_refs(step)
    return WorkbenchTimelineItem(
        id=f"timeline:{step.step_id}:{index}",
        turn_id=step.turn_id,
        run_id=step.run_id,
        kind=_timeline_kind_for_step(step),
        status=step.status,
        title=step.title,
        content=content,
        phase=_timeline_phase_for_step(step),
        source_refs=source_refs,
        started_at=step.started_at,
        completed_at=step.completed_at,
        trace=step.trace,
    )


def _timeline_source_refs(step: TurnStepView) -> dict[str, str]:
    refs: dict[str, str] = {}
    trace = step.trace
    if trace.run_id:
        refs["run_id"] = trace.run_id
    if trace.turn_id:
        refs["turn_id"] = trace.turn_id
    if trace.source_event_id:
        refs["source_event_id"] = trace.source_event_id
    if trace.source_owner:
        refs["source_owner"] = trace.source_owner
    if trace.source_event_name:
        refs["source_event_name"] = trace.source_event_name
    if trace.session_item_id:
        refs["session_item_id"] = trace.session_item_id
    if trace.step_id:
        refs["execution_step_id"] = trace.step_id
    execution_item_id = _execution_item_id_from_step_id(step.step_id)
    if execution_item_id is not None:
        refs["execution_item_id"] = execution_item_id
    if trace.llm_invocation_id:
        refs["llm_invocation_id"] = trace.llm_invocation_id
    if trace.context_render_snapshot_id:
        refs["context_render_snapshot_id"] = trace.context_render_snapshot_id
    if trace.tool_run_id:
        refs["tool_run_id"] = trace.tool_run_id
    if trace.artifact_id:
        refs["artifact_id"] = trace.artifact_id
    return refs


def _execution_item_id_from_step_id(step_id: str) -> str | None:
    marker = ":item-"
    if marker not in step_id:
        return None
    return step_id.rsplit(":", 1)[-1] or None


def _timeline_kind_for_step(step: TurnStepView) -> str:
    if step.type == "agent_progress":
        return "assistant_commentary"
    if step.type == "agent_thinking":
        return "assistant_reasoning"
    if step.type == "llm":
        return "llm_invocation"
    if step.type == "continuation_decision":
        return "continuation"
    if step.type == "tool_call":
        if step.trace.tool_run_id:
            return "tool_run"
        return "tool_call"
    if step.type == "tool_result":
        return "tool_result"
    if step.type == "final_response":
        return "final_answer"
    return step.type


def _timeline_phase_for_step(step: TurnStepView) -> str | None:
    if step.type == "agent_progress":
        return "commentary"
    if step.type in {"agent_thinking", "llm"}:
        return "reasoning"
    if step.type == "final_response":
        return "final"
    return None


def _chain_step_views_for_run(
    run_query: OrchestrationRunQueryPort,
    llm_query: WorkbenchLlmQueryPort | None,
    artifact_query: WorkbenchArtifactQueryPort | None,
    session_query: WorkbenchSessionQueryPort | None,
    run: OrchestrationRun,
    *,
    turn_id: str,
    display_tool_runs: tuple[_DisplayToolRun, ...],
) -> tuple[TurnStepView, ...]:
    bundles = _execution_step_bundles(run_query, run.id)
    if not bundles:
        return ()
    tool_runs_by_id = {
        display_tool_run.tool_run.id: display_tool_run.tool_run
        for display_tool_run in display_tool_runs
    }
    views: list[TurnStepView] = []
    tool_only_streak = 0
    for bundle in bundles:
        step = bundle.step
        if step.kind is ExecutionStepKind.INTAKE:
            views.append(
                _step(
                    run=run,
                    turn_id=turn_id,
                    step_id=f"execution:{step.id}",
                    step_type="user_input",
                    status=(
                        "success"
                        if step.status is ExecutionStepStatus.COMPLETED
                        else _execution_step_view_status(step, run=run)
                    ),
                    title="User Input",
                    summary=_instruction_summary(run),
                    started_at=run.created_at,
                    completed_at=run.created_at,
                    trace_step_id=step.id,
                ),
            )
            continue
        if step.kind is ExecutionStepKind.LLM:
            tool_only_streak = (
                tool_only_streak + 1
                if _llm_bundle_is_tool_only(bundle)
                else 0
            )
            views.extend(
                _chain_llm_step_views(
                    llm_query,
                    session_query,
                    run,
                    turn_id=turn_id,
                    bundle=bundle,
                    tool_only_streak=tool_only_streak,
                ),
            )
            continue
        if step.kind is ExecutionStepKind.TOOL_BATCH:
            views.extend(
                _chain_tool_step_views(
                    run,
                    turn_id=turn_id,
                    bundle=bundle,
                    tool_runs_by_id=tool_runs_by_id,
                    artifact_query=artifact_query,
                ),
            )
            continue
        if step.kind is ExecutionStepKind.APPROVAL:
            approval_view = _chain_approval_step_view(
                run,
                turn_id=turn_id,
                bundle=bundle,
            )
            if approval_view is not None:
                views.append(approval_view)
            continue
        if step.kind is ExecutionStepKind.FINAL_RESPONSE:
            output_text = _output_text(run)
            views.append(
                _step(
                    run=run,
                    turn_id=turn_id,
                    step_id=f"execution:{step.id}",
                    step_type="final_response",
                    status=_execution_step_view_status(step, run=run),
                    title="Final Response",
                    summary=output_text or "Run completed.",
                    markdown=output_text,
                    started_at=step.started_at or step.created_at,
                    completed_at=step.completed_at or run.completed_at or run.updated_at,
                    trace_step_id=step.id,
                ),
            )
            continue
        views.append(
            _generic_execution_step_view(
                run,
                turn_id=turn_id,
                bundle=bundle,
            ),
        )
    return tuple(views)


def _chain_llm_step_views(
    llm_query: WorkbenchLlmQueryPort | None,
    session_query: WorkbenchSessionQueryPort | None,
    run: OrchestrationRun,
    *,
    turn_id: str,
    bundle: _ExecutionStepBundle,
    tool_only_streak: int = 0,
) -> tuple[TurnStepView, ...]:
    return (
        *_assistant_progress_step_views(
            session_query,
            run,
            turn_id=turn_id,
            bundle=bundle,
        ),
        _chain_llm_step_view(
            llm_query,
            run,
            turn_id=turn_id,
            bundle=bundle,
            tool_only_streak=tool_only_streak,
        ),
        *_continuation_decision_step_views(
            run,
            turn_id=turn_id,
            bundle=bundle,
        ),
    )


def _continuation_decision_step_views(
    run: OrchestrationRun,
    *,
    turn_id: str,
    bundle: _ExecutionStepBundle,
) -> tuple[TurnStepView, ...]:
    views: list[TurnStepView] = []
    for index, item in enumerate(bundle.items):
        if item.kind is not ExecutionStepItemKind.CONTINUATION_DECISION:
            continue
        summary = _execution_item_summary(item)
        context_render_snapshot_id = _context_render_snapshot_id(run, summary=summary)
        reason = _summary_text(summary, "reason") or "unknown"
        needs_follow_up = _summary_bool(summary, "needs_follow_up")
        end_turn = summary.get("end_turn")
        provider_state = summary.get("provider_continuation_state")
        provider_state = dict(provider_state) if isinstance(provider_state, dict) else {}
        provider_mode = _optional_text(provider_state.get("mode"))
        previous_response_id = _optional_text(provider_state.get("previous_response_id"))
        end_turn_label = (
            f"end_turn={str(end_turn).lower()}"
            if isinstance(end_turn, bool)
            else "end_turn=-"
        )
        follow_up_label = f"follow_up={str(needs_follow_up).lower()}"
        summary_parts = [reason, end_turn_label, follow_up_label]
        if provider_mode is not None:
            summary_parts.append(f"provider={provider_mode}")
        if previous_response_id is not None:
            summary_parts.append(f"previous_response_id={previous_response_id}")
        badges = [
            StatusBadgeModel(
                label="Follow-up" if needs_follow_up else "End turn",
                tone="info" if needs_follow_up else "success",
            ),
            StatusBadgeModel(label=reason, tone="neutral"),
        ]
        if provider_mode is not None:
            badges.append(StatusBadgeModel(label=provider_mode, tone="info"))
        views.append(
            _step(
                run=run,
                turn_id=turn_id,
                step_id=f"execution:{bundle.step.id}:continuation:{index}",
                step_type="continuation_decision",
                status="running" if needs_follow_up else "success",
                title="Continuation Decision",
                summary="; ".join(summary_parts),
                started_at=item.created_at,
                completed_at=item.completed_at or bundle.step.completed_at,
                badges=tuple(badges),
                llm_invocation_id=_summary_text(summary, "llm_invocation_id"),
                context_render_snapshot_id=context_render_snapshot_id,
                trace_step_id=bundle.step.id,
            ),
        )
    return tuple(views)


def _assistant_progress_step_views(
    session_query: WorkbenchSessionQueryPort | None,
    run: OrchestrationRun,
    *,
    turn_id: str,
    bundle: _ExecutionStepBundle,
) -> tuple[TurnStepView, ...]:
    views: list[TurnStepView] = []
    for index, item in enumerate(bundle.items):
        if item.kind is not ExecutionStepItemKind.SESSION_MESSAGE:
            continue
        summary = _execution_item_summary(item)
        context_render_snapshot_id = _context_render_snapshot_id(run, summary=summary)
        if _summary_text(summary, "message_kind") != "assistant_progress":
            continue
        progress_text = _summary_text(summary, "assistant_progress_text")
        session_item_ids = _summary_text_list(summary, "session_item_ids")
        session_item_id = (
            _summary_text(summary, "session_item_id")
            or (session_item_ids[0] if session_item_ids else None)
        )
        if progress_text is None:
            progress_text = _session_item_text(
                session_query,
                session_item_id,
            )
        if progress_text is None:
            continue
        source_owner = "session_item"
        source_event_id = session_item_id
        views.append(
            _step(
                run=run,
                turn_id=turn_id,
                step_id=f"execution:{bundle.step.id}:progress:{index}",
                step_type="agent_progress",
                status=_execution_item_view_status(item),
                title="Agent Progress",
                summary=progress_text,
                markdown=progress_text,
                started_at=bundle.step.started_at or item.created_at,
                completed_at=item.completed_at or bundle.step.completed_at,
                badges=(StatusBadgeModel(label="Assistant", tone="info"),),
                llm_invocation_id=_summary_text(summary, "llm_invocation_id"),
                context_render_snapshot_id=context_render_snapshot_id,
                session_item_id=session_item_id,
                trace_step_id=bundle.step.id,
                source_owner=source_owner,
                source_event_id=source_event_id,
                source_event_name="assistant_progress",
            ),
        )
    return tuple(views)


def _session_item_text(
    session_query: WorkbenchSessionQueryPort | None,
    item_id: str | None,
) -> str | None:
    if session_query is None or not item_id:
        return None
    try:
        item = session_query.get_item(item_id)
    except Exception:
        return None
    content_payload = getattr(item, "content_payload", None)
    text = extract_text_content(content_blocks_from_payload(content_payload))
    if isinstance(text, str) and text.strip():
        return text.strip()
    return None


def _chain_llm_step_view(
    llm_query: WorkbenchLlmQueryPort | None,
    run: OrchestrationRun,
    *,
    turn_id: str,
    bundle: _ExecutionStepBundle,
    tool_only_streak: int = 0,
) -> TurnStepView:
    step = bundle.step
    invocation_id = _llm_invocation_id_from_execution_items(bundle.items)
    llm_invocation = _safe_llm_invocation(llm_query, invocation_id)
    tool_names = _tool_names_from_execution_items(bundle.items)
    is_dispatch_wait = (
        step.status is ExecutionStepStatus.CREATED
        and run.status in {OrchestrationRunStatus.ACCEPTED, OrchestrationRunStatus.QUEUED}
    )
    if is_dispatch_wait:
        return _step(
            run=run,
            turn_id=turn_id,
            step_id=f"execution:{step.id}",
            step_type="agent_thinking",
            status="queued",
            title="Queued",
            summary=run.waiting_reason or "Run is waiting for scheduler admission.",
            started_at=run.queued_at or step.created_at,
            completed_at=None,
            trace_step_id=step.id,
        )
    diagnostics = _llm_step_diagnostics(llm_invocation, bundle.items)
    context_render_snapshot_id = (
        _summary_text_from_items(bundle.items, "context_render_snapshot_id")
        or _metadata_str(run, "context_render_snapshot_id")
    )
    summary = _llm_summary(run, llm_invocation=llm_invocation)
    if diagnostics:
        summary = f"{summary} {_llm_diagnostics_sentence(diagnostics)}"
    if tool_only_streak >= 3:
        summary = f"{summary} Tool-only streak: {tool_only_streak} LLM steps."
    if llm_invocation is None and tool_names:
        summary = f"{summary} Model requested tool call(s): {', '.join(tool_names)}."
    badge_label = (
        _llm_invocation_llm_id(llm_invocation)
        or _summary_text_from_items(bundle.items, "llm_id")
        or _llm_id(run)
        or "Auto"
    )
    badges = (
        StatusBadgeModel(label=badge_label, tone="info"),
        *_llm_diagnostic_badges(diagnostics),
        *_tool_only_streak_badges(tool_only_streak),
    )
    return _step(
        run=run,
        turn_id=turn_id,
        step_id=f"execution:{step.id}",
        step_type="llm",
        status=_execution_step_view_status(step, run=run),
        title="LLM Thinking",
        summary=summary,
        started_at=step.started_at or _llm_started_at(run, llm_invocation),
        completed_at=(
            step.completed_at
            or (
                _llm_completed_at(run, llm_invocation)
                if step.status in {
                    ExecutionStepStatus.COMPLETED,
                    ExecutionStepStatus.FAILED,
                    ExecutionStepStatus.CANCELLED,
                }
                else None
            )
        ),
        badges=badges,
        llm_invocation_id=invocation_id,
        context_render_snapshot_id=context_render_snapshot_id,
        trace_step_id=step.id,
    )


def _chain_tool_step_views(
    run: OrchestrationRun,
    *,
    turn_id: str,
    bundle: _ExecutionStepBundle,
    tool_runs_by_id: dict[str, ToolRun],
    artifact_query: WorkbenchArtifactQueryPort | None,
) -> tuple[TurnStepView, ...]:
    views: list[TurnStepView] = []
    for item in bundle.items:
        if item.kind is not ExecutionStepItemKind.TOOL_RUN:
            continue
        tool_run_id = _execution_item_owner_id(item, owner_kind="tool_run")
        if tool_run_id is None:
            continue
        tool_run = tool_runs_by_id.get(tool_run_id)
        summary = _execution_item_summary(item)
        status = _tool_status(tool_run) if tool_run is not None else _execution_item_view_status(item)
        failed = (
            tool_run.status in _FAILED_TOOL_RUN_STATUSES
            if tool_run is not None
            else item.status is ExecutionStepItemStatus.FAILED
        )
        artifacts = (
            _tool_artifacts(tool_run, artifact_query=artifact_query)
            if tool_run is not None and tool_run.status in _TERMINAL_TOOL_RUN_STATUSES
            else ()
        )
        tool_label = (
            tool_run.tool_id
            if tool_run is not None
            else _summary_text(summary, "tool_id")
            or _summary_text(summary, "tool_name")
            or "Tool Call"
        )
        views.append(
            _step(
                run=run,
                turn_id=turn_id,
                step_id=f"execution:{bundle.step.id}:{item.id}",
                step_type="error" if failed else "tool_call",
                status=status,
                title="Tool Failed" if failed else "Tool Call",
                summary=(
                    _tool_step_summary(tool_run)
                    if tool_run is not None
                    else _execution_tool_item_summary(summary, item)
                ),
                started_at=(
                    tool_run.created_at
                    if tool_run is not None
                    else bundle.step.started_at or item.created_at
                ),
                completed_at=(
                    tool_run.completed_at
                    if tool_run is not None
                    else item.completed_at
                ),
                artifacts=artifacts,
                badges=(StatusBadgeModel(label=tool_label, tone="danger" if failed else "info"),),
                tool_run_id=tool_run_id,
                artifact_id=artifacts[0].artifact_id if artifacts else None,
                trace_step_id=bundle.step.id,
            ),
        )
    if views:
        return tuple(views)
    return (
        _generic_execution_step_view(
            run,
            turn_id=turn_id,
            bundle=bundle,
        ),
    )


def _chain_approval_step_view(
    run: OrchestrationRun,
    *,
    turn_id: str,
    bundle: _ExecutionStepBundle,
) -> TurnStepView | None:
    approval_item = next(
        (
            item
            for item in bundle.items
            if item.kind is ExecutionStepItemKind.APPROVAL_REQUEST
        ),
        None,
    )
    payload = (
        _execution_item_summary(approval_item)
        if approval_item is not None
        else _pending_approval(run)
    )
    if not payload:
        return None
    request_id = _optional_text(payload.get("request_id")) or _optional_text(payload.get("id"))
    approval_detail = _approval_detail(payload)
    return _step(
        run=run,
        turn_id=turn_id,
        step_id=f"execution:{bundle.step.id}",
        step_type="approval_required",
        status=_execution_step_view_status(bundle.step, run=run),
        title="Approval Required",
        summary=_approval_summary(payload),
        started_at=bundle.step.started_at or bundle.step.created_at,
        completed_at=bundle.step.completed_at,
        badges=(StatusBadgeModel(label="Authorization", tone="warning"),),
        linked_entities=_approval_entities(approval_detail),
        approval=approval_detail,
        approval_request_id=request_id,
        trace_step_id=bundle.step.id,
    )


def _llm_step_diagnostics(
    llm_invocation: Any | None,
    items: tuple[ExecutionStepItem, ...],
) -> dict[str, object]:
    result = getattr(llm_invocation, "result", None)
    text = getattr(result, "text", None)
    text_chars = len(text.strip()) if isinstance(text, str) and text.strip() else 0
    raw_tool_calls = getattr(result, "tool_calls", None)
    tool_calls_count = len(raw_tool_calls) if isinstance(raw_tool_calls, (tuple, list)) else 0
    if tool_calls_count == 0:
        tool_calls_count = len(_tool_call_names_from_execution_items(items))
    tool_call_item_count = len(_tool_call_session_item_ids_from_execution_items(items))
    progress_count = len(_assistant_progress_session_item_ids_from_execution_items(items))
    if progress_count == 0 and _summary_text_from_items(items, "assistant_progress_text"):
        progress_count = 1
    if text_chars == 0:
        progress_text = _summary_text_from_items(items, "assistant_progress_text")
        text_chars = len(progress_text) if progress_text is not None else 0
    diagnostics: dict[str, object] = {
        "text_present": text_chars > 0,
        "text_chars": text_chars,
        "tool_calls_count": tool_calls_count,
        "tool_call_session_item_count": tool_call_item_count,
        "progress_recorded": progress_count > 0,
        "assistant_progress_item_count": progress_count,
    }
    loop_diagnostic = _summary_dict_from_items(items, "llm_loop_diagnostic")
    code = _summary_text(loop_diagnostic, "code") if loop_diagnostic else None
    reason = _summary_text(loop_diagnostic, "reason") if loop_diagnostic else None
    if code is not None:
        diagnostics["loop_diagnostic_code"] = code
    if reason is not None:
        diagnostics["loop_diagnostic_reason"] = reason
    return diagnostics


def _llm_bundle_is_tool_only(bundle: _ExecutionStepBundle) -> bool:
    diagnostics = _llm_step_diagnostics(None, bundle.items)
    return (
        diagnostics.get("tool_calls_count", 0) > 0
        and diagnostics.get("text_present") is False
        and diagnostics.get("progress_recorded") is False
    )


def _llm_diagnostics_sentence(diagnostics: dict[str, object]) -> str:
    text_chars = diagnostics.get("text_chars")
    tool_calls_count = diagnostics.get("tool_calls_count")
    tool_call_item_count = diagnostics.get("tool_call_session_item_count")
    progress_count = diagnostics.get("assistant_progress_item_count")
    parts: list[str] = []
    if isinstance(text_chars, int) and text_chars > 0:
        parts.append(f"text: {text_chars} chars")
    elif isinstance(tool_calls_count, int) and tool_calls_count > 0:
        parts.append("text: none")
    if isinstance(tool_calls_count, int) and tool_calls_count > 0:
        parts.append(f"tool calls: {tool_calls_count}")
    if isinstance(tool_call_item_count, int) and tool_call_item_count > 0:
        parts.append(f"tool call items: {tool_call_item_count}")
    if isinstance(progress_count, int) and progress_count > 0:
        parts.append(f"progress recorded: {progress_count}")
    loop_code = diagnostics.get("loop_diagnostic_code")
    if isinstance(loop_code, str) and loop_code:
        parts.append(f"loop diagnostic: {loop_code}")
    if not parts:
        return ""
    return "Diagnostics: " + "; ".join(parts) + "."


def _llm_diagnostic_badges(
    diagnostics: dict[str, object],
) -> tuple[StatusBadgeModel, ...]:
    tool_calls_count = diagnostics.get("tool_calls_count")
    tool_call_item_count = diagnostics.get("tool_call_session_item_count")
    text_present = diagnostics.get("text_present") is True
    progress_recorded = diagnostics.get("progress_recorded") is True
    badges: list[StatusBadgeModel] = []
    if isinstance(tool_calls_count, int) and tool_calls_count > 0:
        badges.append(
            StatusBadgeModel(
                label="Text + tools" if text_present else "Tool only",
                tone="success" if text_present else "warning",
            ),
        )
    elif text_present:
        badges.append(StatusBadgeModel(label="Text", tone="success"))
    if progress_recorded:
        badges.append(StatusBadgeModel(label="Progress recorded", tone="info"))
    if isinstance(tool_call_item_count, int) and tool_call_item_count > 0:
        badges.append(
            StatusBadgeModel(
                label=f"Tool items: {tool_call_item_count}",
                tone="info",
            ),
        )
    loop_code = diagnostics.get("loop_diagnostic_code")
    if isinstance(loop_code, str) and loop_code:
        badges.append(StatusBadgeModel(label="Loop diagnostic", tone="danger"))
    return tuple(badges)


def _tool_only_streak_badges(tool_only_streak: int) -> tuple[StatusBadgeModel, ...]:
    if tool_only_streak < 3:
        return ()
    return (
        StatusBadgeModel(
            label=f"Tool-only streak: {tool_only_streak}",
            tone="warning",
        ),
    )


def _generic_execution_step_view(
    run: OrchestrationRun,
    *,
    turn_id: str,
    bundle: _ExecutionStepBundle,
) -> TurnStepView:
    step = bundle.step
    if step.kind is ExecutionStepKind.ERROR or step.status is ExecutionStepStatus.FAILED:
        step_type = "error"
        title = "Run Failed"
        summary = (
            step.error_payload.message
            if step.error_payload is not None
            else run.error.message
            if run.error is not None
            else "Run failed."
        )
    else:
        step_type = "agent_thinking"
        title = step.kind.value.replace("_", " ").title()
        summary = f"Execution step: {step.kind.value}."
    return _step(
        run=run,
        turn_id=turn_id,
        step_id=f"execution:{step.id}",
        step_type=step_type,
        status=_execution_step_view_status(step, run=run),
        title=title,
        summary=summary,
        started_at=step.started_at or step.created_at,
        completed_at=step.completed_at,
        trace_step_id=step.id,
    )


def _execution_step_bundles(
    run_query: OrchestrationRunQueryPort,
    turn_id: str,
) -> tuple[_ExecutionStepBundle, ...]:
    try:
        chains = run_query.list_execution_chains(turn_id)
    except Exception:
        return ()
    bundles: list[_ExecutionStepBundle] = []
    for chain in chains:
        try:
            steps = run_query.list_execution_steps(chain.id)
        except Exception:
            continue
        for step in steps:
            try:
                items = tuple(run_query.list_execution_step_items(step.id))
            except Exception:
                items = ()
            bundles.append(_ExecutionStepBundle(step=step, items=items))
    return tuple(
        sorted(
            bundles,
            key=lambda bundle: (
                bundle.step.created_at,
                bundle.step.chain_id,
                bundle.step.step_index,
                bundle.step.id,
            ),
        ),
    )


def _execution_step_view_status(
    step: ExecutionStep,
    *,
    run: OrchestrationRun,
) -> str:
    if step.status is ExecutionStepStatus.COMPLETED:
        return "success"
    if step.status is ExecutionStepStatus.FAILED:
        return "failed"
    if step.status is ExecutionStepStatus.CANCELLED:
        return "cancelled"
    if step.status is ExecutionStepStatus.WAITING:
        return "waiting"
    if step.status is ExecutionStepStatus.RUNNING:
        return "running"
    if run.status in {OrchestrationRunStatus.ACCEPTED, OrchestrationRunStatus.QUEUED}:
        return "queued"
    return "running"


def _execution_item_view_status(item: ExecutionStepItem) -> str:
    if item.status is ExecutionStepItemStatus.COMPLETED:
        return "success"
    if item.status is ExecutionStepItemStatus.FAILED:
        return "failed"
    if item.status is ExecutionStepItemStatus.CANCELLED:
        return "cancelled"
    if item.status is ExecutionStepItemStatus.WAITING:
        return "waiting"
    if item.status is ExecutionStepItemStatus.RUNNING:
        return "running"
    if item.status in {
        ExecutionStepItemStatus.LATE_OBSERVED,
        ExecutionStepItemStatus.LATE_IGNORED,
    }:
        return "success"
    return "queued"


def _execution_item_owner_id(
    item: ExecutionStepItem,
    *,
    owner_kind: str,
) -> str | None:
    if item.owner is None or item.owner.owner_kind != owner_kind:
        return None
    return item.owner.owner_id


def _execution_item_summary(
    item: ExecutionStepItem | None,
) -> dict[str, object]:
    if item is None or not isinstance(item.summary_payload, dict):
        return {}
    return dict(item.summary_payload)


def _summary_text(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _summary_text_list(payload: dict[str, object], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list | tuple):
        return []
    values = [
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ]
    return list(dict.fromkeys(values))


def _summary_bool(payload: dict[str, object], key: str) -> bool:
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _context_render_snapshot_id(
    run: OrchestrationRun,
    *,
    summary: dict[str, object],
) -> str | None:
    return (
        _summary_text(summary, "context_render_snapshot_id")
        or _metadata_str(run, "context_render_snapshot_id")
    )


def _summary_text_from_items(
    items: tuple[ExecutionStepItem, ...],
    key: str,
) -> str | None:
    for item in items:
        value = _summary_text(_execution_item_summary(item), key)
        if value is not None:
            return value
    return None


def _summary_dict_from_items(
    items: tuple[ExecutionStepItem, ...],
    key: str,
) -> dict[str, object]:
    for item in items:
        value = _execution_item_summary(item).get(key)
        if isinstance(value, dict):
            return dict(value)
    return {}


def _llm_invocation_id_from_execution_items(
    items: tuple[ExecutionStepItem, ...],
) -> str | None:
    for item in items:
        if item.kind is not ExecutionStepItemKind.LLM_INVOCATION:
            continue
        owner_id = _execution_item_owner_id(item, owner_kind="llm_invocation")
        if owner_id is not None:
            return owner_id
        summary_id = _summary_text(_execution_item_summary(item), "llm_invocation_id")
        if summary_id is not None:
            return summary_id
    return None


def _tool_names_from_execution_items(
    items: tuple[ExecutionStepItem, ...],
) -> tuple[str, ...]:
    names: list[str] = []
    for item in items:
        if item.kind not in {
            ExecutionStepItemKind.TOOL_CALL,
            ExecutionStepItemKind.TOOL_RUN,
        }:
            continue
        summary = _execution_item_summary(item)
        name = _summary_text(summary, "tool_name") or _summary_text(summary, "tool_id")
        if name is not None and name not in names:
            names.append(name)
    return tuple(names)


def _tool_call_names_from_execution_items(
    items: tuple[ExecutionStepItem, ...],
) -> tuple[str, ...]:
    names: list[str] = []
    for item in items:
        summary = _execution_item_summary(item)
        raw_names = summary.get("tool_call_names")
        if isinstance(raw_names, (list, tuple)):
            for raw_name in raw_names:
                if not isinstance(raw_name, str):
                    continue
                name = raw_name.strip()
                if name and name not in names:
                    names.append(name)
    return tuple(names)


def _assistant_progress_session_item_ids_from_execution_items(
    items: tuple[ExecutionStepItem, ...],
) -> tuple[str, ...]:
    ids: list[str] = []
    for item in items:
        summary = _execution_item_summary(item)
        if _summary_text(summary, "message_kind") != "assistant_progress":
            continue
        raw_ids = summary.get("assistant_progress_item_ids")
        if not isinstance(raw_ids, (list, tuple)):
            raw_ids = summary.get("session_item_ids")
        if isinstance(raw_ids, (list, tuple)):
            for raw_id in raw_ids:
                if not isinstance(raw_id, str):
                    continue
                item_id = raw_id.strip()
                if item_id and item_id not in ids:
                    ids.append(item_id)
        item_id = _summary_text(summary, "session_item_id")
        if item_id is not None and item_id not in ids:
            ids.append(item_id)
    return tuple(ids)


def _tool_call_session_item_ids_from_execution_items(
    items: tuple[ExecutionStepItem, ...],
) -> tuple[str, ...]:
    ids: list[str] = []
    for item in items:
        summary = _execution_item_summary(item)
        raw_ids = summary.get("tool_call_session_item_ids")
        if not isinstance(raw_ids, (list, tuple)):
            continue
        for raw_id in raw_ids:
            if not isinstance(raw_id, str):
                continue
            item_id = raw_id.strip()
            if item_id and item_id not in ids:
                ids.append(item_id)
    return tuple(ids)


def _execution_tool_item_summary(
    summary: dict[str, object],
    item: ExecutionStepItem,
) -> str:
    tool_name = _summary_text(summary, "tool_name") or _summary_text(summary, "tool_id")
    status = _summary_text(summary, "status") or item.status.value
    if tool_name is not None:
        return f"{tool_name} · status: {status}"
    return f"Tool run status: {status}"


def _execution_tool_run_ids_for_run(
    run_query: OrchestrationRunQueryPort,
    turn_id: str,
) -> tuple[str, ...]:
    ids: list[str] = []
    for bundle in _execution_step_bundles(run_query, turn_id):
        for item in bundle.items:
            if item.kind is not ExecutionStepItemKind.TOOL_RUN:
                continue
            tool_run_id = _execution_item_owner_id(item, owner_kind="tool_run")
            if tool_run_id is not None and tool_run_id not in ids:
                ids.append(tool_run_id)
    return tuple(ids)


def _execution_llm_invocation_ids_for_run(
    run_query: OrchestrationRunQueryPort,
    turn_id: str,
) -> tuple[str, ...]:
    ids: list[str] = []
    for bundle in _execution_step_bundles(run_query, turn_id):
        invocation_id = _llm_invocation_id_from_execution_items(bundle.items)
        if invocation_id is not None and invocation_id not in ids:
            ids.append(invocation_id)
    return tuple(ids)


def _safe_llm_invocation(
    llm_query: WorkbenchLlmQueryPort | None,
    invocation_id: str | None,
) -> Any | None:
    if invocation_id is None or llm_query is None:
        return None
    try:
        return llm_query.get_invocation(invocation_id)
    except Exception:
        return None


def _linked_entity(
    *,
    entity_type: str,
    entity_id: str,
    label: str | None = None,
    owner: str | None = None,
    route: str | None = None,
    copy_value: str | None = None,
    trace: TraceContext | None = None,
) -> WorkbenchLinkedEntity:
    return WorkbenchLinkedEntity(
        type=entity_type,
        id=entity_id,
        label=label,
        owner=owner,
        route=route,
        copy_value=copy_value or entity_id,
        trace=trace,
    )


def _runtime_action(
    *,
    action_id: str,
    label: str,
    owner: str,
    risk: str = "normal",
    allowed: bool = True,
    disabled_reason: str | None = None,
    requires_confirmation: bool = False,
    reason_required: bool = False,
    method: str | None = None,
    endpoint: str | None = None,
    target: WorkbenchLinkedEntity | None = None,
    trace: TraceContext | None = None,
) -> WorkbenchAction:
    return WorkbenchAction(
        id=action_id,
        label=label,
        owner=owner,
        risk=risk,
        allowed=allowed,
        disabled_reason=disabled_reason,
        requires_confirmation=requires_confirmation,
        reason_required=reason_required,
        method=method,
        endpoint=endpoint,
        target=target,
        trace=trace,
    )


def _trace_route(trace: TraceContext) -> str:
    route = f"/trace/{trace.trace_id}"
    if trace.step_id:
        return f"{route}?step_id={trace.step_id}"
    return route


def _trace_entity(trace: TraceContext) -> WorkbenchLinkedEntity:
    return _linked_entity(
        entity_type="trace",
        entity_id=trace.trace_id,
        label="Trace",
        owner="events",
        route=_trace_route(trace),
        trace=trace,
    )


def _view_trace_action(trace: TraceContext) -> WorkbenchAction:
    return _runtime_action(
        action_id="view_trace",
        label="View trace",
        owner="events",
        target=_trace_entity(trace),
        trace=trace,
    )


def _linked_entities_for_trace(
    trace: TraceContext,
    *,
    artifacts: tuple[ArtifactPreview, ...] = (),
) -> tuple[WorkbenchLinkedEntity, ...]:
    entities: list[WorkbenchLinkedEntity] = []
    if trace.tool_run_id:
        entities.append(
            _linked_entity(
                entity_type="tool_run",
                entity_id=trace.tool_run_id,
                label="Tool run",
                owner="tool",
                route=_trace_route(trace),
                trace=trace,
            ),
        )
    if trace.llm_invocation_id:
        entities.append(
            _linked_entity(
                entity_type="llm_invocation",
                entity_id=trace.llm_invocation_id,
                label="LLM invocation",
                owner="llm",
                route=_trace_route(trace),
                trace=trace,
            ),
        )
    if trace.session_item_id:
        entities.append(
            _linked_entity(
                entity_type="session_item",
                entity_id=trace.session_item_id,
                label="Session item",
                owner="session",
                route=_trace_route(trace),
                trace=trace,
            ),
        )
    if trace.approval_request_id:
        entities.append(
            _linked_entity(
                entity_type="approval_request",
                entity_id=trace.approval_request_id,
                label="Approval request",
                owner="orchestration",
                route=_trace_route(trace),
                trace=trace,
            ),
        )
    artifact_ids = [trace.artifact_id] if trace.artifact_id else []
    artifact_ids.extend(artifact.artifact_id for artifact in artifacts)
    for artifact_id in dict.fromkeys(artifact_ids):
        entities.append(
            _linked_entity(
                entity_type="artifact",
                entity_id=artifact_id,
                label="Artifact",
                owner="artifacts",
                route=_trace_route(trace),
                trace=trace,
            ),
        )
    return _dedupe_linked_entities(tuple(entities))


def _dedupe_linked_entities(
    entities: tuple[WorkbenchLinkedEntity, ...],
) -> tuple[WorkbenchLinkedEntity, ...]:
    deduped: list[WorkbenchLinkedEntity] = []
    seen: set[tuple[str, str]] = set()
    for entity in entities:
        key = (entity.type, entity.id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entity)
    return tuple(deduped)


def _step_actions(
    run: OrchestrationRun,
    *,
    trace: TraceContext,
    step_type: str,
    status: str,
    artifacts: tuple[ArtifactPreview, ...],
) -> tuple[WorkbenchAction, ...]:
    actions: list[WorkbenchAction] = [_view_trace_action(trace)]
    for artifact in artifacts:
        if artifact.preview_url:
            actions.append(
                _runtime_action(
                    action_id=f"view_artifact:{artifact.artifact_id}",
                    label="View artifact",
                    owner="artifacts",
                    method="GET",
                    endpoint=artifact.preview_url,
                    target=_linked_entity(
                        entity_type="artifact",
                        entity_id=artifact.artifact_id,
                        label=artifact.name,
                        owner="artifacts",
                        route=_trace_route(trace),
                        trace=trace,
                    ),
                    trace=trace,
                ),
            )
        if artifact.download_url:
            actions.append(
                _runtime_action(
                    action_id=f"download_artifact:{artifact.artifact_id}",
                    label="Download artifact",
                    owner="artifacts",
                    method="GET",
                    endpoint=artifact.download_url,
                    target=_linked_entity(
                        entity_type="artifact",
                        entity_id=artifact.artifact_id,
                        label=artifact.name,
                        owner="artifacts",
                        route=_trace_route(trace),
                        trace=trace,
                    ),
                    trace=trace,
                ),
            )
    if (
        step_type == "approval_required"
        and trace.approval_request_id
        and _run_is_waiting_for_approval(run)
    ):
        approval_endpoint = (
            f"/turns/{run.id}/approvals/{trace.approval_request_id}"
        )
        for action_id, label, risk in (
            ("allow_once", "Allow once", "controlled"),
            ("allow_for_session", "Allow for session", "controlled"),
            ("always_for_agent", "Always allow for agent", "controlled"),
            ("deny", "Deny", "dangerous"),
        ):
            actions.append(
                _runtime_action(
                    action_id=f"approval:{action_id}",
                    label=label,
                    owner="orchestration",
                    risk=risk,
                    method="POST",
                    endpoint=approval_endpoint,
                    target=_linked_entity(
                        entity_type="approval_request",
                        entity_id=trace.approval_request_id,
                        label="Approval request",
                        owner="orchestration",
                        route=_trace_route(trace),
                        trace=trace,
                    ),
                    trace=trace,
                ),
            )
    if step_type == "missing_access":
        actions.append(
            _runtime_action(
                action_id="open_access_inventory",
                label="Open access inventory",
                owner="access",
                target=_linked_entity(
                    entity_type="access_inventory",
                    entity_id="access",
                    label="Access inventory",
                    owner="access",
                    route="/settings/access-assets",
                    trace=trace,
                ),
                trace=trace,
            ),
        )
    if step_type == "error" and status == "failed":
        actions.append(_cancelled_or_failed_trace_action(trace))
    return tuple(actions)


def _cancelled_or_failed_trace_action(trace: TraceContext) -> WorkbenchAction:
    return _runtime_action(
        action_id="inspect_failure",
        label="Inspect failure",
        owner="orchestration",
        risk="controlled",
        target=_trace_entity(trace),
        trace=trace,
    )


def _run_actions(
    run: OrchestrationRun,
    *,
    trace: TraceContext,
) -> tuple[WorkbenchAction, ...]:
    cancellable = run.status not in {
        OrchestrationRunStatus.COMPLETED,
        OrchestrationRunStatus.FAILED,
        OrchestrationRunStatus.CANCELLED,
    }
    return (
        _view_trace_action(trace),
        _runtime_action(
            action_id="open_operations",
            label="Open operations",
            owner="orchestration",
            target=_linked_entity(
                entity_type="operations_view",
                entity_id="orchestration",
                label="Orchestration operations",
                owner="orchestration",
                route="/operations/orchestration",
                trace=trace,
            ),
            trace=trace,
        ),
        _runtime_action(
            action_id="cancel_run",
            label="Cancel run",
            owner="orchestration",
            risk="controlled",
            allowed=cancellable,
            disabled_reason=None if cancellable else "Run is already terminal.",
            requires_confirmation=True,
            reason_required=True,
            method="POST",
            endpoint=f"/turns/{run.id}/cancel",
            target=_linked_entity(
                entity_type="run",
                entity_id=run.id,
                label="Run",
                owner="orchestration",
                route=_trace_route(trace),
                trace=trace,
            ),
            trace=trace,
        ),
    )


_TERMINAL_TOOL_RUN_STATUSES = {
    ToolRunStatus.SUCCEEDED,
    ToolRunStatus.FAILED,
    ToolRunStatus.CANCELLED,
    ToolRunStatus.TIMED_OUT,
}

_FAILED_TOOL_RUN_STATUSES = {
    ToolRunStatus.FAILED,
    ToolRunStatus.CANCELLED,
    ToolRunStatus.TIMED_OUT,
}


def _tool_runs_for_run(
    tool_query: WorkbenchToolRunQueryPort | None,
    run_id: str,
) -> tuple[ToolRun, ...]:
    if tool_query is None:
        return ()
    try:
        tool_runs = tool_query.list_tool_runs()
    except Exception:
        return ()
    related: list[ToolRun] = []
    for tool_run in tool_runs:
        if _tool_run_orchestration_run_id(tool_run) == run_id:
            related.append(tool_run)
    return tuple(
        sorted(
            related,
            key=lambda item: item.started_at or item.created_at,
        ),
    )


def _display_tool_runs(
    run_query: OrchestrationRunQueryPort,
    tool_query: WorkbenchToolRunQueryPort | None,
    run: OrchestrationRun,
    *,
    candidate_runs: list[OrchestrationRun] | None = None,
    tool_runs: list[ToolRun] | None = None,
) -> tuple[_DisplayToolRun, ...]:
    return _tool_runs_for_runs(
        run_query,
        tool_query,
        _display_source_runs(run_query, run, candidate_runs=candidate_runs),
        tool_runs=tool_runs,
    )


def _display_source_runs(
    run_query: OrchestrationRunQueryPort,
    run: OrchestrationRun,
    *,
    candidate_runs: list[OrchestrationRun] | None = None,
) -> tuple[OrchestrationRun, ...]:
    runs = [run]
    seen = {run.id}
    for child_run in _linked_child_runs(
        run_query,
        run,
        candidate_runs=candidate_runs,
    ):
        if child_run.id in seen:
            continue
        runs.append(child_run)
        seen.add(child_run.id)
    return tuple(runs)


def _linked_child_runs(
    run_query: OrchestrationRunQueryPort,
    run: OrchestrationRun,
    *,
    candidate_runs: list[OrchestrationRun] | None = None,
) -> tuple[OrchestrationRun, ...]:
    children: list[OrchestrationRun] = []
    seen: set[str] = set()
    for child_run_id in _linked_child_run_ids(run):
        if child_run_id == run.id or child_run_id in seen:
            continue
        try:
            children.append(run_query.get_run(child_run_id))
            seen.add(child_run_id)
        except Exception:
            continue
    if candidate_runs is None:
        try:
            candidates = run_query.list_runs()
        except Exception:
            candidates = []
    else:
        candidates = candidate_runs
    for candidate in candidates:
        if candidate.id == run.id or candidate.id in seen:
            continue
        spawn_payload = candidate.metadata.get("sessions_spawn")
        if not isinstance(spawn_payload, dict):
            continue
        requester_run_id = _optional_text(spawn_payload.get("requester_run_id"))
        if requester_run_id != run.id:
            continue
        children.append(candidate)
        seen.add(candidate.id)
    return tuple(
        sorted(
            children,
            key=lambda item: item.started_at or item.created_at,
        ),
    )


def _linked_child_run_ids(run: OrchestrationRun) -> tuple[str, ...]:
    ids: list[str] = []
    followup_payload = run.metadata.get("sessions_spawn_followup")
    if isinstance(followup_payload, dict):
        child_run_id = _optional_text(followup_payload.get("child_run_id"))
        if child_run_id is not None:
            ids.append(child_run_id)
    child_run_id = _metadata_str(run, "child_run_id")
    if child_run_id is not None:
        ids.append(child_run_id)
    return tuple(dict.fromkeys(ids))


def _tool_runs_for_runs(
    run_query: OrchestrationRunQueryPort,
    tool_query: WorkbenchToolRunQueryPort | None,
    runs: tuple[OrchestrationRun, ...],
    *,
    tool_runs: list[ToolRun] | None = None,
) -> tuple[_DisplayToolRun, ...]:
    if tool_query is None:
        return ()
    if tool_runs is None:
        try:
            tool_runs = tool_query.list_tool_runs()
        except Exception:
            return ()
    run_by_id = {run.id: run for run in runs}
    tool_id_to_run: dict[str, OrchestrationRun] = {}
    for run in runs:
        for tool_run_id in (
            *run.pending_tool_run_ids,
            *_execution_tool_run_ids_for_run(run_query, run.id),
        ):
            tool_id_to_run.setdefault(tool_run_id, run)
    related: list[_DisplayToolRun] = []
    seen_tool_run_ids: set[str] = set()
    for tool_run in tool_runs:
        source_run: OrchestrationRun | None = None
        metadata_run_id = _tool_run_orchestration_run_id(tool_run)
        if metadata_run_id is not None:
            source_run = run_by_id.get(metadata_run_id)
        if source_run is None:
            source_run = tool_id_to_run.get(tool_run.id)
        if source_run is None or tool_run.id in seen_tool_run_ids:
            continue
        related.append(_DisplayToolRun(source_run=source_run, tool_run=tool_run))
        seen_tool_run_ids.add(tool_run.id)
    return tuple(
        sorted(
            related,
            key=lambda item: item.tool_run.started_at or item.tool_run.created_at,
        ),
    )


def _tool_run_orchestration_run_id(tool_run: ToolRun) -> str | None:
    value = tool_run.metadata.get("orchestration_run_id")
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _tool_status(tool_run: ToolRun) -> str:
    if tool_run.status is ToolRunStatus.SUCCEEDED:
        return "success"
    if tool_run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}:
        return "failed"
    if tool_run.status is ToolRunStatus.CANCELLED:
        return "cancelled"
    if tool_run.status in {
        ToolRunStatus.RUNNING,
        ToolRunStatus.DISPATCHING,
        ToolRunStatus.CANCEL_REQUESTED,
    }:
        return "running"
    if tool_run.status in {ToolRunStatus.CREATED, ToolRunStatus.QUEUED}:
        return "queued"
    return "unknown"


def _tool_badge_tone(tool_run: ToolRun) -> str:
    if tool_run.status is ToolRunStatus.SUCCEEDED:
        return "success"
    if tool_run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}:
        return "danger"
    if tool_run.status in {ToolRunStatus.CANCELLED, ToolRunStatus.CANCEL_REQUESTED}:
        return "warning"
    return "info"


def _tool_call_summary(tool_run: ToolRun | None) -> str:
    if tool_run is None:
        return "Waiting for pending tool runs to finish."
    return f"{tool_run.tool_id} · {_compact_payload(tool_run.input_payload, limit=180)}"


def _tool_step_summary(tool_run: ToolRun) -> str:
    lines = [
        f"Request: {_compact_payload(tool_run.input_payload, limit=180)}",
    ]
    if tool_run.status in _TERMINAL_TOOL_RUN_STATUSES:
        lines.append(f"Result: {_truncate(_tool_result_summary(tool_run), limit=260)}")
    else:
        lines.append(f"Status: {tool_run.status.value}")
    return "\n".join(lines)


def _tool_result_summary(tool_run: ToolRun) -> str:
    if tool_run.status is not ToolRunStatus.SUCCEEDED:
        error = tool_run.error
        if error is not None:
            return error.message
        return f"Tool run {tool_run.status.value}."
    result = tool_run.result
    if result is None:
        return "Tool completed."
    for block in result.blocks:
        if block.get("type") == "text":
            text = str(block.get("text") or "").strip()
            if text:
                return text
    return "Tool completed."


def _tool_artifacts(
    tool_run: ToolRun,
    *,
    artifact_query: WorkbenchArtifactQueryPort | None = None,
) -> tuple[ArtifactPreview, ...]:
    result = tool_run.result
    if result is None:
        return ()
    previews: list[ArtifactPreview] = []
    for block in result.blocks:
        block_type = str(block.get("type") or "")
        if block_type not in {"image_ref", "file_ref"}:
            continue
        artifact_id = str(block.get("artifact_id") or "").strip()
        if not artifact_id:
            continue
        name = str(block.get("name") or artifact_id).strip() or artifact_id
        kind = "image" if block_type == "image_ref" else "file"
        artifact = _safe_get_artifact(artifact_query, artifact_id)
        previews.append(
            _artifact_preview_from_block(
                block,
                artifact=artifact,
                fallback_name=name,
                fallback_kind=kind,
            ),
        )
    return tuple(previews)


def _artifact_preview_from_block(
    block: dict[str, Any],
    *,
    artifact: Any | None,
    fallback_name: str,
    fallback_kind: str,
) -> ArtifactPreview:
    artifact_id = str(block.get("artifact_id") or "").strip()
    if artifact is None:
        return ArtifactPreview(
            artifact_id=artifact_id,
            name=fallback_name,
            kind=fallback_kind,
            size_bytes=_optional_int(block.get("size_bytes")),
            mime_type=_optional_text(block.get("mime_type")),
            width=_optional_positive_int(block.get("width")),
            height=_optional_positive_int(block.get("height")),
            preview_url=_optional_url(block.get("preview_url"))
            or (
                f"/artifacts/{artifact_id}/preview"
                if fallback_kind == "image"
                else None
            ),
            download_url=_optional_url(block.get("download_url"))
            or f"/artifacts/{artifact_id}/download",
        )
    kind = getattr(artifact, "kind", fallback_kind)
    kind_value = getattr(kind, "value", kind)
    normalized_kind = str(kind_value or fallback_kind)
    name = _optional_text(getattr(artifact, "name", None)) or fallback_name
    return ArtifactPreview(
        artifact_id=artifact_id,
        name=name,
        kind=normalized_kind,
        size_bytes=_optional_int(getattr(artifact, "size_bytes", None)),
        mime_type=_optional_text(getattr(artifact, "mime_type", None))
        or _optional_text(block.get("mime_type")),
        width=_optional_positive_int(getattr(artifact, "width", None))
        or _optional_positive_int(block.get("width")),
        height=_optional_positive_int(getattr(artifact, "height", None))
        or _optional_positive_int(block.get("height")),
        preview_url=_optional_url(block.get("preview_url"))
        or (
            f"/artifacts/{artifact_id}/preview"
            if normalized_kind == "image"
            else None
        ),
        download_url=_optional_url(block.get("download_url"))
        or f"/artifacts/{artifact_id}/download",
        metadata=_metadata_dict(getattr(artifact, "metadata", None)),
    )


def _cover_artifact(
    tool_runs: tuple[ToolRun, ...],
    *,
    artifact_query: WorkbenchArtifactQueryPort | None,
) -> ArtifactPreview | None:
    for tool_run in sorted(
        tool_runs,
        key=lambda item: item.completed_at or item.started_at or item.created_at,
        reverse=True,
    ):
        if tool_run.status not in _TERMINAL_TOOL_RUN_STATUSES:
            continue
        for artifact in _tool_artifacts(tool_run, artifact_query=artifact_query):
            if artifact.kind == "image":
                return artifact
    return None


def _safe_get_artifact(
    artifact_query: WorkbenchArtifactQueryPort | None,
    artifact_id: str,
) -> Any | None:
    if artifact_query is None:
        return None
    try:
        return artifact_query.get_artifact(artifact_id)
    except Exception:
        return None


def _compact_payload(value: Any, *, limit: int) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        text = str(value)
    return _truncate(text, limit=limit)


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def _optional_positive_int(value: object) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _optional_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _metadata_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    metadata: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        if item is None or isinstance(item, (str, int, float, bool)):
            metadata[key] = item
    return metadata


def _agent_ref(
    run: OrchestrationRun,
    agent_query: WorkbenchAgentQueryPort | None,
) -> RuntimeRef:
    agent_id = run.agent_id or "unknown"
    if agent_query is not None and run.agent_id is not None:
        try:
            profile = agent_query.get_profile(run.agent_id)
        except Exception:
            profile = None
        if profile is not None:
            identity = getattr(profile, "identity", None)
            display_name = _optional_text(getattr(identity, "display_name", None))
            name = display_name or _optional_text(getattr(profile, "name", None))
            if name is not None:
                return RuntimeRef(id=agent_id, name=name)
    return RuntimeRef(id=agent_id, name=run.agent_id or "Unknown Agent")


def _llm_ref(
    run: OrchestrationRun,
    llm_query: WorkbenchLlmQueryPort | None,
    *,
    run_query: OrchestrationRunQueryPort | None = None,
) -> RuntimeRef:
    llm_id = _llm_id(run) or _llm_invocation_llm_id(
        _llm_invocation_for_run(run_query, llm_query, run),
    )
    if llm_id is None:
        return RuntimeRef(id="auto", name="Auto")
    if llm_query is not None:
        try:
            profile = llm_query.get_profile(llm_id)
        except Exception:
            profile = None
        if profile is not None:
            provider = getattr(getattr(profile, "provider", None), "value", None)
            model_name = _optional_text(getattr(profile, "model_name", None))
            if model_name is not None:
                label = f"{provider}/{model_name}" if provider else model_name
                return RuntimeRef(id=llm_id, name=label)
    return RuntimeRef(id=llm_id, name=llm_id)


def _llm_invocation_for_run(
    run_query: OrchestrationRunQueryPort | None,
    llm_query: WorkbenchLlmQueryPort | None,
    run: OrchestrationRun,
) -> Any | None:
    invocation_ids: list[str] = []
    if run_query is not None:
        invocation_ids.extend(_execution_llm_invocation_ids_for_run(run_query, run.id))
    if not invocation_ids or llm_query is None:
        return None
    for invocation_id in dict.fromkeys(invocation_ids):
        invocation = _safe_llm_invocation(llm_query, invocation_id)
        if invocation is not None:
            return invocation
    return None


def _llm_invocations_for_runs(
    run_query: OrchestrationRunQueryPort,
    llm_query: WorkbenchLlmQueryPort | None,
    runs: tuple[OrchestrationRun, ...],
) -> tuple[Any, ...]:
    invocations: list[Any] = []
    seen: set[str] = set()
    for run in runs:
        for invocation_id in _execution_llm_invocation_ids_for_run(run_query, run.id):
            if invocation_id in seen:
                continue
            invocation = _safe_llm_invocation(llm_query, invocation_id)
            resolved_invocation_id = _optional_text(getattr(invocation, "id", None))
            if invocation is None or resolved_invocation_id is None:
                continue
            invocations.append(invocation)
            seen.add(resolved_invocation_id)
    return tuple(invocations)


def _llm_invocation_llm_id(invocation: Any | None) -> str | None:
    if invocation is None:
        return None
    return _optional_text(getattr(invocation, "llm_id", None))


def _llm_started_at(run: OrchestrationRun, invocation: Any | None) -> datetime | None:
    return getattr(invocation, "started_at", None) or run.started_at or run.updated_at


def _llm_completed_at(run: OrchestrationRun, invocation: Any | None) -> datetime | None:
    return getattr(invocation, "completed_at", None) or run.updated_at


def _inspector_for_run(
    run: OrchestrationRun,
    *,
    session_runs: tuple[OrchestrationRun, ...],
    display_tool_runs: tuple[_DisplayToolRun, ...],
    llm_invocations: tuple[Any, ...],
    metrics: RunMetrics,
    cover_artifact: ArtifactPreview | None,
    agent_ref: RuntimeRef,
    model_ref: RuntimeRef,
    trace: TraceContext,
    agent_query: WorkbenchAgentQueryPort | None,
    timeline: tuple[WorkbenchTimelineItem, ...] = (),
) -> WorkbenchInspectorView:
    agent_profile = _safe_agent_profile(agent_query, run.agent_id)
    linked_assets = _linked_assets_for_run(
        run,
        display_tool_runs=display_tool_runs,
        llm_invocations=llm_invocations,
        cover_artifact=cover_artifact,
        trace=trace,
    )
    quick_actions = tuple(
        action
        for action in _run_actions(run, trace=trace)
        if action.id != "cancel_run" or action.allowed
    )
    return WorkbenchInspectorView(
        tabs=("overview", "debug", "memory", "agent"),
        active_tab="overview",
        overview=(
            WorkbenchKeyValueSection(
                id="runtime",
                title="Runtime",
                items=(
                    _kv("Status", run.status.value, tone=_tone_for_status(run.status.value)),
                    _kv("Stage", run.stage.value),
                    _kv("Waiting", run.waiting_reason or "-"),
                    _kv("Duration", _duration_label(_duration_ms(run))),
                ),
            ),
            WorkbenchKeyValueSection(
                id="metrics",
                title="Metrics",
                items=(
                    _kv("Tool calls", str(metrics.tool_calls)),
                    _kv("LLM calls", str(metrics.llm_calls)),
                    _kv("Tokens", str(metrics.tokens)),
                    _kv(
                        "Estimated cost",
                        (
                            f"${metrics.estimated_cost_usd:.3f}"
                            if metrics.estimated_cost_usd is not None
                            else "-"
                        ),
                    ),
                ),
            ),
        ),
        debug=(
            WorkbenchKeyValueSection(
                id="ids",
                title="Identifiers",
                items=(
                    _kv("Trace ID", trace.trace_id, route=_trace_route(trace)),
                    _kv("Run ID", run.id),
                    _kv("Session", run.session_key or "-"),
                    _kv("Current turn", _turn_id(run)),
                    _kv("Lane", run.lane_key or "-"),
                    _kv("Worker", run.worker_id or "-"),
                ),
                actions=(_view_trace_action(trace),),
            ),
            WorkbenchKeyValueSection(
                id="step_counts",
                title="Step Counts",
                items=(
                    _kv("Turns", str(len(session_runs))),
                    _kv("Tool runs", str(len({item.tool_run.id for item in display_tool_runs}))),
                    _kv("LLM invocations", str(len(llm_invocations))),
                ),
            ),
            WorkbenchKeyValueSection(
                id="timeline_diagnostics",
                title="Timeline Diagnostics",
                items=_timeline_diagnostic_items(timeline),
            ),
        ),
        memory=(
            WorkbenchKeyValueSection(
                id="memory_context",
                title="Memory Context",
                items=(
                    _kv("Agent", run.agent_id or "-"),
                    _kv("Memory tools", str(_memory_tool_run_count(display_tool_runs))),
                    _kv("Prompt mode", _metadata_str(run, "prompt_mode") or "-"),
                ),
            ),
        ),
        agent=(
            WorkbenchKeyValueSection(
                id="agent_runtime",
                title="Agent Runtime",
                items=(
                    _kv("Agent", agent_ref.name),
                    _kv("Agent ID", agent_ref.id),
                    _kv("Model", model_ref.name),
                    _kv("Model ID", model_ref.id),
                    _kv(
                        "Default model",
                        _agent_default_llm_id(agent_profile) or "-",
                    ),
                    _kv(
                        "Memory scope",
                        _agent_memory_scope(agent_profile) or "-",
                    ),
                ),
            ),
        ),
        current_turn_summary=_instruction_summary(run),
        linked_assets=linked_assets,
        quick_actions=quick_actions,
    )


def _kv(
    label: str,
    value: object,
    *,
    tone: str = "neutral",
    route: str | None = None,
) -> WorkbenchKeyValueItem:
    return WorkbenchKeyValueItem(
        label=label,
        value=str(value),
        tone=tone,
        route=route,
        copy_value=str(value),
    )


def _timeline_diagnostic_items(
    timeline: tuple[WorkbenchTimelineItem, ...],
) -> tuple[WorkbenchKeyValueItem, ...]:
    response_item_count = sum(
        1 for item in timeline if item.source_refs.get("llm_response_item_id")
    )
    tool_lifecycle_count = sum(
        1 for item in timeline if item.kind in {"tool_call", "tool_run", "tool_result"}
    )
    hidden_reasoning_count = sum(
        1
        for item in timeline
        if item.kind == "reasoning_summary"
        and bool(item.content.get("reasoning_hidden"))
    )
    provider_external_count = sum(
        1 for item in timeline if item.kind == "provider_external_item"
    )
    return (
        _kv("Timeline items", str(len(timeline))),
        _kv("LLM response items", str(response_item_count)),
        _kv("Tool lifecycle items", str(tool_lifecycle_count)),
        _kv("Hidden reasoning items", str(hidden_reasoning_count)),
        _kv("Provider external items", str(provider_external_count)),
    )


def _tone_for_status(status: str) -> str:
    if status in {"completed", "success", "connected"}:
        return "success"
    if status in {"queued", "waiting"}:
        return "warning"
    if status in {"failed", "cancelled"}:
        return "danger"
    if status in {"running", "accepted"}:
        return "info"
    return "neutral"


def _duration_label(duration_ms: int | None) -> str:
    if duration_ms is None:
        return "-"
    if duration_ms < 1000:
        return f"{duration_ms}ms"
    seconds = round(duration_ms / 1000)
    minutes = seconds // 60
    remaining = seconds % 60
    if minutes:
        return f"{minutes}m {remaining}s"
    return f"{remaining}s"


def _safe_agent_profile(
    agent_query: WorkbenchAgentQueryPort | None,
    agent_id: str | None,
) -> Any | None:
    if agent_query is None or agent_id is None:
        return None
    try:
        return agent_query.get_profile(agent_id)
    except Exception:
        return None


def _agent_default_llm_id(agent_profile: Any | None) -> str | None:
    if agent_profile is None:
        return None
    routing = getattr(agent_profile, "llm_routing_policy", None)
    return _optional_text(getattr(routing, "default_llm_id", None))


def _agent_memory_scope(agent_profile: Any | None) -> str | None:
    if agent_profile is None:
        return None
    memory = getattr(agent_profile, "memory", None)
    if not bool(getattr(memory, "enabled", False)):
        return "disabled"
    if hasattr(memory, "effective_scope_ref"):
        agent_id = _optional_text(getattr(agent_profile, "id", None))
        if agent_id is not None:
            return _optional_text(memory.effective_scope_ref(agent_id))
    return _optional_text(getattr(memory, "scope_ref", None)) or "agent default"



def _memory_tool_run_count(display_tool_runs: tuple[_DisplayToolRun, ...]) -> int:
    return sum(
        1
        for item in display_tool_runs
        if item.tool_run.tool_id.startswith("memory_")
    )


def _linked_assets_for_run(
    run: OrchestrationRun,
    *,
    display_tool_runs: tuple[_DisplayToolRun, ...],
    llm_invocations: tuple[Any, ...],
    cover_artifact: ArtifactPreview | None,
    trace: TraceContext,
) -> tuple[WorkbenchLinkedEntity, ...]:
    entities: list[WorkbenchLinkedEntity] = [
        _linked_entity(
            entity_type="run",
            entity_id=run.id,
            label="Run",
            owner="orchestration",
            route=_trace_route(trace),
            trace=trace,
        ),
    ]
    for invocation in llm_invocations:
        invocation_id = _optional_text(getattr(invocation, "id", None))
        if invocation_id is None:
            continue
        entities.append(
            _linked_entity(
                entity_type="llm_invocation",
                entity_id=invocation_id,
                label="LLM invocation",
                owner="llm",
                route=_trace_route(trace),
                trace=trace,
            ),
        )
    for display_tool_run in display_tool_runs:
        tool_run = display_tool_run.tool_run
        entities.append(
            _linked_entity(
                entity_type="tool_run",
                entity_id=tool_run.id,
                label=tool_run.tool_id,
                owner="tool",
                route=_trace_route(trace),
                trace=trace,
            ),
        )
        for artifact in _tool_artifacts(tool_run, artifact_query=None):
            entities.append(
                _linked_entity(
                    entity_type="artifact",
                    entity_id=artifact.artifact_id,
                    label=artifact.name,
                    owner="artifacts",
                    route=_trace_route(trace),
                    trace=trace,
                ),
            )
    if cover_artifact is not None:
        entities.append(
            _linked_entity(
                entity_type="artifact",
                entity_id=cover_artifact.artifact_id,
                label=cover_artifact.name,
                owner="artifacts",
                route=_trace_route(trace),
                trace=trace,
            ),
        )
    return _dedupe_linked_entities(tuple(entities))


def _run_title(run: OrchestrationRun) -> str:
    for key in ("thread_title", "title", "summary"):
        value = _metadata_str(run, key)
        if value is not None:
            return _truncate(value, limit=72)
    return _truncate(_instruction_summary(run), limit=72) or run.id


def _instruction_summary(run: OrchestrationRun) -> str:
    if run.inbound_instruction.source == "sessions_spawn_followup":
        followup_payload = run.metadata.get("sessions_spawn_followup")
        if isinstance(followup_payload, dict):
            child_session_key = _optional_text(followup_payload.get("child_session_key"))
            child_run_id = _optional_text(followup_payload.get("child_run_id"))
            if child_session_key is not None and child_run_id is not None:
                return f"Child session completed: {child_session_key} · {child_run_id}"
            if child_run_id is not None:
                return f"Child session completed: {child_run_id}"
        return "Child session completed."
    try:
        return describe_content_for_text_fallback(run.inbound_instruction.content)
    except Exception:
        return str(run.inbound_instruction.content or run.inbound_instruction.source)


def _llm_summary(run: OrchestrationRun, *, llm_invocation: Any | None = None) -> str:
    invocation_usage = _llm_invocation_token_total(llm_invocation)
    finish_reason = _optional_text(
        getattr(getattr(llm_invocation, "result", None), "finish_reason", None),
    )
    if invocation_usage is not None and finish_reason is not None:
        return f"Model response used {invocation_usage} tokens and finished with {finish_reason}."
    if invocation_usage is not None:
        return f"Model response used {invocation_usage} tokens."
    invocation_status = getattr(getattr(llm_invocation, "status", None), "value", None)
    if isinstance(invocation_status, str) and invocation_status == "failed":
        error = getattr(llm_invocation, "error", None)
        message = _optional_text(getattr(error, "message", None))
        return message or "Model invocation failed."
    if run.stage is OrchestrationRunStage.LLM:
        return "Model invocation is in progress."
    if run.status in {OrchestrationRunStatus.COMPLETED, OrchestrationRunStatus.WAITING}:
        return "Model response was processed by orchestration."
    return f"Run stage: {run.stage.value}."


def _llm_invocation_token_total(invocation: Any | None) -> int | None:
    if invocation is None:
        return None
    result = getattr(invocation, "result", None)
    usage = getattr(result, "usage", None)
    if usage is None:
        return None
    total = getattr(usage, "total_tokens", None)
    if isinstance(total, int) and total >= 0:
        return total
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    parts = [item for item in (input_tokens, output_tokens) if isinstance(item, int)]
    return sum(parts) if parts else None


def _missing_access_payload(run: OrchestrationRun) -> dict[str, object] | None:
    if run.error is None or run.error.code != "access_not_ready":
        return None
    return dict(run.error.details)


def _missing_access_summary(payload: dict[str, object]) -> str:
    display_name = _optional_text(payload.get("display_name"))
    resource_type = _optional_text(payload.get("resource_type")) or "resource"
    resource_id = _optional_text(payload.get("resource_id")) or "unknown"
    access_payload = payload.get("access")
    requirements = _access_requirement_labels(access_payload)
    subject = display_name or f"{resource_type}:{resource_id}"
    if requirements:
        return (
            f"External access is not ready for {subject}: "
            f"{', '.join(requirements)}."
        )
    return f"External access is not ready for {subject}."


def _missing_access_entities(
    payload: dict[str, object],
) -> tuple[WorkbenchLinkedEntity, ...]:
    entities: list[WorkbenchLinkedEntity] = []
    resource_type = _optional_text(payload.get("resource_type")) or "resource"
    resource_id = _optional_text(payload.get("resource_id"))
    if resource_id is not None:
        entities.append(
            _linked_entity(
                entity_type=f"{resource_type}_access",
                entity_id=resource_id,
                label=_optional_text(payload.get("display_name")) or resource_id,
                owner="access",
                route="/settings/access-assets",
            ),
        )
    for requirement in _access_requirement_labels(payload.get("access")):
        entities.append(
            _linked_entity(
                entity_type="access_requirement",
                entity_id=requirement,
                label=requirement,
                owner="access",
                route="/settings/access-assets",
            ),
        )
    return _dedupe_linked_entities(tuple(entities))


def _access_requirement_labels(value: object) -> tuple[str, ...]:
    if not isinstance(value, dict):
        return ()
    labels: list[str] = []
    requirement_sets = value.get("requirement_sets")
    if not isinstance(requirement_sets, list):
        return ()
    for requirement_set in requirement_sets:
        if not isinstance(requirement_set, dict):
            continue
        checks = requirement_set.get("checks")
        if not isinstance(checks, list):
            continue
        for check in checks:
            if not isinstance(check, dict):
                continue
            requirement = _optional_text(check.get("requirement"))
            if requirement is not None:
                labels.append(requirement)
    return tuple(dict.fromkeys(labels))


def _approval_detail(payload: dict[str, object]) -> ApprovalRequestDetail:
    tool_arguments = _approval_tool_arguments(payload.get("tool_arguments"))
    tool_name = _optional_text(payload.get("tool_name"))
    draft_id = (
        _optional_text(tool_arguments.get("draft_id"))
        if tool_name == "skill_draft_apply"
        else None
    )
    return ApprovalRequestDetail(
        request_id=str(payload.get("request_id") or payload.get("id") or ""),
        effect_id=str(payload.get("effect_id") or ""),
        label=str(payload.get("label") or ""),
        reason=str(payload.get("reason") or ""),
        tool_name=tool_name,
        tool_ids=tuple(
            str(item)
            for item in payload.get("tool_ids", ()) or ()
            if str(item).strip()
        ),
        tool_arguments=tool_arguments,
        execution_mode=_optional_text(payload.get("execution_mode")),
        execution_strategy=_optional_text(payload.get("execution_strategy")),
        execution_environment=_optional_text(payload.get("execution_environment")),
        draft_id=draft_id,
    )


def _approval_tool_arguments(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    allowed = {"draft_id", "reason"}
    result: dict[str, object] = {}
    for key, raw in value.items():
        key_text = str(key)
        if key_text not in allowed:
            continue
        if raw is None:
            continue
        if isinstance(raw, (str, int, float, bool)):
            result[key_text] = raw
        else:
            result[key_text] = _truncate(str(raw), limit=200)
    return result


def _approval_entities(
    approval: ApprovalRequestDetail | None,
) -> tuple[WorkbenchLinkedEntity, ...]:
    if approval is None or not approval.draft_id:
        return ()
    return (
        _linked_entity(
            entity_type="skill_draft",
            entity_id=approval.draft_id,
            label="Skill draft",
            owner="skills",
            route="/settings/skills",
        ),
    )


def _approval_summary(payload: dict[str, object]) -> str:
    reason = payload.get("reason")
    if isinstance(reason, str) and reason.strip():
        return reason.strip()
    capability = payload.get("capability")
    if isinstance(capability, str) and capability.strip():
        return f"Approval is required for {capability.strip()}."
    return "Approval is required before the run can continue."


def _llm_step_status(run: OrchestrationRun) -> str:
    if run.status is OrchestrationRunStatus.FAILED:
        return "failed"
    if run.stage is OrchestrationRunStage.LLM:
        return "running"
    if run.status is OrchestrationRunStatus.WAITING:
        return "success"
    if run.status is OrchestrationRunStatus.COMPLETED:
        return "success"
    return "running" if run.status is OrchestrationRunStatus.RUNNING else run.status.value


def _status_strip(run: OrchestrationRun) -> RunStatusStrip | None:
    if run.status in {
        OrchestrationRunStatus.COMPLETED,
        OrchestrationRunStatus.CANCELLED,
        OrchestrationRunStatus.FAILED,
    }:
        return None
    label = {
        OrchestrationRunStatus.ACCEPTED: "Accepted",
        OrchestrationRunStatus.QUEUED: "Queued for execution",
        OrchestrationRunStatus.RUNNING: f"Running: {run.stage.value}",
        OrchestrationRunStatus.WAITING: run.waiting_reason or "Waiting",
    }.get(run.status, run.status.value)
    return RunStatusStrip(
        label=label,
        eta_ms=None,
        queue_wait_ms=_span_ms(run.queued_at, run.started_at or run.updated_at) or 0,
    )


def _metrics(
    run: OrchestrationRun,
    *,
    related_tool_runs: tuple[ToolRun, ...] = (),
    llm_invocations: tuple[Any, ...] = (),
) -> RunMetrics:
    known_tool_ids = {
        *run.pending_tool_run_ids,
        *(tool_run.id for tool_run in related_tool_runs),
    }
    prompt_report = run.metadata.get("prompt_report")
    token_total = _token_total_from_invocations(llm_invocations)
    if not llm_invocations and isinstance(prompt_report, dict):
        raw_total = prompt_report.get("token_total") or prompt_report.get("total_tokens")
        if isinstance(raw_total, int):
            token_total = max(raw_total, 0)
    return RunMetrics(
        tool_calls=len(known_tool_ids),
        llm_calls=(
            len(llm_invocations)
            if llm_invocations
            else max(run.current_step, 1 if _llm_id(run) else 0)
        ),
        tokens=token_total,
        estimated_cost_usd=None,
    )


def _metrics_for_runs(
    runs: tuple[OrchestrationRun, ...],
    *,
    related_tool_runs: tuple[ToolRun, ...] = (),
    llm_invocations: tuple[Any, ...] = (),
    timeline: tuple[WorkbenchTimelineItem, ...] = (),
) -> RunMetrics:
    known_tool_ids = {tool_run.id for tool_run in related_tool_runs}
    known_tool_call_ids: set[str] = set()
    known_llm_invocation_ids = {
        invocation_id
        for invocation in llm_invocations
        if (invocation_id := _optional_text(getattr(invocation, "id", None)))
        is not None
    }
    for item in timeline:
        if tool_call_id := _timeline_ref(item, "tool_call_id"):
            known_tool_call_ids.add(tool_call_id)
        if tool_run_id := _timeline_ref(item, "tool_run_id"):
            known_tool_ids.add(tool_run_id)
        if llm_invocation_id := _timeline_ref(item, "llm_invocation_id"):
            known_llm_invocation_ids.add(llm_invocation_id)
    token_total = _token_total_from_invocations(llm_invocations)
    llm_calls = len(known_llm_invocation_ids)
    for run in runs:
        known_tool_ids.update(run.pending_tool_run_ids)
        prompt_report = run.metadata.get("prompt_report")
        if not known_llm_invocation_ids and isinstance(prompt_report, dict):
            raw_total = prompt_report.get("token_total") or prompt_report.get("total_tokens")
            if isinstance(raw_total, int):
                token_total += max(raw_total, 0)
        if not known_llm_invocation_ids:
            llm_calls += max(run.current_step, 1 if _llm_id(run) else 0)
    return RunMetrics(
        tool_calls=len(known_tool_call_ids) if known_tool_call_ids else len(known_tool_ids),
        llm_calls=llm_calls,
        tokens=token_total,
        estimated_cost_usd=None,
    )


def _token_total_from_invocations(invocations: tuple[Any, ...]) -> int:
    return sum(
        token_total
        for token_total in (
            _llm_invocation_token_total(invocation) for invocation in invocations
        )
        if token_total is not None
    )


def _duration_ms(run: OrchestrationRun) -> int | None:
    started_at = run.started_at or run.queued_at or run.created_at
    ended_at = run.completed_at
    if ended_at is None and run.status not in {
        OrchestrationRunStatus.COMPLETED,
        OrchestrationRunStatus.FAILED,
        OrchestrationRunStatus.CANCELLED,
    }:
        ended_at = run.updated_at
    return _span_ms(started_at, ended_at)


def _span_ms(started_at: datetime | None, ended_at: datetime | None) -> int | None:
    if started_at is None or ended_at is None:
        return None
    start = coerce_utc_datetime(started_at)
    end = coerce_utc_datetime(ended_at)
    return max(int((end - start).total_seconds() * 1000), 0)


def _turn_id(run: OrchestrationRun) -> str:
    return _metadata_str(run, "turn_id") or run.id


def _turn_ordinal(run: OrchestrationRun) -> int:
    value = run.metadata.get("turn_ordinal")
    return value if isinstance(value, int) and value > 0 else 1


def _llm_id(run: OrchestrationRun) -> str | None:
    if run.result_payload is not None:
        value = run.result_payload.get("llm_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return _metadata_str(run, "requested_llm_id")


def _output_text(run: OrchestrationRun) -> str | None:
    if run.result_payload is None:
        return None
    value = run.result_payload.get("output_text")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _pending_approval(run: OrchestrationRun) -> dict[str, object] | None:
    if not _run_is_waiting_for_approval(run):
        return None
    return (
        dict(run.pending_approval_request_payload)
        if run.pending_approval_request_payload is not None
        else None
    )


def _run_is_waiting_for_approval(run: OrchestrationRun) -> bool:
    return (
        run.status is OrchestrationRunStatus.WAITING
        and run.stage is OrchestrationRunStage.WAITING_FOR_CONFIRMATION
    )


def _metadata_str(run: OrchestrationRun, key: str) -> str | None:
    value = run.metadata.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _truncate(value: str, *, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3].rstrip()}..."
