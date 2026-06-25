from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from crxzipple.modules.operations.application.read_models import (
    OperationsModuleOverview,
)
from crxzipple.modules.operations.interfaces.http_models_core_primitives import (
    MetricCardResponse,
    OperationsModuleRoleResponse,
    OperationsTabResponse,
    RuntimeActionResponse,
)
from crxzipple.modules.operations.interfaces.http_models_core_sections import (
    OperationsTableSectionResponse,
)


class OperationsModuleOverviewResponse(BaseModel):
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    metrics: list[MetricCardResponse]
    queue: list[dict[str, str]]
    lane_locks: list[dict[str, str]]
    executor: list[dict[str, str]]
    actions: list[RuntimeActionResponse]

    @classmethod
    def from_view(
        cls,
        view: OperationsModuleOverview,
    ) -> "OperationsModuleOverviewResponse":
        return cls(
            module=view.module,
            title=view.title,
            subtitle=view.subtitle,
            health=view.health,
            updated_at=view.updated_at,
            metrics=[MetricCardResponse.from_value(item) for item in view.metrics],
            queue=list(view.queue),
            lane_locks=list(view.lane_locks),
            executor=list(view.executor),
            actions=[RuntimeActionResponse.from_value(item) for item in view.actions],
        )


class OperationsModulePageResponse(BaseModel):
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    auto_refresh: bool
    role: OperationsModuleRoleResponse
    metrics: list[MetricCardResponse]
    tabs: list[OperationsTabResponse]
    active_tab: str
    actions: list[RuntimeActionResponse]
    sections: list[OperationsTableSectionResponse]

    @classmethod
    def from_view(
        cls,
        view: Any,
    ) -> "OperationsModulePageResponse":
        return cls(
            module=view.module,
            title=view.title,
            subtitle=view.subtitle,
            health=view.health,
            updated_at=view.updated_at,
            auto_refresh=view.auto_refresh,
            role=OperationsModuleRoleResponse.from_value(view.role),
            metrics=[MetricCardResponse.from_value(item) for item in view.metrics],
            tabs=[OperationsTabResponse.from_value(item) for item in view.tabs],
            active_tab=view.active_tab,
            actions=[RuntimeActionResponse.from_value(item) for item in view.actions],
            sections=[
                OperationsTableSectionResponse.from_value(item)
                for item in view.sections
            ],
        )
