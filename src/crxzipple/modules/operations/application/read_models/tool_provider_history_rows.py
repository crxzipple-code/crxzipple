from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)
from crxzipple.modules.operations.application.read_models.tool_metric_values import (
    duration_label,
)
from crxzipple.modules.operations.application.read_models.tool_provider_identity import (
    provider_history_label,
)
from crxzipple.shared.time import format_datetime_utc


def provider_history_bucket() -> dict[str, Any]:
    return {
        "tools": set(),
        "runs": 0,
        "active": 0,
        "terminal": 0,
        "succeeded": 0,
        "failures": 0,
        "cancelled": 0,
        "duration_count": 0,
        "total_duration_seconds": 0,
        "max_duration_seconds": 0,
        "active_duration_seconds": 0,
        "last_run": None,
    }


def provider_history_row(
    provider_key: str,
    bucket: dict[str, Any],
) -> OperationsTableRowModel:
    tool_count = len(bucket.get("tools", set()))
    runs = _int_value(bucket.get("runs"))
    active = _int_value(bucket.get("active"))
    terminal = _int_value(bucket.get("terminal"))
    succeeded = _int_value(bucket.get("succeeded"))
    failures = _int_value(bucket.get("failures"))
    duration_count = _int_value(bucket.get("duration_count"))
    total_duration_seconds = _int_value(bucket.get("total_duration_seconds"))
    avg_duration_seconds = (
        total_duration_seconds / duration_count if duration_count else None
    )
    state, tone = _provider_history_state(
        runs=runs,
        active=active,
        failures=failures,
    )
    last_run = bucket.get("last_run")
    return OperationsTableRowModel(
        id=provider_key,
        cells={
            "provider": provider_history_label(provider_key),
            "provider_key": provider_key,
            "state": state,
            "tools": str(tool_count),
            "runs": str(runs),
            "active": str(active),
            "failures": str(failures),
            "success_rate": _percent_label(succeeded, terminal) if terminal else "-",
            "avg_duration": (
                duration_label(int(round(avg_duration_seconds)))
                if avg_duration_seconds is not None
                else "-"
            ),
            "max_duration": (
                duration_label(_int_value(bucket.get("max_duration_seconds")))
                if duration_count
                else "-"
            ),
            "last_run": (
                format_datetime_utc(last_run) if isinstance(last_run, datetime) else "-"
            ),
        },
        status=state,
        tone=tone,
    )


def _provider_history_state(
    *,
    runs: int,
    active: int,
    failures: int,
) -> tuple[str, str]:
    if failures > 0:
        return "Warning", "warning"
    if active > 0:
        return "Active", "info"
    if runs > 0:
        return "Healthy", "success"
    return "Ready", "neutral"


def _int_value(value: object | None) -> int:
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


def _percent_label(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0%"
    return f"{round((numerator / denominator) * 100)}%"
