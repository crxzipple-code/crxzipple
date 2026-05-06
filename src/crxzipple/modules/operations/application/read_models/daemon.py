from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.daemon import DaemonNotFoundError, DaemonValidationError
from crxzipple.modules.daemon.interfaces.presenters import (
    instance_payload,
    lease_payload,
    service_set_payload,
    spec_payload,
)
from crxzipple.modules.operations.application.observation import (
    OperationsObservedEvent,
    observed_event_from_record,
)
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsChartSectionModel,
    OperationsChartSegmentModel,
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
    OperationsModuleOverview,
    OperationsModuleRoleModel,
    OperationsTabModel,
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
    RuntimeActionModel,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc

_MAX_DAEMON_EVENT_TOPICS = 160
_MAX_RECENT_DAEMON_EVENTS = 160
_RECENT_DAEMON_TOPIC_LIMIT = 80
_DAEMON_DIRECT_EVENT_TOPICS = (
    "events.named.daemon.service.ensure_requested",
    "events.named.daemon.service.healthcheck_requested",
    "events.named.daemon.service.reconcile_requested",
    "events.named.daemon.service.stop_requested",
    "events.named.daemon.instance.started",
    "events.named.daemon.instance.ready",
    "events.named.daemon.instance.degraded",
    "events.named.daemon.instance.failed",
    "events.named.daemon.instance.stopped",
    "events.named.daemon.lease.acquired",
    "events.named.daemon.lease.heartbeated",
    "events.named.daemon.lease.released",
    "events.named.daemon.lease.expired",
    "events.named.process.session.started",
    "events.named.process.session.exited",
    "events.named.process.session.failed",
    "events.named.process.session.output_observed",
    "daemon.service.ensure_requested",
    "daemon.service.healthcheck_requested",
    "daemon.service.reconcile_requested",
    "daemon.service.stop_requested",
    "daemon.instance.started",
    "daemon.instance.ready",
    "daemon.instance.degraded",
    "daemon.instance.failed",
    "daemon.instance.stopped",
    "daemon.lease.acquired",
    "daemon.lease.heartbeated",
    "daemon.lease.released",
    "daemon.lease.expired",
    "process.session.started",
    "process.session.exited",
    "process.session.failed",
    "process.session.output_observed",
)


@dataclass(frozen=True, slots=True)
class DaemonOperationsQuery:
    status: str = "all"
    service_key: str = "all"
    service_group: str = "all"
    search: str = ""
    limit: int = 80
    offset: int = 0


@dataclass(frozen=True, slots=True)
class DaemonInstanceDetailModel:
    instance_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    environment: OperationsKeyValueSectionModel
    service: OperationsKeyValueSectionModel
    leases: OperationsTableSectionModel
    events: OperationsTableSectionModel
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DaemonLeaseDetailModel:
    lease_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    metadata: OperationsKeyValueSectionModel
    events: OperationsTableSectionModel
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DaemonProcessDetailModel:
    process_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    metadata: OperationsKeyValueSectionModel
    output: OperationsTableSectionModel
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DaemonOperationsPage:
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
    service_sets: OperationsTableSectionModel
    services: OperationsTableSectionModel
    instances: OperationsTableSectionModel
    leases: OperationsTableSectionModel
    processes: OperationsTableSectionModel
    process_health: OperationsChartSectionModel
    restart_summary: OperationsChartSectionModel
    lease_health: OperationsChartSectionModel
    dependency_health: OperationsTableSectionModel
    drain_overview: OperationsKeyValueSectionModel
    daemon_events: OperationsTableSectionModel
    quick_actions: tuple[RuntimeActionModel, ...]
    links_to_operations: tuple[dict[str, str], ...]
    instance_details: tuple[DaemonInstanceDetailModel, ...]
    lease_details: tuple[DaemonLeaseDetailModel, ...]
    process_details: tuple[DaemonProcessDetailModel, ...]


@dataclass(slots=True)
class DaemonOperationsReadModelProvider:
    daemon_service: Any | None
    daemon_manager: Any | None
    events_service: Any | None = None
    event_definition_registry: Any | None = None
    operations_observation: Any | None = None
    process_service: Any | None = None

    def overview(self) -> OperationsModuleOverview:
        page = self.page(DaemonOperationsQuery(limit=40))
        return OperationsModuleOverview(
            module=page.module,
            title=page.title,
            subtitle=page.subtitle,
            health=page.health,
            updated_at=page.updated_at,
            metrics=page.metrics,
            queue=_overview_rows(page.service_sets),
            lane_locks=_overview_rows(page.services),
            executor=_overview_rows(page.instances),
            actions=page.actions,
        )

    def page(
        self,
        query: DaemonOperationsQuery | None = None,
    ) -> DaemonOperationsPage:
        query = _normalize_query(query)
        now = datetime.now(timezone.utc)
        services = tuple(
            spec_payload(item)
            for item in _safe_tuple(self.daemon_service, "list_service_specs")
        )
        service_sets = tuple(
            service_set_payload(item)
            for item in _safe_tuple(self.daemon_service, "list_service_sets")
        )
        leases = tuple(
            lease_payload(item)
            for item in _safe_tuple(self.daemon_service, "list_leases")
        )
        instances = tuple(
            instance_payload(item)
            for item in _safe_daemon_instances(self.daemon_manager)
        )
        observed_events = _recent_daemon_events(
            operations_observation=self.operations_observation,
            events_service=self.events_service,
            definition_registry=self.event_definition_registry,
        )

        service_by_key = {_text(item.get("key"), ""): item for item in services}
        instances_by_service = _group_by_key(instances, "service_key")
        instances_by_process_id = _instances_by_process_id(instances)
        leases_by_service = _group_by_key(leases, "service_key")
        leases_by_instance = _group_by_key(leases, "instance_id")
        process_sessions = _daemon_process_sessions(
            process_service=self.process_service,
            instances_by_process_id=instances_by_process_id,
        )
        process_rows = _process_rows(
            process_sessions=process_sessions,
            instances_by_process_id=instances_by_process_id,
        )
        health = _health(
            service_available=self.daemon_service is not None,
            services=services,
            instances=instances,
            leases=leases,
            instances_by_service=instances_by_service,
            process_rows=process_rows,
        )
        filtered_instances = _filter_instances(
            instances,
            query,
            service_by_key=service_by_key,
        )
        visible_instances = filtered_instances[query.offset : query.offset + query.limit]
        filtered_leases = _filter_leases(
            leases,
            query,
            service_by_key=service_by_key,
        )
        visible_leases = filtered_leases[query.offset : query.offset + query.limit]
        filtered_process_rows = _filter_process_rows(
            process_rows,
            query,
            service_by_key=service_by_key,
        )
        visible_process_rows = filtered_process_rows[
            query.offset : query.offset + query.limit
        ]

        actions = _actions()
        service_sets_table = _service_sets_table(
            service_sets=service_sets,
            services=services,
            instances_by_service=instances_by_service,
            leases_by_service=leases_by_service,
        )
        services_table = _services_table(
            services=services,
            instances_by_service=instances_by_service,
            leases_by_service=leases_by_service,
        )
        instances_table = _instances_table(
            visible_instances,
            total=len(filtered_instances),
            service_by_key=service_by_key,
        )
        leases_table = _leases_table(
            visible_leases,
            total=len(filtered_leases),
            service_by_key=service_by_key,
        )
        processes_table = _processes_table(
            visible_process_rows,
            total=len(filtered_process_rows),
        )
        daemon_events_table = _daemon_events_table(observed_events)

        return DaemonOperationsPage(
            module="daemon",
            title="Daemons",
            subtitle="观察守护进程服务集、服务规格、进程实例、租约与运行事件的运维视图。",
            health=health,
            updated_at=format_datetime_utc(now),
            auto_refresh=True,
            role=OperationsModuleRoleModel(
                label="Daemon operator",
                can_operate=True,
                scope="daemon",
            ),
            metrics=_metrics(
                health=health,
                service_sets=service_sets,
                services=services,
                instances=instances,
                leases=leases,
                process_rows=process_rows,
                observed_events=observed_events,
                instances_by_service=instances_by_service,
            ),
            tabs=_tabs(
                service_sets=service_sets_table.total,
                services=services_table.total,
                instances=len(filtered_instances),
                leases=len(filtered_leases),
                processes=len(filtered_process_rows),
                dependencies=len(_service_groups(services)),
                events=len(observed_events),
            ),
            active_tab="instances",
            actions=actions,
            service_sets=service_sets_table,
            services=services_table,
            instances=instances_table,
            leases=leases_table,
            processes=processes_table,
            process_health=_process_health(process_rows),
            restart_summary=_state_summary(instances),
            lease_health=_lease_health(leases),
            dependency_health=_dependency_health_table(
                services=services,
                instances_by_service=instances_by_service,
                leases_by_service=leases_by_service,
            ),
            drain_overview=_drain_overview(
                services=services,
                instances=instances,
                leases=leases,
                process_rows=process_rows,
                instances_by_service=instances_by_service,
                leases_by_service=leases_by_service,
            ),
            daemon_events=daemon_events_table,
            quick_actions=actions,
            links_to_operations=_links_to_operations(),
            instance_details=_instance_details(
                instances=visible_instances,
                service_by_key=service_by_key,
                leases_by_instance=leases_by_instance,
                events=observed_events,
            ),
            lease_details=_lease_details(
                leases=visible_leases,
                service_by_key=service_by_key,
                events=observed_events,
            ),
            process_details=_process_details(
                process_rows=visible_process_rows,
                process_service=self.process_service,
            ),
        )


def _normalize_query(
    query: DaemonOperationsQuery | None,
) -> DaemonOperationsQuery:
    if query is None:
        return DaemonOperationsQuery()
    return DaemonOperationsQuery(
        status=_normalized_filter(query.status),
        service_key=_normalized_filter(query.service_key),
        service_group=_normalized_filter(query.service_group),
        search=query.search.strip() if isinstance(query.search, str) else "",
        limit=max(1, min(int(query.limit), 200)),
        offset=max(0, int(query.offset)),
    )


def _safe_tuple(target: Any, method_name: str, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
    method = getattr(target, method_name, None)
    if not callable(method):
        return ()
    try:
        value = method(*args, **kwargs)
    except Exception:
        return ()
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, set):
        return tuple(value)
    return ()


def _safe_daemon_instances(daemon_manager: Any | None) -> tuple[Any, ...]:
    method = getattr(daemon_manager, "list_instances", None)
    if not callable(method):
        return ()
    try:
        value = method(refresh=True)
    except (DaemonValidationError, DaemonNotFoundError):
        return ()
    except Exception:
        return ()
    return tuple(value or ())


def _safe_process_sessions(process_service: Any | None) -> tuple[Any, ...]:
    if process_service is None:
        return ()
    method = getattr(process_service, "list_sessions_metadata", None)
    if not callable(method):
        method = getattr(process_service, "list_sessions", None)
    if not callable(method):
        return ()
    try:
        value = method()
    except Exception:
        return ()
    return tuple(value or ())


def _daemon_process_sessions(
    *,
    process_service: Any | None,
    instances_by_process_id: dict[str, dict[str, Any]],
) -> tuple[Any, ...]:
    sessions = list(_safe_process_sessions(process_service))
    seen = {
        _text(getattr(session, "id", None), "")
        for session in sessions
        if _text(getattr(session, "id", None), "")
    }
    get_session = getattr(process_service, "get_session", None)
    if callable(get_session):
        for process_id in instances_by_process_id:
            if process_id in seen:
                continue
            try:
                session = get_session(process_id=process_id)
            except Exception:
                continue
            sessions.append(session)
            seen.add(process_id)
    return tuple(sessions)


def _recent_daemon_events(
    *,
    operations_observation: Any | None,
    events_service: Any | None,
    definition_registry: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    return _dedupe_daemon_events(
        (
            *_recent_daemon_events_from_bus(
                events_service,
                definition_registry=definition_registry,
            ),
            *_recent_daemon_events_from_observation(operations_observation),
        ),
    )


def _recent_daemon_events_from_observation(
    operations_observation: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    get_module_observation = getattr(operations_observation, "get_module_observation", None)
    if not callable(get_module_observation):
        return ()
    try:
        observation = get_module_observation("daemon")
    except Exception:
        return ()
    recent_events = tuple(getattr(observation, "recent_events", ()) or ())
    return tuple(
        item
        for item in recent_events
        if isinstance(item, OperationsObservedEvent)
    )


def _recent_daemon_events_from_bus(
    events_service: Any | None,
    *,
    definition_registry: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    if events_service is None:
        return ()
    topics = _dedupe_topic_names(
        (
            *_DAEMON_DIRECT_EVENT_TOPICS,
            *(
                topic
                for topic in _safe_list_event_topics(events_service)
                if _is_daemon_event_topic(topic)
            ),
        ),
    )[:_MAX_DAEMON_EVENT_TOPICS]
    read_recent = getattr(events_service, "read_recent_event_topic", None)
    if not callable(read_recent):
        return ()
    events: list[OperationsObservedEvent] = []
    for topic in topics:
        try:
            records = tuple(read_recent(topic, limit=_RECENT_DAEMON_TOPIC_LIMIT) or ())
        except Exception:
            continue
        for record in records:
            try:
                observed = observed_event_from_record(
                    record,
                    definition_registry=definition_registry,
                )
            except Exception:
                continue
            if _is_daemon_observed_event(observed):
                events.append(observed)
    events.sort(key=lambda event: coerce_utc_datetime(event.occurred_at), reverse=True)
    return tuple(events[:_MAX_RECENT_DAEMON_EVENTS])


def _safe_list_event_topics(events_service: Any) -> tuple[str, ...]:
    list_topics = getattr(events_service, "list_event_topics", None)
    if not callable(list_topics):
        return ()
    try:
        return tuple(str(topic) for topic in list_topics() or () if str(topic))
    except Exception:
        return ()


def _is_daemon_event_topic(topic: str) -> bool:
    normalized = topic.strip().lower()
    return (
        normalized.startswith("daemon.")
        or normalized.startswith("events.named.daemon.")
        or normalized.startswith("process.")
        or normalized.startswith("events.named.process.")
    )


def _is_daemon_observed_event(event: OperationsObservedEvent) -> bool:
    owner = event.owner.strip().lower()
    module = event.module.strip().lower()
    event_name = event.event_name.strip().lower()
    return (
        owner in {"daemon", "process"}
        or module in {"daemon", "process"}
        or event_name.startswith("daemon.")
        or event_name.startswith("process.")
    )


def _dedupe_daemon_events(
    events: tuple[OperationsObservedEvent, ...],
) -> tuple[OperationsObservedEvent, ...]:
    result: list[OperationsObservedEvent] = []
    seen: set[tuple[str, str]] = set()
    for event in sorted(
        events,
        key=lambda item: coerce_utc_datetime(item.occurred_at),
        reverse=True,
    ):
        key = (event.topic, event.cursor or event.id)
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return tuple(result[:_MAX_RECENT_DAEMON_EVENTS])


def _dedupe_topic_names(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return tuple(result)


def _health(
    *,
    service_available: bool,
    services: tuple[dict[str, Any], ...],
    instances: tuple[dict[str, Any], ...],
    leases: tuple[dict[str, Any], ...],
    instances_by_service: dict[str, list[dict[str, Any]]],
    process_rows: tuple[dict[str, Any], ...],
) -> str:
    if not service_available:
        return "error"
    if any(_text(item.get("status"), "").lower() == "failed" for item in instances):
        return "error"
    if any(_text(item.get("status"), "").lower() == "expired" for item in leases):
        return "error"
    if any(
        _process_is_managed(item)
        and _text(item.get("status"), "").lower() in {"failed", "missing"}
        for item in process_rows
    ):
        return "error"
    if any(_bool(item.get("env_drift_detected")) for item in instances):
        return "warning"
    if any(_bool(item.get("orphaned")) for item in process_rows):
        return "warning"
    if any(
        _text(item.get("status"), "").lower() in {"starting", "degraded", "stopping"}
        for item in instances
    ):
        return "warning"
    if _desired_unmet_services(services, instances_by_service):
        return "warning"
    if not services:
        return "warning"
    return "healthy"


def _desired_unmet_services(
    services: tuple[dict[str, Any], ...],
    instances_by_service: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], ...]:
    unmet: list[dict[str, Any]] = []
    for service in services:
        if _text(service.get("start_policy"), "") not in {"eager", "ensure"}:
            continue
        desired = _int(service.get("desired_replicas"), 1)
        ready = _ready_count(instances_by_service.get(_text(service.get("key"), ""), []))
        if ready < desired:
            unmet.append(service)
    return tuple(unmet)


def _metrics(
    *,
    health: str,
    service_sets: tuple[dict[str, Any], ...],
    services: tuple[dict[str, Any], ...],
    instances: tuple[dict[str, Any], ...],
    leases: tuple[dict[str, Any], ...],
    process_rows: tuple[dict[str, Any], ...],
    observed_events: tuple[OperationsObservedEvent, ...],
    instances_by_service: dict[str, list[dict[str, Any]]],
) -> tuple[MetricCardModel, ...]:
    status_counts = Counter(_text(item.get("status"), "unknown").lower() for item in instances)
    lease_counts = Counter(_text(item.get("status"), "unknown").lower() for item in leases)
    process_counts = Counter(_text(item.get("status"), "unknown").lower() for item in process_rows)
    desired_unmet = len(_desired_unmet_services(services, instances_by_service))
    ready = status_counts["ready"]
    non_ready = max(0, len(instances) - ready)
    running_processes = process_counts["running"]
    missing_processes = process_counts["missing"]
    finished_processes = max(
        0,
        len(process_rows) - running_processes - missing_processes,
    )
    process_delta = (
        f"{running_processes} running / {missing_processes} missing"
        if missing_processes
        else f"{running_processes} running / {finished_processes} finished"
    )
    return (
        MetricCardModel(
            id="health",
            label="Overall Health",
            value=_health_label(health),
            delta=_health_delta(health),
            tone=_health_tone(health),
        ),
        MetricCardModel(
            id="service_sets",
            label="Service Sets",
            value=str(len(service_sets)),
            delta="configured daemon sets",
            tone="info" if service_sets else "neutral",
        ),
        MetricCardModel(
            id="services",
            label="Services",
            value=str(len(services)),
            delta=f"{desired_unmet} desired unmet",
            tone="warning" if desired_unmet else "success",
        ),
        MetricCardModel(
            id="instances",
            label="Instances",
            value=str(len(instances)),
            delta=f"{ready} ready / {non_ready} non-ready",
            tone="warning" if non_ready else "success",
        ),
        MetricCardModel(
            id="processes",
            label="Process Sessions",
            value=str(len(process_rows)),
            delta=process_delta,
            tone="danger"
            if process_counts["failed"] or missing_processes
            else "info"
            if process_rows
            else "neutral",
        ),
        MetricCardModel(
            id="leases",
            label="Leases",
            value=str(len(leases)),
            delta=f"{lease_counts['active']} active / {lease_counts['expired']} expired",
            tone="danger" if lease_counts["expired"] else "info" if leases else "neutral",
        ),
        MetricCardModel(
            id="env_drift",
            label="Env Drift",
            value=str(sum(1 for item in instances if _bool(item.get("env_drift_detected")))),
            delta="instances with runtime env drift",
            tone="warning"
            if any(_bool(item.get("env_drift_detected")) for item in instances)
            else "success",
        ),
        MetricCardModel(
            id="events",
            label="Daemon Events",
            value=str(len(observed_events)),
            delta="observed operations events",
            tone="info" if observed_events else "neutral",
        ),
    )


def _tabs(
    *,
    service_sets: int,
    services: int,
    instances: int,
    leases: int,
    processes: int,
    dependencies: int,
    events: int,
) -> tuple[OperationsTabModel, ...]:
    return (
        OperationsTabModel("instances", "Instances", instances),
        OperationsTabModel("processes", "Process Sessions", processes),
        OperationsTabModel("services", "Services", services),
        OperationsTabModel("service_sets", "Service Sets", service_sets),
        OperationsTabModel("leases", "Leases", leases, "warning" if leases else "neutral"),
        OperationsTabModel("dependencies", "Dependencies", dependencies),
        OperationsTabModel("events", "Daemon Events", events),
    )


def _actions() -> tuple[RuntimeActionModel, ...]:
    return (
        RuntimeActionModel(
            id="ensure_service",
            label="Ensure Service",
            owner="daemon",
            risk="controlled",
            method="POST",
            endpoint="/daemon/services/{service_key}/ensure",
        ),
        RuntimeActionModel(
            id="healthcheck_service",
            label="Healthcheck Service",
            owner="daemon",
            risk="normal",
            method="POST",
            endpoint="/daemon/services/{service_key}/healthcheck",
        ),
        RuntimeActionModel(
            id="reconcile_service",
            label="Reconcile Service",
            owner="daemon",
            risk="controlled",
            method="POST",
            endpoint="/daemon/services/{service_key}/reconcile",
        ),
        RuntimeActionModel(
            id="stop_service",
            label="Stop Service",
            owner="daemon",
            risk="dangerous",
            method="POST",
            endpoint="/daemon/services/{service_key}/stop",
            requires_confirmation=True,
            reason_required=True,
        ),
    )


def _service_sets_table(
    *,
    service_sets: tuple[dict[str, Any], ...],
    services: tuple[dict[str, Any], ...],
    instances_by_service: dict[str, list[dict[str, Any]]],
    leases_by_service: dict[str, list[dict[str, Any]]],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for service_set in service_sets:
        matched_services = _matching_services(service_set, services)
        matched_keys = {_text(item.get("key"), "") for item in matched_services}
        matched_instances = [
            instance
            for key in matched_keys
            for instance in instances_by_service.get(key, [])
        ]
        matched_leases = [
            lease
            for key in matched_keys
            for lease in leases_by_service.get(key, [])
        ]
        desired = sum(_int(service.get("desired_replicas"), 1) for service in matched_services)
        ready = _ready_count(matched_instances)
        degraded = _count_status(matched_instances, "degraded")
        stopped = _count_status(matched_instances, "stopped")
        failed = _count_status(matched_instances, "failed")
        active_leases = _count_status(matched_leases, "active")
        status = _availability_status(
            desired=desired,
            ready=ready,
            failed=failed,
            degraded=degraded,
            stopped=stopped,
        )
        rows.append(
            OperationsTableRowModel(
                id=_text(service_set.get("key"), ""),
                cells={
                    "service_set": _text(service_set.get("display_name") or service_set.get("key")),
                    "description": _text(service_set.get("description")),
                    "services": str(len(matched_services)),
                    "desired": str(desired),
                    "ready": str(ready),
                    "degraded": str(degraded),
                    "stopped": str(stopped),
                    "active_leases": str(active_leases),
                    "status": status,
                },
                status=status,
                tone=_tone_for_status(status),
            )
        )
    return OperationsTableSectionModel(
        id="service_sets",
        title="Service Sets",
        columns=(
            OperationsTableColumnModel("service_set", "Service Set"),
            OperationsTableColumnModel("description", "Description"),
            OperationsTableColumnModel("services", "Services"),
            OperationsTableColumnModel("desired", "Desired"),
            OperationsTableColumnModel("ready", "Ready"),
            OperationsTableColumnModel("degraded", "Degraded"),
            OperationsTableColumnModel("stopped", "Stopped"),
            OperationsTableColumnModel("active_leases", "Active Leases"),
            OperationsTableColumnModel("status", "Status"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No records.",
    )


def _services_table(
    *,
    services: tuple[dict[str, Any], ...],
    instances_by_service: dict[str, list[dict[str, Any]]],
    leases_by_service: dict[str, list[dict[str, Any]]],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for service in sorted(services, key=lambda item: _text(item.get("key"), "")):
        service_key = _text(service.get("key"), "")
        service_instances = instances_by_service.get(service_key, [])
        service_leases = leases_by_service.get(service_key, [])
        desired = _int(service.get("desired_replicas"), 1)
        ready = _ready_count(service_instances)
        failed = _count_status(service_instances, "failed")
        degraded = _count_status(service_instances, "degraded")
        stopped = _count_status(service_instances, "stopped")
        active_leases = _count_status(service_leases, "active")
        status = _service_status(service, ready=ready, failed=failed, degraded=degraded)
        rows.append(
            OperationsTableRowModel(
                id=service_key,
                cells={
                    "service_key": service_key,
                    "display_name": _text(service.get("display_name") or service_key),
                    "service_group": _text(service.get("service_group")),
                    "role": _text(service.get("role")),
                    "managed_by": _text(service.get("managed_by")),
                    "transport": _text(service.get("transport")),
                    "start_policy": _text(service.get("start_policy")),
                    "restart_policy": _text(service.get("restart_policy")),
                    "desired": str(desired),
                    "ready": str(ready),
                    "active_leases": str(active_leases),
                    "status": status,
                    "action": "Open / Healthcheck / Reconcile",
                },
                status=status,
                tone=_tone_for_status(status),
            )
        )
    return OperationsTableSectionModel(
        id="services",
        title="Services",
        columns=(
            OperationsTableColumnModel("service_key", "Service Key"),
            OperationsTableColumnModel("display_name", "Display Name"),
            OperationsTableColumnModel("service_group", "Service Group"),
            OperationsTableColumnModel("role", "Role"),
            OperationsTableColumnModel("transport", "Transport"),
            OperationsTableColumnModel("start_policy", "Start Policy"),
            OperationsTableColumnModel("restart_policy", "Restart Policy"),
            OperationsTableColumnModel("desired", "Desired"),
            OperationsTableColumnModel("ready", "Ready"),
            OperationsTableColumnModel("active_leases", "Active Leases"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("action", "Action"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No records.",
    )


def _instances_table(
    instances: tuple[dict[str, Any], ...],
    *,
    total: int,
    service_by_key: dict[str, dict[str, Any]],
) -> OperationsTableSectionModel:
    rows = [
        _instance_row(instance, service_by_key.get(_text(instance.get("service_key"), "")))
        for instance in sorted(
            instances,
            key=lambda item: (
                _status_sort(_text(item.get("status"), "")),
                _text(item.get("service_key"), ""),
                _text(item.get("id"), ""),
            ),
        )
    ]
    return OperationsTableSectionModel(
        id="instances",
        title="Processes",
        columns=(
            OperationsTableColumnModel("instance_id", "Instance ID"),
            OperationsTableColumnModel("service_key", "Service Key"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("pid", "PID"),
            OperationsTableColumnModel("worker_id", "Worker ID"),
            OperationsTableColumnModel("endpoint", "Endpoint"),
            OperationsTableColumnModel("started_at", "Started At"),
            OperationsTableColumnModel("last_healthcheck_at", "Last Healthcheck At"),
            OperationsTableColumnModel("env_drift", "Env Drift"),
            OperationsTableColumnModel("last_error", "Last Error"),
            OperationsTableColumnModel("action", "Action"),
        ),
        rows=tuple(rows),
        total=total,
        empty_state="No records.",
    )


def _instance_row(
    instance: dict[str, Any],
    service: dict[str, Any] | None,
) -> OperationsTableRowModel:
    status = _status_label(instance.get("status"))
    service_key = _text(instance.get("service_key"), "")
    return OperationsTableRowModel(
        id=_text(instance.get("id"), ""),
        cells={
            "instance_id": _text(instance.get("id")),
            "service_key": service_key,
            "display_name": _text((service or {}).get("display_name") or service_key),
            "status": status,
            "pid": _text(instance.get("pid")),
            "worker_id": _text(instance.get("worker_id")),
            "endpoint": _text(instance.get("endpoint")),
            "started_at": _text(instance.get("started_at")),
            "last_healthcheck_at": _text(instance.get("last_healthcheck_at")),
            "env_drift": _yes_no(_bool(instance.get("env_drift_detected"))),
            "last_error": _short(instance.get("last_error"), 96),
            "action": "Open",
        },
        status=status,
        tone=_tone_for_status(status),
    )


def _leases_table(
    leases: tuple[dict[str, Any], ...],
    *,
    total: int,
    service_by_key: dict[str, dict[str, Any]],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for lease in sorted(
        leases,
        key=lambda item: (
            _status_sort(_text(item.get("status"), "")),
            _text(item.get("expires_at"), ""),
            _text(item.get("id"), ""),
        ),
    ):
        status = _status_label(lease.get("status"))
        service_key = _text(lease.get("service_key"), "")
        service = service_by_key.get(service_key, {})
        rows.append(
            OperationsTableRowModel(
                id=_text(lease.get("id"), ""),
                cells={
                    "lease_id": _text(lease.get("id")),
                    "service_key": service_key,
                    "display_name": _text(service.get("display_name") or service_key),
                    "instance_id": _text(lease.get("instance_id")),
                    "owner": f"{_text(lease.get('owner_kind'))}:{_text(lease.get('owner_id'))}",
                    "status": status,
                    "acquired_at": _text(lease.get("acquired_at")),
                    "heartbeat_at": _text(lease.get("heartbeat_at")),
                    "expires_at": _text(lease.get("expires_at")),
                    "action": "Open",
                },
                status=status,
                tone=_tone_for_status(status),
            )
        )
    return OperationsTableSectionModel(
        id="leases",
        title="Leases",
        columns=(
            OperationsTableColumnModel("lease_id", "Lease ID"),
            OperationsTableColumnModel("service_key", "Service Key"),
            OperationsTableColumnModel("instance_id", "Instance ID"),
            OperationsTableColumnModel("owner", "Owner"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("acquired_at", "Acquired At"),
            OperationsTableColumnModel("heartbeat_at", "Heartbeat At"),
            OperationsTableColumnModel("expires_at", "Expires At"),
            OperationsTableColumnModel("action", "Action"),
        ),
        rows=tuple(rows),
        total=total,
        empty_state="No records.",
    )


def _processes_table(
    process_rows: tuple[dict[str, Any], ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for item in sorted(
        process_rows,
        key=lambda row: (
            _status_sort(_text(row.get("status"), "")),
            _text(row.get("service_key"), ""),
            _text(row.get("updated_at"), ""),
            _text(row.get("process_id"), ""),
        ),
    ):
        status = _status_label(item.get("status"))
        rows.append(
            OperationsTableRowModel(
                id=_text(item.get("process_id"), ""),
                cells={
                    "process_id": _text(item.get("process_id")),
                    "service_key": _text(item.get("service_key")),
                    "session_key": _text(item.get("session_key")),
                    "status": status,
                    "pid": _text(item.get("pid")),
                    "exit_code": _text(item.get("exit_code")),
                    "instance_id": _text(item.get("instance_id")),
                    "binding": _process_binding_label(item),
                    "updated_at": _text(item.get("updated_at")),
                    "output": _process_output_marker(item),
                    "command": _short(item.get("command"), 120),
                    "worker_id": _text(item.get("worker_id")),
                    "started_at": _text(item.get("started_at")),
                    "ended_at": _text(item.get("ended_at")),
                    "working_directory": _text(item.get("working_directory")),
                },
                status=_text(item.get("status"), ""),
                tone=_process_tone(item),
            )
        )
    return OperationsTableSectionModel(
        id="processes",
        title="Process Sessions",
        columns=(
            OperationsTableColumnModel("process_id", "Process ID"),
            OperationsTableColumnModel("service_key", "Service Key"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("pid", "PID"),
            OperationsTableColumnModel("exit_code", "Exit Code"),
            OperationsTableColumnModel("instance_id", "Instance ID"),
            OperationsTableColumnModel("binding", "Binding"),
            OperationsTableColumnModel("updated_at", "Updated At"),
            OperationsTableColumnModel("output", "Output"),
        ),
        rows=tuple(rows),
        total=total,
        empty_state="No process sessions observed.",
    )


def _dependency_health_table(
    *,
    services: tuple[dict[str, Any], ...],
    instances_by_service: dict[str, list[dict[str, Any]]],
    leases_by_service: dict[str, list[dict[str, Any]]],
) -> OperationsTableSectionModel:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for service in services:
        groups[_text(service.get("service_group"), "ungrouped")].append(service)
    rows: list[OperationsTableRowModel] = []
    for group, group_services in sorted(groups.items()):
        keys = [_text(service.get("key"), "") for service in group_services]
        group_instances = [
            instance for key in keys for instance in instances_by_service.get(key, [])
        ]
        group_leases = [
            lease for key in keys for lease in leases_by_service.get(key, [])
        ]
        desired = sum(_int(service.get("desired_replicas"), 1) for service in group_services)
        ready = _ready_count(group_instances)
        failed = _count_status(group_instances, "failed")
        degraded = _count_status(group_instances, "degraded")
        active_leases = _count_status(group_leases, "active")
        status = _availability_status(
            desired=desired,
            ready=ready,
            failed=failed,
            degraded=degraded,
            stopped=_count_status(group_instances, "stopped"),
        )
        rows.append(
            OperationsTableRowModel(
                id=group,
                cells={
                    "service_group": group,
                    "services": str(len(group_services)),
                    "desired": str(desired),
                    "ready": str(ready),
                    "active_leases": str(active_leases),
                    "status": status,
                    "details": ", ".join(keys[:6]) if keys else "-",
                },
                status=status,
                tone=_tone_for_status(status),
            )
        )
    return OperationsTableSectionModel(
        id="dependency_health",
        title="Dependency Health",
        columns=(
            OperationsTableColumnModel("service_group", "Service Group"),
            OperationsTableColumnModel("services", "Services"),
            OperationsTableColumnModel("desired", "Desired"),
            OperationsTableColumnModel("ready", "Ready"),
            OperationsTableColumnModel("active_leases", "Active Leases"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("details", "Details"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No records.",
    )


def _daemon_events_table(
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for event in events[:80]:
        payload = dict(event.payload)
        service_key = _first_text(
            payload.get("service_key"),
            payload.get("daemon_service_key"),
            event.entity_id,
        )
        rows.append(
            OperationsTableRowModel(
                id=_text(event.cursor or event.id, ""),
                cells={
                    "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                    "level": event.level,
                    "event": _short_event_name(event.event_name),
                    "service_key": service_key,
                    "entity": _text(event.entity_id),
                    "status": _status_label(event.status),
                    "details": _event_details(payload),
                    "trace": _text(event.trace_id),
                    "trace_route": f"/ui/trace/{event.trace_id}" if event.trace_id else "-",
                },
                status=event.status,
                tone=_event_tone(event),
            )
        )
    return OperationsTableSectionModel(
        id="daemon_events",
        title="Daemon Events",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("level", "Level"),
            OperationsTableColumnModel("event", "Event"),
            OperationsTableColumnModel("service_key", "Service Key"),
            OperationsTableColumnModel("entity", "Entity"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("details", "Details"),
            OperationsTableColumnModel("trace", "Trace"),
        ),
        rows=tuple(rows),
        total=len(events),
        empty_state="No records.",
    )


def _process_rows(
    *,
    process_sessions: tuple[Any, ...],
    instances_by_process_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    observed_process_ids: set[str] = set()
    for session in process_sessions:
        process_id = _text(getattr(session, "id", None), "")
        if not process_id:
            continue
        observed_process_ids.add(process_id)
        metadata = _as_dict(getattr(session, "metadata", None))
        session_key = _text(getattr(session, "session_key", None))
        service_key = _first_text(
            metadata.get("daemon_service_key"),
            _service_key_from_session_key(session_key),
        )
        worker_id = _text(metadata.get("daemon_worker_id"))
        instance = instances_by_process_id.get(process_id)
        instance_id = _text((instance or {}).get("id"))
        status = _process_status_value(getattr(session, "status", None))
        row = {
            "process_id": process_id,
            "service_key": service_key,
            "session_key": session_key,
            "status": status,
            "pid": _text(getattr(session, "pid", None)),
            "exit_code": _text(getattr(session, "exit_code", None)),
            "command": _text(getattr(session, "command", None)),
            "shell": _text(getattr(session, "shell", None)),
            "working_directory": _text(getattr(session, "working_directory", None)),
            "worker_id": worker_id,
            "instance_id": instance_id,
            "created_at": _datetime_text(getattr(session, "created_at", None)),
            "started_at": _datetime_text(getattr(session, "started_at", None)),
            "updated_at": _datetime_text(getattr(session, "updated_at", None)),
            "ended_at": _datetime_text(getattr(session, "ended_at", None)),
            "termination_requested_at": _datetime_text(
                getattr(session, "termination_requested_at", None),
            ),
            "stdout_tail": _short_optional(getattr(session, "stdout", ""), 120),
            "stderr_tail": _short_optional(getattr(session, "stderr", ""), 120),
            "metadata": metadata,
        }
        row["orphaned"] = (
            _process_is_managed(row)
            and status == "running"
            and instance_id == "-"
        )
        rows.append(row)
    rows.extend(
        _missing_process_rows(
            instances_by_process_id=instances_by_process_id,
            observed_process_ids=observed_process_ids,
        )
    )
    return tuple(rows)


def _missing_process_rows(
    *,
    instances_by_process_id: dict[str, dict[str, Any]],
    observed_process_ids: set[str],
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for process_id, instance in sorted(instances_by_process_id.items()):
        if process_id in observed_process_ids:
            continue
        metadata = _as_dict(instance.get("metadata"))
        rows.append(
            {
                "process_id": process_id,
                "service_key": _text(instance.get("service_key")),
                "session_key": _text(metadata.get("session_key")),
                "status": "missing",
                "pid": _text(instance.get("pid")),
                "exit_code": "-",
                "command": _text(metadata.get("command")),
                "shell": "-",
                "working_directory": "-",
                "worker_id": _text(instance.get("worker_id")),
                "instance_id": _text(instance.get("id")),
                "created_at": "-",
                "started_at": _text(instance.get("started_at")),
                "updated_at": _first_text(
                    instance.get("last_healthcheck_at"),
                    instance.get("started_at"),
                ),
                "ended_at": "-",
                "termination_requested_at": "-",
                "stdout_tail": "",
                "stderr_tail": _first_text(
                    instance.get("last_error"),
                    "process session was not found",
                ),
                "metadata": metadata,
                "process_missing": True,
                "orphaned": False,
            }
        )
    return tuple(rows)


def _instances_by_process_id(
    instances: tuple[dict[str, Any], ...],
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for instance in instances:
        metadata = _as_dict(instance.get("metadata"))
        process_id = _text(metadata.get("process_id"), "")
        if process_id:
            indexed[process_id] = instance
    return indexed


def _process_health(
    process_rows: tuple[dict[str, Any], ...],
) -> OperationsChartSectionModel:
    counts = Counter(_text(item.get("status"), "unknown").lower() for item in process_rows)
    segments = tuple(
        OperationsChartSegmentModel(key, _status_label(key), count, _tone_for_status(key))
        for key, count in sorted(counts.items())
    )
    return OperationsChartSectionModel(
        id="process_health",
        title="Process Health",
        kind="donut",
        total=len(process_rows),
        segments=segments,
    )


def _state_summary(
    instances: tuple[dict[str, Any], ...],
) -> OperationsChartSectionModel:
    stopped = _count_status(instances, "stopped")
    failed = _count_status(instances, "failed")
    degraded = _count_status(instances, "degraded")
    drift = sum(1 for item in instances if _bool(item.get("env_drift_detected")))
    segments = (
        OperationsChartSegmentModel("stopped", "Stopped", stopped, "neutral"),
        OperationsChartSegmentModel("failed", "Failed", failed, "danger"),
        OperationsChartSegmentModel("degraded", "Degraded", degraded, "warning"),
        OperationsChartSegmentModel("env_drift", "Env Drift", drift, "warning" if drift else "success"),
    )
    return OperationsChartSectionModel(
        id="restart_summary",
        title="State Changes / Drift",
        kind="bar",
        total=stopped + failed + degraded + drift,
        segments=segments,
    )


def _lease_health(
    leases: tuple[dict[str, Any], ...],
) -> OperationsChartSectionModel:
    counts = Counter(_text(item.get("status"), "unknown").lower() for item in leases)
    ordered = ("active", "expired", "released", "unknown")
    segments = tuple(
        OperationsChartSegmentModel(
            key,
            _status_label(key),
            counts[key],
            _tone_for_status(key),
        )
        for key in ordered
        if counts[key]
    )
    return OperationsChartSectionModel(
        id="lease_health",
        title="Lease Health",
        kind="donut",
        total=len(leases),
        segments=segments,
    )


def _drain_overview(
    *,
    services: tuple[dict[str, Any], ...],
    instances: tuple[dict[str, Any], ...],
    leases: tuple[dict[str, Any], ...],
    process_rows: tuple[dict[str, Any], ...],
    instances_by_service: dict[str, list[dict[str, Any]]],
    leases_by_service: dict[str, list[dict[str, Any]]],
) -> OperationsKeyValueSectionModel:
    instance_ids = {_text(item.get("id"), "") for item in instances}
    active_leases = [item for item in leases if _text(item.get("status"), "").lower() == "active"]
    leased_services = {
        _text(item.get("service_key"), "")
        for item in active_leases
        if _text(item.get("service_key"), "")
    }
    ready_leased_services = sum(
        1
        for service_key in leased_services
        if _ready_count(instances_by_service.get(service_key, [])) > 0
    )
    desired_unmet = len(_desired_unmet_services(services, instances_by_service))
    unmatched = sum(
        1
        for lease in active_leases
        if _text(lease.get("instance_id"), "") not in instance_ids
    )
    release_history = len(
        [item for item in leases if _text(item.get("status"), "").lower() == "released"]
    )
    orphaned_processes = sum(1 for item in process_rows if _bool(item.get("orphaned")))
    return OperationsKeyValueSectionModel(
        id="drain_overview",
        title="Lease / Drain Indicators",
        items=(
            OperationsKeyValueItemModel(
                "Active Leases",
                str(len(active_leases)),
                "info" if active_leases else "neutral",
            ),
            OperationsKeyValueItemModel(
                "Leased Services",
                str(len(leased_services)),
                "info" if leased_services else "neutral",
            ),
            OperationsKeyValueItemModel(
                "Ready Leased Services",
                str(ready_leased_services),
                "success" if ready_leased_services == len(leased_services) else "warning",
            ),
            OperationsKeyValueItemModel(
                "Unmatched Leases",
                str(unmatched),
                "danger" if unmatched else "success",
            ),
            OperationsKeyValueItemModel(
                "Orphaned Processes",
                str(orphaned_processes),
                "warning" if orphaned_processes else "success",
            ),
            OperationsKeyValueItemModel(
                "Desired Unmet",
                str(desired_unmet),
                "warning" if desired_unmet else "success",
            ),
            OperationsKeyValueItemModel(
                "Released History",
                str(release_history),
                "neutral",
            ),
        ),
    )


def _instance_details(
    *,
    instances: tuple[dict[str, Any], ...],
    service_by_key: dict[str, dict[str, Any]],
    leases_by_instance: dict[str, list[dict[str, Any]]],
    events: tuple[OperationsObservedEvent, ...],
) -> tuple[DaemonInstanceDetailModel, ...]:
    details: list[DaemonInstanceDetailModel] = []
    for instance in instances[:80]:
        instance_id = _text(instance.get("id"), "")
        service_key = _text(instance.get("service_key"), "")
        service = service_by_key.get(service_key, {})
        leases = tuple(leases_by_instance.get(instance_id, []))
        matching_events = _matching_events(
            events,
            service_key=service_key,
            entity_id=instance_id,
        )
        status = _status_label(instance.get("status"))
        details.append(
            DaemonInstanceDetailModel(
                instance_id=instance_id,
                title=_text(service.get("display_name") or service_key or instance_id),
                status=status,
                tone=_tone_for_status(status),
                summary=(
                    OperationsKeyValueItemModel("Instance ID", instance_id),
                    OperationsKeyValueItemModel("Service Key", service_key),
                    OperationsKeyValueItemModel("Status", status, _tone_for_status(status)),
                    OperationsKeyValueItemModel("PID", _text(instance.get("pid"))),
                    OperationsKeyValueItemModel("Worker ID", _text(instance.get("worker_id"))),
                    OperationsKeyValueItemModel("Endpoint", _text(instance.get("endpoint"))),
                    OperationsKeyValueItemModel("Started At", _text(instance.get("started_at"))),
                    OperationsKeyValueItemModel(
                        "Last Healthcheck At",
                        _text(instance.get("last_healthcheck_at")),
                    ),
                ),
                environment=_environment_section(instance),
                service=_service_section(service),
                leases=_leases_table(
                    leases,
                    total=len(leases),
                    service_by_key=service_by_key,
                ),
                events=_daemon_events_table(matching_events),
                raw_payload={
                    "instance": dict(instance),
                    "service": dict(service),
                    "leases": [dict(item) for item in leases],
                },
            )
        )
    return tuple(details)


def _lease_details(
    *,
    leases: tuple[dict[str, Any], ...],
    service_by_key: dict[str, dict[str, Any]],
    events: tuple[OperationsObservedEvent, ...],
) -> tuple[DaemonLeaseDetailModel, ...]:
    details: list[DaemonLeaseDetailModel] = []
    for lease in leases[:80]:
        lease_id = _text(lease.get("id"), "")
        service_key = _text(lease.get("service_key"), "")
        status = _status_label(lease.get("status"))
        matching_events = _matching_events(
            events,
            service_key=service_key,
            entity_id=lease_id,
        )
        details.append(
            DaemonLeaseDetailModel(
                lease_id=lease_id,
                title=f"{service_key} lease",
                status=status,
                tone=_tone_for_status(status),
                summary=(
                    OperationsKeyValueItemModel("Lease ID", lease_id),
                    OperationsKeyValueItemModel("Service Key", service_key),
                    OperationsKeyValueItemModel("Instance ID", _text(lease.get("instance_id"))),
                    OperationsKeyValueItemModel("Owner Kind", _text(lease.get("owner_kind"))),
                    OperationsKeyValueItemModel("Owner ID", _text(lease.get("owner_id"))),
                    OperationsKeyValueItemModel("Status", status, _tone_for_status(status)),
                    OperationsKeyValueItemModel("Acquired At", _text(lease.get("acquired_at"))),
                    OperationsKeyValueItemModel("Heartbeat At", _text(lease.get("heartbeat_at"))),
                    OperationsKeyValueItemModel("Expires At", _text(lease.get("expires_at"))),
                ),
                metadata=_metadata_section(lease.get("metadata")),
                events=_daemon_events_table(matching_events),
                raw_payload={
                    "lease": dict(lease),
                    "service": dict(service_by_key.get(service_key, {})),
                },
            )
        )
    return tuple(details)


def _process_details(
    *,
    process_rows: tuple[dict[str, Any], ...],
    process_service: Any | None,
) -> tuple[DaemonProcessDetailModel, ...]:
    details: list[DaemonProcessDetailModel] = []
    for item in process_rows[:80]:
        process_id = _text(item.get("process_id"), "")
        output = _safe_process_output(process_service, process_id)
        status = _status_label(item.get("status"))
        details.append(
            DaemonProcessDetailModel(
                process_id=process_id,
                title=_first_text(item.get("service_key"), item.get("session_key"), process_id),
                status=status,
                tone=_process_tone(item),
                summary=(
                    OperationsKeyValueItemModel("Process ID", process_id),
                    OperationsKeyValueItemModel("Service Key", _text(item.get("service_key"))),
                    OperationsKeyValueItemModel("Session Key", _text(item.get("session_key"))),
                    OperationsKeyValueItemModel("Status", status, _process_tone(item)),
                    OperationsKeyValueItemModel("PID", _text(item.get("pid"))),
                    OperationsKeyValueItemModel("Exit Code", _text(item.get("exit_code"))),
                    OperationsKeyValueItemModel("Instance ID", _text(item.get("instance_id"))),
                    OperationsKeyValueItemModel(
                        "Binding",
                        _process_binding_label(item),
                        _process_binding_tone(item),
                    ),
                    OperationsKeyValueItemModel("Started At", _text(item.get("started_at"))),
                    OperationsKeyValueItemModel("Updated At", _text(item.get("updated_at"))),
                    OperationsKeyValueItemModel("Ended At", _text(item.get("ended_at"))),
                    OperationsKeyValueItemModel("Command", _short(item.get("command"), 180)),
                    OperationsKeyValueItemModel(
                        "Working Directory",
                        _text(item.get("working_directory")),
                    ),
                ),
                metadata=_metadata_section(item.get("metadata")),
                output=_process_output_table(item, output),
                raw_payload={
                    "process": dict(item),
                    "output": _process_output_payload(output),
                },
            )
        )
    return tuple(details)


def _environment_section(instance: dict[str, Any]) -> OperationsKeyValueSectionModel:
    env_keys = instance.get("env_keys")
    if not isinstance(env_keys, list):
        env_keys = []
    drift = _bool(instance.get("env_drift_detected"))
    return OperationsKeyValueSectionModel(
        id="environment",
        title="Environment",
        items=(
            OperationsKeyValueItemModel(
                "Drift Detected",
                _yes_no(drift),
                "warning" if drift else "success",
            ),
            OperationsKeyValueItemModel("Env Fingerprint", _short(instance.get("env_fingerprint"), 32)),
            OperationsKeyValueItemModel(
                "Expected Fingerprint",
                _short(instance.get("expected_env_fingerprint"), 32),
            ),
            OperationsKeyValueItemModel(
                "Actual Fingerprint",
                _short(instance.get("actual_env_fingerprint"), 32),
            ),
            OperationsKeyValueItemModel(
                "Env Keys",
                ", ".join(_text(item, "") for item in env_keys[:12]) if env_keys else "-",
            ),
            OperationsKeyValueItemModel("Last Error", _short(instance.get("last_error"), 160)),
        ),
    )


def _service_section(service: dict[str, Any]) -> OperationsKeyValueSectionModel:
    metadata = service.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    return OperationsKeyValueSectionModel(
        id="service",
        title="Service",
        items=(
            OperationsKeyValueItemModel("Display Name", _text(service.get("display_name"))),
            OperationsKeyValueItemModel("Service Group", _text(service.get("service_group"))),
            OperationsKeyValueItemModel("Role", _text(service.get("role"))),
            OperationsKeyValueItemModel("Managed By", _text(service.get("managed_by"))),
            OperationsKeyValueItemModel("Transport", _text(service.get("transport"))),
            OperationsKeyValueItemModel("Replica Mode", _text(service.get("replica_mode"))),
            OperationsKeyValueItemModel("Desired", _text(service.get("desired_replicas"))),
            OperationsKeyValueItemModel("Start Policy", _text(service.get("start_policy"))),
            OperationsKeyValueItemModel("Restart Policy", _text(service.get("restart_policy"))),
            OperationsKeyValueItemModel("Healthcheck Policy", _text(service.get("healthcheck_policy"))),
            OperationsKeyValueItemModel("Match Policy", _text(service.get("match_policy"))),
            OperationsKeyValueItemModel("CLI Args", _text(metadata.get("cli_args"))),
        ),
    )


def _metadata_section(raw_metadata: Any) -> OperationsKeyValueSectionModel:
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    items = [
        OperationsKeyValueItemModel(_text(key, ""), _short(value, 120))
        for key, value in sorted(metadata.items())
        if not str(key).startswith("_")
    ]
    if not items:
        items = [OperationsKeyValueItemModel("Metadata", "-")]
    return OperationsKeyValueSectionModel(
        id="metadata",
        title="Metadata",
        items=tuple(items[:16]),
    )


def _process_output_table(
    process_row: dict[str, Any],
    output: Any | None,
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    if output is not None:
        stdout = _text(getattr(output, "stdout", None), "")
        stderr = _text(getattr(output, "stderr", None), "")
        rows.extend(
            _process_output_row(
                stream="stdout",
                text=stdout,
                next_offset=_text(getattr(output, "next_stdout_offset", None)),
            ),
        )
        rows.extend(
            _process_output_row(
                stream="stderr",
                text=stderr,
                next_offset=_text(getattr(output, "next_stderr_offset", None)),
            ),
        )
    else:
        rows.extend(
            _process_output_row(
                stream="stdout",
                text=_text(process_row.get("stdout_tail"), ""),
                next_offset="-",
            ),
        )
        rows.extend(
            _process_output_row(
                stream="stderr",
                text=_text(process_row.get("stderr_tail"), ""),
                next_offset="-",
            ),
        )
    return OperationsTableSectionModel(
        id="process_output",
        title="Output",
        columns=(
            OperationsTableColumnModel("stream", "Stream"),
            OperationsTableColumnModel("bytes", "Bytes"),
            OperationsTableColumnModel("preview", "Preview"),
            OperationsTableColumnModel("next_offset", "Next Offset"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No process output observed.",
    )


def _process_output_row(
    *,
    stream: str,
    text: str,
    next_offset: str,
) -> tuple[OperationsTableRowModel, ...]:
    if not text:
        return ()
    return (
        OperationsTableRowModel(
            id=stream,
            cells={
                "stream": stream,
                "bytes": str(len(text.encode("utf-8"))),
                "preview": _short(text.replace("\n", " "), 240),
                "next_offset": next_offset,
            },
            status="observed",
            tone="danger" if stream == "stderr" else "info",
        ),
    )


def _safe_process_output(process_service: Any | None, process_id: str) -> Any | None:
    method = getattr(process_service, "read_output", None)
    if not callable(method) or not process_id:
        return None
    try:
        return method(process_id=process_id, limit=1200)
    except Exception:
        return None


def _process_output_payload(output: Any | None) -> dict[str, Any]:
    if output is None:
        return {}
    return {
        "status": _process_status_value(getattr(output, "status", None)),
        "exit_code": getattr(output, "exit_code", None),
        "stdout": getattr(output, "stdout", ""),
        "stderr": getattr(output, "stderr", ""),
        "stdout_offset": getattr(output, "stdout_offset", 0),
        "stderr_offset": getattr(output, "stderr_offset", 0),
        "next_stdout_offset": getattr(output, "next_stdout_offset", 0),
        "next_stderr_offset": getattr(output, "next_stderr_offset", 0),
    }


def _matching_services(
    service_set: dict[str, Any],
    services: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    keys = set(_string_values(service_set.get("service_keys")))
    roles = set(_string_values(service_set.get("service_roles")))
    groups = set(_string_values(service_set.get("service_groups")))
    return tuple(
        service
        for service in services
        if _text(service.get("key"), "") in keys
        or _text(service.get("role"), "") in roles
        or _text(service.get("service_group"), "") in groups
    )


def _filter_instances(
    instances: tuple[dict[str, Any], ...],
    query: DaemonOperationsQuery,
    *,
    service_by_key: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    needle = query.search.lower()
    filtered: list[dict[str, Any]] = []
    for instance in instances:
        service_key = _text(instance.get("service_key"), "")
        service = service_by_key.get(service_key, {})
        if query.service_key != "all" and service_key.lower() != query.service_key:
            continue
        if (
            query.service_group != "all"
            and _text(service.get("service_group"), "").lower() != query.service_group
        ):
            continue
        if query.status != "all" and _normalized_filter(instance.get("status")) != query.status:
            continue
        if needle and needle not in _search_blob(instance, service):
            continue
        filtered.append(instance)
    return tuple(filtered)


def _filter_leases(
    leases: tuple[dict[str, Any], ...],
    query: DaemonOperationsQuery,
    *,
    service_by_key: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    needle = query.search.lower()
    filtered: list[dict[str, Any]] = []
    for lease in leases:
        service_key = _text(lease.get("service_key"), "")
        service = service_by_key.get(service_key, {})
        if query.service_key != "all" and service_key.lower() != query.service_key:
            continue
        if query.service_group != "all" and _text(service.get("service_group"), "").lower() != query.service_group:
            continue
        if query.status != "all" and _normalized_filter(lease.get("status")) != query.status:
            continue
        if needle and needle not in _search_blob(lease, service):
            continue
        filtered.append(lease)
    return tuple(filtered)


def _filter_process_rows(
    process_rows: tuple[dict[str, Any], ...],
    query: DaemonOperationsQuery,
    *,
    service_by_key: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    needle = query.search.lower()
    filtered: list[dict[str, Any]] = []
    for process in process_rows:
        service_key = _text(process.get("service_key"), "")
        service = service_by_key.get(service_key, {})
        if query.service_key != "all" and service_key.lower() != query.service_key:
            continue
        if query.service_group != "all" and _text(service.get("service_group"), "").lower() != query.service_group:
            continue
        if query.status != "all" and _normalized_filter(process.get("status")) != query.status:
            continue
        if needle and needle not in _search_blob(process, service):
            continue
        filtered.append(process)
    return tuple(filtered)


def _matching_events(
    events: tuple[OperationsObservedEvent, ...],
    *,
    service_key: str,
    entity_id: str,
) -> tuple[OperationsObservedEvent, ...]:
    matches: list[OperationsObservedEvent] = []
    for event in events:
        payload = dict(event.payload)
        candidates = {
            event.entity_id,
            _text(payload.get("process_id"), ""),
            _text(payload.get("service_key"), ""),
            _text(payload.get("daemon_service_key"), ""),
            _text(payload.get("instance_id"), ""),
            _text(payload.get("lease_id"), ""),
            _text(payload.get("worker_id"), ""),
            _text(payload.get("daemon_worker_id"), ""),
        }
        if service_key in candidates or entity_id in candidates:
            matches.append(event)
    return tuple(matches)


def _group_by_key(
    records: tuple[dict[str, Any], ...],
    key: str,
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[_text(record.get(key), "")].append(record)
    return grouped


def _service_groups(services: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    return tuple(sorted({_text(item.get("service_group"), "ungrouped") for item in services}))


def _links_to_operations() -> tuple[dict[str, str], ...]:
    return (
        {"type": "operations_module", "id": "orchestration", "label": "Orchestration", "owner": "operations", "route": "/operations/orchestration"},
        {"type": "operations_module", "id": "tool", "label": "Tool", "owner": "operations", "route": "/operations/tool"},
        {"type": "operations_module", "id": "channels", "label": "Channels", "owner": "operations", "route": "/operations/channels"},
        {"type": "operations_module", "id": "events", "label": "Events", "owner": "operations", "route": "/operations/events"},
    )


def _overview_rows(section: OperationsTableSectionModel) -> tuple[dict[str, str], ...]:
    return tuple(dict(row.cells) for row in section.rows[:80])


def _count_status(records: list[dict[str, Any]] | tuple[dict[str, Any], ...], status: str) -> int:
    return sum(1 for item in records if _text(item.get("status"), "").lower() == status)


def _ready_count(records: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> int:
    return _count_status(records, "ready")


def _service_status(
    service: dict[str, Any],
    *,
    ready: int,
    failed: int,
    degraded: int,
) -> str:
    if failed:
        return "Failed"
    if degraded:
        return "Degraded"
    start_policy = _text(service.get("start_policy"), "")
    desired = _int(service.get("desired_replicas"), 1)
    if start_policy in {"eager", "ensure"} and ready < desired:
        return "Desired Unmet"
    if ready:
        return "Ready"
    if start_policy in {"lazy", "attach-only"}:
        return "Configured"
    return "Stopped"


def _availability_status(
    *,
    desired: int,
    ready: int,
    failed: int,
    degraded: int,
    stopped: int,
) -> str:
    if failed:
        return "Failed"
    if degraded:
        return "Degraded"
    if desired > 0 and ready < desired:
        return "Desired Unmet"
    if stopped and not ready:
        return "Stopped"
    return "Healthy"


def _status_sort(status: str) -> int:
    normalized = status.lower()
    order = {
        "failed": 0,
        "missing": 0,
        "expired": 0,
        "degraded": 1,
        "running": 2,
        "starting": 2,
        "stopping": 2,
        "ready": 3,
        "active": 3,
        "exited": 4,
        "stopped": 4,
        "killed": 4,
        "released": 5,
    }
    return order.get(normalized, 6)


def _tone_for_status(status: Any) -> str:
    text = _text(status, "").lower()
    if text in {"failed", "error", "expired", "desired unmet", "missing"}:
        return "danger"
    if text in {"warning", "degraded", "starting", "stopping", "stopped", "env drift", "killed"}:
        return "warning"
    if text in {"ready", "active", "healthy", "success", "configured", "running", "bound"}:
        return "success"
    if text in {"released", "exited"}:
        return "neutral"
    return "neutral"


def _process_tone(process: dict[str, Any]) -> str:
    if _bool(process.get("process_missing")):
        return "danger"
    if _bool(process.get("orphaned")):
        return "warning"
    return _tone_for_status(process.get("status"))


def _process_binding_label(process: dict[str, Any]) -> str:
    if _bool(process.get("process_missing")):
        return "Missing Session"
    if _bool(process.get("orphaned")):
        return "Unbound"
    return "Bound"


def _process_binding_tone(process: dict[str, Any]) -> str:
    if _bool(process.get("process_missing")):
        return "danger"
    if _bool(process.get("orphaned")):
        return "warning"
    return "success"


def _process_is_managed(process: dict[str, Any]) -> bool:
    service_key = _text(process.get("service_key"), "")
    session_key = _text(process.get("session_key"), "")
    return service_key not in {"", "-"} or session_key.startswith("daemon:")


def _process_output_marker(process: dict[str, Any]) -> str:
    markers: list[str] = []
    if _text(process.get("stdout_tail"), ""):
        markers.append("stdout")
    if _text(process.get("stderr_tail"), ""):
        markers.append("stderr")
    metadata = _as_dict(process.get("metadata"))
    if not markers and (
        _text(metadata.get("stdout_path"), "")
        or _text(metadata.get("stderr_path"), "")
    ):
        markers.append("logs")
    return ", ".join(markers) if markers else "-"


def _service_key_from_session_key(session_key: str) -> str:
    prefix = "daemon:"
    if session_key.startswith(prefix):
        return session_key.removeprefix(prefix)
    return "-"


def _process_status_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return _text(raw, "unknown").lower()


def _datetime_text(value: Any) -> str:
    if isinstance(value, datetime):
        return format_datetime_utc(coerce_utc_datetime(value))
    return _text(value)


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _event_tone(event: OperationsObservedEvent) -> str:
    if event.level == "error" or event.status in {"failed", "error"}:
        return "danger"
    if event.level == "warning" or event.status in {"warning", "degraded"}:
        return "warning"
    return "success" if event.status in {"completed", "success", "observed"} else "neutral"


def _event_details(payload: dict[str, Any]) -> str:
    for key in (
        "summary",
        "message",
        "reason",
        "error_message",
        "status",
        "component",
        "service_key",
    ):
        value = payload.get(key)
        if value is not None and _text(value, "") != "-":
            return _short(value, 120)
    return "-"


def _short_event_name(event_name: str) -> str:
    value = event_name
    for prefix in ("daemon.", "crxzipple."):
        if value.startswith(prefix):
            return value[len(prefix) :]
    return value


def _health_label(health: str) -> str:
    if health == "error":
        return "Error"
    if health == "warning":
        return "Warning"
    return "Healthy"


def _health_delta(health: str) -> str:
    if health == "error":
        return "Operator action required"
    if health == "warning":
        return "Operator attention recommended"
    return "Daemon runtime state is queryable"


def _health_tone(health: str) -> str:
    if health == "error":
        return "danger"
    if health == "warning":
        return "warning"
    return "success"


def _status_label(value: Any) -> str:
    text = _text(value, "unknown").replace("_", " ").strip()
    if not text:
        return "-"
    return " ".join(part.capitalize() for part in text.split())


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def _normalized_filter(value: Any) -> str:
    text = _text(value, "all").strip().lower().replace(" ", "_")
    return text or "all"


def _string_values(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item.strip().lower() for item in value.split(",") if item.strip())
    if isinstance(value, (list, tuple, set)):
        return tuple(_text(item, "").lower() for item in value if _text(item, ""))
    return ()


def _search_blob(*records: dict[str, Any]) -> str:
    values: list[str] = []
    for record in records:
        for value in record.values():
            values.append(_text(value, ""))
    return " ".join(values).lower()


def _first_text(*values: Any) -> str:
    for value in values:
        text = _text(value, "")
        if text and text != "-":
            return text
    return "-"


def _text(value: Any, default: str = "-") -> str:
    if value is None:
        return default
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return ", ".join(_text(item, "") for item in value if _text(item, ""))
    if isinstance(value, dict):
        return ", ".join(f"{key}={_text(item, '')}" for key, item in sorted(value.items()))
    text = str(value).strip()
    return text if text else default


def _short(value: Any, limit: int = 80) -> str:
    text = _text(value)
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)]}..."


def _short_optional(value: Any, limit: int = 80) -> str:
    text = _text(value, "")
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)]}..."


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)
