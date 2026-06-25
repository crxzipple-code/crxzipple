from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.events_models import (
    EventsOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.events_page_builder import (
    events_operations_page,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleOverview,
    OperationsTableSectionModel,
)


def events_operations_overview(
    *,
    events_service: Any | None,
    event_contract_registry: Any | None = None,
    event_definition_registry: Any | None = None,
    operations_observation: Any | None = None,
    operations_observer_runtime: Any | None = None,
) -> OperationsModuleOverview:
    page = events_operations_page(
        events_service=events_service,
        event_contract_registry=event_contract_registry,
        event_definition_registry=event_definition_registry,
        operations_observation=operations_observation,
        operations_observer_runtime=operations_observer_runtime,
        query=EventsOperationsQuery(limit=50),
    )
    return OperationsModuleOverview(
        module=page.module,
        title=page.title,
        subtitle=page.subtitle,
        health=page.health,
        updated_at=page.updated_at,
        metrics=page.metrics,
        queue=_overview_rows(page.subscriptions),
        lane_locks=_overview_rows(page.owners_by_volume),
        executor=_overview_rows(page.observer_coverage),
        actions=page.actions,
    )


def _overview_rows(section: OperationsTableSectionModel) -> tuple[dict[str, str], ...]:
    return tuple(
        {key: str(value) for key, value in row.cells.items()}
        for row in section.rows[:80]
    )
