from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.daemon_common import (
    _bool,
    _int,
    _text,
)
from crxzipple.modules.operations.application.read_models.daemon_process_helpers import (
    _process_is_managed,
)
from crxzipple.modules.operations.application.read_models.daemon_status_helpers import (
    _ready_count,
)


def daemon_health(
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
    if desired_unmet_services(services, instances_by_service):
        return "warning"
    if not services:
        return "warning"
    return "healthy"


def desired_unmet_services(
    services: tuple[dict[str, Any], ...],
    instances_by_service: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], ...]:
    unmet: list[dict[str, Any]] = []
    for service in services:
        if _text(service.get("start_policy"), "") != "eager":
            continue
        desired = _int(service.get("desired_replicas"), 1)
        ready = _ready_count(instances_by_service.get(_text(service.get("key"), ""), []))
        if ready < desired:
            unmet.append(service)
    return tuple(unmet)
