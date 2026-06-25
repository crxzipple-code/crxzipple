from __future__ import annotations

from collections import Counter
from typing import Any

from crxzipple.modules.operations.application.read_models.memory_common import (
    backend_tone,
    index_status,
    record_resolved,
    watch_failures,
)
from crxzipple.modules.operations.application.read_models.memory_models import (
    MemoryContextRecord,
)
from crxzipple.modules.operations.application.read_models.memory_values import (
    status_label,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsChartSectionModel,
    OperationsChartSegmentModel,
)


def index_health(
    records: tuple[MemoryContextRecord, ...],
    watch_metrics: Any | None,
) -> OperationsChartSectionModel:
    counts = Counter(index_status(record) for record in records)
    failures = watch_failures(watch_metrics)
    segments = [
        OperationsChartSegmentModel("ready", "Ready", counts["Ready"], "success"),
        OperationsChartSegmentModel("dirty", "Dirty", counts["Dirty"], "warning"),
        OperationsChartSegmentModel(
            "missing_index",
            "Missing Index",
            counts["Missing Index"],
            "neutral",
        ),
        OperationsChartSegmentModel(
            "no_context",
            "No Context",
            counts["No Context"],
            "warning",
        ),
    ]
    if failures:
        segments.append(
            OperationsChartSegmentModel(
                "watch_failures",
                "Watch Failures",
                failures,
                "danger",
            ),
        )
    return OperationsChartSectionModel(
        "index_health",
        "Index Health",
        "donut",
        sum(item.value for item in segments),
        tuple(item for item in segments if item.value),
    )


def retrieval_performance(
    records: tuple[MemoryContextRecord, ...],
    search_hits: tuple[Any, ...],
    query: str,
) -> OperationsChartSectionModel:
    if query:
        segments = (
            OperationsChartSegmentModel(
                "hits",
                "Hits",
                len(search_hits),
                "success" if search_hits else "neutral",
            ),
            OperationsChartSegmentModel(
                "misses",
                "Misses",
                0 if search_hits else 1,
                "warning" if not search_hits else "neutral",
            ),
        )
        return OperationsChartSectionModel(
            "retrieval_performance",
            "Current Retrieval Trace",
            "donut",
            max(len(search_hits), 1),
            segments,
        )
    counts = Counter(
        record.retrieval_backend or "unknown"
        for record in records
        if record_resolved(record)
    )
    return OperationsChartSectionModel(
        "retrieval_performance",
        "Retrieval Backend Mix",
        "donut",
        sum(counts.values()),
        tuple(
            OperationsChartSegmentModel(key, status_label(key), value, backend_tone(key))
            for key, value in sorted(counts.items())
        ),
    )
