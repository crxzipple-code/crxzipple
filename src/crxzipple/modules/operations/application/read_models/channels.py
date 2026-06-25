from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.operations.application.read_models.channels_models import (
    ChannelsOperationsPage,
    ChannelsOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.channels_overview_builder import (
    channels_operations_overview,
)
from crxzipple.modules.operations.application.read_models.channels_page_builder import (
    channels_operations_page,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleOverview,
)


@dataclass(slots=True)
class ChannelsOperationsReadModelProvider:
    channel_profile_service: Any | None
    channel_runtime_manager: Any | None
    channel_interaction_service: Any | None = None
    events_service: Any | None = None
    event_contract_registry: Any | None = None
    event_definition_registry: Any | None = None
    operations_observation: Any | None = None

    def overview(self) -> OperationsModuleOverview:
        return channels_operations_overview(
            channel_profile_service=self.channel_profile_service,
            channel_runtime_manager=self.channel_runtime_manager,
            channel_interaction_service=self.channel_interaction_service,
            events_service=self.events_service,
            event_contract_registry=self.event_contract_registry,
            event_definition_registry=self.event_definition_registry,
            operations_observation=self.operations_observation,
        )

    def page(
        self,
        query: ChannelsOperationsQuery | None = None,
    ) -> ChannelsOperationsPage:
        return channels_operations_page(
            channel_profile_service=self.channel_profile_service,
            channel_runtime_manager=self.channel_runtime_manager,
            channel_interaction_service=self.channel_interaction_service,
            events_service=self.events_service,
            event_contract_registry=self.event_contract_registry,
            event_definition_registry=self.event_definition_registry,
            operations_observation=self.operations_observation,
            query=query,
        )
