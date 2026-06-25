from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.operations.application.read_models.llm_models import (
    LlmOperationsPage,
)
from crxzipple.modules.operations.application.read_models.llm_overview_builder import (
    llm_operations_overview,
)
from crxzipple.modules.operations.application.read_models.llm_page_builder import (
    llm_operations_page,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_filters import (
    LlmOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleOverview,
)
from crxzipple.modules.operations.application.read_models.ports_llm_agent import (
    OperationsLlmQueryPort,
)
from crxzipple.modules.operations.application.read_models.ports_runtime import (
    OperationsObservationReadPort,
)


@dataclass(slots=True)
class LlmOperationsReadModelProvider:
    llm_service: OperationsLlmQueryPort
    access_service: Any | None = None
    run_query: Any | None = None
    events_service: Any | None = None
    event_definition_registry: Any | None = None
    operations_observation: OperationsObservationReadPort | None = None
    runtime_metrics: Any | None = None

    def overview(self) -> OperationsModuleOverview:
        return llm_operations_overview(
            llm_service=self.llm_service,
            access_service=self.access_service,
        )

    def page(
        self,
        query: LlmOperationsQuery | None = None,
    ) -> LlmOperationsPage:
        return llm_operations_page(
            llm_service=self.llm_service,
            query=query,
            access_service=self.access_service,
            run_query=self.run_query,
            events_service=self.events_service,
            event_definition_registry=self.event_definition_registry,
            operations_observation=self.operations_observation,
            runtime_metrics=self.runtime_metrics,
        )
