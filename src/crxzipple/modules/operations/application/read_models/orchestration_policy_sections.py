from __future__ import annotations

from typing import Any

from crxzipple.modules.orchestration.domain import OrchestrationExecutorLease
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
)
from crxzipple.modules.operations.application.read_models.orchestration_runtime_config_projection import (
    enabled_label,
    runtime_bool,
    runtime_float,
    runtime_int,
    token_pair_label,
)
from crxzipple.modules.operations.application.read_models.orchestration_status_projection import (
    duration_label,
)


def policy_limits_section(
    *,
    leases: list[OrchestrationExecutorLease],
    online_leases: list[OrchestrationExecutorLease],
    capacity: int,
    inflight: int,
    available: int,
    runtime_bootstrap_config: Any | None,
    worker_lease_seconds: int | None,
    worker_heartbeat_seconds: float | None,
) -> OperationsKeyValueSectionModel:
    lease_seconds = runtime_int(
        runtime_bootstrap_config,
        "orchestration_run_lease_seconds",
        fallback=worker_lease_seconds,
    )
    heartbeat_seconds = runtime_float(
        runtime_bootstrap_config,
        "orchestration_run_heartbeat_seconds",
        fallback=worker_heartbeat_seconds,
    )
    executor_limit = runtime_int(
        runtime_bootstrap_config,
        "orchestration_executor_max_concurrent_assignments",
    )
    compaction_enabled = runtime_bool(
        runtime_bootstrap_config,
        "orchestration_auto_compaction_enabled",
    )
    compaction_reserve = runtime_int(
        runtime_bootstrap_config,
        "orchestration_auto_compaction_reserve_tokens",
    )
    compaction_soft = runtime_int(
        runtime_bootstrap_config,
        "orchestration_auto_compaction_soft_threshold_tokens",
    )
    return OperationsKeyValueSectionModel(
        id="policy_limits",
        title="Policy & Limits",
        items=(
            OperationsKeyValueItemModel(label="Per-lane Concurrency", value="1"),
            OperationsKeyValueItemModel(
                label="Global Run Concurrency",
                value=str(max(capacity, inflight)),
            ),
            OperationsKeyValueItemModel(
                label="Executor Max Assignments",
                value=str(executor_limit) if executor_limit is not None else "-",
            ),
            OperationsKeyValueItemModel(
                label="Worker Capacity (Online / Total)",
                value=f"{len(online_leases)}/{len(leases)}",
                tone="success" if online_leases else "warning",
            ),
            OperationsKeyValueItemModel(
                label="Approval Timeout", value="not configured"
            ),
            OperationsKeyValueItemModel(
                label="Lease Timeout",
                value=duration_label(round(lease_seconds))
                if lease_seconds is not None
                else "-",
            ),
            OperationsKeyValueItemModel(
                label="Lane Lock TTL",
                value="executor lease",
            ),
            OperationsKeyValueItemModel(
                label="Queue Retention",
                value="retained",
            ),
            OperationsKeyValueItemModel(
                label="Heartbeat Interval",
                value=duration_label(round(heartbeat_seconds))
                if heartbeat_seconds is not None
                else "-",
            ),
            OperationsKeyValueItemModel(
                label="Auto Compaction",
                value=enabled_label(compaction_enabled),
                tone="success" if compaction_enabled else "neutral",
            ),
            OperationsKeyValueItemModel(
                label="Compaction Reserve / Soft",
                value=token_pair_label(compaction_reserve, compaction_soft),
            ),
        ),
    )
