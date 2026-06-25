from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.operations.application.read_models.events_state_common import (
    display,
    safe_operations_observation_snapshot,
    seconds_since_datetime,
)
from crxzipple.modules.operations.application.read_models.events_subscription_state import (
    safe_observer_subscriptions,
)
from crxzipple.shared.time import format_datetime_utc

_OBSERVER_RUNTIME_STALE_AFTER_SECONDS = 30.0


def observer_runtime_states(
    operations_observation: Any | None,
    *,
    runtime: Any | None,
    now: datetime,
) -> list[dict[str, Any]]:
    snapshot = safe_operations_observation_snapshot(operations_observation)
    heartbeats = tuple(getattr(snapshot, "observer_heartbeats", ()) or ())
    if not heartbeats:
        subscriptions = safe_observer_subscriptions(runtime)
        if runtime is None and not subscriptions:
            return []
        return [
            {
                "runtime_name": display(
                    getattr(runtime, "runtime_name", None),
                    "operations.observer",
                ),
                "worker_id": "-",
                "status": "Missing Heartbeat",
                "last_seen_at": "-",
                "seconds_since_update": 0.0,
                "processed_events": 0,
                "idle_cycles": 0,
                "subscription_count": len(subscriptions),
                "active": False,
                "lagging": True,
                "stuck": False,
                "tone": "warning",
            }
        ]
    entries = [_observer_runtime_state_entry(heartbeat, now=now) for heartbeat in heartbeats]
    active_runtime_names = {
        display(item.get("runtime_name")) for item in entries if item["active"]
    }
    if not active_runtime_names:
        return entries
    return [
        item
        for item in entries
        if not (
            display(item.get("runtime_name")) in active_runtime_names
            and item["lagging"]
            and not item["stuck"]
            and not item["active"]
        )
    ]


def _observer_runtime_state_entry(
    heartbeat: Any,
    *,
    now: datetime,
) -> dict[str, Any]:
    raw_status = (
        display(getattr(heartbeat, "status", None), "unknown")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )
    last_seen_at = getattr(heartbeat, "last_seen_at", None)
    seconds_since_update = seconds_since_datetime(last_seen_at, now=now)
    stale = (
        raw_status in {"running", "idle"}
        and seconds_since_update >= _OBSERVER_RUNTIME_STALE_AFTER_SECONDS
    )
    failed = raw_status == "failed"
    active = raw_status in {"running", "idle"} and not stale
    status = "Stale" if stale else _observer_runtime_status_label(raw_status)
    return {
        "runtime_name": display(getattr(heartbeat, "runtime_name", None)),
        "worker_id": display(getattr(heartbeat, "worker_id", None)),
        "status": status,
        "last_seen_at": (
            format_datetime_utc(last_seen_at.astimezone(timezone.utc))
            if isinstance(last_seen_at, datetime)
            else "-"
        ),
        "seconds_since_update": round(seconds_since_update, 3),
        "processed_events": int(getattr(heartbeat, "processed_events", 0) or 0),
        "idle_cycles": int(getattr(heartbeat, "idle_cycles", 0) or 0),
        "subscription_count": int(
            getattr(heartbeat, "subscription_count", 0) or 0
        ),
        "active": active,
        "lagging": stale,
        "stuck": failed,
        "tone": "danger"
        if failed
        else "warning"
        if stale
        else "success"
        if active
        else "neutral",
    }


def _observer_runtime_status_label(status: str) -> str:
    return {
        "running": "Running",
        "idle": "Idle",
        "completed": "Completed",
        "rebuilt": "Rebuilt",
        "stopped": "Stopped",
        "failed": "Failed",
    }.get(status, status.replace("_", " ").title() or "Unknown")
