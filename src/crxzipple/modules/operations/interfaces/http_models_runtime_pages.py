from __future__ import annotations

from pydantic import BaseModel

from crxzipple.modules.operations.application.read_models import (
    BrowserOperationsPage,
)
from crxzipple.modules.operations.interfaces.http_models_core import (
    MetricCardResponse,
    OperationsModuleRoleResponse,
    OperationsProjectionFreshnessResponse,
    OperationsTabResponse,
    OperationsTableSectionResponse,
    RuntimeActionResponse,
)


class BrowserOperationsResponse(BaseModel):
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
    profiles: OperationsTableSectionResponse
    profile_pools: OperationsTableSectionResponse
    profile_allocations: OperationsTableSectionResponse
    page_observations: OperationsTableSectionResponse
    daemon_runtimes: OperationsTableSectionResponse
    network_activity: OperationsTableSectionResponse
    diagnostics: OperationsTableSectionResponse
    projection_freshness: OperationsProjectionFreshnessResponse | None = None

    @classmethod
    def from_view(
        cls,
        view: BrowserOperationsPage,
    ) -> "BrowserOperationsResponse":
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
            profiles=OperationsTableSectionResponse.from_value(view.profiles),
            profile_pools=OperationsTableSectionResponse.from_value(
                view.profile_pools,
            ),
            profile_allocations=OperationsTableSectionResponse.from_value(
                view.profile_allocations,
            ),
            page_observations=OperationsTableSectionResponse.from_value(
                view.page_observations,
            ),
            daemon_runtimes=OperationsTableSectionResponse.from_value(
                view.daemon_runtimes,
            ),
            network_activity=OperationsTableSectionResponse.from_value(
                view.network_activity,
            ),
            diagnostics=OperationsTableSectionResponse.from_value(
                view.diagnostics,
            ),
        )
