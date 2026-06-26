from __future__ import annotations

from typing import Any

from crxzipple.modules.agent.application.profile_models import (
    UNSET_FIELD,
    UpdateAgentProfileInput,
)


def profile_update_kwargs(data: UpdateAgentProfileInput) -> dict[str, Any]:
    return {
        "name": data.name if data.name is not UNSET_FIELD else None,
        "enabled": data.enabled if data.enabled is not UNSET_FIELD else None,
        "identity": data.identity if data.identity is not UNSET_FIELD else None,
        "instruction_policy": (
            data.instruction_policy
            if data.instruction_policy is not UNSET_FIELD
            else None
        ),
        "llm_routing_policy": (
            data.llm_routing_policy
            if data.llm_routing_policy is not UNSET_FIELD
            else None
        ),
        "llm_policy": data.llm_policy if data.llm_policy is not UNSET_FIELD else None,
        "execution_policy": (
            data.execution_policy
            if data.execution_policy is not UNSET_FIELD
            else None
        ),
        "runtime_preferences": (
            data.runtime_preferences
            if data.runtime_preferences is not UNSET_FIELD
            else None
        ),
        "memory": data.memory if data.memory is not UNSET_FIELD else None,
        "reason": data.reason,
        "actor": data.actor,
    }
