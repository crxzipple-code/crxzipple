from __future__ import annotations

from crxzipple.modules.operations.application.read_models.models import (
    RuntimeActionModel,
)


def llm_actions() -> tuple[RuntimeActionModel, ...]:
    return (
        RuntimeActionModel(
            id="open_invocation",
            label="Open Invocation",
            owner="llm",
            kind="navigation",
            method="GET",
            endpoint="/operations/llm/invocations/{invocation_id}/detail",
        ),
        RuntimeActionModel(
            id="open_trace",
            label="Open Trace",
            owner="events",
            kind="navigation",
            method="GET",
            endpoint="/workbench/traces/{trace_id}",
        ),
        RuntimeActionModel(
            id="open_access",
            label="Open Access",
            owner="access",
            kind="navigation",
            method="GET",
            endpoint="/operations/access",
        ),
        RuntimeActionModel(
            id="warmup_profile",
            label="Warmup",
            owner="llm",
            kind="operation",
            risk="controlled",
            method="POST",
            endpoint="/operations/llm/profiles/{llm_id}/warmup",
            audit_event="llm.profile.warmup",
        ),
        RuntimeActionModel(
            id="view_limits",
            label="View Limits",
            owner="llm",
            kind="navigation",
            method="GET",
            endpoint="/settings/llm-profiles",
        ),
        RuntimeActionModel(
            id="configure_pricing",
            label="Configure Pricing",
            owner="settings",
            kind="navigation",
            risk="controlled",
            method="GET",
            endpoint="/settings/llm-profiles",
        ),
        RuntimeActionModel(
            id="disable_profile",
            label="Disable Profile",
            owner="llm",
            risk="dangerous",
            allowed=False,
            disabled_reason=(
                "LLM profile disable is not exposed as an operations action; "
                "update the configured profile source instead."
            ),
            requires_confirmation=True,
            reason_required=True,
        ),
    )
