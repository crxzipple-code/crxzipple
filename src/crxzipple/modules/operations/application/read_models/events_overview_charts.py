from __future__ import annotations

from collections import Counter
from typing import Any

from crxzipple.modules.operations.application.read_models.events_overview_helpers import (
    display,
    int_value,
    kind_tone,
    slug,
    status_label,
    status_tone,
    tone_for_index,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsChartSectionModel,
    OperationsChartSegmentModel,
)


def events_over_time(
    events: list[dict[str, Any]],
) -> OperationsChartSectionModel:
    counts = Counter(display(item["kind"]) for item in events)
    segments = tuple(
        OperationsChartSegmentModel(
            id=slug(kind),
            label=kind.title(),
            value=count,
            tone=kind_tone(kind),
        )
        for kind, count in counts.most_common()
    )
    return OperationsChartSectionModel(
        id="events_over_time",
        title="Events by Kind",
        kind="bar",
        total=len(events),
        segments=segments,
    )


def events_by_surface(
    events: list[dict[str, Any]],
) -> OperationsChartSectionModel:
    counts: Counter[str] = Counter()
    for item in events:
        surfaces = item.get("surface_ids")
        if isinstance(surfaces, tuple) and surfaces:
            counts.update(surfaces)
        else:
            counts[display(item.get("owner"))] += 1
    segments = tuple(
        OperationsChartSegmentModel(
            id=slug(label),
            label=label,
            value=count,
            tone=tone_for_index(index),
        )
        for index, (label, count) in enumerate(counts.most_common(8))
    )
    return OperationsChartSectionModel(
        id="events_by_surface",
        title="Events by Surface",
        kind="donut",
        total=sum(counts.values()),
        segments=segments,
    )


def events_over_time_from_buckets(
    buckets: tuple[dict[str, Any], ...],
) -> OperationsChartSectionModel:
    counts = Counter()
    for bucket in buckets:
        status = display(bucket.get("status"), "observed")
        counts[status] += int_value(bucket.get("count"))
    segments = tuple(
        OperationsChartSegmentModel(
            id=slug(status),
            label=status_label(status),
            value=count,
            tone=status_tone(status),
        )
        for status, count in counts.most_common()
        if count > 0
    )
    return OperationsChartSectionModel(
        id="events_over_time",
        title="Events by Status (24h)",
        kind="bar",
        total=sum(item.value for item in segments),
        segments=segments,
    )


def events_by_surface_from_buckets(
    buckets: tuple[dict[str, Any], ...],
) -> OperationsChartSectionModel:
    counts = Counter()
    for bucket in buckets:
        owner = display(bucket.get("owner") or bucket.get("module"), "unknown")
        counts[owner] += int_value(bucket.get("count"))
    segments = tuple(
        OperationsChartSegmentModel(
            id=slug(label),
            label=label,
            value=count,
            tone=tone_for_index(index),
        )
        for index, (label, count) in enumerate(counts.most_common(8))
        if count > 0
    )
    return OperationsChartSectionModel(
        id="events_by_surface",
        title="Events by Owner (24h)",
        kind="donut",
        total=sum(item.value for item in segments),
        segments=segments,
    )
