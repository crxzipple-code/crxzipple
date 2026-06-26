from __future__ import annotations

from crxzipple.modules.agent.domain.entities import AgentProfile
from crxzipple.modules.agent.domain.exceptions import AgentValidationError
from crxzipple.modules.agent.domain.value_objects import AgentRuntimePreferences


def require_agent_home_root(agent_home_root: str | None) -> str:
    if agent_home_root is None or not agent_home_root.strip():
        raise AgentValidationError("Agent home root is not configured.")
    return agent_home_root


def default_home_dir(agent_id: str, *, agent_home_root: str | None) -> str:
    root = require_agent_home_root(agent_home_root).rstrip("/")
    return f"{root}/{agent_id}"


def normalize_runtime_preferences(
    agent_id: str,
    runtime_preferences: AgentRuntimePreferences,
    *,
    agent_home_root: str | None,
) -> AgentRuntimePreferences:
    resolved_home_dir = (
        runtime_preferences.home_dir
        or default_home_dir(agent_id, agent_home_root=agent_home_root)
    )
    resolved_workdir = (
        runtime_preferences.workdir
        or runtime_preferences.workspace
        or resolved_home_dir
    )
    return AgentRuntimePreferences(
        home_dir=resolved_home_dir,
        workdir=resolved_workdir,
        workspace=runtime_preferences.workspace,
        sandbox_mode=runtime_preferences.sandbox_mode,
        attrs=dict(runtime_preferences.attrs),
    )


def resolve_agent_home_dir(
    *,
    profile: AgentProfile,
    home_dir: str | None,
) -> str | None:
    resolved_home_dir = (
        home_dir.strip()
        if home_dir is not None and home_dir.strip()
        else profile.runtime_preferences.home_dir
    )
    if resolved_home_dir is None or not resolved_home_dir.strip():
        return None
    return resolved_home_dir


def resolve_required_home_dir(
    *,
    profile: AgentProfile,
    home_dir: str | None,
    agent_home_root: str | None,
) -> str:
    resolved = resolve_agent_home_dir(profile=profile, home_dir=home_dir)
    if resolved is not None:
        return resolved
    return default_home_dir(profile.id, agent_home_root=agent_home_root)


__all__ = [
    "default_home_dir",
    "normalize_runtime_preferences",
    "require_agent_home_root",
    "resolve_agent_home_dir",
    "resolve_required_home_dir",
]
