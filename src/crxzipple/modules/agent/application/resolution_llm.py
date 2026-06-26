from __future__ import annotations

from typing import Any

from crxzipple.modules.agent.application.resolution_access import pending_access_grant
from crxzipple.modules.agent.application.resolution_models import (
    AgentAccessGrant,
    AgentResolutionTrace,
    AgentResolvedLlm,
    AgentValidationIssue,
)
from crxzipple.modules.agent.application.resolution_values import (
    enum_tuple,
    enum_value,
    optional_int,
    optional_text,
    text_tuple,
)


def resolve_llm_routes(
    profile: Any,
    *,
    llm_profiles: Any | None,
    validation: list[AgentValidationIssue],
    trace: list[AgentResolutionTrace],
) -> tuple[list[AgentResolvedLlm], list[AgentAccessGrant]]:
    llm_by_id: dict[str, Any] = {}
    if llm_profiles is None:
        trace.append(
            AgentResolutionTrace(
                source="llm",
                status="unavailable",
                detail="LLM profile query port is not configured",
            ),
        )
    else:
        try:
            llm_by_id = {item.id: item for item in llm_profiles.list_profiles()}
            trace.append(
                AgentResolutionTrace(
                    source="llm",
                    status="resolved",
                    detail=f"{len(llm_by_id)} LLM profiles available",
                ),
            )
        except Exception as exc:  # pragma: no cover - defensive partial stack guard
            trace.append(
                AgentResolutionTrace(
                    source="llm",
                    status="error",
                    detail=str(exc),
                ),
            )

    rows: list[AgentResolvedLlm] = []
    access: list[AgentAccessGrant] = []
    for slot, llm_id in _llm_route_slots(profile.llm_routing_policy):
        llm = llm_by_id.get(llm_id)
        if llm is None:
            rows.append(
                AgentResolvedLlm(
                    slot=slot,
                    llm_id=llm_id,
                    resolved=False,
                    enabled=False,
                ),
            )
            validation.append(
                AgentValidationIssue(
                    severity="error",
                    code="agent.llm_not_found",
                    message=(
                        f"LLM route '{slot}' references missing profile '{llm_id}'."
                    ),
                    ref=f"llm:{llm_id}",
                ),
            )
            continue

        credential_binding_id = optional_text(
            getattr(llm, "credential_binding_id", None),
        )
        enabled = bool(getattr(llm, "enabled", False))
        rows.append(
            AgentResolvedLlm(
                slot=slot,
                llm_id=llm_id,
                resolved=True,
                enabled=enabled,
                provider=enum_value(getattr(llm, "provider", None)),
                model_name=optional_text(getattr(llm, "model_name", None)),
                capabilities=enum_tuple(getattr(llm, "capabilities", ())),
                context_window_tokens=optional_int(
                    getattr(llm, "context_window_tokens", None),
                ),
                credential_binding_id=credential_binding_id,
            ),
        )
        if not enabled:
            validation.append(
                AgentValidationIssue(
                    severity="warning",
                    code="agent.llm_disabled",
                    message=f"LLM route '{slot}' points to disabled profile '{llm_id}'.",
                    ref=f"llm:{llm_id}",
                ),
            )
        if credential_binding_id:
            access.append(
                pending_access_grant(
                    source_type="llm",
                    source_id=llm_id,
                    requirement=credential_binding_id,
                    grant_kind="credential_binding",
                ),
            )
    return rows, access


def _llm_route_slots(policy: Any) -> list[tuple[str, str]]:
    slots: list[tuple[str, str]] = []
    default_llm_id = optional_text(getattr(policy, "default_llm_id", None))
    if default_llm_id:
        slots.append(("default", default_llm_id))
    for index, llm_id in enumerate(
        text_tuple(getattr(policy, "fallback_llm_ids", ())),
        start=1,
    ):
        slots.append((f"fallback:{index}", llm_id))
    image_llm_id = optional_text(getattr(policy, "image_llm_id", None))
    if image_llm_id:
        slots.append(("image", image_llm_id))
    document_llm_id = optional_text(getattr(policy, "document_llm_id", None))
    if document_llm_id:
        slots.append(("document", document_llm_id))
    return list(dict.fromkeys(slots))


__all__ = ["resolve_llm_routes"]
