from __future__ import annotations

from crxzipple.modules.authorization.domain import TemporaryAuthorizationGrant


def agent_effect_policy_id(agent_id: str, effect_id: str) -> str:
    return f"local_allow_agent_effect__{_clean(agent_id)}__{_clean(effect_id)}"


def agent_tool_authorization_policy_id(agent_id: str, tool_id: str) -> str:
    return f"local_allow_agent_tool__{_clean(agent_id)}__{_clean(tool_id)}"


def normalize_values(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            value.strip()
            for value in values
            if value is not None and value.strip()
        ),
    )


def run_grant_id(run_id: str, approval_request_id: str | None) -> str:
    request_id = (approval_request_id or "").strip() or "manual"
    return f"run:{run_id}:{request_id}"


def session_grant_id(session_key: str, approval_request_id: str | None) -> str:
    request_id = (approval_request_id or "").strip() or "manual"
    return f"session:{session_key}:{request_id}"


def grant_matches_agent(grant: TemporaryAuthorizationGrant, agent_id: str) -> bool:
    grant_agent_id = (grant.agent_id or "").strip()
    if not grant_agent_id:
        return True
    return bool(agent_id) and grant_agent_id == agent_id


def _clean(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in value)


__all__ = [
    "agent_effect_policy_id",
    "agent_tool_authorization_policy_id",
    "grant_matches_agent",
    "normalize_values",
    "run_grant_id",
    "session_grant_id",
]
