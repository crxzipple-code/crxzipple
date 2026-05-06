from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Protocol
from uuid import uuid4

from crxzipple.modules.orchestration.domain import (
    OrchestrationBoundSessionTarget,
    OrchestrationIngressRequest,
    OrchestrationIngressRequestRepository,
    OrchestrationRun,
    OrchestrationRunRepository,
)
from crxzipple.shared.domain.aggregates import AggregateRoot

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application.commands import (
        SubmitBoundOrchestrationTurnInput,
        SubmitOrchestrationTurnInput,
    )


class IngressCoordinatorUnitOfWork(Protocol):
    orchestration_runs: OrchestrationRunRepository
    orchestration_ingress_requests: OrchestrationIngressRequestRepository

    def __enter__(self) -> "IngressCoordinatorUnitOfWork":
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

    def flush(self) -> None:
        ...

    def commit(self) -> None:
        ...


@dataclass(slots=True)
class RunIngressCoordinator:
    uow_factory: Callable[[], IngressCoordinatorUnitOfWork]

    def submit_turn(
        self,
        data: "SubmitOrchestrationTurnInput",
        *,
        claimed_worker_id: str | None = None,
    ) -> OrchestrationRun:
        run = OrchestrationRun.accept(
            run_id=data.accept_input.run_id or uuid4().hex,
            inbound_instruction=data.accept_input.inbound_instruction,
            reply_target=data.accept_input.reply_target,
            queue_policy=data.accept_input.queue_policy,
            priority=data.accept_input.priority,
            max_steps=data.accept_input.max_steps,
            metadata=data.accept_input.metadata,
        )
        request = OrchestrationIngressRequest.queue_turn(
            request_id=uuid4().hex,
            run_id=run.id,
            route_context_payload=self._route_context_payload(data),
            requested_llm_id=data.requested_llm_id,
            ensure_session=data.ensure_session,
            touch_activity=data.touch_activity,
            reset_policy_payload=self._reset_policy_payload(data),
            prepare_metadata=dict(data.prepare_metadata),
            queue_policy=(
                data.enqueue_queue_policy
                if data.enqueue_queue_policy is not None
                else data.accept_input.queue_policy
            ),
            priority=(
                data.enqueue_priority
                if data.enqueue_priority is not None
                else data.accept_input.priority
            ),
        )
        if claimed_worker_id is not None:
            request.claim(worker_id=claimed_worker_id)
        return self._persist_submitted(run=run, request=request)

    def submit_bound_turn(
        self,
        data: "SubmitBoundOrchestrationTurnInput",
        *,
        claimed_worker_id: str | None = None,
    ) -> OrchestrationRun:
        run = OrchestrationRun.accept(
            run_id=data.accept_input.run_id or uuid4().hex,
            inbound_instruction=data.accept_input.inbound_instruction,
            reply_target=data.accept_input.reply_target,
            queue_policy=data.accept_input.queue_policy,
            priority=data.accept_input.priority,
            max_steps=data.accept_input.max_steps,
            metadata=data.accept_input.metadata,
        )
        request = OrchestrationIngressRequest.queue_bound_turn(
            request_id=uuid4().hex,
            run_id=run.id,
            bound_session_target=self._bound_session_target(data),
            requested_llm_id=data.requested_llm_id,
            prepare_metadata=dict(data.metadata),
            queue_policy=(
                data.enqueue_queue_policy
                if data.enqueue_queue_policy is not None
                else data.accept_input.queue_policy
            ),
            priority=(
                data.enqueue_priority
                if data.enqueue_priority is not None
                else data.accept_input.priority
            ),
        )
        if claimed_worker_id is not None:
            request.claim(worker_id=claimed_worker_id)
        return self._persist_submitted(run=run, request=request)

    def _persist_submitted(
        self,
        *,
        run: OrchestrationRun,
        request: OrchestrationIngressRequest,
    ) -> OrchestrationRun:
        with self.uow_factory() as uow:
            uow.orchestration_runs.add(run)
            uow.flush()
            uow.orchestration_ingress_requests.add(request)
            uow.collect(run)
            uow.collect(request)
            uow.commit()
        return run

    def claim_next_request(self, *, worker_id: str) -> OrchestrationIngressRequest | None:
        with self.uow_factory() as uow:
            request = uow.orchestration_ingress_requests.claim_next(worker_id=worker_id)
            if request is None:
                return None
            uow.collect(request)
            uow.commit()
            return request

    def claim_request_for_run(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> OrchestrationIngressRequest | None:
        with self.uow_factory() as uow:
            request = uow.orchestration_ingress_requests.claim_for_run(
                run_id=run_id,
                worker_id=worker_id,
            )
            if request is None:
                return None
            uow.collect(request)
            uow.commit()
            return request

    def get_request_for_run(self, run_id: str) -> OrchestrationIngressRequest | None:
        with self.uow_factory() as uow:
            return uow.orchestration_ingress_requests.get_by_run_id(run_id)

    def complete_request(self, request_id: str) -> OrchestrationIngressRequest | None:
        with self.uow_factory() as uow:
            request = uow.orchestration_ingress_requests.get(request_id)
            if request is None:
                return None
            request.complete()
            uow.orchestration_ingress_requests.add(request)
            uow.collect(request)
            uow.commit()
            return request

    def fail_request(
        self,
        request_id: str,
        *,
        message: str,
        code: str = "ingress_failed",
        details: dict[str, object] | None = None,
    ) -> OrchestrationIngressRequest | None:
        with self.uow_factory() as uow:
            request = uow.orchestration_ingress_requests.get(request_id)
            if request is None:
                return None
            request.fail(
                message=message,
                code=code,
                details=details or {},
            )
            uow.orchestration_ingress_requests.add(request)
            uow.collect(request)
            uow.commit()
            return request

    @staticmethod
    def _route_context_payload(data: "SubmitOrchestrationTurnInput") -> dict[str, object]:
        context = data.context
        return {
            "agent_id": context.agent_id,
            "channel": context.channel,
            "chat_type": context.chat_type,
            "peer_id": context.peer_id,
            "conversation_id": context.conversation_id,
            "thread_id": context.thread_id,
            "account_id": context.account_id,
            "label": context.label,
            "surface": context.surface,
            "main_key": context.main_key,
            "direct_scope": context.direct_scope.value,
            "status": context.status,
            "metadata": dict(context.metadata),
        }

    @staticmethod
    def _reset_policy_payload(data: "SubmitOrchestrationTurnInput") -> dict[str, object]:
        reset_policy = data.reset_policy
        if reset_policy is None:
            return {}
        payload: dict[str, object] = {}
        if reset_policy.idle_minutes is not None:
            payload["idle_minutes"] = reset_policy.idle_minutes
        if reset_policy.daily_reset_hour_utc is not None:
            payload["daily_reset_hour_utc"] = reset_policy.daily_reset_hour_utc
        return payload

    @staticmethod
    def _bound_session_target(
        data: "SubmitBoundOrchestrationTurnInput",
    ) -> OrchestrationBoundSessionTarget:
        return OrchestrationBoundSessionTarget(
            agent_id=data.agent_id,
            session_key=data.session_key,
            active_session_id=data.active_session_id,
            lane_key=data.lane_key,
        )
