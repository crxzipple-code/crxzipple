from __future__ import annotations

from collections import Counter
from typing import Any

from crxzipple.modules.daemon import DaemonNotFoundError, DaemonValidationError
from crxzipple.modules.daemon.interfaces.presenters import (
    instance_payload,
    lease_payload,
    service_set_payload,
    spec_payload,
)
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsModuleOverview,
    RuntimeActionModel,
)
from crxzipple.modules.operations.application.read_models.modules_daemon_rows import (
    daemon_instance_row,
    daemon_service_row,
    daemon_service_set_row,
)
from crxzipple.modules.operations.application.read_models.modules_helpers import (
    health_metric,
    now,
    overview,
    s,
)
from crxzipple.shared.time import format_datetime_utc


def daemon_operations_overview(query: Any) -> OperationsModuleOverview:
    current_time = now()
    services = [
        spec_payload(spec) for spec in query.daemon_service.list_service_specs()
    ]
    service_sets = [
        service_set_payload(item)
        for item in query.daemon_service.list_service_sets()
    ]
    leases = [lease_payload(item) for item in query.daemon_service.list_leases()]
    try:
        instances = [
            instance_payload(item)
            for item in query.daemon_manager.list_instances(refresh=False)
        ]
    except (DaemonValidationError, DaemonNotFoundError):
        instances = []

    status_counts = Counter(s(item.get("status")) for item in instances)
    ready = status_counts["ready"]
    stopped = status_counts["stopped"]
    other = max(0, len(instances) - ready - stopped)
    health = "warning" if stopped or other else "healthy"
    service_by_key = {s(service.get("key")): service for service in services}

    return overview(
        module="daemon",
        title="Daemons",
        subtitle="聚合守护进程服务集、进程实例、租约与服务组健康。",
        health=health,
        updated_at=format_datetime_utc(current_time),
        metrics=(
            health_metric(health, "Loaded from daemon registry"),
            MetricCardModel(
                "service_sets",
                "Service Sets",
                str(len(service_sets)),
                "configured sets",
                "info",
            ),
            MetricCardModel(
                "processes",
                "Processes",
                str(len(instances)),
                f"ready {ready} / stopped {stopped}",
                "info",
            ),
            MetricCardModel(
                "healthy", "Healthy", str(ready), "ready instances", "success"
            ),
            MetricCardModel(
                "unhealthy",
                "Unhealthy",
                str(other),
                "non-ready non-stopped instances",
                "warning" if other else "success",
            ),
            MetricCardModel(
                "stopped",
                "Stopped",
                str(stopped),
                "historical stopped instances",
                "warning" if stopped else "success",
            ),
            MetricCardModel(
                "leases",
                "Leases",
                str(len(leases)),
                "active daemon leases",
                "info" if leases else "neutral",
            ),
        ),
        queue=tuple(
            daemon_service_set_row(item, services, instances) for item in service_sets
        ),
        lane_locks=tuple(daemon_service_row(item) for item in services),
        executor=tuple(
            daemon_instance_row(item, service_by_key.get(s(item.get("service_key"))))
            for item in instances[:80]
        ),
        actions=(
            RuntimeActionModel(
                id="ensure_service",
                label="Ensure Service",
                owner="daemon",
                risk="controlled",
            ),
            RuntimeActionModel(
                id="stop_service",
                label="Stop Service",
                owner="daemon",
                risk="dangerous",
                requires_confirmation=True,
            ),
            RuntimeActionModel(
                id="restart_service",
                label="Restart Service",
                owner="daemon",
                risk="controlled",
                requires_confirmation=True,
            ),
        ),
    )
