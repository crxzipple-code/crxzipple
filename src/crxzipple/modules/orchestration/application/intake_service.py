from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from crxzipple.modules.orchestration.domain import OrchestrationRun

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application.intake_commands import (
        AcceptOrchestrationRunInput,
        BindSessionInput,
        EnqueueOrchestrationRunInput,
        PrepareSessionRunInput,
        RouteOrchestrationRunInput,
    )
    from crxzipple.modules.orchestration.application.coordinators.intake import (
        RunIntakeCoordinator,
    )


@dataclass(slots=True)
class OrchestrationIntakeService:
    coordinator: "RunIntakeCoordinator"

    def accept(self, data: "AcceptOrchestrationRunInput") -> OrchestrationRun:
        return self.coordinator.accept(data)

    def route(self, data: "RouteOrchestrationRunInput") -> OrchestrationRun:
        return self.coordinator.route(data)

    def bind_session(self, data: "BindSessionInput") -> OrchestrationRun:
        return self.coordinator.bind_session(data)

    def enqueue(self, data: "EnqueueOrchestrationRunInput") -> OrchestrationRun:
        return self.coordinator.enqueue(data)

    def prepare_session_run(self, data: "PrepareSessionRunInput") -> OrchestrationRun:
        return self.coordinator.prepare_session_run(data)
