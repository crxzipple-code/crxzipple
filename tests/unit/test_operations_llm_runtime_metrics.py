from __future__ import annotations

from crxzipple.modules.operations.application.read_models.llm_runtime_metrics import (
    LLM_LIMITER_ACTIVE,
    LLM_LIMITER_PREFIX,
    LLM_LIMITER_WAIT_SECONDS,
    LLM_LIMITER_WAITERS,
    combined_timing,
    limiter_waiter_count,
    metric_values_by_label,
    runtime_snapshot,
    sum_metric_values,
    timing_values_by_label,
)


class _RuntimeMetrics:
    def __init__(self, snapshot: dict[str, object]) -> None:
        self.snapshot_payload = snapshot
        self.prefixes: tuple[str, ...] | None = None

    def snapshot(self, *, prefixes: tuple[str, ...]) -> dict[str, object]:
        self.prefixes = prefixes
        return self.snapshot_payload


def test_runtime_snapshot_reads_llm_limiter_prefix() -> None:
    metrics = _RuntimeMetrics({"gauges": [], "counters": [], "timings": []})

    snapshot = runtime_snapshot(metrics)

    assert snapshot == {"gauges": [], "counters": [], "timings": []}
    assert metrics.prefixes == (LLM_LIMITER_PREFIX,)


def test_limiter_metric_helpers_aggregate_values_by_label() -> None:
    snapshot = {
        "gauges": [
            {"name": LLM_LIMITER_ACTIVE, "value": 2, "labels": {"llm_id": "a"}},
            {"name": LLM_LIMITER_ACTIVE, "value": "3", "labels": {"llm_id": "a"}},
            {"name": LLM_LIMITER_WAITERS, "value": 4, "labels": {"llm_id": "b"}},
        ],
        "timings": [
            {
                "name": LLM_LIMITER_WAIT_SECONDS,
                "count": 2,
                "total_seconds": 6,
                "max_seconds": 4,
                "labels": {"llm_id": "a"},
            },
            {
                "name": LLM_LIMITER_WAIT_SECONDS,
                "count": 1,
                "total_seconds": 3,
                "max_seconds": 3,
                "labels": {"llm_id": "a"},
            },
        ],
    }

    assert sum_metric_values(snapshot, section="gauges", name=LLM_LIMITER_ACTIVE) == 5
    assert limiter_waiter_count(snapshot) == 4
    assert metric_values_by_label(
        snapshot,
        section="gauges",
        name=LLM_LIMITER_ACTIVE,
        label="llm_id",
    ) == {"a": 5}
    assert timing_values_by_label(
        snapshot,
        name=LLM_LIMITER_WAIT_SECONDS,
        label="llm_id",
    ) == {"a": {"count": 3.0, "avg_seconds": 3.0, "max_seconds": 4.0}}
    assert combined_timing(snapshot, LLM_LIMITER_WAIT_SECONDS) == {
        "count": 3.0,
        "avg_seconds": 3.0,
        "max_seconds": 4.0,
    }
