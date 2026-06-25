from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.domain import LlmInvocation, LlmProfile
from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.llm_provider_rows import (
    model_availability_rows,
    provider_access_health_rows,
    provider_auth_blocked_rows,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableSectionModel,
)


def provider_access_health_section(
    profiles: list[LlmProfile],
    *,
    invocations: list[LlmInvocation],
    access_service: Any | None,
    warmup_events_by_profile: dict[str, OperationsObservedEvent],
) -> OperationsTableSectionModel:
    rows = provider_access_health_rows(
        profiles,
        invocations=invocations,
        access_service=access_service,
        warmup_events_by_profile=warmup_events_by_profile,
    )
    return OperationsTableSectionModel(
        id="provider_access_health",
        title="Provider Access & Health",
        columns=_columns(
            ("profile", "LLM Profile"),
            ("provider", "Provider"),
            ("model", "Model"),
            ("api_family", "API Family"),
            ("credential", "Credential"),
            ("status", "Status"),
            ("warmup", "Warmup"),
            ("invocations", "Invocations"),
            ("last_invocation", "Last Invocation"),
            ("next_action", "Next Action"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No LLM profiles configured.",
    )


def provider_auth_blocked_section(
    profiles: list[LlmProfile],
    *,
    invocations: list[LlmInvocation],
    access_service: Any | None,
    warmup_events_by_profile: dict[str, OperationsObservedEvent],
) -> OperationsTableSectionModel:
    rows = provider_auth_blocked_rows(
        profiles,
        invocations=invocations,
        access_service=access_service,
        warmup_events_by_profile=warmup_events_by_profile,
    )
    return OperationsTableSectionModel(
        id="provider_auth_blocked",
        title="Provider Auth / Access Blocked",
        columns=_columns(
            ("profile", "LLM Profile"),
            ("provider", "Provider"),
            ("credential", "Credential"),
            ("issue", "Issue"),
            ("warmup", "Warmup"),
            ("affected_invocations", "Affected Invocations"),
            ("action", "Action"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No provider access blockers.",
    )


def model_availability_section(
    profiles: list[LlmProfile],
    *,
    access_service: Any | None,
) -> OperationsTableSectionModel:
    rows = model_availability_rows(profiles, access_service=access_service)
    return OperationsTableSectionModel(
        id="model_availability",
        title="Model Availability",
        columns=_columns(
            ("profile", "LLM Profile"),
            ("provider", "Provider"),
            ("model", "Model"),
            ("availability", "Availability"),
            ("context", "Context"),
            ("max_concurrency", "Max Concurrency"),
            ("credential", "Credential"),
            ("capabilities", "Capabilities"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No LLM profiles configured.",
    )


def _columns(*pairs: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(OperationsTableColumnModel(key=key, label=label) for key, label in pairs)
