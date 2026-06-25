from __future__ import annotations

from collections import defaultdict
from typing import Any

from crxzipple.modules.operations.application.read_models.daemon_common import (
    _int,
    _string_values,
    _text,
)
from crxzipple.modules.operations.application.read_models.daemon_status_helpers import (
    _availability_status,
    _count_status,
    _health_desired_replicas,
    _ready_count,
    _service_status,
    _tone_for_status,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)


def service_set_rows(
    *,
    service_sets: tuple[dict[str, Any], ...],
    services: tuple[dict[str, Any], ...],
    instances_by_service: dict[str, list[dict[str, Any]]],
    leases_by_service: dict[str, list[dict[str, Any]]],
) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    for service_set in service_sets:
        matched_services = matching_services(service_set, services)
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
        desired = sum(_health_desired_replicas(service) for service in matched_services)
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
    return tuple(rows)


def service_rows(
    *,
    services: tuple[dict[str, Any], ...],
    instances_by_service: dict[str, list[dict[str, Any]]],
    leases_by_service: dict[str, list[dict[str, Any]]],
) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    for service in sorted(services, key=lambda item: _text(item.get("key"), "")):
        service_key = _text(service.get("key"), "")
        service_instances = instances_by_service.get(service_key, [])
        service_leases = leases_by_service.get(service_key, [])
        desired = _int(service.get("desired_replicas"), 1)
        ready = _ready_count(service_instances)
        failed = _count_status(service_instances, "failed")
        degraded = _count_status(service_instances, "degraded")
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
    return tuple(rows)


def dependency_health_rows(
    *,
    services: tuple[dict[str, Any], ...],
    instances_by_service: dict[str, list[dict[str, Any]]],
    leases_by_service: dict[str, list[dict[str, Any]]],
) -> tuple[OperationsTableRowModel, ...]:
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
        desired = sum(_health_desired_replicas(service) for service in group_services)
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
    return tuple(rows)


def matching_services(
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
