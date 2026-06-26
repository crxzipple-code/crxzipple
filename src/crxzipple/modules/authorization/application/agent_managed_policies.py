from __future__ import annotations

from crxzipple.modules.authorization.domain import (
    AuthorizationEffect,
    AuthorizationPolicy,
)

from .grant_helpers import (
    agent_effect_policy_id as _agent_effect_policy_id,
    agent_tool_authorization_policy_id as _agent_tool_authorization_policy_id,
)


LOCAL_MANAGED_SOURCE_KIND = "local_managed"


def build_agent_effect_authorization_policy(
    *,
    agent_id: str,
    effect_id: str,
) -> AuthorizationPolicy:
    agent = required_text(agent_id, "agent_id")
    effect = required_text(effect_id, "effect_id")
    return AuthorizationPolicy(
        id=_agent_effect_policy_id(agent, effect),
        description=f"Allow agent '{agent}' to authorize effect '{effect}'.",
        effect=AuthorizationEffect.ALLOW,
        actions=("tool.effect.authorize",),
        resource_kind="tool",
        resource_match={"authorization_effect_ids": [effect]},
        context_match={"agent_id": agent},
        priority=1000,
        enabled=True,
        source_kind=LOCAL_MANAGED_SOURCE_KIND,
    )


def build_agent_tool_authorization_policy(
    *,
    agent_id: str,
    tool_id: str,
) -> AuthorizationPolicy:
    agent = required_text(agent_id, "agent_id")
    tool = required_text(tool_id, "tool_id")
    return AuthorizationPolicy(
        id=_agent_tool_authorization_policy_id(agent, tool),
        description=f"Allow agent '{agent}' to authorize tool '{tool}'.",
        effect=AuthorizationEffect.ALLOW,
        actions=("tool.authorize",),
        resource_kind="tool",
        resource_id=tool,
        context_match={"agent_id": agent},
        priority=1000,
        enabled=True,
        source_kind=LOCAL_MANAGED_SOURCE_KIND,
    )


def agent_effect_authorization_policy_id(
    *,
    agent_id: str,
    effect_id: str,
) -> str:
    return _agent_effect_policy_id(
        required_text(agent_id, "agent_id"),
        required_text(effect_id, "effect_id"),
    )


def agent_tool_authorization_policy_id(
    *,
    agent_id: str,
    tool_id: str,
) -> str:
    return _agent_tool_authorization_policy_id(
        required_text(agent_id, "agent_id"),
        required_text(tool_id, "tool_id"),
    )


def ensure_local_managed_policy(policy: AuthorizationPolicy, policy_id: str) -> None:
    if policy.source_kind == LOCAL_MANAGED_SOURCE_KIND:
        return
    raise ValueError(
        f"Authorization policy '{policy_id}' is not a local managed agent grant.",
    )


def required_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty.")
    return normalized


__all__ = [
    "LOCAL_MANAGED_SOURCE_KIND",
    "agent_effect_authorization_policy_id",
    "agent_tool_authorization_policy_id",
    "build_agent_effect_authorization_policy",
    "build_agent_tool_authorization_policy",
    "ensure_local_managed_policy",
]
