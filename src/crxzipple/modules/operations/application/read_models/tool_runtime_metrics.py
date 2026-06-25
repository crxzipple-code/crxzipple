from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.models import MetricCardModel


def runtime_default_metric_cards(
    runtime_bootstrap_config: Any | None,
) -> tuple[MetricCardModel, ...]:
    max_in_flight = _runtime_int(runtime_bootstrap_config, "tool_worker_max_in_flight")
    default_concurrency = _runtime_int(
        runtime_bootstrap_config,
        "tool_worker_default_run_concurrency",
    )
    image_concurrency = _runtime_int(
        runtime_bootstrap_config,
        "tool_worker_image_run_concurrency",
    )
    shared_state_concurrency = _runtime_int(
        runtime_bootstrap_config,
        "tool_worker_shared_state_run_concurrency",
    )
    max_attempts = _runtime_int(runtime_bootstrap_config, "tool_run_max_attempts")
    lease_seconds = _runtime_float(runtime_bootstrap_config, "tool_run_lease_seconds")
    heartbeat_seconds = _runtime_float(runtime_bootstrap_config, "tool_run_heartbeat_seconds")
    remote_limit = _runtime_int(
        runtime_bootstrap_config,
        "tool_remote_default_max_concurrency",
    )
    if (
        max_in_flight is None
        and default_concurrency is None
        and image_concurrency is None
        and shared_state_concurrency is None
        and max_attempts is None
        and lease_seconds is None
        and heartbeat_seconds is None
        and remote_limit is None
    ):
        return ()
    return (
        MetricCardModel(
            id="worker_policy",
            label="Worker Policy",
            value=str(max_in_flight) if max_in_flight is not None else "-",
            delta=_worker_policy_delta(
                default_concurrency,
                image_concurrency,
                shared_state_concurrency,
            ),
            tone="info",
        ),
        MetricCardModel(
            id="retry_policy",
            label="Retry Policy",
            value=_retry_policy_value(
                max_attempts=max_attempts,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
            ),
            delta=f"remote {_display_int(remote_limit)}",
            tone="info",
        ),
    )


def _runtime_int(runtime_bootstrap_config: Any | None, name: str) -> int | None:
    value = getattr(runtime_bootstrap_config, name, None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _runtime_float(runtime_bootstrap_config: Any | None, name: str) -> float | None:
    value = getattr(runtime_bootstrap_config, name, None)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _display_int(value: int | None) -> str:
    return str(value) if value is not None else "-"


def _worker_policy_delta(
    default_concurrency: int | None,
    image_concurrency: int | None,
    shared_state_concurrency: int | None,
) -> str:
    return (
        f"default {_display_int(default_concurrency)} / "
        f"image {_display_int(image_concurrency)} / "
        f"shared {_display_int(shared_state_concurrency)}"
    )


def _retry_policy_value(
    *,
    max_attempts: int | None,
    lease_seconds: float | None,
    heartbeat_seconds: float | None,
) -> str:
    if max_attempts is None and lease_seconds is None and heartbeat_seconds is None:
        return "-"
    return (
        f"{_display_int(max_attempts)}x / "
        f"{_duration_value(lease_seconds)} / "
        f"{_duration_value(heartbeat_seconds)}"
    )


def _duration_value(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    return _duration_label(round(seconds))


def _duration_label(seconds: int) -> str:
    seconds = max(seconds, 0)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"
