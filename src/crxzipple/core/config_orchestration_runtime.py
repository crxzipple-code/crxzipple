from __future__ import annotations

import os

from crxzipple.core.config_env import env_flag


DEFAULT_ORCHESTRATION_RUN_LEASE_SECONDS = 30
DEFAULT_ORCHESTRATION_RUN_HEARTBEAT_SECONDS = 5.0
DEFAULT_ORCHESTRATION_EXECUTOR_MAX_CONCURRENT_ASSIGNMENTS = 4
DEFAULT_ORCHESTRATION_DETAILED_ENGINE_METRICS_ENABLED = False
DEFAULT_ORCHESTRATION_AUTO_COMPACTION_ENABLED = True
DEFAULT_ORCHESTRATION_AUTO_COMPACTION_RESERVE_TOKENS = 20_000
DEFAULT_ORCHESTRATION_AUTO_COMPACTION_SOFT_THRESHOLD_TOKENS = 4_000


def load_orchestration_run_lease_seconds() -> int:
    return _positive_int_env(
        "APP_ORCHESTRATION_RUN_LEASE_SECONDS",
        DEFAULT_ORCHESTRATION_RUN_LEASE_SECONDS,
    )


def load_orchestration_run_heartbeat_seconds() -> float:
    return _positive_float_env(
        "APP_ORCHESTRATION_RUN_HEARTBEAT_SECONDS",
        DEFAULT_ORCHESTRATION_RUN_HEARTBEAT_SECONDS,
        minimum=0.1,
    )


def load_orchestration_executor_max_concurrent_assignments() -> int:
    return _positive_int_env(
        "APP_ORCHESTRATION_EXECUTOR_MAX_CONCURRENT_ASSIGNMENTS",
        DEFAULT_ORCHESTRATION_EXECUTOR_MAX_CONCURRENT_ASSIGNMENTS,
    )


def load_orchestration_detailed_engine_metrics_enabled() -> bool:
    return env_flag(
        "APP_ORCHESTRATION_DETAILED_ENGINE_METRICS_ENABLED",
        default=DEFAULT_ORCHESTRATION_DETAILED_ENGINE_METRICS_ENABLED,
    )


def load_orchestration_auto_compaction_enabled() -> bool:
    return env_flag(
        "APP_ORCHESTRATION_AUTO_COMPACTION_ENABLED",
        default=DEFAULT_ORCHESTRATION_AUTO_COMPACTION_ENABLED,
    )


def load_orchestration_auto_compaction_reserve_tokens() -> int:
    return _non_negative_int_env(
        "APP_ORCHESTRATION_AUTO_COMPACTION_RESERVE_TOKENS",
        DEFAULT_ORCHESTRATION_AUTO_COMPACTION_RESERVE_TOKENS,
    )


def load_orchestration_auto_compaction_soft_threshold_tokens() -> int:
    return _non_negative_int_env(
        "APP_ORCHESTRATION_AUTO_COMPACTION_SOFT_THRESHOLD_TOKENS",
        DEFAULT_ORCHESTRATION_AUTO_COMPACTION_SOFT_THRESHOLD_TOKENS,
    )


def _positive_int_env(name: str, default: int) -> int:
    return max(int(os.getenv(name, str(default))), 1)


def _non_negative_int_env(name: str, default: int) -> int:
    return max(int(os.getenv(name, str(default))), 0)


def _positive_float_env(name: str, default: float, *, minimum: float) -> float:
    return max(float(os.getenv(name, str(default))), minimum)
