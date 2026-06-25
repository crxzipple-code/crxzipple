from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleOverview,
)
from crxzipple.modules.operations.application.read_models.skills_catalog_tables import (
    sources_table,
)
from crxzipple.modules.operations.application.read_models.skills_common import (
    overview_rows,
)
from crxzipple.modules.operations.application.read_models.skills_models import (
    SkillsOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.skills_page_builder import (
    skills_operations_page,
)


def skills_operations_overview(
    *,
    skill_manager: Any | None,
    tool_service: Any | None = None,
    access_service: Any | None = None,
    agent_service: Any | None = None,
    events_service: Any | None = None,
    event_definition_registry: Any | None = None,
    operations_observation: Any | None = None,
) -> OperationsModuleOverview:
    page = skills_operations_page(
        skill_manager=skill_manager,
        tool_service=tool_service,
        access_service=access_service,
        agent_service=agent_service,
        events_service=events_service,
        event_definition_registry=event_definition_registry,
        operations_observation=operations_observation,
        query=SkillsOperationsQuery(limit=50),
    )
    return OperationsModuleOverview(
        module=page.module,
        title=page.title,
        subtitle=page.subtitle,
        health=page.health,
        updated_at=page.updated_at,
        metrics=page.metrics,
        queue=overview_rows(page.recently_resolved_skills),
        lane_locks=overview_rows(sources_table(page.skill_package_sources)),
        executor=overview_rows(page.missing_capabilities),
        actions=page.actions,
    )
