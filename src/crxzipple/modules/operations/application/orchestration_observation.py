from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.observation import OperationsObservedEvent
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


RUN_ACCEPTED_EVENT = "orchestration.run.accepted"
RUN_ROUTED_EVENT = "orchestration.run.routed"
RUN_BULK_READY_EVENT = "orchestration.run.bulk_ready"
RUN_QUEUED_EVENT = "orchestration.run.queued"
RUN_CLAIMED_EVENT = "orchestration.run.claimed"
RUN_HEARTBEATED_EVENT = "orchestration.run.heartbeated"
RUN_ADVANCED_EVENT = "orchestration.run.advanced"
RUN_LLM_ATTEMPT_REWOUND_EVENT = "orchestration.run.llm_attempt_rewound"
RUN_WAITING_EVENT = "orchestration.run.waiting"
RUN_WAITING_FOR_CONFIRMATION_EVENT = "orchestration.run.waiting_for_confirmation"
RUN_APPROVAL_RESOLVED_EVENT = "orchestration.run.approval_resolved"
RUN_RESUMED_EVENT = "orchestration.run.resumed"
RUN_COMPLETED_EVENT = "orchestration.run.completed"
RUN_FAILED_EVENT = "orchestration.run.failed"
RUN_CANCELLED_EVENT = "orchestration.run.cancelled"

INGRESS_REQUESTED_EVENT = "orchestration.ingress.requested"
INGRESS_CLAIMED_EVENT = "orchestration.ingress.claimed"
INGRESS_COMPLETED_EVENT = "orchestration.ingress.completed"
INGRESS_FAILED_EVENT = "orchestration.ingress.failed"

SCHEDULER_SIGNAL_REQUESTED_EVENT = "orchestration.scheduler.signal.requested"
SCHEDULER_SIGNAL_CLAIMED_EVENT = "orchestration.scheduler.signal.claimed"
SCHEDULER_SIGNAL_COMPLETED_EVENT = "orchestration.scheduler.signal.completed"
SCHEDULER_SIGNAL_FAILED_EVENT = "orchestration.scheduler.signal.failed"

EXECUTOR_ASSIGNMENT_REQUESTED_EVENT = "orchestration.executor.assignment.requested"
EXECUTOR_LEASE_REGISTERED_EVENT = "orchestration.executor.lease.registered"
EXECUTOR_LEASE_HEARTBEATED_EVENT = "orchestration.executor.lease.heartbeated"
EXECUTOR_LEASE_ASSIGNMENT_CLAIMED_EVENT = (
    "orchestration.executor.lease.assignment_claimed"
)
EXECUTOR_LEASE_ASSIGNMENT_RELEASED_EVENT = (
    "orchestration.executor.lease.assignment_released"
)
EXECUTOR_LEASE_OFFLINE_EVENT = "orchestration.executor.lease.offline"

RUNTIME_STATUS_EVENT = "orchestration.runtime.status"

ORCHESTRATION_OPERATIONAL_EVENT_NAMES: tuple[str, ...] = (
    RUN_ACCEPTED_EVENT,
    RUN_ROUTED_EVENT,
    RUN_BULK_READY_EVENT,
    RUN_QUEUED_EVENT,
    RUN_CLAIMED_EVENT,
    RUN_HEARTBEATED_EVENT,
    RUN_ADVANCED_EVENT,
    RUN_LLM_ATTEMPT_REWOUND_EVENT,
    RUN_WAITING_EVENT,
    RUN_WAITING_FOR_CONFIRMATION_EVENT,
    RUN_APPROVAL_RESOLVED_EVENT,
    RUN_RESUMED_EVENT,
    RUN_COMPLETED_EVENT,
    RUN_FAILED_EVENT,
    RUN_CANCELLED_EVENT,
    INGRESS_REQUESTED_EVENT,
    INGRESS_CLAIMED_EVENT,
    INGRESS_COMPLETED_EVENT,
    INGRESS_FAILED_EVENT,
    SCHEDULER_SIGNAL_REQUESTED_EVENT,
    SCHEDULER_SIGNAL_CLAIMED_EVENT,
    SCHEDULER_SIGNAL_COMPLETED_EVENT,
    SCHEDULER_SIGNAL_FAILED_EVENT,
    EXECUTOR_ASSIGNMENT_REQUESTED_EVENT,
    EXECUTOR_LEASE_REGISTERED_EVENT,
    EXECUTOR_LEASE_HEARTBEATED_EVENT,
    EXECUTOR_LEASE_ASSIGNMENT_CLAIMED_EVENT,
    EXECUTOR_LEASE_ASSIGNMENT_RELEASED_EVENT,
    EXECUTOR_LEASE_OFFLINE_EVENT,
    RUNTIME_STATUS_EVENT,
)


@dataclass(frozen=True, slots=True)
class OperationsOrchestrationRunState:
    run_id: str
    status: str = "observed"
    stage: str = "observed"
    worker_id: str | None = None
    lane_key: str | None = None
    lane_lock_key: str | None = None
    session_key: str | None = None
    active_session_id: str | None = None
    agent_id: str | None = None
    priority: int | None = None
    current_step: int | None = None
    waiting_reason: str | None = None
    pending_tool_run_ids: tuple[str, ...] = ()
    source: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    trace_id: str | None = None
    created_at: datetime | None = None
    queued_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime | None = None
    last_event_name: str | None = None
    last_event_cursor: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "stage": self.stage,
            "worker_id": self.worker_id,
            "lane_key": self.lane_key,
            "lane_lock_key": self.lane_lock_key,
            "session_key": self.session_key,
            "active_session_id": self.active_session_id,
            "agent_id": self.agent_id,
            "priority": self.priority,
            "current_step": self.current_step,
            "waiting_reason": self.waiting_reason,
            "pending_tool_run_ids": list(self.pending_tool_run_ids),
            "source": self.source,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "trace_id": self.trace_id,
            "created_at": _format_optional_datetime(self.created_at),
            "queued_at": _format_optional_datetime(self.queued_at),
            "started_at": _format_optional_datetime(self.started_at),
            "completed_at": _format_optional_datetime(self.completed_at),
            "updated_at": _format_optional_datetime(self.updated_at),
            "last_event_name": self.last_event_name,
            "last_event_cursor": self.last_event_cursor,
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
    ) -> "OperationsOrchestrationRunState | None":
        run_id = _optional_text(payload.get("run_id"))
        if run_id is None:
            return None
        return cls(
            run_id=run_id,
            status=_optional_text(payload.get("status")) or "observed",
            stage=_optional_text(payload.get("stage")) or "observed",
            worker_id=_optional_text(payload.get("worker_id")),
            lane_key=_optional_text(payload.get("lane_key")),
            lane_lock_key=_optional_text(payload.get("lane_lock_key")),
            session_key=_optional_text(payload.get("session_key")),
            active_session_id=_optional_text(payload.get("active_session_id")),
            agent_id=_optional_text(payload.get("agent_id")),
            priority=_optional_int(payload.get("priority")),
            current_step=_optional_int(payload.get("current_step")),
            waiting_reason=_optional_text(payload.get("waiting_reason")),
            pending_tool_run_ids=_text_tuple(payload.get("pending_tool_run_ids")),
            source=_optional_text(payload.get("source")),
            error_code=_optional_text(payload.get("error_code")),
            error_message=_optional_text(payload.get("error_message")),
            trace_id=_optional_text(payload.get("trace_id")),
            created_at=_parse_datetime(payload.get("created_at")),
            queued_at=_parse_datetime(payload.get("queued_at")),
            started_at=_parse_datetime(payload.get("started_at")),
            completed_at=_parse_datetime(payload.get("completed_at")),
            updated_at=_parse_datetime(payload.get("updated_at")),
            last_event_name=_optional_text(payload.get("last_event_name")),
            last_event_cursor=_optional_text(payload.get("last_event_cursor")),
        )


@dataclass(frozen=True, slots=True)
class OperationsOrchestrationIngressState:
    request_id: str
    run_id: str | None = None
    kind: str | None = None
    status: str = "queued"
    worker_id: str | None = None
    source: str | None = None
    target_lane: str | None = None
    priority: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    trace_id: str | None = None
    created_at: datetime | None = None
    claimed_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime | None = None
    last_event_name: str | None = None
    last_event_cursor: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "run_id": self.run_id,
            "kind": self.kind,
            "status": self.status,
            "worker_id": self.worker_id,
            "source": self.source,
            "target_lane": self.target_lane,
            "priority": self.priority,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "trace_id": self.trace_id,
            "created_at": _format_optional_datetime(self.created_at),
            "claimed_at": _format_optional_datetime(self.claimed_at),
            "completed_at": _format_optional_datetime(self.completed_at),
            "updated_at": _format_optional_datetime(self.updated_at),
            "last_event_name": self.last_event_name,
            "last_event_cursor": self.last_event_cursor,
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
    ) -> "OperationsOrchestrationIngressState | None":
        request_id = _optional_text(payload.get("request_id"))
        if request_id is None:
            return None
        return cls(
            request_id=request_id,
            run_id=_optional_text(payload.get("run_id")),
            kind=_optional_text(payload.get("kind")),
            status=_optional_text(payload.get("status")) or "queued",
            worker_id=_optional_text(payload.get("worker_id")),
            source=_optional_text(payload.get("source")),
            target_lane=_optional_text(payload.get("target_lane")),
            priority=_optional_int(payload.get("priority")),
            error_code=_optional_text(payload.get("error_code")),
            error_message=_optional_text(payload.get("error_message")),
            trace_id=_optional_text(payload.get("trace_id")),
            created_at=_parse_datetime(payload.get("created_at")),
            claimed_at=_parse_datetime(payload.get("claimed_at")),
            completed_at=_parse_datetime(payload.get("completed_at")),
            updated_at=_parse_datetime(payload.get("updated_at")),
            last_event_name=_optional_text(payload.get("last_event_name")),
            last_event_cursor=_optional_text(payload.get("last_event_cursor")),
        )


@dataclass(frozen=True, slots=True)
class OperationsOrchestrationSchedulerSignalState:
    signal_id: str
    signal_kind: str | None = None
    status: str = "queued"
    worker_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    claimed_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime | None = None
    last_event_name: str | None = None
    last_event_cursor: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "signal_kind": self.signal_kind,
            "status": self.status,
            "worker_id": self.worker_id,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "created_at": _format_optional_datetime(self.created_at),
            "claimed_at": _format_optional_datetime(self.claimed_at),
            "completed_at": _format_optional_datetime(self.completed_at),
            "updated_at": _format_optional_datetime(self.updated_at),
            "last_event_name": self.last_event_name,
            "last_event_cursor": self.last_event_cursor,
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
    ) -> "OperationsOrchestrationSchedulerSignalState | None":
        signal_id = _optional_text(payload.get("signal_id"))
        if signal_id is None:
            return None
        return cls(
            signal_id=signal_id,
            signal_kind=_optional_text(payload.get("signal_kind")),
            status=_optional_text(payload.get("status")) or "queued",
            worker_id=_optional_text(payload.get("worker_id")),
            error_code=_optional_text(payload.get("error_code")),
            error_message=_optional_text(payload.get("error_message")),
            created_at=_parse_datetime(payload.get("created_at")),
            claimed_at=_parse_datetime(payload.get("claimed_at")),
            completed_at=_parse_datetime(payload.get("completed_at")),
            updated_at=_parse_datetime(payload.get("updated_at")),
            last_event_name=_optional_text(payload.get("last_event_name")),
            last_event_cursor=_optional_text(payload.get("last_event_cursor")),
        )


@dataclass(frozen=True, slots=True)
class OperationsOrchestrationExecutorState:
    worker_id: str
    status: str = "observed"
    effective_status: str | None = None
    max_inflight_assignments: int | None = None
    inflight_assignment_count: int | None = None
    available_assignment_slots: int | None = None
    active_run_ids: tuple[str, ...] = ()
    last_heartbeat_at: datetime | None = None
    lease_expires_at: datetime | None = None
    updated_at: datetime | None = None
    last_event_name: str | None = None
    last_event_cursor: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "status": self.status,
            "effective_status": self.effective_status,
            "max_inflight_assignments": self.max_inflight_assignments,
            "inflight_assignment_count": self.inflight_assignment_count,
            "available_assignment_slots": self.available_assignment_slots,
            "active_run_ids": list(self.active_run_ids),
            "last_heartbeat_at": _format_optional_datetime(self.last_heartbeat_at),
            "lease_expires_at": _format_optional_datetime(self.lease_expires_at),
            "updated_at": _format_optional_datetime(self.updated_at),
            "last_event_name": self.last_event_name,
            "last_event_cursor": self.last_event_cursor,
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
    ) -> "OperationsOrchestrationExecutorState | None":
        worker_id = _optional_text(payload.get("worker_id"))
        if worker_id is None:
            return None
        return cls(
            worker_id=worker_id,
            status=_optional_text(payload.get("status")) or "observed",
            effective_status=_optional_text(payload.get("effective_status")),
            max_inflight_assignments=_optional_int(
                payload.get("max_inflight_assignments"),
            ),
            inflight_assignment_count=_optional_int(
                payload.get("inflight_assignment_count"),
            ),
            available_assignment_slots=_optional_int(
                payload.get("available_assignment_slots"),
            ),
            active_run_ids=_text_tuple(payload.get("active_run_ids")),
            last_heartbeat_at=_parse_datetime(payload.get("last_heartbeat_at")),
            lease_expires_at=_parse_datetime(payload.get("lease_expires_at")),
            updated_at=_parse_datetime(payload.get("updated_at")),
            last_event_name=_optional_text(payload.get("last_event_name")),
            last_event_cursor=_optional_text(payload.get("last_event_cursor")),
        )


@dataclass(frozen=True, slots=True)
class OperationsOrchestrationObservation:
    updated_at: datetime | None = None
    last_cursor: str | None = None
    last_event_name: str | None = None
    runtime_payload: dict[str, Any] = field(default_factory=dict)
    runs: tuple[OperationsOrchestrationRunState, ...] = ()
    ingress_requests: tuple[OperationsOrchestrationIngressState, ...] = ()
    scheduler_signals: tuple[OperationsOrchestrationSchedulerSignalState, ...] = ()
    executors: tuple[OperationsOrchestrationExecutorState, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "updated_at": _format_optional_datetime(self.updated_at),
            "last_cursor": self.last_cursor,
            "last_event_name": self.last_event_name,
            "runtime_payload": dict(self.runtime_payload),
            "runs": [item.to_payload() for item in self.runs],
            "ingress_requests": [
                item.to_payload() for item in self.ingress_requests
            ],
            "scheduler_signals": [
                item.to_payload() for item in self.scheduler_signals
            ],
            "executors": [item.to_payload() for item in self.executors],
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
    ) -> "OperationsOrchestrationObservation":
        runtime_payload = payload.get("runtime_payload")
        return cls(
            updated_at=_parse_datetime(payload.get("updated_at")),
            last_cursor=_optional_text(payload.get("last_cursor")),
            last_event_name=_optional_text(payload.get("last_event_name")),
            runtime_payload=dict(runtime_payload) if isinstance(runtime_payload, dict) else {},
            runs=tuple(
                item
                for raw in payload.get("runs", ())
                if isinstance(raw, dict)
                for item in (OperationsOrchestrationRunState.from_payload(raw),)
                if item is not None
            ),
            ingress_requests=tuple(
                item
                for raw in payload.get("ingress_requests", ())
                if isinstance(raw, dict)
                for item in (OperationsOrchestrationIngressState.from_payload(raw),)
                if item is not None
            ),
            scheduler_signals=tuple(
                item
                for raw in payload.get("scheduler_signals", ())
                if isinstance(raw, dict)
                for item in (
                    OperationsOrchestrationSchedulerSignalState.from_payload(raw),
                )
                if item is not None
            ),
            executors=tuple(
                item
                for raw in payload.get("executors", ())
                if isinstance(raw, dict)
                for item in (OperationsOrchestrationExecutorState.from_payload(raw),)
                if item is not None
            ),
        )


def record_orchestration_observed_event(
    current: OperationsOrchestrationObservation | None,
    event: OperationsObservedEvent,
) -> OperationsOrchestrationObservation:
    observation = current or OperationsOrchestrationObservation()
    runs = {item.run_id: item for item in observation.runs}
    ingress_requests = {item.request_id: item for item in observation.ingress_requests}
    scheduler_signals = {item.signal_id: item for item in observation.scheduler_signals}
    executors = {item.worker_id: item for item in observation.executors}
    runtime_payload = dict(observation.runtime_payload)

    if event.event_name.startswith("orchestration.run."):
        run_id = event.run_id or _optional_text(event.payload.get("run_id"))
        if run_id is not None:
            runs[run_id] = _project_run(runs.get(run_id), event, run_id=run_id)
    elif event.event_name.startswith("orchestration.ingress."):
        request_id = _optional_text(event.payload.get("request_id")) or event.entity_id
        ingress_requests[request_id] = _project_ingress(
            ingress_requests.get(request_id),
            event,
            request_id=request_id,
        )
    elif event.event_name.startswith("orchestration.scheduler.signal."):
        signal_id = _optional_text(event.payload.get("signal_id")) or event.entity_id
        scheduler_signals[signal_id] = _project_scheduler_signal(
            scheduler_signals.get(signal_id),
            event,
            signal_id=signal_id,
        )
    elif event.event_name == EXECUTOR_ASSIGNMENT_REQUESTED_EVENT:
        worker_id = _optional_text(event.payload.get("worker_id"))
        if worker_id is not None:
            executors[worker_id] = _project_executor_assignment_request(
                executors.get(worker_id),
                event,
                worker_id=worker_id,
            )
    elif event.event_name.startswith("orchestration.executor.lease."):
        worker_id = _optional_text(event.payload.get("worker_id")) or event.entity_id
        executors[worker_id] = _project_executor(
            executors.get(worker_id),
            event,
            worker_id=worker_id,
        )
    elif event.event_name == RUNTIME_STATUS_EVENT:
        runtime_payload = dict(event.payload)
        executors.update(_executors_from_runtime_status(event, executors=executors))

    return OperationsOrchestrationObservation(
        updated_at=event.occurred_at,
        last_cursor=event.cursor,
        last_event_name=event.event_name,
        runtime_payload=runtime_payload,
        runs=tuple(runs[key] for key in sorted(runs)),
        ingress_requests=tuple(ingress_requests[key] for key in sorted(ingress_requests)),
        scheduler_signals=tuple(scheduler_signals[key] for key in sorted(scheduler_signals)),
        executors=tuple(executors[key] for key in sorted(executors)),
    )


def _project_run(
    current: OperationsOrchestrationRunState | None,
    event: OperationsObservedEvent,
    *,
    run_id: str,
) -> OperationsOrchestrationRunState:
    payload = event.payload
    previous = current or OperationsOrchestrationRunState(run_id=run_id)
    status, stage = _run_status_stage(previous, event)
    pending_tools = _text_tuple(payload.get("pending_tool_run_ids"))
    worker_id = _optional_text(payload.get("worker_id"))
    lane_key = _optional_text(payload.get("lane_key"))
    lane_lock_key = _optional_text(payload.get("lane_lock_key"))
    completed_at = previous.completed_at
    queued_at = previous.queued_at
    started_at = previous.started_at
    created_at = previous.created_at
    if event.event_name == RUN_ACCEPTED_EVENT:
        created_at = created_at or event.occurred_at
    if event.event_name in {RUN_QUEUED_EVENT, RUN_RESUMED_EVENT}:
        queued_at = event.occurred_at
        completed_at = None
    if event.event_name == RUN_CLAIMED_EVENT:
        started_at = started_at or event.occurred_at
    if status in {"completed", "failed", "cancelled"}:
        completed_at = event.occurred_at
    return OperationsOrchestrationRunState(
        run_id=run_id,
        status=status,
        stage=stage,
        worker_id=worker_id if worker_id is not None else previous.worker_id,
        lane_key=lane_key if lane_key is not None else previous.lane_key,
        lane_lock_key=(
            lane_lock_key if lane_lock_key is not None else previous.lane_lock_key
        ),
        session_key=_coalesce_text(payload.get("session_key"), previous.session_key),
        active_session_id=_coalesce_text(
            payload.get("active_session_id"),
            previous.active_session_id,
        ),
        agent_id=_coalesce_text(payload.get("agent_id"), previous.agent_id),
        priority=_coalesce_int(payload.get("priority"), previous.priority),
        current_step=_coalesce_int(payload.get("current_step"), previous.current_step),
        waiting_reason=_coalesce_text(
            payload.get("waiting_reason"),
            _coalesce_text(payload.get("reason"), previous.waiting_reason),
        ),
        pending_tool_run_ids=pending_tools or previous.pending_tool_run_ids,
        source=_coalesce_text(payload.get("source"), previous.source),
        error_code=_coalesce_text(payload.get("code"), previous.error_code),
        error_message=_coalesce_text(payload.get("message"), previous.error_message),
        trace_id=event.trace_id or _coalesce_text(payload.get("trace_id"), previous.trace_id),
        created_at=created_at,
        queued_at=queued_at,
        started_at=started_at,
        completed_at=completed_at,
        updated_at=event.occurred_at,
        last_event_name=event.event_name,
        last_event_cursor=event.cursor,
    )


def _project_ingress(
    current: OperationsOrchestrationIngressState | None,
    event: OperationsObservedEvent,
    *,
    request_id: str,
) -> OperationsOrchestrationIngressState:
    payload = event.payload
    previous = current or OperationsOrchestrationIngressState(request_id=request_id)
    status = _ingress_status(event.event_name, payload, previous.status)
    claimed_at = previous.claimed_at
    completed_at = previous.completed_at
    if event.event_name == INGRESS_CLAIMED_EVENT:
        claimed_at = event.occurred_at
    if status in {"completed", "failed"}:
        completed_at = event.occurred_at
    return OperationsOrchestrationIngressState(
        request_id=request_id,
        run_id=_coalesce_text(payload.get("run_id"), previous.run_id),
        kind=_coalesce_text(payload.get("kind"), previous.kind),
        status=status,
        worker_id=_coalesce_text(payload.get("worker_id"), previous.worker_id),
        source=_coalesce_text(
            payload.get("source"),
            _coalesce_text(payload.get("surface"), previous.source),
        ),
        target_lane=_coalesce_text(
            payload.get("target_lane"),
            _coalesce_text(payload.get("lane_key"), previous.target_lane),
        ),
        priority=_coalesce_int(payload.get("priority"), previous.priority),
        error_code=_coalesce_text(payload.get("code"), previous.error_code),
        error_message=_coalesce_text(payload.get("message"), previous.error_message),
        trace_id=event.trace_id or _coalesce_text(payload.get("trace_id"), previous.trace_id),
        created_at=previous.created_at or event.occurred_at,
        claimed_at=claimed_at,
        completed_at=completed_at,
        updated_at=event.occurred_at,
        last_event_name=event.event_name,
        last_event_cursor=event.cursor,
    )


def _project_scheduler_signal(
    current: OperationsOrchestrationSchedulerSignalState | None,
    event: OperationsObservedEvent,
    *,
    signal_id: str,
) -> OperationsOrchestrationSchedulerSignalState:
    payload = event.payload
    previous = current or OperationsOrchestrationSchedulerSignalState(
        signal_id=signal_id,
    )
    status = _scheduler_signal_status(event.event_name, payload, previous.status)
    claimed_at = previous.claimed_at
    completed_at = previous.completed_at
    if event.event_name == SCHEDULER_SIGNAL_CLAIMED_EVENT:
        claimed_at = event.occurred_at
    if status in {"completed", "failed"}:
        completed_at = event.occurred_at
    return OperationsOrchestrationSchedulerSignalState(
        signal_id=signal_id,
        signal_kind=_coalesce_text(payload.get("signal_kind"), previous.signal_kind),
        status=status,
        worker_id=_coalesce_text(payload.get("worker_id"), previous.worker_id),
        error_code=_coalesce_text(payload.get("code"), previous.error_code),
        error_message=_coalesce_text(payload.get("message"), previous.error_message),
        created_at=previous.created_at or event.occurred_at,
        claimed_at=claimed_at,
        completed_at=completed_at,
        updated_at=event.occurred_at,
        last_event_name=event.event_name,
        last_event_cursor=event.cursor,
    )


def _project_executor_assignment_request(
    current: OperationsOrchestrationExecutorState | None,
    event: OperationsObservedEvent,
    *,
    worker_id: str,
) -> OperationsOrchestrationExecutorState:
    previous = current or OperationsOrchestrationExecutorState(worker_id=worker_id)
    run_id = _optional_text(event.payload.get("run_id"))
    active_run_ids = previous.active_run_ids
    if run_id is not None and run_id not in active_run_ids:
        active_run_ids = (*active_run_ids, run_id)
    return _replace_executor(
        previous,
        event,
        active_run_ids=active_run_ids,
    )


def _project_executor(
    current: OperationsOrchestrationExecutorState | None,
    event: OperationsObservedEvent,
    *,
    worker_id: str,
) -> OperationsOrchestrationExecutorState:
    payload = event.payload
    previous = current or OperationsOrchestrationExecutorState(worker_id=worker_id)
    status = _coalesce_text(payload.get("status"), previous.status) or "observed"
    if event.event_name == EXECUTOR_LEASE_OFFLINE_EVENT:
        status = "offline"
    return _replace_executor(
        previous,
        event,
        status=status,
        effective_status=_coalesce_text(
            payload.get("effective_status"),
            previous.effective_status,
        ),
        max_inflight_assignments=_coalesce_int(
            payload.get("max_inflight_assignments"),
            previous.max_inflight_assignments,
        ),
        inflight_assignment_count=_coalesce_int(
            payload.get("inflight_assignment_count"),
            previous.inflight_assignment_count,
        ),
        available_assignment_slots=_coalesce_int(
            payload.get("available_assignment_slots"),
            previous.available_assignment_slots,
        ),
        active_run_ids=_text_tuple(payload.get("active_run_ids"))
        or previous.active_run_ids,
        last_heartbeat_at=_parse_datetime(payload.get("last_heartbeat_at"))
        or (
            event.occurred_at
            if event.event_name
            in {EXECUTOR_LEASE_REGISTERED_EVENT, EXECUTOR_LEASE_HEARTBEATED_EVENT}
            else previous.last_heartbeat_at
        ),
        lease_expires_at=_parse_datetime(payload.get("lease_expires_at"))
        or previous.lease_expires_at,
    )


def _replace_executor(
    previous: OperationsOrchestrationExecutorState,
    event: OperationsObservedEvent,
    *,
    status: str | None = None,
    effective_status: str | None = None,
    max_inflight_assignments: int | None = None,
    inflight_assignment_count: int | None = None,
    available_assignment_slots: int | None = None,
    active_run_ids: tuple[str, ...] | None = None,
    last_heartbeat_at: datetime | None = None,
    lease_expires_at: datetime | None = None,
) -> OperationsOrchestrationExecutorState:
    return OperationsOrchestrationExecutorState(
        worker_id=previous.worker_id,
        status=status or previous.status,
        effective_status=effective_status or previous.effective_status,
        max_inflight_assignments=(
            max_inflight_assignments
            if max_inflight_assignments is not None
            else previous.max_inflight_assignments
        ),
        inflight_assignment_count=(
            inflight_assignment_count
            if inflight_assignment_count is not None
            else previous.inflight_assignment_count
        ),
        available_assignment_slots=(
            available_assignment_slots
            if available_assignment_slots is not None
            else previous.available_assignment_slots
        ),
        active_run_ids=active_run_ids if active_run_ids is not None else previous.active_run_ids,
        last_heartbeat_at=last_heartbeat_at or previous.last_heartbeat_at,
        lease_expires_at=lease_expires_at or previous.lease_expires_at,
        updated_at=event.occurred_at,
        last_event_name=event.event_name,
        last_event_cursor=event.cursor,
    )


def _executors_from_runtime_status(
    event: OperationsObservedEvent,
    *,
    executors: dict[str, OperationsOrchestrationExecutorState],
) -> dict[str, OperationsOrchestrationExecutorState]:
    executor_payload = event.payload.get("executor")
    if not isinstance(executor_payload, dict):
        return {}
    raw_leases = executor_payload.get("leases")
    if not isinstance(raw_leases, list):
        return {}
    updates: dict[str, OperationsOrchestrationExecutorState] = {}
    for raw_lease in raw_leases:
        if not isinstance(raw_lease, dict):
            continue
        worker_id = _optional_text(raw_lease.get("worker_id"))
        if worker_id is None:
            continue
        previous = executors.get(worker_id) or OperationsOrchestrationExecutorState(
            worker_id=worker_id,
        )
        runtime_state = raw_lease.get("runtime_state")
        active_run_ids = ()
        if isinstance(runtime_state, dict):
            active_run_ids = _text_tuple(runtime_state.get("active_run_ids"))
        updates[worker_id] = _replace_executor(
            previous,
            event,
            status=_coalesce_text(raw_lease.get("status"), previous.status),
            effective_status=_coalesce_text(
                raw_lease.get("effective_status"),
                previous.effective_status,
            ),
            max_inflight_assignments=_coalesce_int(
                raw_lease.get("max_inflight_assignments"),
                previous.max_inflight_assignments,
            ),
            inflight_assignment_count=_coalesce_int(
                raw_lease.get("inflight_assignment_count"),
                previous.inflight_assignment_count,
            ),
            available_assignment_slots=_coalesce_int(
                raw_lease.get("available_assignment_slots"),
                previous.available_assignment_slots,
            ),
            active_run_ids=active_run_ids or previous.active_run_ids,
            last_heartbeat_at=_parse_datetime(raw_lease.get("last_heartbeat_at"))
            or previous.last_heartbeat_at,
            lease_expires_at=_parse_datetime(raw_lease.get("lease_expires_at"))
            or previous.lease_expires_at,
        )
    return updates


def _run_status_stage(
    previous: OperationsOrchestrationRunState,
    event: OperationsObservedEvent,
) -> tuple[str, str]:
    payload_status = _optional_text(event.payload.get("status"))
    payload_stage = _optional_text(event.payload.get("stage"))
    mapping = {
        RUN_ACCEPTED_EVENT: ("accepted", "accepted"),
        RUN_ROUTED_EVENT: ("accepted", "routed"),
        RUN_BULK_READY_EVENT: ("accepted", "bulk_ready"),
        RUN_QUEUED_EVENT: ("queued", "queued"),
        RUN_CLAIMED_EVENT: ("running", "running"),
        RUN_HEARTBEATED_EVENT: ("running", payload_stage or previous.stage),
        RUN_ADVANCED_EVENT: ("running", payload_stage or "running"),
        RUN_LLM_ATTEMPT_REWOUND_EVENT: ("running", payload_stage or previous.stage),
        RUN_WAITING_EVENT: ("waiting", payload_stage or "waiting_on_tool"),
        RUN_WAITING_FOR_CONFIRMATION_EVENT: (
            "waiting",
            "waiting_for_confirmation",
        ),
        RUN_RESUMED_EVENT: ("queued", "queued"),
        RUN_COMPLETED_EVENT: ("completed", "completed"),
        RUN_FAILED_EVENT: ("failed", "failed"),
        RUN_CANCELLED_EVENT: ("cancelled", "cancelled"),
    }
    status, stage = mapping.get(event.event_name, (previous.status, previous.stage))
    if event.event_name == RUN_APPROVAL_RESOLVED_EVENT:
        status = payload_status or previous.status
        stage = payload_stage or previous.stage
    return payload_status or status, payload_stage or stage


def _ingress_status(event_name: str, payload: dict[str, Any], previous: str) -> str:
    explicit = _optional_text(payload.get("status"))
    if explicit is not None:
        return explicit
    return {
        INGRESS_REQUESTED_EVENT: "queued",
        INGRESS_CLAIMED_EVENT: "processing",
        INGRESS_COMPLETED_EVENT: "completed",
        INGRESS_FAILED_EVENT: "failed",
    }.get(event_name, previous)


def _scheduler_signal_status(
    event_name: str,
    payload: dict[str, Any],
    previous: str,
) -> str:
    explicit = _optional_text(payload.get("status"))
    if explicit is not None:
        return explicit
    return {
        SCHEDULER_SIGNAL_REQUESTED_EVENT: "queued",
        SCHEDULER_SIGNAL_CLAIMED_EVENT: "processing",
        SCHEDULER_SIGNAL_COMPLETED_EVENT: "completed",
        SCHEDULER_SIGNAL_FAILED_EVENT: "failed",
    }.get(event_name, previous)


def _format_optional_datetime(value: datetime | None) -> str | None:
    return format_datetime_utc(value) if value is not None else None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return coerce_utc_datetime(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return coerce_utc_datetime(datetime.fromisoformat(value))
    except ValueError:
        return None


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _coalesce_text(value: Any, fallback: str | None) -> str | None:
    return _optional_text(value) or fallback


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value))
        except ValueError:
            return None
    return None


def _coalesce_int(value: Any, fallback: int | None) -> int | None:
    parsed = _optional_int(value)
    return parsed if parsed is not None else fallback


def _text_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(
        text
        for item in value
        for text in (_optional_text(item),)
        if text is not None
    )
