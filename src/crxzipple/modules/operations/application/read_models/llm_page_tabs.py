from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.llm_invocation_facts import (
    token_total,
)
from crxzipple.modules.operations.application.read_models.llm_runtime_metrics import (
    limiter_waiter_count,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTabModel,
)


def llm_page_tabs(
    *,
    invocations: tuple[Any, ...],
    streaming_invocations: tuple[Any, ...],
    failed_invocations: tuple[Any, ...],
    profiles: tuple[Any, ...],
    runtime_snapshot: Any | None,
    observed_events: tuple[Any, ...],
) -> tuple[OperationsTabModel, ...]:
    waiter_count = limiter_waiter_count(runtime_snapshot)
    return (
        OperationsTabModel(
            id="invocations",
            label="Invocations",
            count=len(invocations),
        ),
        OperationsTabModel(
            id="streaming",
            label="Streaming Requests",
            count=len(streaming_invocations),
        ),
        OperationsTabModel(
            id="rate_limits",
            label="Rate Limits",
            count=waiter_count,
            tone="warning" if waiter_count > 0 else "neutral",
        ),
        OperationsTabModel(
            id="token_usage",
            label="Token Usage",
            count=token_total(invocations),
        ),
        OperationsTabModel(
            id="errors",
            label="Errors",
            count=len(failed_invocations),
            tone="danger" if failed_invocations else "neutral",
        ),
        OperationsTabModel(
            id="models",
            label="Models",
            count=len(profiles),
        ),
        OperationsTabModel(
            id="providers",
            label="Providers",
            count=len({profile.provider.value for profile in profiles}),
        ),
        OperationsTabModel(
            id="events",
            label="Events",
            count=len(observed_events),
        ),
    )
