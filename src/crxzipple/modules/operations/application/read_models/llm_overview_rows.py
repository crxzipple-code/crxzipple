from __future__ import annotations

from collections import Counter
from datetime import datetime

from crxzipple.modules.llm.domain import LlmInvocation, LlmProfile
from crxzipple.modules.operations.application.read_models.llm_invocation_facts import (
    age_label,
)


def queue_rows(
    invocations: list[LlmInvocation],
    *,
    now: datetime,
) -> tuple[dict[str, str], ...]:
    sorted_invocations = sorted(
        invocations,
        key=lambda invocation: invocation.created_at,
        reverse=True,
    )
    return tuple(
        {
            "Priority": invocation.status.value,
            "Run ID": invocation.id,
            "Lane Key": invocation.llm_id,
            "Wait Reason": invocation_reason(invocation),
            "Wait Time": age_label(
                invocation.started_at or invocation.created_at,
                now=now,
            ),
        }
        for invocation in sorted_invocations[:20]
    )


def profile_limit_rows(profiles: list[LlmProfile]) -> tuple[dict[str, str], ...]:
    limited_profiles = [
        profile
        for profile in profiles
        if profile.max_concurrency is not None or profile.concurrency_key is not None
    ]
    return tuple(
        {
            "Lane Key": profile.concurrency_key or f"provider:{profile.provider.value}",
            "Holder Run ID": profile.id,
            "TTL": f"{profile.timeout_seconds}s",
            "Expires At": (
                str(profile.max_concurrency)
                if profile.max_concurrency is not None
                else "-"
            ),
            "Reason": f"{profile.provider.value}/{profile.api_family.value}",
        }
        for profile in sorted(limited_profiles, key=lambda item: item.id)[:20]
    )


def profile_rows(
    profiles: list[LlmProfile],
    invocations: list[LlmInvocation],
) -> tuple[dict[str, str], ...]:
    invocation_counts = Counter(invocation.llm_id for invocation in invocations)
    latest_invocation_by_profile: dict[str, LlmInvocation] = {}
    for invocation in sorted(invocations, key=lambda item: item.created_at, reverse=True):
        latest_invocation_by_profile.setdefault(invocation.llm_id, invocation)
    rows: list[dict[str, str]] = []
    for profile in sorted(profiles, key=lambda item: item.id):
        latest = latest_invocation_by_profile.get(profile.id)
        rows.append(
            {
                "Worker ID": profile.id,
                "Status": "enabled" if profile.enabled else "disabled",
                "Last Heartbeat": "-",
                "Current Run": latest.id if latest is not None else "-",
                "Load": str(invocation_counts[profile.id]),
            },
        )
    return tuple(rows[:20])


def max_context_label(profiles: list[LlmProfile]) -> str:
    values = [
        profile.context_window_tokens
        for profile in profiles
        if profile.context_window_tokens is not None
    ]
    if not values:
        return "-"
    return str(max(values))


def invocation_reason(invocation: LlmInvocation) -> str:
    if invocation.error is not None:
        return f"{invocation.error.code}: {invocation.error.message}"
    if invocation.result is not None and invocation.result.finish_reason:
        return invocation.result.finish_reason
    return invocation.status.value
