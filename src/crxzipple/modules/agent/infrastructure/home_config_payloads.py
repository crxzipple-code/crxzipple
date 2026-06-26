from __future__ import annotations

from pathlib import Path
from typing import Any

from crxzipple.modules.agent.domain.entities import AgentProfile
from crxzipple.modules.agent.domain.exceptions import AgentValidationError
from crxzipple.modules.agent.domain.value_objects import (
    AgentExecutionPolicy,
    AgentIdentity,
    AgentInstructionPolicy,
    AgentLlmPolicy,
    AgentLlmRoutingPolicy,
    AgentMemoryBinding,
    AgentRuntimePreferences,
)
from crxzipple.modules.agent.infrastructure.home_config_payload_helpers import (
    execution_payload as _execution_payload,
    instruction_payload as _instruction_payload,
    llm_routing_payload as _llm_routing_payload,
    memory_payload as _memory_payload,
    merge_runtime_payload as _merge_runtime_payload,
    optional_text as _optional_text,
    profile_timestamps as _profile_timestamps,
    runtime_payload_from_config_payload as _runtime_payload_from_config_payload,
    section_payload as _section_payload,
)
from crxzipple.shared.time import format_datetime_utc


def profile_from_agent_home_config_payload(
    payload: dict[str, Any],
    *,
    home_dir: str,
) -> AgentProfile:
    profile_id = _optional_text(payload.get("id"))
    if profile_id is None:
        raise AgentValidationError("Agent home config must define a non-empty id.")

    identity_payload = _section_payload(payload, "identity")
    instruction_payload = _instruction_payload(payload)
    llm_payload = _llm_routing_payload(payload)
    llm_policy_payload = _section_payload(payload, "llm_policy")
    execution_payload = _execution_payload(payload)
    runtime_payload = _runtime_payload_from_config_payload(payload, home_dir=home_dir)
    memory_payload = _memory_payload(payload)

    created_at, updated_at = _profile_timestamps(payload, home_dir=home_dir)
    return AgentProfile(
        id=profile_id,
        name=_optional_text(payload.get("name")) or profile_id,
        enabled=bool(payload.get("enabled", True)),
        identity=AgentIdentity.from_payload(identity_payload),
        instruction_policy=AgentInstructionPolicy.from_payload(instruction_payload),
        llm_routing_policy=AgentLlmRoutingPolicy.from_payload(llm_payload),
        llm_policy=AgentLlmPolicy.from_payload(llm_policy_payload),
        execution_policy=AgentExecutionPolicy.from_payload(execution_payload),
        runtime_preferences=AgentRuntimePreferences.from_payload(runtime_payload),
        memory=AgentMemoryBinding.from_payload(memory_payload),
        created_at=created_at,
        updated_at=updated_at,
    )


def apply_agent_home_config_payload(
    profile: AgentProfile,
    payload: dict[str, Any],
    *,
    home_dir: str,
) -> AgentProfile:
    file_agent_id = _optional_text(payload.get("id"))
    if file_agent_id is not None and file_agent_id != profile.id:
        raise AgentValidationError(
            "Agent home config id does not match the target agent profile.",
        )

    identity_payload = _section_payload(payload, "identity")
    instruction_payload = _section_payload(payload, "instruction_policy")
    llm_payload = _llm_routing_payload(payload)
    llm_policy_payload = _section_payload(payload, "llm_policy")
    execution_payload = _section_payload(payload, "execution_policy")
    runtime_payload = _merge_runtime_payload(
        profile,
        payload,
        home_dir=home_dir,
    )
    memory_payload = _memory_payload(payload)

    profile.apply_updates(
        name=_optional_text(payload.get("name")) or profile.name,
        enabled=bool(payload.get("enabled", profile.enabled)),
        identity=(
            AgentIdentity.from_payload(identity_payload)
            if identity_payload
            else profile.identity
        ),
        instruction_policy=(
            AgentInstructionPolicy.from_payload(instruction_payload)
            if instruction_payload
            else profile.instruction_policy
        ),
        llm_routing_policy=(
            AgentLlmRoutingPolicy.from_payload(llm_payload)
            if llm_payload
            else profile.llm_routing_policy
        ),
        llm_policy=(
            AgentLlmPolicy.from_payload(llm_policy_payload)
            if llm_policy_payload
            else profile.llm_policy
        ),
        execution_policy=(
            AgentExecutionPolicy.from_payload(execution_payload)
            if execution_payload
            else profile.execution_policy
        ),
        runtime_preferences=AgentRuntimePreferences.from_payload(runtime_payload),
        memory=(
            AgentMemoryBinding.from_payload(memory_payload)
            if memory_payload
            else profile.memory
        ),
    )
    profile.created_at, profile.updated_at = _profile_timestamps(
        payload,
        home_dir=home_dir,
    )
    return profile


def build_agent_home_config_payload(
    profile: AgentProfile,
    *,
    root: Path,
) -> dict[str, object]:
    runtime_payload: dict[str, object] = {
        "home_dir": str(root),
        "attrs": dict(profile.runtime_preferences.attrs),
    }
    if profile.runtime_preferences.resolved_workdir is not None:
        runtime_payload["workdir"] = profile.runtime_preferences.resolved_workdir
    if profile.runtime_preferences.workspace is not None:
        runtime_payload["workspace"] = profile.runtime_preferences.workspace
    if profile.runtime_preferences.sandbox_mode is not None:
        runtime_payload["sandbox_mode"] = profile.runtime_preferences.sandbox_mode

    return {
        "id": profile.id,
        "name": profile.name,
        "enabled": profile.enabled,
        "created_at": format_datetime_utc(profile.created_at),
        "updated_at": format_datetime_utc(profile.updated_at),
        "identity": profile.identity.to_payload(),
        "instruction_policy": profile.instruction_policy.to_payload(),
        "llm_routing_policy": profile.llm_routing_policy.to_payload(),
        "llm_policy": profile.llm_policy.to_payload(),
        "execution_policy": profile.execution_policy.to_payload(),
        "runtime_preferences": runtime_payload,
        "memory": profile.memory.to_payload(),
    }


__all__ = [
    "apply_agent_home_config_payload",
    "build_agent_home_config_payload",
    "profile_from_agent_home_config_payload",
]
