"""Session runtime control backed by orchestration runtime surfaces.

This module intentionally lives in ``crxzipple.app.integration`` rather than in
the Session, Tool or Orchestration modules: it is the cross-module use case that
binds Session-level runtime actions to Orchestration-owned run processing.
"""

from __future__ import annotations

from crxzipple.modules.orchestration.application.commands import (
    SubmitBoundOrchestrationTurnInput,
    SubmitOrchestrationTurnInput,
)
from crxzipple.modules.orchestration.application.intake_commands import (
    AcceptOrchestrationRunInput,
)
from crxzipple.modules.orchestration.application.ports.runtime import (
    OrchestrationCancellationPort,
    OrchestrationIngressProcessingPort,
    OrchestrationRunQueryPort,
    OrchestrationSubmissionPort,
)
from crxzipple.modules.orchestration.domain import InboundInstruction
from crxzipple.modules.orchestration.domain.entities import OrchestrationRun
from crxzipple.modules.session.application import (
    SessionRuntimeRunRecord,
    SubmitSessionBoundTurnInput,
    SubmitSessionSpawnTurnInput,
)
from crxzipple.modules.session.domain import (
    DirectSessionScope,
    SessionRouteContext,
)


class SchedulerBackedSessionRuntimeControl:
    """Session runtime control backed by the full orchestration scheduler surface."""

    def __init__(
        self,
        *,
        run_query_service: OrchestrationRunQueryPort,
        scheduler_service: OrchestrationSubmissionPort,
        cancellation_service: OrchestrationCancellationPort,
    ) -> None:
        self._run_query_service = run_query_service
        self._scheduler_service = scheduler_service
        self._cancellation_service = cancellation_service

    def submit_bound_turn(
        self,
        data: SubmitSessionBoundTurnInput,
        *,
        inline_worker_id: str | None = None,
    ) -> SessionRuntimeRunRecord:
        run = self._scheduler_service.submit_bound_turn(
            _bound_turn_input(data),
            inline_worker_id=inline_worker_id,
        )
        return _runtime_run_record_from_orchestration_run(run)

    def submit_spawn_turn(
        self,
        data: SubmitSessionSpawnTurnInput,
        *,
        inline_worker_id: str | None = None,
    ) -> SessionRuntimeRunRecord:
        run = self._scheduler_service.submit_turn(
            _spawn_turn_input(data),
            inline_worker_id=inline_worker_id,
        )
        return _runtime_run_record_from_orchestration_run(run)

    def list_runs(self) -> tuple[SessionRuntimeRunRecord, ...]:
        return tuple(
            _runtime_run_record_from_orchestration_run(run)
            for run in self._run_query_service.list_runs()
        )

    def cancel_session_tree(
        self,
        session_key: str,
        *,
        reason: str | None = None,
    ) -> dict[str, object]:
        return self._cancellation_service.cancel_session_tree(
            session_key,
            reason=reason,
        )


class IngressBackedSessionRuntimeControl:
    """Session runtime control for targets without the full scheduler runtime."""

    def __init__(
        self,
        *,
        run_query_service: OrchestrationRunQueryPort,
        submission_service: OrchestrationSubmissionPort,
        ingress_processing_service: OrchestrationIngressProcessingPort,
        cancellation_service: OrchestrationCancellationPort,
    ) -> None:
        self._run_query_service = run_query_service
        self._submission_service = submission_service
        self._ingress_processing_service = ingress_processing_service
        self._cancellation_service = cancellation_service

    def submit_bound_turn(
        self,
        data: SubmitSessionBoundTurnInput,
        *,
        inline_worker_id: str | None = None,
    ) -> SessionRuntimeRunRecord:
        run = self._submission_service.submit_bound_turn(
            _bound_turn_input(data),
            inline_worker_id=None,
        )
        if inline_worker_id is not None:
            run = (
                self._ingress_processing_service.process_run_request(
                    run_id=run.id,
                    worker_id=inline_worker_id,
                )
                or self._run_query_service.get_run(run.id)
            )
        return _runtime_run_record_from_orchestration_run(run)

    def submit_spawn_turn(
        self,
        data: SubmitSessionSpawnTurnInput,
        *,
        inline_worker_id: str | None = None,
    ) -> SessionRuntimeRunRecord:
        run = self._submission_service.submit_turn(
            _spawn_turn_input(data),
            inline_worker_id=None,
        )
        if inline_worker_id is not None:
            run = (
                self._ingress_processing_service.process_run_request(
                    run_id=run.id,
                    worker_id=inline_worker_id,
                )
                or self._run_query_service.get_run(run.id)
            )
        return _runtime_run_record_from_orchestration_run(run)

    def list_runs(self) -> tuple[SessionRuntimeRunRecord, ...]:
        return tuple(
            _runtime_run_record_from_orchestration_run(run)
            for run in self._run_query_service.list_runs()
        )

    def cancel_session_tree(
        self,
        session_key: str,
        *,
        reason: str | None = None,
    ) -> dict[str, object]:
        return self._cancellation_service.cancel_session_tree(
            session_key,
            reason=reason,
        )


def _bound_turn_input(
    data: SubmitSessionBoundTurnInput,
) -> SubmitBoundOrchestrationTurnInput:
    return SubmitBoundOrchestrationTurnInput(
        agent_id=data.agent_id,
        session_key=data.session_key,
        active_session_id=data.active_session_id,
        metadata=data.metadata,
        accept_input=AcceptOrchestrationRunInput(
            inbound_instruction=InboundInstruction(
                source=data.source,
                metadata=data.inbound_metadata,
            ),
        ),
    )


def _spawn_turn_input(
    data: SubmitSessionSpawnTurnInput,
) -> SubmitOrchestrationTurnInput:
    spawn_metadata = {
        key: value
        for key, value in data.spawn_metadata.items()
        if value is not None
    }
    return SubmitOrchestrationTurnInput(
        accept_input=AcceptOrchestrationRunInput(
            inbound_instruction=InboundInstruction(
                source=data.source,
                content={
                    "blocks": [
                        {
                            "type": "text",
                            "text": data.text,
                        },
                    ],
                },
                metadata=data.spawn_metadata,
            ),
            metadata={data.source: spawn_metadata},
        ),
        context=SessionRouteContext(
            agent_id=data.agent_id,
            main_key=data.child_main_key,
            direct_scope=DirectSessionScope.MAIN,
            label="subagent",
            surface="session_tool",
            metadata={"spawn": spawn_metadata},
        ),
        prepare_metadata={data.source: spawn_metadata},
    )


def _runtime_run_record_from_orchestration_run(
    run: OrchestrationRun,
) -> SessionRuntimeRunRecord:
    runtime_request_mode = run.metadata.get("runtime_request_mode")
    return SessionRuntimeRunRecord(
        id=run.id,
        status=run.status.value,
        stage=run.stage.value,
        current_step=run.current_step,
        max_steps=run.max_steps,
        waiting_reason=run.waiting_reason,
        runtime_request_mode=str(runtime_request_mode) if runtime_request_mode is not None else None,
        worker_id=run.worker_id,
        session_key=run.session_key,
        metadata=dict(run.metadata),
        queued_at=run.queued_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


__all__ = [
    "IngressBackedSessionRuntimeControl",
    "SchedulerBackedSessionRuntimeControl",
]
