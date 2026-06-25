from __future__ import annotations

from collections import Counter
from typing import Any

from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.daemon_common import (
    _bool,
    _text,
)
from crxzipple.modules.operations.application.read_models.daemon_health import (
    desired_unmet_services,
)
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsTabModel,
)


def daemon_metrics(
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
    desired_unmet = len(desired_unmet_services(services, instances_by_service))
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


def daemon_tabs(
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
