from __future__ import annotations

from dataclasses import dataclass
import os


DEFAULT_TOOL_DETAILS_MAX_CHARS = 131_072
DEFAULT_TOOL_REMOTE_DEFAULT_MAX_CONCURRENCY = 16
DEFAULT_TOOL_RUN_MAX_ATTEMPTS = 3
DEFAULT_TOOL_RUN_LEASE_SECONDS = 30
DEFAULT_TOOL_RUN_HEARTBEAT_SECONDS = 5.0
DEFAULT_TOOL_WORKER_MAX_IN_FLIGHT = 4
DEFAULT_TOOL_WORKER_SHARED_STATE_RUN_CONCURRENCY = 1


@dataclass(frozen=True, slots=True)
class ToolWorkerConcurrencySettings:
    max_in_flight: int = DEFAULT_TOOL_WORKER_MAX_IN_FLIGHT
    default_run_concurrency: int = DEFAULT_TOOL_WORKER_MAX_IN_FLIGHT
    image_run_concurrency: int = DEFAULT_TOOL_WORKER_MAX_IN_FLIGHT
    shared_state_run_concurrency: int = DEFAULT_TOOL_WORKER_SHARED_STATE_RUN_CONCURRENCY


def load_tool_details_max_chars() -> int:
    return _positive_int_env(
        "APP_TOOL_DETAILS_MAX_CHARS",
        DEFAULT_TOOL_DETAILS_MAX_CHARS,
    )


def load_tool_remote_default_max_concurrency() -> int:
    return _positive_int_env(
        "APP_TOOL_REMOTE_DEFAULT_MAX_CONCURRENCY",
        DEFAULT_TOOL_REMOTE_DEFAULT_MAX_CONCURRENCY,
    )


def load_tool_run_max_attempts() -> int:
    return _positive_int_env(
        "APP_TOOL_RUN_MAX_ATTEMPTS",
        DEFAULT_TOOL_RUN_MAX_ATTEMPTS,
    )


def load_tool_run_lease_seconds() -> int:
    return _positive_int_env(
        "APP_TOOL_RUN_LEASE_SECONDS",
        DEFAULT_TOOL_RUN_LEASE_SECONDS,
    )


def load_tool_run_heartbeat_seconds() -> float:
    return _positive_float_env(
        "APP_TOOL_RUN_HEARTBEAT_SECONDS",
        DEFAULT_TOOL_RUN_HEARTBEAT_SECONDS,
        minimum=0.1,
    )


def load_tool_worker_concurrency_settings() -> ToolWorkerConcurrencySettings:
    max_in_flight = _positive_int_env(
        "APP_TOOL_WORKER_MAX_IN_FLIGHT",
        DEFAULT_TOOL_WORKER_MAX_IN_FLIGHT,
    )
    return ToolWorkerConcurrencySettings(
        max_in_flight=max_in_flight,
        default_run_concurrency=_positive_int_env(
            "APP_TOOL_WORKER_DEFAULT_RUN_CONCURRENCY",
            max_in_flight,
        ),
        image_run_concurrency=_positive_int_env(
            "APP_TOOL_WORKER_IMAGE_RUN_CONCURRENCY",
            max_in_flight,
        ),
        shared_state_run_concurrency=_positive_int_env(
            "APP_TOOL_WORKER_SHARED_STATE_RUN_CONCURRENCY",
            DEFAULT_TOOL_WORKER_SHARED_STATE_RUN_CONCURRENCY,
        ),
    )


def _positive_int_env(name: str, default: int) -> int:
    return max(int(os.getenv(name, str(default))), 1)


def _positive_float_env(name: str, default: float, *, minimum: float) -> float:
    return max(float(os.getenv(name, str(default))), minimum)
