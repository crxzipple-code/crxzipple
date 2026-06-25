from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.operations.application.read_models.access_common import (
    overview_rows as _overview_rows,
)
from crxzipple.modules.operations.application.read_models.access_models import (
    AccessOperationsPage,
    AccessOperationsQuery,
    AccessTargetDetailModel,
)
from crxzipple.modules.operations.application.read_models.access_page_builder import (
    access_operations_page,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleOverview,
)


@dataclass(slots=True)
class AccessOperationsReadModelProvider:
    access_service: Any | None
    access_governance_repository: Any | None
    llm_service: Any | None
    tool_service: Any | None
    channel_profile_service: Any | None
    lark_channel_runtime_service: Any | None
    web_channel_runtime_service: Any | None
    webhook_channel_runtime_service: Any | None
    settings_query_service: Any | None = None
    settings_environment: str | None = None
    events_service: Any | None = None
    event_definition_registry: Any | None = None
    operations_observation: Any | None = None

    def overview(self) -> OperationsModuleOverview:
        page = self.page(AccessOperationsQuery(limit=40))
        return OperationsModuleOverview(
            module=page.module,
            title=page.title,
            subtitle=page.subtitle,
            health=page.health,
            updated_at=page.updated_at,
            metrics=page.metrics,
            queue=_overview_rows(page.missing_access),
            lane_locks=_overview_rows(page.access_targets),
            executor=_overview_rows(page.authentication_status),
            actions=page.actions,
        )

    def page(
        self,
        query: AccessOperationsQuery | None = None,
    ) -> AccessOperationsPage:
        return access_operations_page(provider=self, query=query)


__all__ = [
    "AccessOperationsPage",
    "AccessOperationsQuery",
    "AccessOperationsReadModelProvider",
    "AccessTargetDetailModel",
]
