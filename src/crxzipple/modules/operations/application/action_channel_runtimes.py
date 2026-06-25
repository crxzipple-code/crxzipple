from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.operations.application.action_results import (
    ChannelRuntimePruneItem,
    ChannelRuntimePruneResult,
)
from crxzipple.shared.time import coerce_utc_datetime

DEFAULT_STALE_CHANNEL_RUNTIME_AFTER_SECONDS = 300.0


def prune_stale_channel_runtimes(
    channel_runtime_manager: Any,
    *,
    runtime_id: str | None = None,
    channel_type: str | None = None,
    stale_after_seconds: float = DEFAULT_STALE_CHANNEL_RUNTIME_AFTER_SECONDS,
    dry_run: bool = False,
    reason: str | None = None,
) -> ChannelRuntimePruneResult:
    normalized_runtime_id = _optional_text(runtime_id)
    normalized_channel_type = _optional_text(channel_type)
    runtimes = channel_runtime_manager.list_runtimes(
        channel_type=normalized_channel_type,
    )
    now = datetime.now(timezone.utc)
    items: list[ChannelRuntimePruneItem] = []
    pruned_count = 0
    skipped_count = 0

    for runtime in runtimes:
        current_runtime_id = str(getattr(runtime, "runtime_id", "") or "").strip()
        if normalized_runtime_id is not None and current_runtime_id != normalized_runtime_id:
            continue
        heartbeat_age = _seconds_since(
            getattr(runtime, "last_heartbeat_at", None),
            now=now,
        )
        is_stale = heartbeat_age > max(float(stale_after_seconds), 0.0)
        status = "stale" if is_stale else _runtime_status(runtime)
        account_bindings = channel_runtime_manager.list_account_bindings(
            runtime_id=current_runtime_id,
        )
        connection_bindings = channel_runtime_manager.list_connection_bindings(
            runtime_id=current_runtime_id,
        )
        if is_stale:
            if not dry_run:
                channel_runtime_manager.unregister_runtime(current_runtime_id)
            pruned_count += 1
        else:
            skipped_count += 1
        items.append(
            ChannelRuntimePruneItem(
                runtime_id=current_runtime_id,
                channel_type=str(getattr(runtime, "channel_type", "") or ""),
                status=status,
                heartbeat_age_seconds=heartbeat_age,
                account_bindings_removed=len(account_bindings) if is_stale else 0,
                connection_bindings_removed=len(connection_bindings) if is_stale else 0,
                pruned=is_stale,
            )
        )

    return ChannelRuntimePruneResult(
        matched_count=len(items),
        pruned_count=pruned_count,
        skipped_count=skipped_count,
        dry_run=dry_run,
        reason=_optional_text(reason),
        items=tuple(items),
    )


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _seconds_since(value: Any, *, now: datetime) -> float:
    if value is None:
        return float("inf")
    try:
        resolved = coerce_utc_datetime(value)
    except (TypeError, ValueError):
        return float("inf")
    return max(0.0, (now - resolved).total_seconds())


def _runtime_status(runtime: Any) -> str:
    raw = str(getattr(runtime, "status", "") or "online").strip().lower()
    if raw in {"online", "ready", "healthy"}:
        return "online"
    if raw in {"offline", "stopped"}:
        return "offline"
    if raw in {"error", "failed"}:
        return "error"
    return raw or "unknown"
