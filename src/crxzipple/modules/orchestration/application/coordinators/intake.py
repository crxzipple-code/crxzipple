from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Protocol
from uuid import uuid4

from crxzipple.modules.dispatch.domain import DispatchTaskRepository
from crxzipple.modules.orchestration.application.ports import RunDispatchPort
from crxzipple.modules.orchestration.application.scheduler import (
    OrchestrationScheduler,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
    OrchestrationRunRepository,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationRunNotFoundError,
    OrchestrationValidationError,
)
from crxzipple.shared.domain.aggregates import AggregateRoot

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application.services import (
        AcceptOrchestrationRunInput,
        BindSessionInput,
        EnqueueOrchestrationRunInput,
        PrepareSessionRunInput,
        RouteOrchestrationRunInput,
    )
    from crxzipple.modules.orchestration.application.session_resolver import (
        ResolveSessionBundleInput,
        SessionBundle,
    )


class IntakeCoordinatorUnitOfWork(Protocol):
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

    def commit(self) -> None:
        ...


@dataclass(slots=True)
class RunIntakeCoordinator:
    uow_factory: Callable[[], IntakeCoordinatorUnitOfWork]
    scheduler: OrchestrationScheduler
    dispatch_port: RunDispatchPort
    resolve_session_bundle: Callable[["ResolveSessionBundleInput"], "SessionBundle"]
    resolve_session_bundle_input_factory: Callable[..., "ResolveSessionBundleInput"]
    session_start_prompt_flow_hint: Callable[["SessionBundle"], dict[str, object] | None]

    def accept(self, data: "AcceptOrchestrationRunInput") -> OrchestrationRun:
        run = OrchestrationRun.accept(
            run_id=data.run_id or uuid4().hex,
            inbound_instruction=data.inbound_instruction,
            delivery_target=data.delivery_target,
            queue_policy=data.queue_policy,
            priority=data.priority,
            max_steps=data.max_steps,
            metadata=data.metadata,
        )
        with self.uow_factory() as uow:
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def route(self, data: "RouteOrchestrationRunInput") -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            run.route(
                agent_id=data.agent_id,
                bulk_key=data.bulk_key,
                lane_key=data.lane_key,
                priority=data.priority,
                metadata=data.metadata,
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
                bulk_key=data.bulk_key,
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
            self.dispatch_port.enqueue(uow.dispatch_tasks, uow, run)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def prepare_session_run(self, data: "PrepareSessionRunInput") -> OrchestrationRun:
        bundle = self.resolve_session_bundle(
            self.resolve_session_bundle_input_factory(
                context=data.context,
                ensure=data.ensure,
                touch_activity=data.touch_activity,
                reset_policy=data.reset_policy,
                now=data.now,
            ),
        )
        if bundle.session is None or bundle.active_instance is None:
            raise OrchestrationValidationError(
                "Session resolution did not produce an active session to bind.",
            )

        route_metadata = {
            "session_key": bundle.routing.key_resolution.key,
            "session_kind": bundle.routing.key_resolution.kind.value,
        }
        route_metadata.update(data.metadata)

        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            run.route(
                agent_id=data.context.agent_id,
                bulk_key=bundle.routing.bulk_key,
                lane_key=bundle.routing.lane_key,
                priority=data.priority,
                metadata=route_metadata,
            )
            run.bind_session(
                active_session_id=bundle.active_instance.id,
                bulk_key=bundle.routing.bulk_key,
            )
            prompt_flow_hint = self.session_start_prompt_flow_hint(bundle)
            if prompt_flow_hint is not None:
                run.metadata["prompt_flow_hint"] = prompt_flow_hint
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
