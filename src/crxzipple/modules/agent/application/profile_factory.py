from __future__ import annotations

from datetime import datetime

from crxzipple.modules.agent.application.home_runtime import normalize_runtime_preferences
from crxzipple.modules.agent.application.profile_models import RegisterAgentProfileInput
from crxzipple.modules.agent.domain.entities import AgentProfile


def build_agent_profile_from_registration(
    data: RegisterAgentProfileInput,
    *,
    agent_home_root: str | None,
    created_at: datetime | None = None,
) -> AgentProfile:
    profile_kwargs: dict[str, object] = {
        "id": data.id,
        "name": data.name,
        "enabled": data.enabled,
        "identity": data.identity,
        "instruction_policy": data.instruction_policy,
        "llm_routing_policy": data.llm_routing_policy,
        "llm_policy": data.llm_policy,
        "execution_policy": data.execution_policy,
        "runtime_preferences": normalize_runtime_preferences(
            data.id,
            data.runtime_preferences,
            agent_home_root=agent_home_root,
        ),
        "memory": data.memory,
    }
    if created_at is not None:
        profile_kwargs["created_at"] = created_at
    return AgentProfile(**profile_kwargs)
