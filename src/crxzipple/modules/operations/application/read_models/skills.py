from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleOverview,
)
from crxzipple.modules.operations.application.read_models.skills_models import (
    SkillsOperationsPage,
    SkillsOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.skills_overview_builder import (
    skills_operations_overview,
)
from crxzipple.modules.operations.application.read_models.skills_page_builder import (
    skills_operations_page,
)


@dataclass(slots=True)
class SkillsOperationsReadModelProvider:
    skill_manager: Any | None
    tool_service: Any | None = None
    access_service: Any | None = None
    agent_service: Any | None = None
    events_service: Any | None = None
    event_definition_registry: Any | None = None
    operations_observation: Any | None = None

    def overview(self) -> OperationsModuleOverview:
        return skills_operations_overview(
            skill_manager=self.skill_manager,
            tool_service=self.tool_service,
            access_service=self.access_service,
            agent_service=self.agent_service,
            events_service=self.events_service,
            event_definition_registry=self.event_definition_registry,
            operations_observation=self.operations_observation,
        )

    def page(
        self,
        query: SkillsOperationsQuery | None = None,
    ) -> SkillsOperationsPage:
        return skills_operations_page(
            skill_manager=self.skill_manager,
            tool_service=self.tool_service,
            access_service=self.access_service,
            agent_service=self.agent_service,
            events_service=self.events_service,
            event_definition_registry=self.event_definition_registry,
            operations_observation=self.operations_observation,
            query=query,
        )
