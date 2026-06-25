from __future__ import annotations

from crxzipple.modules.llm.domain import LlmProfile
from crxzipple.modules.operations.application.read_models.llm_invocation_facts import (
    seconds_label,
)
from crxzipple.modules.operations.application.read_models.llm_runtime_metrics import (
    LLM_LIMITER_ACTIVE,
    LLM_LIMITER_WAIT_SECONDS,
    LLM_LIMITER_WAITERS,
    metric_values_by_label,
    timing_values_by_label,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def limiter_queue_section(
    profiles: list[LlmProfile],
    *,
    runtime_snapshot: dict[str, object],
) -> OperationsTableSectionModel:
    active_by_profile = metric_values_by_label(
        runtime_snapshot,
        section="gauges",
        name=LLM_LIMITER_ACTIVE,
        label="llm_id",
    )
    waiters_by_profile = metric_values_by_label(
        runtime_snapshot,
        section="gauges",
        name=LLM_LIMITER_WAITERS,
        label="llm_id",
    )
    wait_timing_by_profile = timing_values_by_label(
        runtime_snapshot,
        name=LLM_LIMITER_WAIT_SECONDS,
        label="llm_id",
    )
    rows: list[OperationsTableRowModel] = []
    for profile in sorted(profiles, key=lambda item: item.id):
        active = int(active_by_profile.get(profile.id, 0))
        waiters = int(waiters_by_profile.get(profile.id, 0))
        if profile.max_concurrency is None and not active and not waiters:
            continue
        timing = wait_timing_by_profile.get(
            profile.id,
            {"count": 0.0, "avg_seconds": 0.0, "max_seconds": 0.0},
        )
        saturated = (
            profile.max_concurrency is not None
            and active >= profile.max_concurrency
        )
        rows.append(
            OperationsTableRowModel(
                id=profile.id,
                cells={
                    "profile": profile.id,
                    "provider": profile.provider.value,
                    "concurrency_key": profile.concurrency_key or f"profile:{profile.id}",
                    "capacity": str(profile.max_concurrency or "-"),
                    "active": str(active),
                    "waiting": str(waiters),
                    "avg_wait": seconds_label(timing["avg_seconds"]),
                    "max_wait": seconds_label(timing["max_seconds"]),
                    "reason": (
                        "waiting for limiter slot"
                        if waiters
                        else "profile saturated"
                        if saturated
                        else "capacity available"
                    ),
                },
                status="waiting" if waiters else "saturated" if saturated else "available",
                tone="warning" if waiters or saturated else "success",
            ),
        )
    return OperationsTableSectionModel(
        id="limiter_queue",
        title="Limiter Queue",
        columns=_columns(
            ("profile", "LLM Profile"),
            ("provider", "Provider"),
            ("concurrency_key", "Concurrency Key"),
            ("capacity", "Capacity"),
            ("active", "Active"),
            ("waiting", "Waiting"),
            ("avg_wait", "Avg Wait"),
            ("max_wait", "Max Wait"),
            ("reason", "Reason"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No LLM limiter queue observed.",
    )


def _columns(*pairs: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(OperationsTableColumnModel(key=key, label=label) for key, label in pairs)
