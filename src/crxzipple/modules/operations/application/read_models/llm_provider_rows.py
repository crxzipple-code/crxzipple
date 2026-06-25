from __future__ import annotations

from collections import Counter
from typing import Any

from crxzipple.modules.llm.domain import LlmInvocation, LlmProfile
from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.llm_provider_readiness import (
    availability_label,
    capability_label,
    context_label,
    credential_label,
    latest_invocation_by_profile,
    profile_access_readiness,
    readiness_tone,
)
from crxzipple.modules.operations.application.read_models.llm_provider_warmup import (
    warmup_next_action,
    warmup_status_label,
    warmup_tone,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)
from crxzipple.shared.time import format_datetime_utc


def provider_access_health_rows(
    profiles: list[LlmProfile],
    *,
    invocations: list[LlmInvocation],
    access_service: Any | None,
    warmup_events_by_profile: dict[str, OperationsObservedEvent],
) -> tuple[OperationsTableRowModel, ...]:
    invocation_counts = Counter(invocation.llm_id for invocation in invocations)
    latest_invocation = latest_invocation_by_profile(invocations)
    rows: list[OperationsTableRowModel] = []
    for profile in sorted(profiles, key=lambda item: item.id):
        readiness = profile_access_readiness(profile, access_service=access_service)
        latest = latest_invocation.get(profile.id)
        warmup_event = warmup_events_by_profile.get(profile.id)
        rows.append(
            OperationsTableRowModel(
                id=profile.id,
                cells={
                    "profile": profile.id,
                    "provider": profile.provider.value,
                    "model": profile.model_name,
                    "api_family": profile.api_family.value,
                    "credential": credential_label(profile.credential_binding_id),
                    "status": availability_label(profile, readiness),
                    "warmup": warmup_status_label(warmup_event),
                    "invocations": str(invocation_counts[profile.id]),
                    "last_invocation": (
                        format_datetime_utc(latest.created_at)
                        if latest is not None
                        else "-"
                    ),
                    "next_action": warmup_next_action(
                        warmup_event,
                        readiness=readiness,
                    ),
                },
                status=readiness["status"],
                tone=warmup_tone(warmup_event, fallback=readiness_tone(readiness)),
            ),
        )
    return tuple(rows)


def provider_auth_blocked_rows(
    profiles: list[LlmProfile],
    *,
    invocations: list[LlmInvocation],
    access_service: Any | None,
    warmup_events_by_profile: dict[str, OperationsObservedEvent],
) -> tuple[OperationsTableRowModel, ...]:
    invocation_counts = Counter(invocation.llm_id for invocation in invocations)
    rows: list[OperationsTableRowModel] = []
    for profile in sorted(profiles, key=lambda item: item.id):
        readiness = profile_access_readiness(profile, access_service=access_service)
        if readiness["ready"]:
            continue
        warmup_event = warmup_events_by_profile.get(profile.id)
        rows.append(
            OperationsTableRowModel(
                id=profile.id,
                cells={
                    "profile": profile.id,
                    "provider": profile.provider.value,
                    "credential": credential_label(profile.credential_binding_id),
                    "issue": readiness["reason"],
                    "warmup": warmup_status_label(warmup_event),
                    "affected_invocations": str(invocation_counts[profile.id]),
                    "action": warmup_next_action(warmup_event, readiness=readiness),
                },
                status=readiness["status"],
                tone=warmup_tone(warmup_event, fallback=readiness_tone(readiness)),
            ),
        )
    return tuple(rows)


def model_availability_rows(
    profiles: list[LlmProfile],
    *,
    access_service: Any | None,
) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    for profile in sorted(profiles, key=lambda item: item.id):
        readiness = profile_access_readiness(profile, access_service=access_service)
        availability = availability_label(profile, readiness)
        rows.append(
            OperationsTableRowModel(
                id=profile.id,
                cells={
                    "profile": profile.id,
                    "provider": profile.provider.value,
                    "model": profile.model_name,
                    "availability": availability,
                    "context": context_label(profile),
                    "max_concurrency": (
                        str(profile.max_concurrency)
                        if profile.max_concurrency is not None
                        else "-"
                    ),
                    "credential": credential_label(profile.credential_binding_id),
                    "capabilities": capability_label(profile),
                },
                status=readiness["status"],
                tone=readiness_tone(readiness),
            ),
        )
    return tuple(rows)
