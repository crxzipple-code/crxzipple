from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from crxzipple.modules.operations.application.read_models.events_models import (
    EventsOperationsPage,
    EventsOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.events_overview_builder import (
    events_operations_overview,
)
from crxzipple.modules.operations.application.read_models.events_page_builder import (
    events_operations_page,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleOverview,
)


@dataclass(slots=True)
class EventsOperationsReadModelProvider:
    events_service: Any | None
    event_contract_registry: Any | None = None
    event_definition_registry: Any | None = None
    operations_observation: Any | None = None
    operations_observer_runtime: Any | None = None
    operations_observer_runtime_provider: Callable[[], Any | None] | None = None

    def overview(self) -> OperationsModuleOverview:
        return events_operations_overview(
            events_service=self.events_service,
            event_contract_registry=self.event_contract_registry,
            event_definition_registry=self.event_definition_registry,
            operations_observation=self.operations_observation,
            operations_observer_runtime=self._operations_observer_runtime(),
        )

    def page(
        self,
        query: EventsOperationsQuery | None = None,
    ) -> EventsOperationsPage:
        return events_operations_page(
            events_service=self.events_service,
            event_contract_registry=self.event_contract_registry,
            event_definition_registry=self.event_definition_registry,
            operations_observation=self.operations_observation,
            operations_observer_runtime=self._operations_observer_runtime(),
            query=query,
        )

    def _operations_observer_runtime(self) -> Any | None:
        if self.operations_observer_runtime_provider is not None:
            return self.operations_observer_runtime_provider()
        return self.operations_observer_runtime
