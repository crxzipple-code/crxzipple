from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from typing import Any, Protocol

from crxzipple.modules.orchestration.application.ports import OrchestrationRunQueryPort
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationRunStage,
    OrchestrationRunStatus,
)
from crxzipple.modules.tool.domain import ToolRun
from crxzipple.modules.tool.domain.value_objects import ToolRunStatus
from crxzipple.shared.content_blocks import describe_content_for_text_fallback
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


@dataclass(frozen=True, slots=True)
class _DisplayToolRun:
    source_run: OrchestrationRun
    tool_run: ToolRun


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
    actions: tuple[WorkbenchAction, ...]
    inspector: WorkbenchInspectorView
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
    details_available: bool
    trace: TraceContext


@dataclass(slots=True)
class WorkbenchReadModelProvider:
    run_query: OrchestrationRunQueryPort
    tool_query: WorkbenchToolRunQueryPort | None = None
    artifact_query: WorkbenchArtifactQueryPort | None = None
    llm_query: WorkbenchLlmQueryPort | None = None
    agent_query: WorkbenchAgentQueryPort | None = None

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
            threads[0].id if threads else None,
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
        llm_invocations = _llm_invocations_for_runs(self.llm_query, session_runs)
        trace = _trace_for_run(run, turn_id=turn_id)
        agent_ref = _agent_ref(run, self.agent_query)
        model_ref = _llm_ref(run, self.llm_query)
        metrics = _metrics_for_runs(
            session_runs,
            related_tool_runs=tuple(
                display_tool_run.tool_run
                for display_tool_run in session_display_tool_runs
            ),
            llm_invocations=llm_invocations,
        )
        cover_artifact = _cover_artifact(
            tuple(
                display_tool_run.tool_run
                for display_tool_run in session_display_tool_runs
            ),
            artifact_query=self.artifact_query,
        )
        actions = _run_actions(run, trace=trace)
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
        pending_tool_run_ids = set(run.pending_tool_run_ids)
        llm_invocation = _llm_invocation_for_run(self.llm_query, run)
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
                    llm_invocation_id=_metadata_str(run, "llm_invocation_id"),
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
                    title="Access Required",
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
    artifact_id: str | None = None,
    approval_request_id: str | None = None,
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
        artifact_id=artifact_id,
        approval_request_id=approval_request_id,
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
    tool_run_id: str | None = None,
    llm_invocation_id: str | None = None,
    artifact_id: str | None = None,
    approval_request_id: str | None = None,
) -> TurnStepView:
    stable_step_id = f"{run.id}:{step_id}"
    trace = _trace_for_run(
        run,
        turn_id=turn_id,
        step_id=stable_step_id,
        tool_run_id=tool_run_id,
        llm_invocation_id=llm_invocation_id,
        artifact_id=artifact_id,
        approval_request_id=approval_request_id,
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
        details_available=True,
        trace=trace,
    )


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
    return f"/trace/{trace.trace_id}"


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
        context = tool_run.invocation_context
        if context is not None and context.get_str("run_id") == run_id:
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
            *_metadata_list(run, "inline_tool_run_ids"),
        ):
            tool_id_to_run.setdefault(tool_run_id, run)
    related: list[_DisplayToolRun] = []
    seen_tool_run_ids: set[str] = set()
    for tool_run in tool_runs:
        context = tool_run.invocation_context
        source_run: OrchestrationRun | None = None
        context_run_id = context.get_str("run_id") if context is not None else None
        if context_run_id is not None:
            source_run = run_by_id.get(context_run_id)
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
) -> RuntimeRef:
    llm_id = _llm_id(run) or _llm_invocation_llm_id(_llm_invocation_for_run(llm_query, run))
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
    llm_query: WorkbenchLlmQueryPort | None,
    run: OrchestrationRun,
) -> Any | None:
    invocation_id = _metadata_str(run, "llm_invocation_id")
    if invocation_id is None or llm_query is None:
        return None
    try:
        return llm_query.get_invocation(invocation_id)
    except Exception:
        return None


def _llm_invocations_for_runs(
    llm_query: WorkbenchLlmQueryPort | None,
    runs: tuple[OrchestrationRun, ...],
) -> tuple[Any, ...]:
    invocations: list[Any] = []
    seen: set[str] = set()
    for run in runs:
        invocation = _llm_invocation_for_run(llm_query, run)
        invocation_id = _optional_text(getattr(invocation, "id", None))
        if invocation is None or invocation_id is None or invocation_id in seen:
            continue
        invocations.append(invocation)
        seen.add(invocation_id)
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
        ),
        memory=(
            WorkbenchKeyValueSection(
                id="memory_context",
                title="Memory Context",
                items=(
                    _kv("Agent", run.agent_id or "-"),
                    _kv("Recalled blocks", str(_prompt_block_count(run, "recalled_memory"))),
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
                        "Memory backend",
                        _agent_memory_backend(agent_profile) or "-",
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


def _agent_memory_backend(agent_profile: Any | None) -> str | None:
    if agent_profile is None:
        return None
    preferences = getattr(agent_profile, "runtime_preferences", None)
    return _optional_text(getattr(preferences, "memory_retrieval_backend", None))


def _prompt_block_count(run: OrchestrationRun, kind: str) -> int:
    prompt_report = run.metadata.get("prompt_report")
    if not isinstance(prompt_report, dict):
        return 0
    blocks = prompt_report.get("system_blocks")
    if not isinstance(blocks, list):
        return 0
    return sum(
        1
        for block in blocks
        if isinstance(block, dict) and block.get("kind") == kind
    )


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
    if run.stage is OrchestrationRunStage.TOOL:
        names = _metadata_list(run, "tool_call_names")
        if names:
            return f"Model requested tool call(s): {', '.join(names)}."
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
        return f"Access is not ready for {subject}: {', '.join(requirements)}."
    return f"Access is not ready for {subject}."


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
    inline_tool_ids = _metadata_list(run, "inline_tool_run_ids")
    known_tool_ids = {
        *run.pending_tool_run_ids,
        *inline_tool_ids,
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
) -> RunMetrics:
    known_tool_ids = {tool_run.id for tool_run in related_tool_runs}
    token_total = _token_total_from_invocations(llm_invocations)
    llm_calls = len(llm_invocations)
    for run in runs:
        known_tool_ids.update(run.pending_tool_run_ids)
        known_tool_ids.update(_metadata_list(run, "inline_tool_run_ids"))
        prompt_report = run.metadata.get("prompt_report")
        if not llm_invocations and isinstance(prompt_report, dict):
            raw_total = prompt_report.get("token_total") or prompt_report.get("total_tokens")
            if isinstance(raw_total, int):
                token_total += max(raw_total, 0)
        if not llm_invocations:
            llm_calls += max(run.current_step, 1 if _llm_id(run) else 0)
    return RunMetrics(
        tool_calls=len(known_tool_ids),
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
    value = run.metadata.get("pending_approval_request")
    if isinstance(value, dict):
        return dict(value)
    return None


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


def _metadata_list(run: OrchestrationRun, key: str) -> list[str]:
    value = run.metadata.get(key)
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _truncate(value: str, *, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3].rstrip()}..."
