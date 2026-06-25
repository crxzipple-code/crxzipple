from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.daemon.interfaces.presenters import instance_payload, spec_payload
from crxzipple.modules.operations.application.read_models.browser_events import (
    diagnostic_rows,
    network_activity_rows,
    recent_browser_events,
)
from crxzipple.modules.operations.application.read_models.browser_health import (
    health as browser_health,
)
from crxzipple.modules.operations.application.read_models.browser_models import (
    BrowserOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.browser_page_filters import (
    filter_rows,
    normalize_browser_query,
    visible_rows,
)
from crxzipple.modules.operations.application.read_models.browser_profile_rows import (
    page_rows as browser_page_rows,
    profile_rows as browser_profile_rows,
)
from crxzipple.modules.operations.application.read_models.browser_page_sources import (
    safe_profiles,
    safe_tuple,
)
from crxzipple.modules.operations.application.read_models.browser_rows import (
    allocation_rows as browser_allocation_rows,
    daemon_rows as browser_daemon_rows,
    pool_rows as browser_pool_rows,
)
from crxzipple.modules.operations.application.read_models.browser_runtime_facts import (
    proxy_metadata_by_profile,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)


@dataclass(frozen=True, slots=True)
class BrowserPageData:
    query: BrowserOperationsQuery
    now: datetime
    profile_rows: tuple[OperationsTableRowModel, ...]
    pool_rows: tuple[OperationsTableRowModel, ...]
    allocation_rows: tuple[OperationsTableRowModel, ...]
    page_rows: tuple[OperationsTableRowModel, ...]
    daemon_rows: tuple[OperationsTableRowModel, ...]
    network_activity_rows: tuple[OperationsTableRowModel, ...]
    diagnostic_rows: tuple[OperationsTableRowModel, ...]
    filtered_profiles: tuple[OperationsTableRowModel, ...]
    visible_profiles: tuple[OperationsTableRowModel, ...]
    filtered_pools: tuple[OperationsTableRowModel, ...]
    visible_pools: tuple[OperationsTableRowModel, ...]
    filtered_allocations: tuple[OperationsTableRowModel, ...]
    visible_allocations: tuple[OperationsTableRowModel, ...]
    filtered_pages: tuple[OperationsTableRowModel, ...]
    visible_pages: tuple[OperationsTableRowModel, ...]
    filtered_daemons: tuple[OperationsTableRowModel, ...]
    visible_daemons: tuple[OperationsTableRowModel, ...]
    filtered_network_activity: tuple[OperationsTableRowModel, ...]
    visible_network_activity: tuple[OperationsTableRowModel, ...]
    filtered_diagnostics: tuple[OperationsTableRowModel, ...]
    visible_diagnostics: tuple[OperationsTableRowModel, ...]
    health: str


def build_browser_page_data(
    *,
    browser_profile_service: Any | None,
    access_service: Any | None = None,
    daemon_service: Any | None = None,
    daemon_manager: Any | None = None,
    operations_observation: Any | None = None,
    query: BrowserOperationsQuery | None = None,
) -> BrowserPageData:
    normalized_query = normalize_browser_query(query)
    now = datetime.now(timezone.utc)
    profiles = safe_profiles(browser_profile_service)
    pools = safe_tuple(browser_profile_service, "list_pools")
    allocations = safe_tuple(browser_profile_service, "list_allocations")
    instances = tuple(
        instance_payload(item)
        for item in safe_tuple(daemon_manager, "list_instances", refresh=False)
    )
    services = tuple(
        spec_payload(item)
        for item in safe_tuple(daemon_service, "list_service_specs")
    )
    profile_rows = browser_profile_rows(
        profiles,
        access_service=access_service,
        proxy_metadata_by_profile=proxy_metadata_by_profile(instances),
    )
    page_rows = browser_page_rows(profiles)
    daemon_rows = browser_daemon_rows(services=services, instances=instances)
    pool_rows = browser_pool_rows(pools)
    allocation_rows = browser_allocation_rows(allocations, now=now)
    observed_events = recent_browser_events(operations_observation)
    network_rows = network_activity_rows(observed_events)
    diagnostics = diagnostic_rows(observed_events)
    filtered_profiles = filter_rows(profile_rows, normalized_query)
    filtered_pools = filter_rows(pool_rows, normalized_query)
    filtered_allocations = filter_rows(allocation_rows, normalized_query)
    filtered_pages = filter_rows(page_rows, normalized_query)
    filtered_daemons = filter_rows(daemon_rows, normalized_query)
    filtered_network = filter_rows(network_rows, normalized_query)
    filtered_diagnostics = filter_rows(diagnostics, normalized_query)
    return BrowserPageData(
        query=normalized_query,
        now=now,
        profile_rows=profile_rows,
        pool_rows=pool_rows,
        allocation_rows=allocation_rows,
        page_rows=page_rows,
        daemon_rows=daemon_rows,
        network_activity_rows=network_rows,
        diagnostic_rows=diagnostics,
        filtered_profiles=filtered_profiles,
        visible_profiles=visible_rows(filtered_profiles, normalized_query),
        filtered_pools=filtered_pools,
        visible_pools=visible_rows(filtered_pools, normalized_query),
        filtered_allocations=filtered_allocations,
        visible_allocations=visible_rows(filtered_allocations, normalized_query),
        filtered_pages=filtered_pages,
        visible_pages=visible_rows(filtered_pages, normalized_query),
        filtered_daemons=filtered_daemons,
        visible_daemons=visible_rows(filtered_daemons, normalized_query),
        filtered_network_activity=filtered_network,
        visible_network_activity=visible_rows(filtered_network, normalized_query),
        filtered_diagnostics=filtered_diagnostics,
        visible_diagnostics=visible_rows(filtered_diagnostics, normalized_query),
        health=browser_health(
            profile_rows=profile_rows,
            page_rows=page_rows,
            pool_rows=pool_rows,
            allocation_rows=allocation_rows,
            network_activity_rows=network_rows,
            diagnostic_rows=diagnostics,
        ),
    )
