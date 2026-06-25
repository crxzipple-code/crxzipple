from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleOverview,
)
from crxzipple.modules.operations.application.read_models.ports_tooling import (
    OperationsToolQueryPort,
)
from crxzipple.modules.operations.application.read_models.tool_models import (
    ToolOperationsPage,
)
from crxzipple.modules.operations.application.read_models.tool_overview_builder import (
    tool_operations_overview,
)
from crxzipple.modules.operations.application.read_models.tool_page_builder import (
    tool_operations_page,
)
from crxzipple.modules.operations.application.read_models.tool_run_query import (
    ToolOperationsQuery,
)


@dataclass(slots=True)
class ToolOperationsReadModelProvider:
    tool_service: OperationsToolQueryPort
    access_service: Any | None = None
    artifact_service: Any | None = None
    run_query: Any | None = None
    events_service: Any | None = None
    event_definition_registry: Any | None = None
    operations_observation: Any | None = None
    runtime_metrics: Any | None = None
    runtime_registry: Any | None = None
    runtime_bootstrap_config: Any | None = None

    def overview(self) -> OperationsModuleOverview:
        return tool_operations_overview(
            tool_service=self.tool_service,
            runtime_bootstrap_config=self.runtime_bootstrap_config,
        )

    def page(
        self,
        query: ToolOperationsQuery | None = None,
    ) -> ToolOperationsPage:
        return tool_operations_page(
            tool_service=self.tool_service,
            query=query,
            access_service=self.access_service,
            artifact_service=self.artifact_service,
            run_query=self.run_query,
            events_service=self.events_service,
            event_definition_registry=self.event_definition_registry,
            operations_observation=self.operations_observation,
            runtime_metrics=self.runtime_metrics,
            runtime_registry=self.runtime_registry,
            runtime_bootstrap_config=self.runtime_bootstrap_config,
        )
