from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.tool_provider_limit_rows import (
    int_value,
    optional_str,
)

TOOL_PROVIDER_LIMITER_PREFIX = "tool.remote_provider_limiter."
TOOL_PROVIDER_LIMITER_ACTIVE = f"{TOOL_PROVIDER_LIMITER_PREFIX}active"
TOOL_PROVIDER_LIMITER_WAITERS = f"{TOOL_PROVIDER_LIMITER_PREFIX}waiters"
TOOL_PROVIDER_LIMITER_WAIT_SECONDS = f"{TOOL_PROVIDER_LIMITER_PREFIX}wait_seconds"


def provider_limiter_configurations(
    snapshot: dict[str, Any],
) -> tuple[tuple[str, dict[str, Any]], ...]:
    registrations = snapshot.get("registrations")
    if not isinstance(registrations, list):
        return ()
    grouped: dict[str, dict[str, Any]] = {}
    for registration in registrations:
        if not isinstance(registration, dict):
            continue
        runtime_key = optional_str(registration.get("runtime_key"))
        concurrency_key = optional_str(registration.get("concurrency_key"))
        provider_key = concurrency_key or runtime_key
        if provider_key is None:
            continue
        limit = registration.get("max_concurrency")
        bucket = grouped.setdefault(provider_key, {"runtime_keys": set(), "limit": None})
        if runtime_key is not None:
            bucket["runtime_keys"].add(runtime_key)
        if limit is not None:
            bucket["limit"] = max(
                int_value(bucket.get("limit")),
                int_value(limit),
            )
    return tuple(sorted(grouped.items()))


def metric_items(snapshot: dict[str, Any], group: str) -> tuple[dict[str, Any], ...]:
    items = snapshot.get(group)
    if not isinstance(items, list):
        return ()
    return tuple(item for item in items if isinstance(item, dict))


def metric_provider_key(item: dict[str, Any]) -> str | None:
    labels = item.get("labels")
    if not isinstance(labels, dict):
        return None
    return optional_str(labels.get("provider_key"))
