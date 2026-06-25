from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.domain import LlmInvocation, LlmProfile
from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.models import (
    OperationsOwnerFactSourceModel,
    OperationsProjectionDiagnosticsModel,
)


def llm_projection_diagnostics(
    *,
    profiles: list[LlmProfile],
    invocations: list[LlmInvocation],
    observed_events: tuple[OperationsObservedEvent, ...],
    resolver_events: tuple[OperationsObservedEvent, ...],
    response_events_by_invocation: dict[str, tuple[Any, ...]],
    owner_call_count: int,
    elapsed_ms: float,
    freshness_at: str,
) -> OperationsProjectionDiagnosticsModel:
    response_event_count = sum(
        len(items) for items in response_events_by_invocation.values()
    )
    return OperationsProjectionDiagnosticsModel(
        module="llm",
        owner_sources=(
            OperationsOwnerFactSourceModel(
                module="llm",
                facts=("profiles", "invocations", "response_events", "retention_policy"),
                read_path="OperationsLlmQueryPort",
            ),
            OperationsOwnerFactSourceModel(
                module="access",
                facts=("provider_access_readiness",),
                read_path="OperationsAccessReadinessPort",
            ),
            OperationsOwnerFactSourceModel(
                module="orchestration",
                facts=("execution_step_items", "resolver_events"),
                read_path="OrchestrationRunQueryPort",
            ),
            OperationsOwnerFactSourceModel(
                module="operations",
                facts=("observed_events", "runtime_metrics"),
                read_path="OperationsObservationReadPort",
            ),
        ),
        owner_call_count=owner_call_count,
        processed_item_count=(
            len(profiles)
            + len(invocations)
            + len(observed_events)
            + len(resolver_events)
            + response_event_count
        ),
        elapsed_ms=round(elapsed_ms, 3),
        freshness_at=freshness_at,
    )
