from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.channels_models import (
    ChannelsOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.channels_page_builder import (
    channels_operations_page,
)
from crxzipple.modules.operations.application.read_models.channels_sections import (
    overview_rows,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleOverview,
)


def channels_operations_overview(
    *,
    channel_profile_service: Any | None,
    channel_runtime_manager: Any | None,
    channel_interaction_service: Any | None = None,
    events_service: Any | None = None,
    event_contract_registry: Any | None = None,
    event_definition_registry: Any | None = None,
    operations_observation: Any | None = None,
) -> OperationsModuleOverview:
    page = channels_operations_page(
        channel_profile_service=channel_profile_service,
        channel_runtime_manager=channel_runtime_manager,
        channel_interaction_service=channel_interaction_service,
        events_service=events_service,
        event_contract_registry=event_contract_registry,
        event_definition_registry=event_definition_registry,
        operations_observation=operations_observation,
        query=ChannelsOperationsQuery(limit=40),
    )
    return OperationsModuleOverview(
        module=page.module,
        title=page.title,
        subtitle=page.subtitle,
        health=page.health,
        updated_at=page.updated_at,
        metrics=page.metrics,
        queue=overview_rows(page.channel_status),
        lane_locks=overview_rows(page.dead_letter_queue),
        executor=overview_rows(page.channel_profiles),
        actions=page.actions,
    )
