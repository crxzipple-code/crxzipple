from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.read_models.tool_provider_limit_facts import (
    TOOL_PROVIDER_LIMITER_PREFIX,
)
from crxzipple.modules.operations.application.read_models.tool_worker_runtime import (
    worker_is_online,
)
from crxzipple.modules.tool.domain import ToolWorkerRegistration


def provider_metric_snapshots(
    *,
    workers: list[ToolWorkerRegistration],
    runtime_metrics: Any | None,
    now: datetime,
) -> tuple[tuple[str, dict[str, Any]], ...]:
    snapshots: list[tuple[str, dict[str, Any]]] = []
    local_snapshot = runtime_metrics_snapshot(runtime_metrics)
    if local_snapshot:
        snapshots.append(("api-process", local_snapshot))
    for worker in workers:
        if not worker_is_online(worker, now=now):
            continue
        snapshot = worker.capabilities_payload.get("runtime_metrics")
        if isinstance(snapshot, dict):
            snapshots.append((worker.id, snapshot))
    return tuple(snapshots)


def runtime_metrics_snapshot(runtime_metrics: Any | None) -> dict[str, Any]:
    snapshot = getattr(runtime_metrics, "snapshot", None)
    if not callable(snapshot):
        return {}
    try:
        payload = snapshot(prefixes=(TOOL_PROVIDER_LIMITER_PREFIX,))
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def provider_limiter_configuration_snapshots(
    *,
    workers: list[ToolWorkerRegistration],
    runtime_registry: Any | None,
    now: datetime,
) -> tuple[tuple[str, dict[str, Any]], ...]:
    snapshots: list[tuple[str, dict[str, Any]]] = []
    local_snapshot = runtime_registry_snapshot(runtime_registry)
    if local_snapshot:
        snapshots.append(("api-process", local_snapshot))
    for worker in workers:
        if not worker_is_online(worker, now=now):
            continue
        snapshot = worker.capabilities_payload.get("runtime_registry")
        if isinstance(snapshot, dict):
            snapshots.append((worker.id, snapshot))
    return tuple(snapshots)


def runtime_registry_snapshot(runtime_registry: Any | None) -> dict[str, Any]:
    snapshot = getattr(runtime_registry, "snapshot", None)
    if callable(snapshot):
        try:
            payload = snapshot()
        except Exception:
            return {}
        return dict(payload) if isinstance(payload, dict) else {}
    registrations_fn = getattr(runtime_registry, "registrations", None)
    if not callable(registrations_fn):
        return {}
    try:
        registrations = registrations_fn()
    except Exception:
        return {}
    return {
        "registrations": [
            {
                "runtime_key": getattr(registration, "runtime_key", None),
                "concurrency_key": getattr(registration, "concurrency_key", None),
                "max_concurrency": getattr(registration, "max_concurrency", None),
            }
            for registration in registrations
        ],
    }
