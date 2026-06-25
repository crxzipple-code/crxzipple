from __future__ import annotations

from collections import Counter
from typing import Any

from crxzipple.modules.operations.application.read_models.modules_helpers import (
    s,
    short,
)


def daemon_service_set_row(
    service_set: dict[str, Any],
    services: list[dict[str, Any]],
    instances: list[dict[str, Any]],
) -> dict[str, str]:
    matched = _daemon_matching_services(service_set, services)
    matched_keys = {s(service.get("key")) for service in matched}
    matched_instances = [
        item for item in instances if s(item.get("service_key")) in matched_keys
    ]
    status_counts = Counter(s(item.get("status")) for item in matched_instances)
    ready = status_counts["ready"]
    stopped = status_counts["stopped"]
    unhealthy = max(0, len(matched_instances) - ready - stopped)
    return {
        "key": s(service_set.get("key")),
        "set": s(service_set.get("display_name") or service_set.get("key")),
        "display_name": s(service_set.get("display_name") or service_set.get("key")),
        "description": s(service_set.get("description")),
        "service_keys": s(service_set.get("service_keys")),
        "service_roles": s(service_set.get("service_roles")),
        "service_groups": s(service_set.get("service_groups")),
        "processes": str(len(matched_instances)),
        "healthy": str(ready),
        "unhealthy": str(unhealthy),
        "stopped": str(stopped),
        "status": "Warning" if unhealthy or stopped else "Healthy",
    }


def daemon_service_row(service: dict[str, Any]) -> dict[str, str]:
    return {
        "key": s(service.get("key")),
        "display_name": s(service.get("display_name")),
        "service_group": s(service.get("service_group")),
        "role": s(service.get("role")),
        "status": "Configured",
        "restart_policy": s(service.get("restart_policy")),
    }


def daemon_instance_row(
    instance: dict[str, Any],
    service: dict[str, Any] | None,
) -> dict[str, str]:
    return {
        "id": s(instance.get("id")),
        "service_key": s(instance.get("service_key")),
        "process": s(
            (service or {}).get("display_name") or instance.get("service_key")
        ),
        "set": s((service or {}).get("service_group")),
        "loop": s((service or {}).get("role")),
        "status": s(instance.get("status")).title(),
        "worker_id": s(instance.get("worker_id")),
        "pid": s(instance.get("pid")),
        "endpoint": s(instance.get("endpoint")),
        "last_healthcheck_at": s(instance.get("last_healthcheck_at")),
        "started_at": s(instance.get("started_at")),
        "env_fingerprint": short(instance.get("env_fingerprint"), 18),
        "env_drift_detected": s(instance.get("env_drift_detected")),
        "last_error": short(instance.get("last_error"), 80),
    }


def _daemon_matching_services(
    service_set: dict[str, Any],
    services: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    keys = set(_split_csv(s(service_set.get("service_keys"))))
    roles = set(_split_csv(s(service_set.get("service_roles"))))
    groups = set(_split_csv(s(service_set.get("service_groups"))))
    return [
        service
        for service in services
        if s(service.get("key")) in keys
        or s(service.get("role")) in roles
        or s(service.get("service_group")) in groups
    ]


def _split_csv(value: str) -> list[str]:
    if value == "-":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
