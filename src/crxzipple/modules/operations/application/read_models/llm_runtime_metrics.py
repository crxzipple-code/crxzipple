from __future__ import annotations

from typing import Any

LLM_LIMITER_PREFIX = "llm.profile_limiter."
LLM_LIMITER_ACTIVE = f"{LLM_LIMITER_PREFIX}active"
LLM_LIMITER_WAITERS = f"{LLM_LIMITER_PREFIX}waiters"
LLM_LIMITER_WAIT_SECONDS = f"{LLM_LIMITER_PREFIX}wait_seconds"

_EMPTY_RUNTIME_SNAPSHOT = {"counters": [], "gauges": [], "timings": []}


def runtime_snapshot(runtime_metrics: Any | None) -> dict[str, object]:
    if runtime_metrics is None or not hasattr(runtime_metrics, "snapshot"):
        return dict(_EMPTY_RUNTIME_SNAPSHOT)
    try:
        snapshot = runtime_metrics.snapshot(prefixes=(LLM_LIMITER_PREFIX,))
    except Exception:
        return dict(_EMPTY_RUNTIME_SNAPSHOT)
    return snapshot if isinstance(snapshot, dict) else dict(_EMPTY_RUNTIME_SNAPSHOT)


def sum_metric_values(
    runtime_snapshot: dict[str, object],
    *,
    section: str,
    name: str,
) -> float:
    total = 0.0
    raw_items = runtime_snapshot.get(section)
    if not isinstance(raw_items, list):
        return total
    for item in raw_items:
        if not isinstance(item, dict) or item.get("name") != name:
            continue
        total += _float(item.get("value"))
    return total


def metric_values_by_label(
    runtime_snapshot: dict[str, object],
    *,
    section: str,
    name: str,
    label: str,
) -> dict[str, float]:
    values: dict[str, float] = {}
    raw_items = runtime_snapshot.get(section)
    if not isinstance(raw_items, list):
        return values
    for item in raw_items:
        if not isinstance(item, dict) or item.get("name") != name:
            continue
        labels = item.get("labels")
        if not isinstance(labels, dict):
            continue
        key = _text(labels.get(label))
        if key is None:
            continue
        values[key] = values.get(key, 0.0) + _float(item.get("value"))
    return values


def timing_values_by_label(
    runtime_snapshot: dict[str, object],
    *,
    name: str,
    label: str,
) -> dict[str, dict[str, float]]:
    values: dict[str, dict[str, float]] = {}
    raw_items = runtime_snapshot.get("timings")
    if not isinstance(raw_items, list):
        return values
    for item in raw_items:
        if not isinstance(item, dict) or item.get("name") != name:
            continue
        labels = item.get("labels")
        if not isinstance(labels, dict):
            continue
        key = _text(labels.get(label))
        if key is None:
            continue
        bucket = values.setdefault(
            key,
            {"count": 0.0, "total_seconds": 0.0, "max_seconds": 0.0},
        )
        item_count = _float(item.get("count"))
        bucket["count"] += item_count
        bucket["total_seconds"] += _float(item.get("total_seconds"))
        bucket["max_seconds"] = max(
            bucket["max_seconds"],
            _float(item.get("max_seconds")),
        )
    return {
        key: {
            "count": bucket["count"],
            "avg_seconds": (
                bucket["total_seconds"] / bucket["count"]
                if bucket["count"]
                else 0.0
            ),
            "max_seconds": bucket["max_seconds"],
        }
        for key, bucket in values.items()
    }


def combined_timing(
    runtime_snapshot: dict[str, object],
    name: str,
) -> dict[str, float]:
    count = 0
    total_seconds = 0.0
    max_seconds = 0.0
    raw_items = runtime_snapshot.get("timings")
    if not isinstance(raw_items, list):
        return {"count": 0, "avg_seconds": 0.0, "max_seconds": 0.0}
    for item in raw_items:
        if not isinstance(item, dict) or item.get("name") != name:
            continue
        item_count = int(_float(item.get("count")))
        count += item_count
        total_seconds += _float(item.get("total_seconds"))
        max_seconds = max(max_seconds, _float(item.get("max_seconds")))
    return {
        "count": float(count),
        "avg_seconds": total_seconds / count if count else 0.0,
        "max_seconds": max_seconds,
    }


def limiter_waiter_count(runtime_snapshot: dict[str, object]) -> int:
    return int(
        sum_metric_values(
            runtime_snapshot,
            section="gauges",
            name=LLM_LIMITER_WAITERS,
        ),
    )


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0
