from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Protocol
from uuid import uuid4

from crxzipple.modules.dispatch.domain import DispatchTaskRepository
from crxzipple.modules.orchestration.application.execution_chain_lifecycle import (
    ORCHESTRATION_RUN_INTAKE_OWNER_KIND,
    ensure_intake_execution_chain,
    prepare_dispatch_execution_step,
)
from crxzipple.modules.orchestration.application.ports import OrchestrationDispatchPort
from crxzipple.modules.orchestration.application.scheduler import (
    OrchestrationScheduler,
)
from crxzipple.modules.orchestration.domain import (
    ExecutionChainRepository,
    ExecutionOwnerReference,
    ExecutionStepItemRepository,
    ExecutionStepRepository,
    OrchestrationRun,
    OrchestrationRunRepository,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationRunNotFoundError,
)
from crxzipple.shared.domain.aggregates import AggregateRoot

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application.intake_commands import (
        AcceptOrchestrationRunInput,
        BindSessionInput,
        EnqueueOrchestrationRunInput,
        PrepareSessionRunInput,
        RouteOrchestrationRunInput,
    )
    from crxzipple.modules.orchestration.application.intake_workflows import (
        PreparedSessionRunPlan,
    )


class IntakeCoordinatorUnitOfWork(Protocol):
    execution_chains: ExecutionChainRepository
    execution_steps: ExecutionStepRepository
    execution_step_items: ExecutionStepItemRepository
    orchestration_runs: OrchestrationRunRepository
    dispatch_tasks: DispatchTaskRepository

    def __enter__(self) -> "IntakeCoordinatorUnitOfWork":
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
class RunIntakeCoordinator:
    uow_factory: Callable[[], IntakeCoordinatorUnitOfWork]
    scheduler: OrchestrationScheduler
    dispatch_port: OrchestrationDispatchPort
    plan_prepared_session_run: Callable[
        ["PrepareSessionRunInput"],
        "PreparedSessionRunPlan",
    ]

    def accept(self, data: "AcceptOrchestrationRunInput") -> OrchestrationRun:
        run = OrchestrationRun.accept(
            run_id=data.run_id or uuid4().hex,
            inbound_instruction=data.inbound_instruction,
            reply_target=data.reply_target,
            queue_policy=data.queue_policy,
            priority=data.priority,
            max_steps=data.max_steps,
            metadata=data.metadata,
        )
        with self.uow_factory() as uow:
            uow.orchestration_runs.add(run)
            uow.flush()
            ensure_intake_execution_chain(
                uow,
                run=run,
                owner=ExecutionOwnerReference(
                    owner_kind=ORCHESTRATION_RUN_INTAKE_OWNER_KIND,
                    owner_id=run.id,
                ),
            )
            uow.collect(run)
            uow.commit()
            return run

    def route(self, data: "RouteOrchestrationRunInput") -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            route_metadata = dict(data.metadata)
            if data.session_key is not None and data.session_key.strip():
                route_metadata.setdefault("session_key", data.session_key.strip())
            run.route(
                agent_id=data.agent_id,
                lane_key=data.lane_key,
                priority=data.priority,
                metadata=route_metadata,
            )
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def bind_session(self, data: "BindSessionInput") -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            run.bind_session(
                active_session_id=data.active_session_id,
            )
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def enqueue(self, data: "EnqueueOrchestrationRunInput") -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            self.scheduler.enqueue(
                run,
                lane_key=data.lane_key,
                queue_policy=data.queue_policy,
                priority=data.priority,
            )
            dispatch_step = prepare_dispatch_execution_step(
                uow,
                run=run,
            )
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

    def prepare_session_run(self, data: "PrepareSessionRunInput") -> OrchestrationRun:
        plan = self.plan_prepared_session_run(data)

        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            run.route(
                agent_id=plan.agent_id,
                lane_key=plan.lane_key,
                priority=plan.priority,
                metadata=dict(plan.route_metadata),
            )
            run.bind_session(
                active_session_id=plan.active_session_id,
            )
            if plan.prompt_flow_hint is not None:
                run.metadata["prompt_flow_hint"] = dict(plan.prompt_flow_hint)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    @staticmethod
    def _get_run(
        uow: IntakeCoordinatorUnitOfWork,
        run_id: str,
    ) -> OrchestrationRun:
        run = uow.orchestration_runs.get(run_id)
        if run is None:
            raise OrchestrationRunNotFoundError(
                f"Orchestration run '{run_id}' was not found.",
            )
        return run
