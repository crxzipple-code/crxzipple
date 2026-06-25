from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.daemon_table_rows import (
    instance_rows,
    lease_rows,
)
from crxzipple.modules.operations.application.read_models.daemon_service_rows import (
    dependency_health_rows,
    service_rows,
    service_set_rows,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableSectionModel,
)


def daemon_service_sets_table(
    *,
    service_sets: tuple[dict[str, Any], ...],
    services: tuple[dict[str, Any], ...],
    instances_by_service: dict[str, list[dict[str, Any]]],
    leases_by_service: dict[str, list[dict[str, Any]]],
) -> OperationsTableSectionModel:
    rows = service_set_rows(
        service_sets=service_sets,
        services=services,
        instances_by_service=instances_by_service,
        leases_by_service=leases_by_service,
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
        rows=rows,
        total=len(rows),
        empty_state="No records.",
    )


def daemon_services_table(
    *,
    services: tuple[dict[str, Any], ...],
    instances_by_service: dict[str, list[dict[str, Any]]],
    leases_by_service: dict[str, list[dict[str, Any]]],
) -> OperationsTableSectionModel:
    rows = service_rows(
        services=services,
        instances_by_service=instances_by_service,
        leases_by_service=leases_by_service,
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
        rows=rows,
        total=len(rows),
        empty_state="No records.",
    )


def daemon_instances_table(
    instances: tuple[dict[str, Any], ...],
    *,
    total: int,
    service_by_key: dict[str, dict[str, Any]],
) -> OperationsTableSectionModel:
    rows = instance_rows(instances, service_by_key=service_by_key)
    return OperationsTableSectionModel(
        id="instances",
        title="Processes",
        columns=(
            OperationsTableColumnModel("instance_id", "Instance ID"),
            OperationsTableColumnModel("service_key", "Service Key"),
            OperationsTableColumnModel("runtime", "Runtime"),
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
        rows=rows,
        total=total,
        empty_state="No records.",
    )


def daemon_leases_table(
    leases: tuple[dict[str, Any], ...],
    *,
    total: int,
    service_by_key: dict[str, dict[str, Any]],
) -> OperationsTableSectionModel:
    rows = lease_rows(leases, service_by_key=service_by_key)
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
        rows=rows,
        total=total,
        empty_state="No records.",
    )


def daemon_dependency_health_table(
    *,
    services: tuple[dict[str, Any], ...],
    instances_by_service: dict[str, list[dict[str, Any]]],
    leases_by_service: dict[str, list[dict[str, Any]]],
) -> OperationsTableSectionModel:
    rows = dependency_health_rows(
        services=services,
        instances_by_service=instances_by_service,
        leases_by_service=leases_by_service,
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
        rows=rows,
        total=len(rows),
        empty_state="No records.",
    )
