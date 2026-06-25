from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
)
from crxzipple.modules.operations.application.read_models.tool_metric_values import (
    duration_label,
)


def provider_metric_bucket() -> dict[str, Any]:
    return {
        "configured_capacity": 0,
        "configured_limit_entries": set(),
        "process_limits": set(),
        "runtime_keys": set(),
        "active": 0.0,
        "waiting": 0.0,
        "wait_count": 0,
        "total_wait_seconds": 0.0,
        "max_wait_seconds": 0.0,
        "sources": set(),
    }


def provider_limit_row(
    provider_key: str,
    bucket: dict[str, Any],
) -> OperationsTableRowModel:
    configured_limit_entries = {
        (str(scope), int_value(limit))
        for scope, limit in bucket.get("configured_limit_entries", set())
        if int_value(limit) > 0
    }
    configured_capacity = max(int_value(bucket.get("configured_capacity")), 0)
    active = max(int(round(float_value(bucket.get("active")))), 0)
    waiting = max(int(round(float_value(bucket.get("waiting")))), 0)
    wait_count = max(int_value(bucket.get("wait_count")), 0)
    total_wait = float_value(bucket.get("total_wait_seconds"))
    max_wait = float_value(bucket.get("max_wait_seconds"))
    avg_wait = total_wait / wait_count if wait_count else 0.0
    state, tone = provider_limit_state(
        active=active,
        waiting=waiting,
        has_config_drift=len(bucket.get("process_limits", set())) > 1,
    )
    sources = sorted(str(item) for item in bucket.get("sources", set()) if item)
    return OperationsTableRowModel(
        id=provider_key,
        cells={
            "provider": provider_label(provider_key),
            "provider_key": provider_key,
            "state": state,
            "limit": provider_limit_label(configured_limit_entries),
            "capacity": (
                f"{active}/{configured_capacity}"
                if configured_capacity
                else f"{active}/-"
            ),
            "active": str(active),
            "waiting": str(waiting),
            "runtimes": str(len(bucket.get("runtime_keys", set()))),
            "wait_count": str(wait_count),
            "avg_wait": seconds_label(avg_wait),
            "max_wait": seconds_label(max_wait),
            "total_wait": seconds_label(total_wait),
            "sources": join_values(tuple(sources)),
        },
        status=state,
        tone=tone,
    )


def provider_limit_state(
    *,
    active: int,
    waiting: int,
    has_config_drift: bool = False,
) -> tuple[str, str]:
    if waiting > 0:
        return "Waiting", "warning"
    if has_config_drift:
        return "Config Drift", "warning"
    if active > 0:
        return "Active", "info"
    return "Ready", "success"


def provider_label(provider_key: str) -> str:
    if provider_key.startswith("provider:"):
        return provider_key.removeprefix("provider:")
    if provider_key.startswith("openapi:"):
        return f"openapi / {provider_key.removeprefix('openapi:')}"
    if provider_key.startswith("mcp:"):
        return f"mcp / {provider_key.removeprefix('mcp:')}"
    return provider_key


def provider_limit_label(limit_entries: set[tuple[str, int]]) -> str:
    if not limit_entries:
        return "-"
    if len(limit_entries) == 1:
        scope, limit = next(iter(limit_entries))
        return f"{limit}/{scope}"
    return "mixed"


def columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(
        OperationsTableColumnModel(key=key, label=label) for key, label in items
    )


def optional_str(value: object | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def int_value(value: object | None) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def float_value(value: object | None) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def seconds_label(seconds: float) -> str:
    value = max(float(seconds), 0.0)
    if value <= 0:
        return "0s"
    if value < 1:
        return f"{int(round(value * 1000))}ms"
    if value < 60:
        return f"{value:.1f}s" if value < 10 else f"{int(round(value))}s"
    return duration_label(int(round(value)))


def join_values(values: tuple[str, ...] | list[str]) -> str:
    normalized = [value.strip() for value in values if value and value.strip()]
    return ", ".join(normalized) if normalized else "-"
