from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.daemon.interfaces.presenters import (
    instance_payload,
    lease_payload,
    service_set_payload,
    spec_payload,
)
from crxzipple.modules.operations.application.read_models.daemon_common import (
    _text,
)
from crxzipple.modules.operations.application.read_models.daemon_event_sources import (
    recent_daemon_events,
)
from crxzipple.modules.operations.application.read_models.daemon_filters import (
    filter_daemon_instances,
    filter_daemon_leases,
    filter_daemon_process_rows,
    normalize_daemon_query,
)
from crxzipple.modules.operations.application.read_models.daemon_health import (
    daemon_health,
)
from crxzipple.modules.operations.application.read_models.daemon_models import (
    DaemonOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.daemon_process_facts import (
    daemon_instances_by_process_id,
    daemon_process_rows,
    daemon_process_sessions,
)
from crxzipple.modules.operations.application.read_models.daemon_runtime_facts import (
    current_daemon_instances,
    current_daemon_leases,
    current_daemon_process_rows,
    group_by_key,
    safe_daemon_instances,
    safe_tuple,
)


@dataclass(frozen=True, slots=True)
class DaemonPageFacts:
    now: datetime
    query: DaemonOperationsQuery
    services: tuple[dict[str, Any], ...]
    service_sets: tuple[dict[str, Any], ...]
    leases: tuple[dict[str, Any], ...]
    instances: tuple[dict[str, Any], ...]
    observed_events: list[Any]
    service_by_key: dict[str, dict[str, Any]]
    instances_by_service: dict[str, list[dict[str, Any]]]
    instances_by_process_id: dict[str, dict[str, Any]]
    leases_by_service: dict[str, list[dict[str, Any]]]
    leases_by_instance: dict[str, list[dict[str, Any]]]
    process_sessions: tuple[dict[str, Any], ...]
    process_rows: tuple[dict[str, Any], ...]
    current_instances: list[dict[str, Any]]
    current_instances_by_service: dict[str, list[dict[str, Any]]]
    current_process_rows: list[dict[str, Any]]
    current_leases: list[dict[str, Any]]
    health: str
    filtered_instances: tuple[dict[str, Any], ...]
    visible_instances: tuple[dict[str, Any], ...]
    filtered_leases: tuple[dict[str, Any], ...]
    visible_leases: tuple[dict[str, Any], ...]
    filtered_process_rows: tuple[dict[str, Any], ...]
    visible_process_rows: tuple[dict[str, Any], ...]


def collect_daemon_page_facts(
    *,
    query: DaemonOperationsQuery | None,
    daemon_service: Any | None,
    daemon_manager: Any | None,
    events_service: Any | None,
    event_definition_registry: Any | None,
    operations_observation: Any | None,
    process_service: Any | None,
) -> DaemonPageFacts:
    normalized_query = normalize_daemon_query(query)
    now = datetime.now(timezone.utc)
    services = tuple(
        spec_payload(item)
        for item in safe_tuple(daemon_service, "list_service_specs")
    )
    service_sets = tuple(
        service_set_payload(item)
        for item in safe_tuple(daemon_service, "list_service_sets")
    )
    leases = tuple(
        lease_payload(item)
        for item in safe_tuple(daemon_service, "list_leases")
    )
    instances = tuple(
        instance_payload(item)
        for item in safe_daemon_instances(daemon_manager)
    )
    observed_events = recent_daemon_events(
        operations_observation=operations_observation,
        events_service=events_service,
        definition_registry=event_definition_registry,
    )

    service_by_key = {_text(item.get("key"), ""): item for item in services}
    instances_by_service = group_by_key(instances, "service_key")
    instances_by_process_id = daemon_instances_by_process_id(instances)
    leases_by_service = group_by_key(leases, "service_key")
    leases_by_instance = group_by_key(leases, "instance_id")
    process_sessions = daemon_process_sessions(
        process_service=process_service,
        instances_by_process_id=instances_by_process_id,
    )
    process_rows = daemon_process_rows(
        process_sessions=process_sessions,
        instances_by_process_id=instances_by_process_id,
    )
    current_instances = current_daemon_instances(instances, now=now)
    current_instances_by_service = group_by_key(current_instances, "service_key")
    current_process_rows = current_daemon_process_rows(process_rows, now=now)
    current_leases = current_daemon_leases(leases, now=now)
    health = daemon_health(
        service_available=daemon_service is not None,
        services=services,
        instances=current_instances,
        leases=current_leases,
        instances_by_service=current_instances_by_service,
        process_rows=current_process_rows,
    )
    filtered_instances = filter_daemon_instances(
        instances,
        normalized_query,
        service_by_key=service_by_key,
    )
    visible_instances = filtered_instances[
        normalized_query.offset : normalized_query.offset + normalized_query.limit
    ]
    filtered_leases = filter_daemon_leases(
        leases,
        normalized_query,
        service_by_key=service_by_key,
    )
    visible_leases = filtered_leases[
        normalized_query.offset : normalized_query.offset + normalized_query.limit
    ]
    filtered_process_rows = filter_daemon_process_rows(
        process_rows,
        normalized_query,
        service_by_key=service_by_key,
    )
    visible_process_rows = filtered_process_rows[
        normalized_query.offset : normalized_query.offset + normalized_query.limit
    ]

    return DaemonPageFacts(
        now=now,
        query=normalized_query,
        services=services,
        service_sets=service_sets,
        leases=leases,
        instances=instances,
        observed_events=observed_events,
        service_by_key=service_by_key,
        instances_by_service=instances_by_service,
        instances_by_process_id=instances_by_process_id,
        leases_by_service=leases_by_service,
        leases_by_instance=leases_by_instance,
        process_sessions=process_sessions,
        process_rows=process_rows,
        current_instances=current_instances,
        current_instances_by_service=current_instances_by_service,
        current_process_rows=current_process_rows,
        current_leases=current_leases,
        health=health,
        filtered_instances=filtered_instances,
        visible_instances=visible_instances,
        filtered_leases=filtered_leases,
        visible_leases=visible_leases,
        filtered_process_rows=filtered_process_rows,
        visible_process_rows=visible_process_rows,
    )
