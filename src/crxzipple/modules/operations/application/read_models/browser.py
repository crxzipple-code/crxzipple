from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.daemon.interfaces.presenters import instance_payload, spec_payload
from crxzipple.modules.operations.application.observation import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsModuleOverview,
    OperationsModuleRoleModel,
    OperationsTabModel,
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
    RuntimeActionModel,
)
from crxzipple.shared.time import format_datetime_utc


@dataclass(frozen=True, slots=True)
class BrowserOperationsQuery:
    status: str = "all"
    profile: str = "all"
    search: str = ""
    limit: int = 80
    offset: int = 0


@dataclass(frozen=True, slots=True)
class BrowserOperationsPage:
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    auto_refresh: bool
    role: OperationsModuleRoleModel
    metrics: tuple[MetricCardModel, ...]
    tabs: tuple[OperationsTabModel, ...]
    active_tab: str
    actions: tuple[RuntimeActionModel, ...]
    profiles: OperationsTableSectionModel
    profile_pools: OperationsTableSectionModel
    profile_allocations: OperationsTableSectionModel
    page_observations: OperationsTableSectionModel
    daemon_runtimes: OperationsTableSectionModel
    network_activity: OperationsTableSectionModel
    diagnostics: OperationsTableSectionModel


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
        query = _normalize_query(query)
        now = datetime.now(timezone.utc)
        profiles = _safe_profiles(self.browser_profile_service)
        pools = _safe_tuple(self.browser_profile_service, "list_pools")
        allocations = _safe_tuple(self.browser_profile_service, "list_allocations")
        instances = tuple(
            instance_payload(item)
            for item in _safe_tuple(
                self.daemon_manager,
                "list_instances",
                refresh=False,
            )
        )
        services = tuple(
            spec_payload(item)
            for item in _safe_tuple(self.daemon_service, "list_service_specs")
        )
        proxy_metadata_by_profile = _proxy_metadata_by_profile(instances)
        profile_rows = _profile_rows(
            profiles,
            access_service=self.access_service,
            proxy_metadata_by_profile=proxy_metadata_by_profile,
        )
        page_rows = _page_rows(profiles)
        daemon_rows = _daemon_rows(services=services, instances=instances)
        pool_rows = _pool_rows(pools)
        allocation_rows = _allocation_rows(allocations, now=now)
        observed_events = _recent_browser_events(self.operations_observation)
        network_activity_rows = _network_activity_rows(observed_events)
        diagnostic_rows = _diagnostic_rows(observed_events)
        filtered_profiles = _filter_rows(profile_rows, query)
        visible_profiles = filtered_profiles[query.offset : query.offset + query.limit]
        filtered_pools = _filter_rows(pool_rows, query)
        visible_pools = filtered_pools[query.offset : query.offset + query.limit]
        filtered_allocations = _filter_rows(allocation_rows, query)
        visible_allocations = filtered_allocations[
            query.offset : query.offset + query.limit
        ]
        filtered_pages = _filter_rows(page_rows, query)
        visible_pages = filtered_pages[query.offset : query.offset + query.limit]
        filtered_daemons = _filter_rows(daemon_rows, query)
        visible_daemons = filtered_daemons[query.offset : query.offset + query.limit]
        filtered_network_activity = _filter_rows(network_activity_rows, query)
        visible_network_activity = filtered_network_activity[
            query.offset : query.offset + query.limit
        ]
        filtered_diagnostics = _filter_rows(diagnostic_rows, query)
        visible_diagnostics = filtered_diagnostics[
            query.offset : query.offset + query.limit
        ]
        health = _health(
            profile_rows=profile_rows,
            page_rows=page_rows,
            pool_rows=pool_rows,
            allocation_rows=allocation_rows,
            network_activity_rows=network_activity_rows,
            diagnostic_rows=diagnostic_rows,
        )

        profiles_table = _profiles_table(visible_profiles, total=len(filtered_profiles))
        pools_table = _profile_pools_table(visible_pools, total=len(filtered_pools))
        allocations_table = _profile_allocations_table(
            visible_allocations,
            total=len(filtered_allocations),
        )
        pages_table = _page_observations_table(visible_pages, total=len(filtered_pages))
        daemon_table = _daemon_runtimes_table(visible_daemons, total=len(filtered_daemons))
        network_table = _network_activity_table(
            visible_network_activity,
            total=len(filtered_network_activity),
        )
        diagnostics_table = _diagnostics_table(
            visible_diagnostics,
            total=len(filtered_diagnostics),
        )

        return BrowserOperationsPage(
            module="browser",
            title="Browser Runtime",
            subtitle="观察浏览器 profile、CDP endpoint、页面 generation 与 daemon 托管状态。",
            health=health,
            updated_at=format_datetime_utc(now),
            auto_refresh=True,
            role=OperationsModuleRoleModel(
                label="Browser operator",
                can_operate=True,
                scope="browser",
            ),
            metrics=_metrics(
                health=health,
                profile_rows=profile_rows,
                pool_rows=pool_rows,
                allocation_rows=allocation_rows,
                page_rows=page_rows,
                daemon_rows=daemon_rows,
                network_activity_rows=network_activity_rows,
                diagnostic_rows=diagnostic_rows,
            ),
            tabs=_tabs(
                profile_count=len(filtered_profiles),
                pool_count=len(filtered_pools),
                allocation_count=len(filtered_allocations),
                page_count=len(filtered_pages),
                daemon_count=len(filtered_daemons),
                network_count=len(filtered_network_activity),
                diagnostic_count=len(filtered_diagnostics),
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


def _normalize_query(query: BrowserOperationsQuery | None) -> BrowserOperationsQuery:
    if query is None:
        return BrowserOperationsQuery()
    return BrowserOperationsQuery(
        status=_normalized_filter(query.status),
        profile=_normalized_filter(query.profile),
        search=query.search.strip() if isinstance(query.search, str) else "",
        limit=max(1, min(int(query.limit), 200)),
        offset=max(0, int(query.offset)),
    )


def _safe_profiles(target: Any | None) -> tuple[Any, ...]:
    method = getattr(target, "list_profiles", None)
    if not callable(method):
        return ()
    try:
        return tuple(method())
    except Exception:
        return ()


def _safe_tuple(target: Any | None, method_name: str, **kwargs: Any) -> tuple[Any, ...]:
    method = getattr(target, method_name, None)
    if not callable(method):
        return ()
    try:
        return tuple(method(**kwargs))
    except Exception:
        return ()


def _profile_rows(
    profiles: tuple[Any, ...],
    *,
    access_service: Any | None,
    proxy_metadata_by_profile: dict[str, dict[str, Any]] | None = None,
) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    proxy_metadata_by_profile = proxy_metadata_by_profile or {}
    for profile in profiles:
        profile_name = _text(getattr(profile, "name", None), "unknown")
        proxy_metadata = proxy_metadata_by_profile.get(profile_name, {})
        driver = _text(getattr(profile, "driver", None))
        enabled = bool(getattr(profile, "enabled", True))
        runtime = _runtime(profile)
        status = _runtime_status(runtime) if enabled else "disabled"
        proxy_metadata = {**_runtime_proxy_metadata(runtime), **proxy_metadata}
        page_state = _dict(runtime.get("page_state"))
        active_page = _dict(page_state.get("active_page"))
        endpoint = _text(
            getattr(profile, "resolved_cdp_url", None)
            or getattr(profile, "configured_cdp_url", None),
        )
        rows.append(
            OperationsTableRowModel(
                id=f"profile:{_text(getattr(profile, 'name', 'unknown'), 'unknown')}",
                status=status,
                tone=_status_tone(status, driver=driver),
                cells={
                    "profile": profile_name,
                    "driver": driver,
                    "enabled": "Yes" if enabled else "No",
                    "mode": _text(getattr(profile, "mode", None)),
                    "status": status,
                    "endpoint": endpoint,
                    "host_generation": _short_generation(
                        runtime.get("host_generation"),
                    ),
                    "active_target": _text(page_state.get("active_target_id")),
                    "pages": str(_int(page_state.get("page_count"))),
                    "page_generation": _text(active_page.get("page_generation")),
                    "snapshot_generation": _text(active_page.get("snapshot_generation")),
                    "proxy": _proxy_label(profile),
                    "proxy_readiness": _proxy_readiness_label(
                        profile,
                        access_service=access_service,
                    ),
                    "proxy_egress": _proxy_egress_label(proxy_metadata),
                },
            ),
        )
    return tuple(rows)


def _page_rows(profiles: tuple[Any, ...]) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    for profile in profiles:
        profile_name = _text(getattr(profile, "name", None))
        runtime = _runtime(profile)
        page_state = _dict(runtime.get("page_state"))
        for page in _list(page_state.get("pages")):
            page_record = _dict(page)
            target_id = _text(page_record.get("target_id"))
            stale = _page_stale(page_record)
            rows.append(
                OperationsTableRowModel(
                    id=f"page:{profile_name}:{target_id}",
                    status="stale" if stale else "fresh",
                    tone="warning" if stale else "success",
                    cells={
                        "profile": profile_name,
                        "target_id": target_id,
                        "page_generation": _text(page_record.get("page_generation")),
                        "reason": _text(page_record.get("page_generation_reason")),
                        "snapshot_generation": _text(
                            page_record.get("snapshot_generation"),
                        ),
                        "ref_generation": _text(
                            page_record.get("current_ref_generation"),
                        ),
                        "last_action": _text(page_record.get("last_action_kind")),
                        "refs": _text(page_record.get("last_snapshot_ref_count")),
                        "frames": _text(page_record.get("last_snapshot_frame_count")),
                        "stale": "Yes" if stale else "No",
                    },
                ),
            )
    return tuple(rows)


def _daemon_rows(
    *,
    services: tuple[dict[str, Any], ...],
    instances: tuple[dict[str, Any], ...],
) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    service_by_key = {
        _text(service.get("key"), ""): service
        for service in services
        if _is_browser_service(_text(service.get("key"), ""))
    }
    instance_by_service = _preferred_browser_instances_by_service(instances)
    for service_key in sorted({*service_by_key.keys(), *instance_by_service.keys()}):
        service = service_by_key.get(service_key, {})
        instance = instance_by_service.get(service_key, {})
        status = _text(instance.get("status") or service.get("status") or "configured")
        metadata = _dict(instance.get("metadata"))
        rows.append(
            OperationsTableRowModel(
                id=f"daemon:{service_key}",
                status=status,
                tone=_daemon_tone(status),
                cells={
                    "service_key": service_key,
                    "runtime": _browser_runtime_kind(service_key),
                    "status": status,
                    "profile": service_key.rsplit(":", 1)[-1],
                    "endpoint": _text(
                        instance.get("endpoint")
                        or metadata.get("cdp_url"),
                    ),
                    "pid": _text(instance.get("pid") or metadata.get("browser_pid")),
                    "manifest": _text(metadata.get("manifest_status")),
                    "required": _text(service.get("requires_service_key")),
                    "proxy_egress": _proxy_egress_label(metadata),
                    "last_error": _text(instance.get("last_error")),
                },
            ),
        )
    return tuple(rows)


def _pool_rows(pools: tuple[Any, ...]) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    for pool in pools:
        status = _text(getattr(pool, "status", None), "active").lower()
        pool_id = _text(getattr(pool, "pool_id", None), "unknown")
        diagnostics = _dict(getattr(pool, "diagnostics", None))
        profile_names = tuple(getattr(pool, "profile_names", ()) or ())
        missing = tuple(getattr(pool, "missing_profile_names", ()) or ())
        disabled = tuple(getattr(pool, "disabled_profile_names", ()) or ())
        attach_only = tuple(getattr(pool, "attach_only_profile_names", ()) or ())
        rows.append(
            OperationsTableRowModel(
                id=f"pool:{pool_id}",
                status=status,
                tone=_pool_tone(status, diagnostics=diagnostics),
                cells={
                    "pool": pool_id,
                    "profile": _join(profile_names),
                    "name": _text(getattr(pool, "display_name", None)),
                    "status": status,
                    "profiles": _join(profile_names),
                    "ready_profiles": str(
                        _int(getattr(pool, "ready_profile_count", 0)),
                    ),
                    "available_profiles": _text(
                        diagnostics.get("available_profile_count"),
                    ),
                    "active_allocations": str(
                        _int(getattr(pool, "active_allocation_count", 0)),
                    ),
                    "cooling": _join(diagnostics.get("cooling_profiles")),
                    "failure_cooldown": _join(
                        diagnostics.get("failure_cooldown_profiles"),
                    ),
                    "recent_failures": str(
                        _int(diagnostics.get("failed_allocation_count")),
                    ),
                    "strategy": _text(getattr(pool, "selection_strategy", None)),
                    "concurrency": _pool_concurrency_label(pool),
                    "ttl": _duration_seconds_label(
                        getattr(pool, "allocation_ttl_seconds", None),
                    ),
                    "cooldown": _duration_seconds_label(
                        getattr(pool, "cooldown_seconds", None),
                    ),
                    "target_hosts": _join(getattr(pool, "target_hosts", ()) or ()),
                    "missing": _join(missing),
                    "disabled": _join(disabled),
                    "attach_only": _join(attach_only),
                },
            ),
        )
    return tuple(rows)


def _allocation_rows(
    allocations: tuple[Any, ...],
    *,
    now: datetime,
) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    for allocation in allocations:
        status = _text(getattr(allocation, "status", None), "unknown").lower()
        allocation_id = _text(getattr(allocation, "allocation_id", None), "unknown")
        consumer = _consumer_label(allocation)
        owned_target_ids = tuple(getattr(allocation, "owned_target_ids", ()) or ())
        rows.append(
            OperationsTableRowModel(
                id=f"allocation:{allocation_id}",
                status=status,
                tone=_allocation_tone(status),
                cells={
                    "allocation": allocation_id,
                    "pool": _text(getattr(allocation, "pool_id", None)),
                    "profile": _text(getattr(allocation, "profile_name", None)),
                    "consumer": consumer,
                    "target_host": _text(getattr(allocation, "target_host", None)),
                    "targets": str(len(owned_target_ids)),
                    "age": _age_label(getattr(allocation, "acquired_at", None), now=now),
                    "heartbeat": _age_label(
                        getattr(allocation, "last_heartbeat_at", None),
                        now=now,
                    ),
                    "ttl": _ttl_label(
                        getattr(allocation, "expires_at", None),
                        now=now,
                    ),
                    "status": status,
                    "release_reason": _text(
                        getattr(allocation, "release_reason", None),
                    ),
                },
            ),
        )
    return tuple(rows)


_NETWORK_EVENT_NAMES = frozenset(
    {
        "browser.network.capture.started",
        "browser.network.capture.stopped",
        "browser.network.request.observed",
        "browser.network.request.failed",
        "browser.network.fetch.executed",
        "browser.network.fetch.failed",
        "browser.network.replay.executed",
        "browser.network.replay.failed",
    },
)
_DIAGNOSTIC_EVENT_NAMES = frozenset(
    {
        "browser.diagnostics.collected",
        "browser.trace.started",
        "browser.trace.exported",
        "browser.environment.changed",
    },
)


def _recent_browser_events(
    operations_observation: Any | None,
    *,
    limit: int = 80,
) -> tuple[OperationsObservedEvent, ...]:
    get_module_observation = getattr(
        operations_observation,
        "get_module_observation",
        None,
    )
    if not callable(get_module_observation):
        return ()
    try:
        observation = get_module_observation("browser")
    except Exception:
        return ()
    if observation is None:
        return ()
    recent_events = getattr(observation, "recent_events", ())
    return tuple(
        event
        for event in tuple(recent_events)[: max(int(limit), 1)]
        if isinstance(event, OperationsObservedEvent)
    )


def _network_activity_rows(
    events: tuple[OperationsObservedEvent, ...],
) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    for event in events:
        if event.event_name not in _NETWORK_EVENT_NAMES:
            continue
        payload = _dict(event.payload)
        status = _text(payload.get("status") or event.status, event.status)
        rows.append(
            OperationsTableRowModel(
                id=f"browser-network:{event.id}:{event.cursor}",
                status=status,
                tone=_event_tone(event),
                cells={
                    "time": format_datetime_utc(event.occurred_at),
                    "event": _browser_event_label(event.event_name),
                    "status": status,
                    "profile": _text(payload.get("profile_name")),
                    "target_id": _short_generation(payload.get("target_id")),
                    "capture": _short_generation(payload.get("capture_id")),
                    "request": _short_generation(payload.get("request_id")),
                    "method": _text(payload.get("method")),
                    "http_status": _text(payload.get("status_code")),
                    "resource": _text(payload.get("resource_type")),
                    "url": _text(payload.get("url") or payload.get("page_url")),
                    "summary": _event_summary(event),
                },
            ),
        )
    return tuple(rows)


def _diagnostic_rows(
    events: tuple[OperationsObservedEvent, ...],
) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    for event in events:
        if event.event_name not in _DIAGNOSTIC_EVENT_NAMES:
            continue
        payload = _dict(event.payload)
        status = _text(payload.get("status") or event.status, event.status)
        rows.append(
            OperationsTableRowModel(
                id=f"browser-diagnostic:{event.id}:{event.cursor}",
                status=status,
                tone=_event_tone(event),
                cells={
                    "time": format_datetime_utc(event.occurred_at),
                    "event": _browser_event_label(event.event_name),
                    "kind": _text(
                        payload.get("diagnostic_kind")
                        or payload.get("environment_action"),
                    ),
                    "status": status,
                    "profile": _text(payload.get("profile_name")),
                    "target_id": _short_generation(payload.get("target_id")),
                    "issues": _text(payload.get("issue_count")),
                    "console": _text(payload.get("console_count")),
                    "errors": _text(payload.get("error_count")),
                    "ready_state": _text(payload.get("ready_state")),
                    "trace": _short_generation(payload.get("trace_id")),
                    "trace_size": _bytes_label(payload.get("trace_size_bytes")),
                    "changed": _join(payload.get("changed_controls")),
                    "summary": _event_summary(event),
                },
            ),
        )
    return tuple(rows)


def _filter_rows(
    rows: tuple[OperationsTableRowModel, ...],
    query: BrowserOperationsQuery,
) -> tuple[OperationsTableRowModel, ...]:
    filtered = rows
    if query.status != "all":
        filtered = tuple(
            row for row in filtered if _text(row.status, "").lower() == query.status
        )
    if query.profile != "all":
        filtered = tuple(
            row
            for row in filtered
            if row.cells.get("profile", "").lower() == query.profile
        )
    if query.search:
        needle = query.search.lower()
        filtered = tuple(
            row
            for row in filtered
            if needle in " ".join(str(value) for value in row.cells.values()).lower()
        )
    return filtered


def _profiles_table(
    rows: tuple[OperationsTableRowModel, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    return OperationsTableSectionModel(
        id="profiles",
        title="Browser Profiles",
        columns=(
            OperationsTableColumnModel("profile", "Profile"),
            OperationsTableColumnModel("driver", "Driver"),
            OperationsTableColumnModel("enabled", "Enabled"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("endpoint", "CDP Endpoint"),
            OperationsTableColumnModel("host_generation", "Host Gen"),
            OperationsTableColumnModel("active_target", "Active Target"),
            OperationsTableColumnModel("pages", "Pages"),
            OperationsTableColumnModel("snapshot_generation", "Snapshot Gen"),
            OperationsTableColumnModel("proxy", "Proxy"),
            OperationsTableColumnModel("proxy_readiness", "Proxy Ready"),
            OperationsTableColumnModel("proxy_egress", "Egress"),
        ),
        rows=rows,
        total=total,
        view_all_route="/operations/browser?tab=profiles",
        empty_state="No browser profiles configured.",
    )


def _profile_pools_table(
    rows: tuple[OperationsTableRowModel, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    return OperationsTableSectionModel(
        id="profile_pools",
        title="Browser Profile Pools",
        columns=(
            OperationsTableColumnModel("pool", "Pool"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("profiles", "Profiles"),
            OperationsTableColumnModel("ready_profiles", "Ready"),
            OperationsTableColumnModel("available_profiles", "Available"),
            OperationsTableColumnModel("active_allocations", "Active"),
            OperationsTableColumnModel("cooling", "Cooling"),
            OperationsTableColumnModel("recent_failures", "Failures"),
            OperationsTableColumnModel("strategy", "Strategy"),
            OperationsTableColumnModel("concurrency", "Concurrency"),
            OperationsTableColumnModel("ttl", "TTL"),
            OperationsTableColumnModel("cooldown", "Cooldown"),
            OperationsTableColumnModel("target_hosts", "Target Hosts"),
            OperationsTableColumnModel("missing", "Missing"),
        ),
        rows=rows,
        total=total,
        view_all_route="/operations/browser?tab=pools",
        empty_state="No browser profile pools configured.",
    )


def _profile_allocations_table(
    rows: tuple[OperationsTableRowModel, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    return OperationsTableSectionModel(
        id="profile_allocations",
        title="Browser Profile Allocations",
        columns=(
            OperationsTableColumnModel("allocation", "Allocation"),
            OperationsTableColumnModel("pool", "Pool"),
            OperationsTableColumnModel("profile", "Profile"),
            OperationsTableColumnModel("consumer", "Consumer"),
            OperationsTableColumnModel("target_host", "Target Host"),
            OperationsTableColumnModel("targets", "Targets"),
            OperationsTableColumnModel("age", "Age"),
            OperationsTableColumnModel("heartbeat", "Heartbeat"),
            OperationsTableColumnModel("ttl", "TTL"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("release_reason", "Release Reason"),
        ),
        rows=rows,
        total=total,
        view_all_route="/operations/browser?tab=allocations",
        empty_state="No browser profile allocations recorded.",
    )


def _page_observations_table(
    rows: tuple[OperationsTableRowModel, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    return OperationsTableSectionModel(
        id="page_observations",
        title="Page Observations",
        columns=(
            OperationsTableColumnModel("profile", "Profile"),
            OperationsTableColumnModel("target_id", "Target"),
            OperationsTableColumnModel("page_generation", "Page Gen"),
            OperationsTableColumnModel("reason", "Reason"),
            OperationsTableColumnModel("snapshot_generation", "Snapshot Gen"),
            OperationsTableColumnModel("ref_generation", "Ref Gen"),
            OperationsTableColumnModel("last_action", "Last Action"),
            OperationsTableColumnModel("refs", "Refs"),
            OperationsTableColumnModel("stale", "Stale"),
        ),
        rows=rows,
        total=total,
        view_all_route="/operations/browser?tab=pages",
        empty_state="No browser page observations yet.",
    )


def _daemon_runtimes_table(
    rows: tuple[OperationsTableRowModel, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    return OperationsTableSectionModel(
        id="daemon_runtimes",
        title="Browser Daemon Runtimes",
        columns=(
            OperationsTableColumnModel("service_key", "Service Key"),
            OperationsTableColumnModel("runtime", "Runtime"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("profile", "Profile"),
            OperationsTableColumnModel("endpoint", "Endpoint"),
            OperationsTableColumnModel("pid", "PID"),
            OperationsTableColumnModel("manifest", "Manifest"),
            OperationsTableColumnModel("required", "Requires"),
            OperationsTableColumnModel("proxy_egress", "Egress"),
        ),
        rows=rows,
        total=total,
        view_all_route="/operations/browser?tab=daemon",
        empty_state="No browser daemon runtimes registered.",
    )


def _network_activity_table(
    rows: tuple[OperationsTableRowModel, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    return OperationsTableSectionModel(
        id="network_activity",
        title="Browser Network Activity",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("event", "Event"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("profile", "Profile"),
            OperationsTableColumnModel("target_id", "Target"),
            OperationsTableColumnModel("capture", "Capture"),
            OperationsTableColumnModel("request", "Request"),
            OperationsTableColumnModel("method", "Method"),
            OperationsTableColumnModel("http_status", "HTTP"),
            OperationsTableColumnModel("resource", "Resource"),
            OperationsTableColumnModel("url", "URL"),
            OperationsTableColumnModel("summary", "Summary"),
        ),
        rows=rows,
        total=total,
        view_all_route="/operations/browser?tab=network",
        empty_state="No browser network activity observed.",
    )


def _diagnostics_table(
    rows: tuple[OperationsTableRowModel, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    return OperationsTableSectionModel(
        id="diagnostics",
        title="Browser Diagnostics",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("event", "Event"),
            OperationsTableColumnModel("kind", "Kind"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("profile", "Profile"),
            OperationsTableColumnModel("target_id", "Target"),
            OperationsTableColumnModel("issues", "Issues"),
            OperationsTableColumnModel("console", "Console"),
            OperationsTableColumnModel("errors", "Errors"),
            OperationsTableColumnModel("ready_state", "Ready"),
            OperationsTableColumnModel("trace", "Trace"),
            OperationsTableColumnModel("trace_size", "Trace Size"),
            OperationsTableColumnModel("changed", "Changed"),
            OperationsTableColumnModel("summary", "Summary"),
        ),
        rows=rows,
        total=total,
        view_all_route="/operations/browser?tab=diagnostics",
        empty_state="No browser diagnostics observed.",
    )


def _metrics(
    *,
    health: str,
    profile_rows: tuple[OperationsTableRowModel, ...],
    pool_rows: tuple[OperationsTableRowModel, ...],
    allocation_rows: tuple[OperationsTableRowModel, ...],
    page_rows: tuple[OperationsTableRowModel, ...],
    daemon_rows: tuple[OperationsTableRowModel, ...],
    network_activity_rows: tuple[OperationsTableRowModel, ...],
    diagnostic_rows: tuple[OperationsTableRowModel, ...],
) -> tuple[MetricCardModel, ...]:
    attached = sum(1 for row in profile_rows if row.status == "attached")
    active_pools = sum(1 for row in pool_rows if row.status == "active")
    active_allocations = sum(1 for row in allocation_rows if row.status == "active")
    cooling_pools = sum(1 for row in pool_rows if row.cells.get("cooling") != "-")
    failed_allocations = sum(1 for row in allocation_rows if row.status == "failed")
    stale_pages = sum(1 for row in page_rows if row.status == "stale")
    ready_daemons = sum(1 for row in daemon_rows if row.status == "ready")
    network_failures = sum(1 for row in network_activity_rows if row.tone == "danger")
    diagnostic_warnings = sum(
        1 for row in diagnostic_rows if row.tone in {"warning", "danger"}
    )
    return (
        MetricCardModel(
            "health",
            "Overall Health",
            health.title(),
            _health_delta(health),
            _health_tone(health),
        ),
        MetricCardModel(
            "profiles",
            "Profiles",
            str(len(profile_rows)),
            f"{attached} attached",
            "info",
        ),
        MetricCardModel(
            "profile_pools",
            "Profile Pools",
            str(len(pool_rows)),
            (
                f"{active_pools} active · {cooling_pools} cooling"
                if cooling_pools
                else f"{active_pools} active"
            ),
            "warning" if cooling_pools else "success" if active_pools else "neutral",
        ),
        MetricCardModel(
            "profile_allocations",
            "Profile Allocations",
            str(len(allocation_rows)),
            (
                f"{active_allocations} active · {failed_allocations} failed"
                if failed_allocations
                else f"{active_allocations} active"
            ),
            "warning" if failed_allocations else "info" if active_allocations else "neutral",
        ),
        MetricCardModel(
            "pages",
            "Page Observations",
            str(len(page_rows)),
            f"{stale_pages} stale",
            "warning" if stale_pages else "success",
        ),
        MetricCardModel(
            "daemon_runtimes",
            "Daemon Runtimes",
            str(len(daemon_rows)),
            f"{ready_daemons} ready",
            "success" if ready_daemons else "neutral",
        ),
        MetricCardModel(
            "network_activity",
            "Network Activity",
            str(len(network_activity_rows)),
            f"{network_failures} failed",
            "warning" if network_failures else "info" if network_activity_rows else "neutral",
        ),
        MetricCardModel(
            "diagnostics",
            "Diagnostics",
            str(len(diagnostic_rows)),
            f"{diagnostic_warnings} warnings",
            "warning" if diagnostic_warnings else "success" if diagnostic_rows else "neutral",
        ),
    )


def _tabs(
    *,
    profile_count: int,
    pool_count: int,
    allocation_count: int,
    page_count: int,
    daemon_count: int,
    network_count: int,
    diagnostic_count: int,
) -> tuple[OperationsTabModel, ...]:
    return (
        OperationsTabModel("profiles", "Profiles", profile_count),
        OperationsTabModel("pools", "Pools", pool_count),
        OperationsTabModel("allocations", "Allocations", allocation_count),
        OperationsTabModel("pages", "Pages", page_count),
        OperationsTabModel("daemon", "Daemon", daemon_count),
        OperationsTabModel("network", "Network", network_count),
        OperationsTabModel("diagnostics", "Diagnostics", diagnostic_count),
    )


def _actions() -> tuple[RuntimeActionModel, ...]:
    return (
        RuntimeActionModel(
            id="open_daemon",
            label="Open Daemon",
            owner="daemon",
            method="GET",
            endpoint="/operations/daemon?service_group=browser",
        ),
        RuntimeActionModel(
            id="open_tool_sources",
            label="Open Tool Sources",
            owner="tool",
            method="GET",
            endpoint="/operations/tool?tab=sources&provider=browser",
        ),
    )


def _health(
    *,
    profile_rows: tuple[OperationsTableRowModel, ...],
    page_rows: tuple[OperationsTableRowModel, ...],
    pool_rows: tuple[OperationsTableRowModel, ...],
    allocation_rows: tuple[OperationsTableRowModel, ...],
    network_activity_rows: tuple[OperationsTableRowModel, ...],
    diagnostic_rows: tuple[OperationsTableRowModel, ...],
) -> str:
    if any(row.tone == "danger" for row in profile_rows):
        return "error"
    if any(row.tone == "danger" for row in pool_rows):
        return "error"
    if any(row.tone == "danger" for row in allocation_rows):
        return "error"
    if any(row.tone == "danger" for row in network_activity_rows):
        return "error"
    if any(row.status == "stale" for row in page_rows):
        return "warning"
    if any(row.tone == "warning" for row in profile_rows):
        return "warning"
    if any(row.tone == "warning" for row in pool_rows):
        return "warning"
    if any(row.tone == "warning" for row in allocation_rows):
        return "warning"
    if any(row.tone == "warning" for row in diagnostic_rows):
        return "warning"
    return "healthy"


def _runtime(profile: Any) -> dict[str, Any]:
    runtime = getattr(profile, "runtime", None)
    return runtime if isinstance(runtime, dict) else {}


def _runtime_status(runtime: dict[str, Any]) -> str:
    return _text(runtime.get("attachment_status"), "idle").lower()


def _page_stale(page: dict[str, Any]) -> bool:
    reason = _text(page.get("page_generation_reason"), "").lower()
    snapshot_generation = _int(page.get("snapshot_generation"))
    page_generation = _int(page.get("page_generation"))
    if reason in {"navigate", "reload", "changed", "host-generation-changed"}:
        return snapshot_generation < 1
    return page_generation > 1 and snapshot_generation < 1


def _proxy_label(profile: Any) -> str:
    mode = _text(getattr(profile, "proxy_mode", None), "none")
    binding = _text(getattr(profile, "proxy_binding_id", None))
    credential_kind = _text(getattr(profile, "proxy_credential_kind", None), "basic")
    if binding != "-":
        return f"{mode} · {credential_kind} · {binding}"
    return f"{mode} · {credential_kind}" if mode == "access_binding" else mode


def _proxy_readiness_label(profile: Any, *, access_service: Any | None) -> str:
    mode = _text(getattr(profile, "proxy_mode", None), "none")
    if mode != "access_binding":
        return "not required"
    binding_id = _text(getattr(profile, "proxy_binding_id", None))
    if binding_id == "-":
        return "setup_needed"
    credential_kind = _text(getattr(profile, "proxy_credential_kind", None), "basic")
    check = getattr(access_service, "check_credential_binding", None)
    if not callable(check):
        return "unknown"
    try:
        readiness = check(binding_id, expected_kind=credential_kind)
    except TypeError:
        try:
            readiness = check(binding_id)
        except Exception:
            return "unknown"
    except Exception:
        return "unknown"
    payload = _to_payload(readiness)
    status = _text(payload.get("status") or getattr(readiness, "status", None))
    if not status or status == "-":
        return "ready" if bool(getattr(readiness, "ready", False)) else "setup_needed"
    return status


def _proxy_metadata_by_profile(
    instances: tuple[dict[str, Any], ...],
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for instance in instances:
        service_key = _text(instance.get("service_key"), "")
        if not service_key.startswith("host:browser:"):
            continue
        metadata = _dict(instance.get("metadata"))
        profile = _text(metadata.get("profile_name") or service_key.rsplit(":", 1)[-1])
        if profile != "-":
            grouped.setdefault(profile, []).append(instance)
    mapped: dict[str, dict[str, Any]] = {}
    for profile, profile_instances in grouped.items():
        mapped[profile] = _dict(_preferred_instance(profile_instances).get("metadata"))
    return mapped


def _runtime_proxy_metadata(runtime: dict[str, Any]) -> dict[str, Any]:
    proxy_egress = _dict(runtime.get("proxy_egress"))
    metadata: dict[str, Any] = {}
    if proxy_egress:
        metadata["proxy_egress"] = proxy_egress
    for key in ("proxy_egress_status", "proxy_egress_ip", "proxy_egress_checked_at"):
        value = runtime.get(key)
        if value is not None:
            metadata[key] = value
    return metadata


def _preferred_browser_instances_by_service(
    instances: tuple[dict[str, Any], ...],
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for instance in instances:
        service_key = _text(instance.get("service_key"), "")
        if not _is_browser_service(service_key):
            continue
        grouped.setdefault(service_key, []).append(instance)
    return {
        service_key: _preferred_instance(service_instances)
        for service_key, service_instances in grouped.items()
    }


def _preferred_instance(instances: list[dict[str, Any]]) -> dict[str, Any]:
    return max(instances, key=_instance_preference_key) if instances else {}


def _instance_preference_key(instance: dict[str, Any]) -> tuple[int, str, str]:
    status = _text(instance.get("status"), "").lower()
    rank = {
        "ready": 50,
        "running": 40,
        "active": 40,
        "launched": 40,
        "adopted": 40,
        "starting": 30,
        "configured": 20,
        "failed": 10,
        "degraded": 10,
        "stopped": 0,
    }.get(status, 0)
    timestamp = _text(
        instance.get("last_healthcheck_at")
        or instance.get("updated_at")
        or instance.get("started_at")
        or instance.get("created_at"),
        "",
    )
    return rank, timestamp, _text(instance.get("id"), "")


def _proxy_egress_label(metadata: dict[str, Any]) -> str:
    if not metadata:
        return "-"
    raw = metadata.get("proxy_egress")
    egress = _dict(raw) if isinstance(raw, dict) else {}
    status = _text(
        egress.get("status")
        or metadata.get("proxy_egress_status")
        or ("ready" if metadata.get("proxy_egress_ip") else None),
    )
    ip = _text(egress.get("ip") or metadata.get("proxy_egress_ip"))
    if ip != "-":
        return f"{status} · {ip}" if status != "-" else ip
    return status


def _browser_runtime_kind(service_key: str) -> str:
    if service_key.startswith("host:browser:"):
        return "Browser Host"
    return "Browser"


def _is_browser_service(service_key: str) -> bool:
    return service_key.startswith("host:browser:")


def _status_tone(status: str, *, driver: str = "-") -> str:
    if status == "attached":
        return "success"
    if status in {"failed", "degraded"}:
        if driver == "existing-session":
            return "warning"
        return "danger"
    if status in {"attaching", "recovering"}:
        return "warning"
    if status == "disabled":
        return "neutral"
    return "neutral"


def _daemon_tone(status: str) -> str:
    normalized = status.lower()
    if normalized == "ready":
        return "success"
    if normalized in {"failed", "degraded"}:
        return "danger"
    if normalized in {"starting", "configured"}:
        return "warning"
    return "neutral"


def _pool_tone(status: str, *, diagnostics: dict[str, Any] | None = None) -> str:
    normalized = status.lower()
    if normalized == "active":
        diagnostics = diagnostics or {}
        if _int(diagnostics.get("failed_allocation_count")) > 0:
            return "warning"
        if diagnostics.get("cooling_profiles"):
            return "warning"
        return "success"
    if normalized == "degraded":
        return "danger"
    if normalized == "disabled":
        return "neutral"
    return "warning"


def _allocation_tone(status: str) -> str:
    normalized = status.lower()
    if normalized == "active":
        return "success"
    if normalized in {"failed"}:
        return "danger"
    if normalized in {"expired", "released"}:
        return "neutral"
    return "warning"


def _health_tone(health: str) -> str:
    if health == "healthy":
        return "success"
    if health == "error":
        return "danger"
    return "warning"


def _health_delta(health: str) -> str:
    if health == "healthy":
        return "Browser runtime state is queryable"
    if health == "error":
        return "Operator action required"
    return "Operator attention recommended"


def _short_generation(value: Any) -> str:
    text = _text(value)
    if text == "-" or len(text) <= 12:
        return text
    return text[:12]


def _event_tone(event: OperationsObservedEvent) -> str:
    status = _text(event.status, "").lower()
    level = _text(event.level, "").lower()
    if level == "error" or status in {"failed", "error"} or event.event_name.endswith(".failed"):
        return "danger"
    if level == "warning" or status in {"warning", "degraded", "setup_needed"}:
        return "warning"
    if status in {"healthy", "ready", "started", "stopped", "exported", "observed", "executed"}:
        return "success"
    return "neutral"


def _browser_event_label(event_name: str) -> str:
    text = event_name.removeprefix("browser.")
    return text.replace(".", " ")


def _event_summary(event: OperationsObservedEvent) -> str:
    payload = _dict(event.payload)
    for key in (
        "display_summary",
        "summary",
        "error_message",
        "failure_text",
        "release_reason",
    ):
        value = _text(payload.get(key))
        if value != "-":
            return value
    return _browser_event_label(event.event_name)


def _bytes_label(value: Any) -> str:
    size = _int(value, -1)
    if size < 0:
        return "-"
    if size < 1024:
        return f"{size} B"
    kib = size / 1024
    if kib < 1024:
        return f"{kib:.1f} KiB"
    mib = kib / 1024
    return f"{mib:.1f} MiB"


def _pool_concurrency_label(pool: Any) -> str:
    per_profile = _int(getattr(pool, "max_concurrency_per_profile", None), 1)
    total = getattr(pool, "max_concurrency_total", None)
    total_label = _text(total) if total is not None else "unlimited"
    return f"{per_profile}/profile · {total_label} total"


def _consumer_label(allocation: Any) -> str:
    kind = _text(getattr(allocation, "consumer_kind", None))
    consumer_id = _text(getattr(allocation, "consumer_id", None))
    if kind == "-":
        return consumer_id
    if consumer_id == "-":
        return kind
    return f"{kind}:{consumer_id}"


def _duration_seconds_label(value: Any) -> str:
    seconds = _int(value, -1)
    if seconds < 0:
        return "-"
    return _compact_seconds(seconds)


def _age_label(value: Any, *, now: datetime) -> str:
    timestamp = _datetime(value)
    if timestamp is None:
        return "-"
    seconds = max(0, int((now - timestamp).total_seconds()))
    return _compact_seconds(seconds)


def _ttl_label(value: Any, *, now: datetime) -> str:
    timestamp = _datetime(value)
    if timestamp is None:
        return "-"
    seconds = int((timestamp - now).total_seconds())
    if seconds < 0:
        return "expired"
    return _compact_seconds(seconds)


def _compact_seconds(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes, rem = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {rem}s" if rem else f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m" if minutes else f"{hours}h"


def _normalized_filter(value: Any) -> str:
    text = str(value or "all").strip().lower()
    return text or "all"


def _text(value: Any, fallback: str = "-") -> str:
    if value is None or value == "":
        return fallback
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _to_payload(value: Any) -> dict[str, Any]:
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        payload = to_payload()
        if isinstance(payload, dict):
            return dict(payload)
    return {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _join(values: Any) -> str:
    if not values:
        return "-"
    return ", ".join(str(value) for value in values if str(value)) or "-"
