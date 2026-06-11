from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Callable, Protocol
from uuid import uuid4

from crxzipple.modules.dispatch.domain import DispatchTaskRepository
from crxzipple.modules.orchestration.application.execution_chain_lifecycle import (
    prepare_dispatch_execution_step,
)
from crxzipple.modules.orchestration.application.ports import (
    OrchestrationDispatchPort,
    SessionCompactionStatePort,
)
from crxzipple.modules.orchestration.application.scheduler import (
    OrchestrationScheduler,
)
from crxzipple.modules.orchestration.domain import (
    ExecutionChainRepository,
    ExecutionStepItemRepository,
    ExecutionStepRepository,
    InboundInstruction,
    OrchestrationQueuePolicy,
    OrchestrationRun,
    OrchestrationRunRepository,
    OrchestrationRunStatus,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationRunNotFoundError,
    OrchestrationValidationError,
)
from crxzipple.shared.domain.aggregates import AggregateRoot
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application.commands import (
        RequestCompactionInput,
        RequestDueHeartbeatsInput,
        RequestHeartbeatInput,
        RequestMemoryFlushInput,
    )


_TERMINAL_RUN_STATUSES = {
    OrchestrationRunStatus.COMPLETED,
    OrchestrationRunStatus.FAILED,
    OrchestrationRunStatus.CANCELLED,
}


@dataclass(frozen=True, slots=True)
class RequestAnchorContext:
    run: OrchestrationRun
    session_key: str
    session_kind: str


class RequestCoordinatorUnitOfWork(Protocol):
    execution_chains: ExecutionChainRepository
    execution_steps: ExecutionStepRepository
    execution_step_items: ExecutionStepItemRepository
    orchestration_runs: OrchestrationRunRepository
    dispatch_tasks: DispatchTaskRepository

    def __enter__(self) -> "RequestCoordinatorUnitOfWork":
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        ...

    def collect(self, aggregate: AggregateRoot[Any]) -> None:
        ...

    def commit(self) -> None:
        ...


@dataclass(slots=True)
class RunRequestCoordinator:
    uow_factory: Callable[[], RequestCoordinatorUnitOfWork]
    scheduler: OrchestrationScheduler
    dispatch_port: OrchestrationDispatchPort
    session_service: SessionCompactionStatePort | None
    request_heartbeat_input_factory: Callable[..., "RequestHeartbeatInput"]

    def request_compaction(self, data: "RequestCompactionInput") -> OrchestrationRun:
        trigger_basis = data.trigger_basis.strip() or "manual"
        trigger_details = dict(data.trigger_details)
        with self.uow_factory() as uow:
            anchor = self._load_anchor_context(
                uow,
                anchor_run_id=data.anchor_run_id,
                label="Compaction",
            )
            run = self._create_requested_run(
                uow,
                anchor=anchor,
                source="compaction",
                queue_policy=data.queue_policy,
                priority=data.priority,
                max_steps=data.max_steps,
                prompt_flow_hint=self._compaction_prompt_flow_hint(
                    reason=data.reason,
                    preserve=data.preserve,
                ),
                metadata={
                    "compaction_anchor_run_id": anchor.run.id,
                    "compaction_request": {
                        "basis": trigger_basis,
                        "details": trigger_details,
                        "reason": (data.reason or "").strip() or "manual",
                    },
                },
            )
        if self.session_service is not None:
            self._merge_session_compaction_metadata(
                session_key=anchor.session_key,
                metadata={
                    "pending_run_id": run.id,
                    "requested_at": format_datetime_utc(run.created_at),
                    "request_reason": (data.reason or "").strip() or "manual",
                    "trigger_basis": trigger_basis,
                    "trigger_details": trigger_details,
                    "anchor_run_id": anchor.run.id,
                },
            )
        return run

    def request_heartbeat(self, data: "RequestHeartbeatInput") -> OrchestrationRun:
        with self.uow_factory() as uow:
            anchor = self._load_anchor_context(
                uow,
                anchor_run_id=data.anchor_run_id,
                label="Heartbeat",
            )
            return self._create_requested_run(
                uow,
                anchor=anchor,
                source="heartbeat",
                queue_policy=data.queue_policy,
                priority=data.priority,
                max_steps=data.max_steps,
                prompt_flow_hint=self._heartbeat_prompt_flow_hint(
                    reason=data.reason,
                    idle_reply=data.idle_reply,
                ),
                metadata={
                    "heartbeat_anchor_run_id": anchor.run.id,
                    "heartbeat_request": {
                        "basis": data.trigger_basis.strip() or "manual",
                        "details": dict(data.trigger_details),
                        "reason": (data.reason or "").strip() or "manual",
                        "idle_reply": (data.idle_reply or "").strip() or "HEARTBEAT_OK",
                    },
                },
            )

    def request_memory_flush(
        self,
        data: "RequestMemoryFlushInput",
    ) -> OrchestrationRun:
        trigger_basis = data.trigger_basis.strip() or "manual"
        trigger_details = dict(data.trigger_details)
        with self.uow_factory() as uow:
            anchor = self._load_anchor_context(
                uow,
                anchor_run_id=data.anchor_run_id,
                label="Memory flush",
            )
            run = self._create_requested_run(
                uow,
                anchor=anchor,
                source="memory_flush",
                queue_policy=data.queue_policy,
                priority=data.priority,
                max_steps=data.max_steps,
                prompt_flow_hint=self._memory_flush_prompt_flow_hint(
                    reason=data.reason,
                ),
                metadata={
                    "memory_flush_anchor_run_id": anchor.run.id,
                    "memory_flush_request": {
                        "basis": trigger_basis,
                        "details": trigger_details,
                        "reason": (data.reason or "").strip() or "manual",
                    },
                },
            )
        if self.session_service is not None and trigger_basis == "pre_compaction":
            self._merge_session_compaction_metadata(
                session_key=anchor.session_key,
                metadata={
                    "pending_memory_flush_run_id": run.id,
                    "pending_memory_flush_requested_at": format_datetime_utc(
                        run.created_at,
                    ),
                    "pending_memory_flush_reason": (
                        (data.reason or "").strip() or "auto_pre_compaction_flush"
                    ),
                    "pending_memory_flush_basis": trigger_basis,
                    "pending_memory_flush_anchor_run_id": anchor.run.id,
                },
            )
        return run

    def request_due_heartbeats(
        self,
        data: "RequestDueHeartbeatsInput",
    ) -> list[OrchestrationRun]:
        if self.session_service is None:
            raise RuntimeError("Orchestration session service is not configured.")
        if data.idle_seconds <= 0:
            raise OrchestrationValidationError(
                "Heartbeat idle_seconds must be greater than zero.",
            )
        if data.limit is not None and data.limit <= 0:
            raise OrchestrationValidationError(
                "Heartbeat limit must be greater than zero when provided.",
            )

        now = data.now or datetime.now(timezone.utc)
        idle_before = now - timedelta(seconds=data.idle_seconds)
        latest_runs = self._latest_anchor_runs_by_session_key()
        requested: list[OrchestrationRun] = []
        sessions = sorted(
            self.session_service.list_sessions(agent_id=data.agent_id),
            key=lambda item: item.updated_at,
        )
        for session in sessions:
            if data.limit is not None and len(requested) >= data.limit:
                break
            if session.status.strip().lower() != "active":
                continue
            updated_at = coerce_utc_datetime(session.updated_at)
            if updated_at > idle_before:
                continue
            if self._existing_inflight_run(session.id) is not None:
                continue
            anchor = latest_runs.get(session.id)
            if anchor is None:
                continue
            requested.append(
                self.request_heartbeat(
                    self.request_heartbeat_input_factory(
                        anchor_run_id=anchor.id,
                        reason=data.reason or "idle_session_heartbeat",
                        idle_reply=data.idle_reply,
                        trigger_basis="idle_session",
                        trigger_details={
                            "idle_seconds": data.idle_seconds,
                            "session_updated_at": format_datetime_utc(updated_at),
                        },
                        queue_policy=data.queue_policy,
                        priority=data.priority,
                        max_steps=data.max_steps,
                    ),
                ),
            )
        return requested

    def existing_pending_compaction_run(
        self,
        session_key: str,
    ) -> OrchestrationRun | None:
        if self.session_service is None:
            return None
        session = self.session_service.get_session(session_key)
        compaction_payload = session.metadata.get("compaction")
        if not isinstance(compaction_payload, dict):
            return None
        pending_run_id = compaction_payload.get("pending_run_id")
        if not isinstance(pending_run_id, str) or not pending_run_id.strip():
            return None
        with self.uow_factory() as uow:
            pending_run = uow.orchestration_runs.get(pending_run_id.strip())
        if pending_run is None or pending_run.status in _TERMINAL_RUN_STATUSES:
            return None
        return pending_run

    def existing_pending_memory_flush_run(
        self,
        session_key: str,
    ) -> OrchestrationRun | None:
        if self.session_service is None:
            return None
        session = self.session_service.get_session(session_key)
        compaction_payload = session.metadata.get("compaction")
        if not isinstance(compaction_payload, dict):
            return None
        pending_run_id = compaction_payload.get("pending_memory_flush_run_id")
        if not isinstance(pending_run_id, str) or not pending_run_id.strip():
            return None
        with self.uow_factory() as uow:
            pending_run = uow.orchestration_runs.get(pending_run_id.strip())
        if pending_run is None or pending_run.status in _TERMINAL_RUN_STATUSES:
            return None
        return pending_run

    def clear_pending_compaction_marker(self, run: OrchestrationRun) -> None:
        session_key = run.session_key or ""
        if not session_key:
            return
        self._merge_session_compaction_metadata(
            session_key=session_key,
            metadata={},
            remove_keys=(
                "pending_run_id",
                "requested_at",
                "request_reason",
                "anchor_run_id",
            ),
        )

    def clear_pending_memory_flush_marker(self, run: OrchestrationRun) -> None:
        session_key = run.session_key or ""
        if not session_key:
            return
        self._merge_session_compaction_metadata(
            session_key=session_key,
            metadata={},
            remove_keys=(
                "pending_memory_flush_run_id",
                "pending_memory_flush_requested_at",
                "pending_memory_flush_reason",
                "pending_memory_flush_basis",
                "pending_memory_flush_anchor_run_id",
            ),
        )

    def _create_requested_run(
        self,
        uow: RequestCoordinatorUnitOfWork,
        *,
        anchor: RequestAnchorContext,
        source: str,
        queue_policy: OrchestrationQueuePolicy,
        priority: int | None,
        max_steps: int,
        prompt_flow_hint: dict[str, object],
        metadata: dict[str, object],
    ) -> OrchestrationRun:
        run_metadata = {
            "session_key": anchor.session_key,
            "session_kind": anchor.session_kind,
            "prompt_flow_hint": prompt_flow_hint,
            **metadata,
        }
        run = OrchestrationRun.accept(
            run_id=uuid4().hex,
            inbound_instruction=InboundInstruction(source=source),
            queue_policy=queue_policy,
            priority=anchor.run.priority if priority is None else priority,
            max_steps=max_steps,
            metadata=run_metadata,
        )
        run.route(
            agent_id=anchor.run.agent_id,
            lane_key=anchor.run.lane_key,
            priority=run.priority,
            metadata=run_metadata,
        )
        run.bind_session(
            active_session_id=anchor.run.active_session_id,
        )
        self.scheduler.enqueue(
            run,
            lane_key=anchor.run.lane_key,
            queue_policy=queue_policy,
            priority=run.priority,
        )
        dispatch_step = prepare_dispatch_execution_step(uow, run=run)
        self.dispatch_port.enqueue(
            uow.dispatch_tasks,
            uow,
            run,
            dispatch_task_id=dispatch_step.step.dispatch_task_id
            or dispatch_step.step.id,
        )
        uow.orchestration_runs.add(run)
        uow.collect(run)
        uow.commit()
        return run

    def _load_anchor_context(
        self,
        uow: RequestCoordinatorUnitOfWork,
        *,
        anchor_run_id: str,
        label: str,
    ) -> RequestAnchorContext:
        anchor = self._get_run(uow, anchor_run_id)
        normalized_label = label.strip() or "Orchestration"
        if anchor.agent_id is None or not anchor.agent_id.strip():
            raise OrchestrationValidationError(
                f"{normalized_label} anchor run agent_id is required.",
            )
        if anchor.active_session_id is None or not anchor.active_session_id.strip():
            raise OrchestrationValidationError(
                f"{normalized_label} anchor run active_session_id is required.",
            )
        session_key = str(anchor.metadata.get("session_key", "")).strip()
        if not session_key:
            raise OrchestrationValidationError(
                f"{normalized_label} anchor run metadata.session_key is required.",
            )
        return RequestAnchorContext(
            run=anchor,
            session_key=session_key,
            session_kind=str(anchor.metadata.get("session_kind", "")).strip(),
        )

    def _latest_anchor_runs_by_session_key(self) -> dict[str, OrchestrationRun]:
        with self.uow_factory() as uow:
            runs = sorted(
                uow.orchestration_runs.list(),
                key=lambda item: item.updated_at,
                reverse=True,
            )
        latest: dict[str, OrchestrationRun] = {}
        for run in runs:
            session_key = run.session_key or ""
            if not session_key or session_key in latest:
                continue
            if run.agent_id is None or not run.agent_id.strip():
                continue
            if run.active_session_id is None or not run.active_session_id.strip():
                continue
            latest[session_key] = run
        return latest

    def _existing_inflight_run(self, session_key: str) -> OrchestrationRun | None:
        with self.uow_factory() as uow:
            runs = uow.orchestration_runs.list()
        for run in sorted(runs, key=lambda item: item.updated_at, reverse=True):
            current_session_key = run.session_key or ""
            if current_session_key != session_key:
                continue
            if run.status in _TERMINAL_RUN_STATUSES:
                continue
            return run
        return None

    def _merge_session_compaction_metadata(
        self,
        *,
        session_key: str,
        metadata: dict[str, object],
        remove_keys: tuple[str, ...] = (),
    ) -> None:
        if self.session_service is None:
            return
        session = self.session_service.get_session(session_key)
        current = session.metadata.get("compaction")
        payload = dict(current) if isinstance(current, dict) else {}
        payload.update(metadata)
        for key in remove_keys:
            payload.pop(key, None)
        self.session_service.merge_session_metadata(
            session_key=session_key,
            metadata={"compaction": payload},
            touch_activity=False,
        )

    @staticmethod
    def _compaction_prompt_flow_hint(
        *,
        reason: str | None,
        preserve: str | None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {"mode": "compaction"}
        if reason is not None and reason.strip():
            payload["reason"] = reason.strip()
        if preserve is not None and preserve.strip():
            payload["preserve"] = preserve.strip()
        return payload

    @staticmethod
    def _heartbeat_prompt_flow_hint(
        *,
        reason: str | None,
        idle_reply: str | None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {"mode": "heartbeat"}
        if reason is not None and reason.strip():
            payload["reason"] = reason.strip()
        if idle_reply is not None and idle_reply.strip():
            payload["idle_reply"] = idle_reply.strip()
        return payload

    @staticmethod
    def _memory_flush_prompt_flow_hint(
        *,
        reason: str | None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {"mode": "memory_flush"}
        if reason is not None and reason.strip():
            payload["reason"] = reason.strip()
        return payload

    @staticmethod
    def _get_run(
        uow: RequestCoordinatorUnitOfWork,
        run_id: str,
    ) -> OrchestrationRun:
        run = uow.orchestration_runs.get(run_id)
        if run is None:
            raise OrchestrationRunNotFoundError(
                f"Orchestration run '{run_id}' was not found.",
            )
        return run
