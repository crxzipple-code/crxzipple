from __future__ import annotations

from typing import Any


def daemon_setup_available(spec: Any) -> bool:
    return getattr(spec, "start_policy", None) in {"eager", "ensure", "lazy"}


def daemon_status(instances: tuple[Any, ...]) -> str:
    statuses = {str(getattr(instance, "status", "")).strip().lower() for instance in instances}
    if "degraded" in statuses:
        return "degraded"
    if statuses & {"starting", "stopping"}:
        return "degraded"
    if statuses & {"failed", "stopped"}:
        return "setup_needed"
    return "degraded"


def daemon_reason(service_key: str, instances: tuple[Any, ...], *, status: str) -> str:
    errors = tuple(
        str(getattr(instance, "last_error", "") or "").strip()
        for instance in instances
        if str(getattr(instance, "last_error", "") or "").strip()
    )
    if errors:
        return f"Daemon service '{service_key}' is not ready: {'; '.join(errors)}"
    statuses = ", ".join(
        sorted({str(getattr(instance, "status", "unknown")) for instance in instances})
    )
    return f"Daemon service '{service_key}' is {status}: {statuses or 'unknown'}."


def daemon_metadata(spec: Any, instances: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "service_key": getattr(spec, "key", None),
        "display_name": getattr(spec, "display_name", None),
        "service_group": getattr(spec, "service_group", None),
        "role": getattr(spec, "role", None),
        "start_policy": getattr(spec, "start_policy", None),
        "desired_replicas": getattr(spec, "desired_replicas", None),
        "instance_count": len(instances),
        "instance_statuses": [
            str(getattr(instance, "status", "unknown")) for instance in instances
        ],
    }


def daemon_group_metadata(
    service_group: str,
    specs: tuple[Any, ...],
    instances: tuple[Any, ...],
) -> dict[str, Any]:
    return {
        "service_group": service_group,
        "service_keys": [str(getattr(spec, "key", "")) for spec in specs],
        "start_policies": [str(getattr(spec, "start_policy", "")) for spec in specs],
        "desired_replicas": sum(
            int(getattr(spec, "desired_replicas", 0) or 0) for spec in specs
        ),
        "instance_count": len(instances),
        "instance_statuses": [
            str(getattr(instance, "status", "unknown")) for instance in instances
        ],
    }


__all__ = [
    "daemon_group_metadata",
    "daemon_metadata",
    "daemon_reason",
    "daemon_setup_available",
    "daemon_status",
]
