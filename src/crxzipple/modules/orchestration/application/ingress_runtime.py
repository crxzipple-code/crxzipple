from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from crxzipple.modules.orchestration.application.coordinators import (
    RunIngressCoordinator,
)
from crxzipple.modules.orchestration.application.ingress_processing import (
    fail_ingress_backed_run_record,
    process_ingress_request,
)
from crxzipple.modules.orchestration.application.intake_workflows import (
    build_run_intake_coordinator,
)
from crxzipple.modules.orchestration.application.ports import (
    OrchestrationDispatchPort,
    SessionResolutionPort,
)
from crxzipple.modules.orchestration.application.ports.runtime import (
    OrchestrationRunQueryPort,
)
from crxzipple.modules.orchestration.application.scheduler import (
    OrchestrationScheduler,
)

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application.commands import (
        SubmitBoundOrchestrationTurnInput,
        SubmitOrchestrationTurnInput,
    )
    from crxzipple.modules.orchestration.domain import (
        OrchestrationIngressRequest,
        OrchestrationRun,
    )
    from crxzipple.modules.orchestration.application.coordinators import (
        RunIntakeCoordinator,
    )


@dataclass(slots=True)
class OrchestrationIngressRuntimeService:
    """Owns lightweight ingress submission and processing without scheduler runtime."""

    uow_factory: Callable[[], Any]
    run_query_service: OrchestrationRunQueryPort
    session_resolution_service: SessionResolutionPort
    dispatch_port: OrchestrationDispatchPort
    _ingress: RunIngressCoordinator = field(init=False)
    _intake: RunIntakeCoordinator = field(init=False)

    def __post_init__(self) -> None:
        self._ingress = RunIngressCoordinator(uow_factory=self.uow_factory)
        self._intake = build_run_intake_coordinator(
            uow_factory=self.uow_factory,
            scheduler=OrchestrationScheduler(),
            dispatch_port=self.dispatch_port,
            resolve_session_bundle=self.session_resolution_service.resolve,
        )

    def submit_turn(
        self,
        data: "SubmitOrchestrationTurnInput",
        *,
        inline_worker_id: str | None = None,
    ) -> "OrchestrationRun":
        run = self._ingress.submit_turn(data)
        if inline_worker_id is None:
            return run
        processed = self.process_run_request(
            run_id=run.id,
            worker_id=inline_worker_id,
        )
        return processed or self.run_query_service.get_run(run.id)

    def submit_bound_turn(
        self,
        data: "SubmitBoundOrchestrationTurnInput",
        *,
        inline_worker_id: str | None = None,
    ) -> "OrchestrationRun":
        run = self._ingress.submit_bound_turn(data)
        if inline_worker_id is None:
            return run
        processed = self.process_run_request(
            run_id=run.id,
            worker_id=inline_worker_id,
        )
        return processed or self.run_query_service.get_run(run.id)

    def process_run_request(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> "OrchestrationRun | None":
        return process_ingress_request(
            self._ingress.claim_dispatch_request_for_run(
                run_id=run_id,
                worker_id=worker_id,
            ),
            worker_id=worker_id,
            ingress_coordinator=self._ingress,
            intake_port=self._intake,
            fail_run=self._fail_ingress_backed_run,
        )

    def _fail_ingress_backed_run(
        self,
        request: "OrchestrationIngressRequest",
        worker_id: str,
        exc: Exception,
    ) -> None:
        fail_ingress_backed_run_record(
            uow_factory=self.uow_factory,
            dispatch_port=self.dispatch_port,
            request=request,
            worker_id=worker_id,
            exc=exc,
        )


__all__ = ["OrchestrationIngressRuntimeService"]
