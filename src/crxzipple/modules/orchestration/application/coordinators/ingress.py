from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Protocol
from uuid import uuid4

from crxzipple.modules.dispatch.domain import (
    DispatchPolicy,
    DispatchTask,
    DispatchTaskRepository,
)
from crxzipple.modules.orchestration.application.dispatch_owner_kinds import (
    ORCHESTRATION_INGRESS_DISPATCH_OWNER_KIND,
)
from crxzipple.modules.orchestration.domain import (
    ExecutionChainRepository,
    ExecutionOwnerReference,
    ExecutionStepItemRepository,
    ExecutionStepRepository,
    OrchestrationBoundSessionTarget,
    OrchestrationIngressRequest,
    OrchestrationIngressRequestRepository,
    OrchestrationIngressStatus,
    OrchestrationQueuePolicy,
    OrchestrationRun,
    OrchestrationRunRepository,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.application.execution_chain_lifecycle import (
    INTAKE_OWNER_KIND,
    ensure_intake_execution_chain,
)
from crxzipple.modules.session.application.resolution import resolve_session_key
from crxzipple.modules.session.domain.exceptions import SessionValidationError
from crxzipple.shared.domain.aggregates import AggregateRoot

_INGRESS_TASK_KIND = "orchestration_ingress_request"
_DEFAULT_INGRESS_LEASE_SECONDS = 300

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application.commands import (
        SubmitBoundOrchestrationTurnInput,
        SubmitOrchestrationTurnInput,
    )


class IngressCoordinatorUnitOfWork(Protocol):
    execution_chains: ExecutionChainRepository
    execution_steps: ExecutionStepRepository
    execution_step_items: ExecutionStepItemRepository
    orchestration_runs: OrchestrationRunRepository
    orchestration_ingress_requests: OrchestrationIngressRequestRepository
    dispatch_tasks: DispatchTaskRepository

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
    lease_seconds: int = _DEFAULT_INGRESS_LEASE_SECONDS

    def submit_turn(
        self,
        data: "SubmitOrchestrationTurnInput",
    ) -> OrchestrationRun:
        run = OrchestrationRun.accept(
            run_id=data.accept_input.run_id or uuid4().hex,
            inbound_instruction=data.accept_input.inbound_instruction,
            reply_target=data.accept_input.reply_target,
            queue_policy=data.accept_input.queue_policy,
            priority=data.accept_input.priority,
            max_steps=data.accept_input.max_steps,
            metadata=self._initial_routed_metadata(data),
        )
        request = OrchestrationIngressRequest.queue_turn(
            request_id=uuid4().hex,
            run_id=run.id,
            route_context_payload=self._route_context_payload(data),
            requested_llm_id=data.requested_llm_id,
            ensure_session=data.ensure_session,
            touch_activity=data.touch_activity,
            reset_policy_payload=self._reset_policy_payload(data),
            prepare_metadata={
                **dict(data.accept_input.metadata),
                **dict(data.prepare_metadata),
            },
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
        return self._persist_submitted(run=run, request=request)

    def submit_bound_turn(
        self,
        data: "SubmitBoundOrchestrationTurnInput",
    ) -> OrchestrationRun:
        run = OrchestrationRun.accept(
            run_id=data.accept_input.run_id or uuid4().hex,
            inbound_instruction=data.accept_input.inbound_instruction,
            reply_target=data.accept_input.reply_target,
            queue_policy=data.accept_input.queue_policy,
            priority=data.accept_input.priority,
            max_steps=data.accept_input.max_steps,
            metadata=self._initial_bound_metadata(data),
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
            ensure_intake_execution_chain(
                uow,
                run=run,
                owner=ExecutionOwnerReference(
                    owner_kind=INTAKE_OWNER_KIND,
                    owner_id=request.id,
                ),
            )
            uow.orchestration_ingress_requests.add(request)
            self._enqueue_ingress_dispatch_task(uow, request)
            uow.collect(run)
            uow.collect(request)
            uow.commit()
        return run

    def claim_next_dispatch_request(
        self,
        *,
        worker_id: str,
    ) -> OrchestrationIngressRequest | None:
        with self.uow_factory() as uow:
            if self._recover_missing_ingress_dispatch_tasks(uow):
                uow.flush()
            self._recover_abandoned_ingress_tasks(uow)
            task = uow.dispatch_tasks.claim_next_queued(
                owner_kind=ORCHESTRATION_INGRESS_DISPATCH_OWNER_KIND,
                worker_id=worker_id,
                claim_token=_claim_token(worker_id),
                lease_seconds=self.lease_seconds,
            )
            if task is None:
                uow.commit()
                return None
            request = self._claim_request_for_dispatch_task(
                uow,
                task,
                worker_id=worker_id,
            )
            if request is None:
                uow.commit()
                return None
            uow.collect(request)
            uow.commit()
            return request

    def claim_dispatch_request_for_run(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> OrchestrationIngressRequest | None:
        with self.uow_factory() as uow:
            request = uow.orchestration_ingress_requests.get_by_run_id(run_id)
            if request is None:
                return None
            if (
                request.status is OrchestrationIngressStatus.QUEUED
                and uow.dispatch_tasks.get(_ingress_task_id(request.id)) is None
            ):
                self._enqueue_ingress_dispatch_task(uow, request)
                uow.flush()
            task = uow.dispatch_tasks.claim_queued(
                task_id=_ingress_task_id(request.id),
                owner_kind=ORCHESTRATION_INGRESS_DISPATCH_OWNER_KIND,
                worker_id=worker_id,
                claim_token=_claim_token(worker_id),
                lease_seconds=self.lease_seconds,
            )
            if task is None:
                return None
            request = self._claim_request_for_dispatch_task(
                uow,
                task,
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
            task = uow.dispatch_tasks.get(_ingress_task_id(request.id))
            if task is not None and _is_ingress_dispatch_task(task):
                task.complete(now=request.completed_at)
                uow.dispatch_tasks.add(task)
                uow.collect(task)
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
            task = uow.dispatch_tasks.get(_ingress_task_id(request.id))
            if task is not None and _is_ingress_dispatch_task(task):
                task.fail(
                    message=message,
                    code=code,
                    details=details or {},
                    now=request.completed_at,
                )
                uow.dispatch_tasks.add(task)
                uow.collect(task)
            uow.collect(request)
            uow.commit()
            return request

    def _enqueue_ingress_dispatch_task(
        self,
        uow: IngressCoordinatorUnitOfWork,
        request: OrchestrationIngressRequest,
    ) -> DispatchTask:
        task = uow.dispatch_tasks.get(_ingress_task_id(request.id))
        if task is None:
            task = DispatchTask.create(
                task_id=_ingress_task_id(request.id),
                owner_kind=ORCHESTRATION_INGRESS_DISPATCH_OWNER_KIND,
                owner_id=request.id,
                policy=_to_dispatch_policy(request.queue_policy),
                priority=_dispatch_priority(request.priority),
                payload_ref=request.run_id,
                metadata={
                    "task_kind": _INGRESS_TASK_KIND,
                    "request_id": request.id,
                    "request_kind": request.kind.value,
                    "run_id": request.run_id,
                },
            )
        task.enqueue(
            policy=_to_dispatch_policy(request.queue_policy),
            priority=_dispatch_priority(request.priority),
            queued_at=request.created_at,
        )
        uow.dispatch_tasks.add(task)
        uow.collect(task)
        return task

    def _recover_missing_ingress_dispatch_tasks(
        self,
        uow: IngressCoordinatorUnitOfWork,
    ) -> int:
        recovered_count = 0
        for request in uow.orchestration_ingress_requests.list(
            status=OrchestrationIngressStatus.QUEUED,
        ):
            if uow.dispatch_tasks.get(_ingress_task_id(request.id)) is not None:
                continue
            self._enqueue_ingress_dispatch_task(uow, request)
            recovered_count += 1
        return recovered_count

    def _recover_abandoned_ingress_tasks(
        self,
        uow: IngressCoordinatorUnitOfWork,
    ) -> None:
        for task in uow.dispatch_tasks.recover_abandoned(
            owner_kind=ORCHESTRATION_INGRESS_DISPATCH_OWNER_KIND,
        ):
            task.recover_abandoned(
                reason="Orchestration ingress lease expired before processing.",
            )
            uow.dispatch_tasks.add(task)
            uow.collect(task)

    def _claim_request_for_dispatch_task(
        self,
        uow: IngressCoordinatorUnitOfWork,
        task: DispatchTask,
        *,
        worker_id: str,
    ) -> OrchestrationIngressRequest | None:
        task.claim(
            worker_id=worker_id,
            claim_token=task.claim_token or _claim_token(worker_id),
            lease_seconds=self.lease_seconds,
            claimed_at=task.claimed_at,
        )
        uow.dispatch_tasks.add(task)
        uow.collect(task)
        if not _is_ingress_dispatch_task(task):
            return None
        request = uow.orchestration_ingress_requests.get(task.owner_id)
        if request is None:
            task.fail(
                message=f"Orchestration ingress request '{task.owner_id}' was not found.",
                code="ingress_request_not_found",
                details={"request_id": task.owner_id},
            )
            uow.dispatch_tasks.add(task)
            uow.collect(task)
            return None
        if request.status in {
            OrchestrationIngressStatus.COMPLETED,
            OrchestrationIngressStatus.FAILED,
        }:
            task.complete(now=request.completed_at)
            uow.dispatch_tasks.add(task)
            uow.collect(task)
            return None
        request.claim(worker_id=worker_id, claimed_at=task.claimed_at)
        uow.orchestration_ingress_requests.add(request)
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
    def _initial_routed_metadata(
        data: "SubmitOrchestrationTurnInput",
    ) -> dict[str, object]:
        metadata = dict(data.accept_input.metadata)
        try:
            resolution = resolve_session_key(data.context)
        except SessionValidationError as exc:
            raise OrchestrationValidationError(str(exc)) from exc
        metadata["session_key"] = resolution.key
        metadata["session_kind"] = resolution.kind.value
        requested_llm_id = _requested_llm_id(data.requested_llm_id)
        if requested_llm_id is not None:
            metadata.setdefault("requested_llm_id", requested_llm_id)
        return metadata

    @staticmethod
    def _initial_bound_metadata(
        data: "SubmitBoundOrchestrationTurnInput",
    ) -> dict[str, object]:
        metadata = dict(data.accept_input.metadata)
        metadata["session_key"] = data.session_key
        requested_llm_id = _requested_llm_id(data.requested_llm_id)
        if requested_llm_id is not None:
            metadata.setdefault("requested_llm_id", requested_llm_id)
        return metadata

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


def _requested_llm_id(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _ingress_task_id(request_id: str) -> str:
    return f"ingress:{request_id.strip()}"


def _is_ingress_dispatch_task(task: DispatchTask) -> bool:
    return (
        task.owner_kind == ORCHESTRATION_INGRESS_DISPATCH_OWNER_KIND
        and task.metadata.get("task_kind") == _INGRESS_TASK_KIND
    )


def _to_dispatch_policy(policy: OrchestrationQueuePolicy) -> DispatchPolicy:
    return DispatchPolicy(policy.value)


def _dispatch_priority(priority: int | None) -> int:
    return priority if priority is not None else 100


def _claim_token(worker_id: str) -> str:
    return f"orchestration-ingress:{worker_id.strip()}"
