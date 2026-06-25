from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.operations.application.read_models.browser_health import (
    actions as _actions,
    metrics as _metrics,
    tabs as _tabs,
)
from crxzipple.modules.operations.application.read_models.browser_models import (
    BrowserOperationsPage,
    BrowserOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.browser_page_data import (
    build_browser_page_data,
)
from crxzipple.modules.operations.application.read_models.browser_activity_tables import (
    diagnostics_table as _diagnostics_table,
    network_activity_table as _network_activity_table,
)
from crxzipple.modules.operations.application.read_models.browser_profile_tables import (
    page_observations_table as _page_observations_table,
    profile_allocations_table as _profile_allocations_table,
    profile_pools_table as _profile_pools_table,
    profiles_table as _profiles_table,
)
from crxzipple.modules.operations.application.read_models.browser_runtime_tables import (
    daemon_runtimes_table as _daemon_runtimes_table,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleOverview,
    OperationsModuleRoleModel,
)
from crxzipple.shared.time import format_datetime_utc


@dataclass(slots=True)
class BrowserOperationsReadModelProvider:
    browser_profile_service: Any | None
    access_service: Any | None = None
    daemon_service: Any | None = None
    daemon_manager: Any | None = None
    operations_observation: Any | None = None

    def overview(self) -> OperationsModuleOverview:
        page = self.page(BrowserOperationsQuery(limit=40))
        return OperationsModuleOverview(
            module=page.module,
            title=page.title,
            subtitle=page.subtitle,
            health=page.health,
            updated_at=page.updated_at,
            metrics=page.metrics,
            queue=tuple(row.cells for row in page.profiles.rows[:20]),
            lane_locks=tuple(row.cells for row in page.page_observations.rows[:20]),
            executor=tuple(row.cells for row in page.daemon_runtimes.rows[:20]),
            actions=page.actions,
        )

    def page(
        self,
        query: BrowserOperationsQuery | None = None,
    ) -> BrowserOperationsPage:
        data = build_browser_page_data(
            browser_profile_service=self.browser_profile_service,
            access_service=self.access_service,
            daemon_service=self.daemon_service,
            daemon_manager=self.daemon_manager,
            operations_observation=self.operations_observation,
            query=query,
        )

        profiles_table = _profiles_table(
            data.visible_profiles,
            total=len(data.filtered_profiles),
        )
        pools_table = _profile_pools_table(
            data.visible_pools,
            total=len(data.filtered_pools),
        )
        allocations_table = _profile_allocations_table(
            data.visible_allocations,
            total=len(data.filtered_allocations),
        )
        pages_table = _page_observations_table(
            data.visible_pages,
            total=len(data.filtered_pages),
        )
        daemon_table = _daemon_runtimes_table(
            data.visible_daemons,
            total=len(data.filtered_daemons),
        )
        network_table = _network_activity_table(
            data.visible_network_activity,
            total=len(data.filtered_network_activity),
        )
        diagnostics_table = _diagnostics_table(
            data.visible_diagnostics,
            total=len(data.filtered_diagnostics),
        )

        return BrowserOperationsPage(
            module="browser",
            title="Browser Runtime",
            subtitle="观察浏览器 profile、CDP endpoint、页面 generation 与 daemon 托管状态。",
            health=data.health,
            updated_at=format_datetime_utc(data.now),
            auto_refresh=True,
            role=OperationsModuleRoleModel(
                label="Browser operator",
                can_operate=True,
                scope="browser",
            ),
            metrics=_metrics(
                health=data.health,
                profile_rows=data.profile_rows,
                pool_rows=data.pool_rows,
                allocation_rows=data.allocation_rows,
                page_rows=data.page_rows,
                daemon_rows=data.daemon_rows,
                network_activity_rows=data.network_activity_rows,
                diagnostic_rows=data.diagnostic_rows,
            ),
            tabs=_tabs(
                profile_count=len(data.filtered_profiles),
                pool_count=len(data.filtered_pools),
                allocation_count=len(data.filtered_allocations),
                page_count=len(data.filtered_pages),
                daemon_count=len(data.filtered_daemons),
                network_count=len(data.filtered_network_activity),
                diagnostic_count=len(data.filtered_diagnostics),
            ),
            active_tab="profiles",
            actions=_actions(),
            profiles=profiles_table,
            profile_pools=pools_table,
            profile_allocations=allocations_table,
            page_observations=pages_table,
            daemon_runtimes=daemon_table,
            network_activity=network_table,
            diagnostics=diagnostics_table,
        )
