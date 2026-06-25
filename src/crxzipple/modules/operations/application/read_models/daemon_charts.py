from __future__ import annotations

from collections import Counter
from typing import Any

from crxzipple.modules.operations.application.read_models.daemon_common import (
    _bool,
    _status_label,
    _text,
)
from crxzipple.modules.operations.application.read_models.daemon_status_helpers import (
    _count_status,
    _tone_for_status,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsChartSectionModel,
    OperationsChartSegmentModel,
)


def daemon_process_health(
    process_rows: tuple[dict[str, Any], ...],
) -> OperationsChartSectionModel:
    counts = Counter(_text(item.get("status"), "unknown").lower() for item in process_rows)
    segments = tuple(
        OperationsChartSegmentModel(key, _status_label(key), count, _tone_for_status(key))
        for key, count in sorted(counts.items())
    )
    return OperationsChartSectionModel(
        id="process_health",
        title="Process Health",
        kind="donut",
        total=len(process_rows),
        segments=segments,
    )


def daemon_state_summary(
    instances: tuple[dict[str, Any], ...],
) -> OperationsChartSectionModel:
    stopped = _count_status(instances, "stopped")
    failed = _count_status(instances, "failed")
    degraded = _count_status(instances, "degraded")
    drift = sum(1 for item in instances if _bool(item.get("env_drift_detected")))
    segments = (
        OperationsChartSegmentModel("stopped", "Stopped", stopped, "neutral"),
        OperationsChartSegmentModel("failed", "Failed", failed, "danger"),
        OperationsChartSegmentModel("degraded", "Degraded", degraded, "warning"),
        OperationsChartSegmentModel("env_drift", "Env Drift", drift, "warning" if drift else "success"),
    )
    return OperationsChartSectionModel(
        id="restart_summary",
        title="State Changes / Drift",
        kind="bar",
        total=stopped + failed + degraded + drift,
        segments=segments,
    )


def daemon_lease_health(
    leases: tuple[dict[str, Any], ...],
) -> OperationsChartSectionModel:
    counts = Counter(_text(item.get("status"), "unknown").lower() for item in leases)
    ordered = ("active", "expired", "released", "unknown")
    segments = tuple(
        OperationsChartSegmentModel(
            key,
            _status_label(key),
            counts[key],
            _tone_for_status(key),
        )
        for key in ordered
        if counts[key]
    )
    return OperationsChartSectionModel(
        id="lease_health",
        title="Lease Health",
        kind="donut",
        total=len(leases),
        segments=segments,
    )
