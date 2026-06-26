from __future__ import annotations

from fnmatch import fnmatch
from typing import Any

from crxzipple.modules.agent.application.resolution_models import (
    AgentAuthorizationGrant,
)
from crxzipple.modules.agent.application.resolution_values import (
    dict_payload,
    enum_value,
    optional_text,
    text_tuple,
)


def authorization_grant_from_policy(
    policy: Any,
    profile_id: str,
) -> AgentAuthorizationGrant | None:
    if not policy_targets_agent(policy, profile_id):
        return None

    actions = text_tuple(getattr(policy, "actions", ()))
    action = authorization_action(actions)
    if action is None:
        return None

    resource_match = dict_payload(getattr(policy, "resource_match", {}))
    effect_ids = text_tuple(resource_match.get("authorization_effect_ids", ()))
    tool_ids = text_tuple(getattr(policy, "resource_id", None))
    tool_ids = tuple(dict.fromkeys((*tool_ids, *text_tuple(resource_match.get("tool_ids", ())))))
    if not tool_ids:
        tool_ids = text_tuple(resource_match.get("tool_id", ()))

    return AgentAuthorizationGrant(
        policy_id=str(getattr(policy, "id", "")).strip(),
        effect=enum_value(getattr(policy, "effect", None)) or "unknown",
        action=action,
        status="enabled" if bool(getattr(policy, "enabled", False)) else "disabled",
        effect_ids=effect_ids,
        tool_ids=tool_ids,
        source_kind=optional_text(getattr(policy, "source_kind", None)),
        description=optional_text(getattr(policy, "description", None)) or "",
    )


def tool_ids_from_authorization_grants(
    grants: list[AgentAuthorizationGrant],
    *,
    tool_by_id: dict[str, Any],
) -> list[str]:
    tool_ids: list[str] = []
    granted_effect_ids: set[str] = set()
    for grant in grants:
        if grant.effect != "allow" or grant.status != "enabled":
            continue
        tool_ids.extend(grant.tool_ids)
        granted_effect_ids.update(grant.effect_ids)

    if granted_effect_ids:
        for tool in tool_by_id.values():
            required_effect_ids = text_tuple(
                getattr(tool, "required_effect_ids", ()),
            )
            if required_effect_ids and all(
                effect_id in granted_effect_ids for effect_id in required_effect_ids
            ):
                tool_ids.append(str(getattr(tool, "id", "")).strip())
    return [tool_id for tool_id in dict.fromkeys(tool_ids) if tool_id]


def authorization_action(actions: tuple[str, ...]) -> str | None:
    for candidate in ("tool.effect.authorize", "tool.authorize"):
        if any(fnmatch(candidate, pattern) for pattern in actions):
            return candidate
    return None


def policy_targets_agent(policy: Any, profile_id: str) -> bool:
    subject_type = optional_text(getattr(policy, "subject_type", None))
    subject_id = optional_text(getattr(policy, "subject_id", None))
    if subject_type == "agent" and matches_agent_selector(subject_id, profile_id):
        return True

    subject_match = dict_payload(getattr(policy, "subject_match", {}))
    context_match = dict_payload(getattr(policy, "context_match", {}))
    return any(
        matches_agent_selector(value, profile_id)
        for value in (
            subject_match.get("agent_id"),
            subject_match.get("profile_id"),
            context_match.get("agent_id"),
            context_match.get("profile_id"),
        )
    )


def matches_agent_selector(value: object, profile_id: str) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, set)):
        return any(matches_agent_selector(item, profile_id) for item in value)
    selector = str(value).strip()
    if not selector:
        return False
    return fnmatch(profile_id, selector)


__all__ = [
    "authorization_action",
    "authorization_grant_from_policy",
    "matches_agent_selector",
    "policy_targets_agent",
    "tool_ids_from_authorization_grants",
]
