from __future__ import annotations

from typing import Any

from crxzipple.modules.tool.application.concurrency import ToolRunConcurrencyPolicy


def build_worker_capabilities_payload(
    capabilities_payload: dict[str, Any] | None,
    *,
    metrics,
    runtime_registry,
    concurrency_policy: ToolRunConcurrencyPolicy,
) -> dict[str, Any]:
    payload = dict(capabilities_payload or {})
    payload["runtime_metrics"] = metrics.snapshot(
        prefixes=("tool.remote_provider_limiter.",),
    )
    registry_snapshot = runtime_registry_snapshot(runtime_registry)
    if registry_snapshot:
        payload["runtime_registry"] = registry_snapshot
    payload["concurrency_policy"] = {
        "default_max_in_flight": concurrency_policy.default_max_in_flight,
        "image_max_in_flight": concurrency_policy.image_max_in_flight,
        "shared_state_max_in_flight": concurrency_policy.shared_state_max_in_flight,
    }
    return payload


def runtime_registry_snapshot(runtime_registry) -> dict[str, Any]:
    snapshot = getattr(runtime_registry, "snapshot", None)
    if callable(snapshot):
        try:
            payload = snapshot()
        except Exception:
            return {}
        return dict(payload) if isinstance(payload, dict) else {}
    registrations = getattr(runtime_registry, "registrations", None)
    if not callable(registrations):
        return {}
    try:
        values = registrations()
    except Exception:
        return {}
    entries: list[dict[str, object]] = []
    for item in values:
        runtime_key = getattr(item, "runtime_key", None)
        if not isinstance(runtime_key, str) or not runtime_key.strip():
            continue
        entries.append(
            {
                "runtime_key": runtime_key.strip(),
                "concurrency_key": getattr(item, "concurrency_key", None),
                "max_concurrency": getattr(item, "max_concurrency", None),
            },
        )
    return {"registrations": entries} if entries else {}


__all__ = [
    "build_worker_capabilities_payload",
    "runtime_registry_snapshot",
]
