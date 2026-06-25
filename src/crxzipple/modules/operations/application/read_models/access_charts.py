from __future__ import annotations

from collections import Counter
from typing import Any

from crxzipple.modules.access.application.events import (
    ACCESS_CREDENTIAL_RESOLVE_FAILED_EVENT,
    ACCESS_CREDENTIAL_RESOLVE_SUCCEEDED_EVENT,
)
from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.access_common import (
    kind_label,
    kind_tone,
    status_label,
    tone_for_status,
)
from crxzipple.modules.operations.application.read_models.access_target_projection import (
    target_metadata,
    target_worst_status,
)
from crxzipple.modules.operations.application.read_models.access_values import (
    int_value,
    text,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsChartSectionModel,
    OperationsChartSegmentModel,
)


def credential_health(
    targets: tuple[dict[str, Any], ...],
) -> OperationsChartSectionModel:
    counts = Counter(target_worst_status(target) for target in targets)
    segments = tuple(
        OperationsChartSegmentModel(
            key,
            status_label(key),
            counts[key],
            tone_for_status(key),
        )
        for key in ("ready", "setup_needed", "unsupported", "waiting_user", "expired")
        if counts[key]
    )
    return OperationsChartSectionModel(
        "credential_health",
        "Credential Health",
        "donut",
        len(targets),
        segments,
    )


def credentials_by_kind(
    targets: tuple[dict[str, Any], ...],
) -> OperationsChartSectionModel:
    counts = Counter(
        text(target_metadata(target).get("asset_kind"), "unknown")
        for target in targets
    )
    segments = tuple(
        OperationsChartSegmentModel(kind, kind_label(kind), count, kind_tone(kind))
        for kind, count in sorted(counts.items())
    )
    return OperationsChartSectionModel(
        "credentials_by_kind",
        "Credentials by Kind",
        "donut",
        len(targets),
        segments,
    )


def auth_success_rate(
    events: tuple[OperationsObservedEvent, ...],
    *,
    event_buckets: tuple[dict[str, Any], ...] = (),
) -> OperationsChartSectionModel:
    succeeded, failed = access_resolve_counts(events, event_buckets=event_buckets)
    total = succeeded + failed
    return OperationsChartSectionModel(
        "auth_success_rate",
        "Credential Resolve Success",
        "donut",
        total,
        tuple(
            segment
            for segment in (
                OperationsChartSegmentModel(
                    "succeeded",
                    "Succeeded",
                    succeeded,
                    "success",
                ),
                OperationsChartSegmentModel(
                    "failed",
                    "Failed",
                    failed,
                    "danger" if failed else "success",
                ),
            )
            if segment.value
        ),
    )


def access_resolve_counts(
    events: tuple[OperationsObservedEvent, ...],
    *,
    event_buckets: tuple[dict[str, Any], ...] = (),
) -> tuple[int, int]:
    if event_buckets:
        succeeded = sum(
            int_value(bucket.get("count"), 0)
            for bucket in event_buckets
            if bucket.get("event_name") == ACCESS_CREDENTIAL_RESOLVE_SUCCEEDED_EVENT
        )
        failed = sum(
            int_value(bucket.get("count"), 0)
            for bucket in event_buckets
            if bucket.get("event_name") == ACCESS_CREDENTIAL_RESOLVE_FAILED_EVENT
        )
        return succeeded, failed
    succeeded = sum(
        1
        for event in events
        if event.event_name == ACCESS_CREDENTIAL_RESOLVE_SUCCEEDED_EVENT
    )
    failed = sum(
        1
        for event in events
        if event.event_name == ACCESS_CREDENTIAL_RESOLVE_FAILED_EVENT
    )
    return succeeded, failed


def failed_access_event_count(
    events: tuple[OperationsObservedEvent, ...],
    *,
    event_buckets: tuple[dict[str, Any], ...],
) -> int:
    if event_buckets:
        return sum(
            int_value(bucket.get("count"), 0)
            for bucket in event_buckets
            if bucket.get("level") == "error"
            or bucket.get("status") in {"failed", "error"}
        )
    return sum(
        1
        for item in events
        if item.level == "error" or item.status in {"failed", "error"}
    )
