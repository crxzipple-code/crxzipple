from __future__ import annotations

from collections import Counter
from typing import Any

from crxzipple.modules.operations.application.read_models.channels_event_helpers import (
    event_direction,
    failure_reason,
)
from crxzipple.modules.operations.application.read_models.channels_formatting import (
    id_for,
    int_value,
    status_label,
    text,
    tone_for_status,
)
from crxzipple.modules.operations.application.read_models.channels_models import (
    ChannelEventRecord,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsChartSectionModel,
    OperationsChartSegmentModel,
)


def message_flow(
    events: tuple[ChannelEventRecord, ...],
    interactions: tuple[Any, ...],
) -> OperationsChartSectionModel:
    counts = Counter(event_direction(event) for event in events)
    for interaction in interactions:
        counts["Intake"] += 1
    return chart(
        "message_flow",
        "Message Flow",
        "donut",
        counts,
        tone_by_label={
            "Intake": "info",
            "Observe": "info",
            "Live": "success",
            "Broadcast": "info",
            "Control": "warning",
            "Dead Letter": "danger",
            "Other": "neutral",
        },
    )


def delivery_trend(
    events: tuple[ChannelEventRecord, ...],
    runtime_records: tuple[dict[str, Any], ...],
    interactions: tuple[Any, ...],
    *,
    event_buckets: tuple[dict[str, Any], ...] = (),
) -> OperationsChartSectionModel:
    if event_buckets:
        counts = Counter()
        for bucket in event_buckets:
            counts[status_label(text(bucket.get("status"), "observed"))] += int_value(
                bucket.get("count"),
            )
    elif events:
        counts = Counter(status_label(event.status) for event in events)
    elif interactions:
        counts = Counter(
            status_label(text(getattr(interaction, "status", None), "received"))
            for interaction in interactions
        )
    else:
        counts = Counter(status_label(text(row.get("status"))) for row in runtime_records)
    return chart(
        "delivery_trend",
        "Runtime / Delivery Status (24h)" if event_buckets else "Runtime / Delivery Status",
        "bar",
        counts,
    )


def top_channels(
    events: tuple[ChannelEventRecord, ...],
    runtime_records: tuple[dict[str, Any], ...],
    interactions: tuple[Any, ...],
) -> OperationsChartSectionModel:
    counts = Counter(
        event.channel_type or "unknown"
        for event in events
        if event.channel_type or event.topic.startswith("channel.")
    )
    for interaction in interactions:
        channel_type = text(getattr(interaction, "channel_type", None), "")
        if channel_type:
            counts[channel_type] += 1
    if not counts:
        counts = Counter(text(row.get("channel_type"), "unknown") for row in runtime_records)
    return chart("top_channels", "Top Channels", "bar", counts)


def failures_by_category(
    dead_letters: tuple[ChannelEventRecord, ...],
) -> OperationsChartSectionModel:
    counts = Counter(failure_reason(event) for event in dead_letters)
    return chart(
        "failures_by_category",
        "Failures by Category",
        "bar",
        counts,
        default_tone="danger",
    )


def chart(
    section_id: str,
    title: str,
    kind: str,
    counts: Counter[str],
    *,
    default_tone: str = "neutral",
    tone_by_label: dict[str, str] | None = None,
) -> OperationsChartSectionModel:
    tone_by_label = tone_by_label or {}
    segments = tuple(
        OperationsChartSegmentModel(
            id=id_for(label),
            label=label,
            value=count,
            tone=tone_by_label.get(label, tone_for_status(label, default=default_tone)),
        )
        for label, count in counts.most_common()
        if count > 0
    )
    return OperationsChartSectionModel(
        id=section_id,
        title=title,
        kind=kind,
        total=sum(segment.value for segment in segments),
        segments=segments,
    )
