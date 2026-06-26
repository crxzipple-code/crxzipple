from __future__ import annotations

from crxzipple.modules.agent.application.profile_models import AgentProfileActionInput
from crxzipple.modules.agent.domain.entities import AgentProfile


def coerce_action_input(
    profile: str | AgentProfileActionInput,
    *,
    reason: str | None,
    actor: str | None,
) -> AgentProfileActionInput:
    if isinstance(profile, AgentProfileActionInput):
        return AgentProfileActionInput(
            id=profile.id,
            reason=profile.reason if profile.reason is not None else reason,
            actor=profile.actor if profile.actor is not None else actor,
        )
    return AgentProfileActionInput(id=profile, reason=reason, actor=actor)


def agent_profile_event_payload(
    profile: AgentProfile,
    *,
    reason: str | None = None,
    actor: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "agent_profile_id": profile.id,
        "agent_profile_name": profile.name,
    }
    normalized_reason = _normalize_optional_text(reason)
    normalized_actor = _normalize_optional_text(actor)
    if normalized_reason is not None:
        payload["reason"] = normalized_reason
    if normalized_actor is not None:
        payload["actor"] = normalized_actor
    return payload


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
