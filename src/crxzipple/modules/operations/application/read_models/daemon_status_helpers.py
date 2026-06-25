from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.daemon_common import (
    _int,
    _text,
)


def _count_status(records: list[dict[str, Any]] | tuple[dict[str, Any], ...], status: str) -> int:
    return sum(1 for item in records if _text(item.get("status"), "").lower() == status)


def _ready_count(records: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> int:
    return _count_status(records, "ready")


def _health_desired_replicas(service: dict[str, Any]) -> int:
    if _text(service.get("start_policy"), "") != "eager":
        return 0
    return _int(service.get("desired_replicas"), 1)


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
    if start_policy == "eager" and ready < desired:
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
