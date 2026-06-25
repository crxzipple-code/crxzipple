from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.operations.application.read_models.daemon_models import (
    DaemonOperationsPage,
    DaemonOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.daemon_page_helpers import (
    overview_rows,
)
from crxzipple.modules.operations.application.read_models.daemon_page_builder import (
    daemon_operations_page,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleOverview,
)


@dataclass(slots=True)
class DaemonOperationsReadModelProvider:
    daemon_service: Any | None
    daemon_manager: Any | None
    events_service: Any | None = None
    event_definition_registry: Any | None = None
    operations_observation: Any | None = None
    process_service: Any | None = None
    runtime_bootstrap_config: Any | None = None

    def overview(self) -> OperationsModuleOverview:
        page = self.page(DaemonOperationsQuery(limit=40))
        return OperationsModuleOverview(
            module=page.module,
            title=page.title,
            subtitle=page.subtitle,
            health=page.health,
            updated_at=page.updated_at,
            metrics=page.metrics,
            queue=overview_rows(page.service_sets),
            lane_locks=overview_rows(page.services),
            executor=overview_rows(page.instances),
            actions=page.actions,
        )

    def page(
        self,
        query: DaemonOperationsQuery | None = None,
    ) -> DaemonOperationsPage:
        return daemon_operations_page(
            query=query,
            daemon_service=self.daemon_service,
            daemon_manager=self.daemon_manager,
            events_service=self.events_service,
            event_definition_registry=self.event_definition_registry,
            operations_observation=self.operations_observation,
            process_service=self.process_service,
            runtime_bootstrap_config=self.runtime_bootstrap_config,
        )
