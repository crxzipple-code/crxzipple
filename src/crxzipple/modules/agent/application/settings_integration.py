from __future__ import annotations

# Compatibility helpers for importing Settings materializations into Agent truth.

from collections.abc import Mapping
import json
from typing import Any

from crxzipple.modules.agent.application.services import RegisterAgentProfileInput
from crxzipple.modules.agent.domain.value_objects import (
    AgentExecutionPolicy,
    AgentIdentity,
    AgentInstructionPolicy,
    AgentLlmRoutingPolicy,
    AgentRuntimePreferences,
)


_MEMORY_BINDING_SIDECAR_PATH = ".state/memory-binding.json"


def agent_profile_input_from_settings(
    config: Mapping[str, Any],
) -> RegisterAgentProfileInput:
    payload = _coerce_agent_profile_payload(config)
    profile_id = _required_text(
        payload.get("profile_id") or payload.get("id"), "profile_id"
    )
    name = (
        _optional_text(payload.get("name") or payload.get("display_name")) or profile_id
    )
    identity_payload = _identity_payload(payload)
    llm_payload = _llm_routing_payload(payload)
    runtime_payload = _runtime_preferences_payload(payload)
    return RegisterAgentProfileInput(
        id=profile_id,
        name=name,
        description=str(payload.get("description") or "").strip(),
        enabled=_bool_value(payload.get("enabled"), default=True),
        identity=AgentIdentity.from_payload(identity_payload),
        instruction_policy=AgentInstructionPolicy.from_payload(
            _mapping_payload(payload.get("instruction_policy")),
        ),
        llm_routing_policy=AgentLlmRoutingPolicy.from_payload(llm_payload),
        execution_policy=AgentExecutionPolicy.from_payload(
            _mapping_payload(payload.get("execution_policy")),
        ),
        runtime_preferences=AgentRuntimePreferences.from_payload(runtime_payload),
        home_sidecar_files=_memory_sidecar_files(_memory_space(payload)),
    )


def agent_profile_inputs_from_settings(
    configs: tuple[Mapping[str, Any], ...],
) -> tuple[RegisterAgentProfileInput, ...]:
    return tuple(agent_profile_input_from_settings(config) for config in configs)


def _coerce_agent_profile_payload(config: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(config, Mapping):
        raise TypeError("Agent settings import config must be a mapping.")
    payload = dict(config)
    payload.setdefault("profile_id", payload.get("id"))
    return payload


def _identity_payload(config: Mapping[str, Any]) -> dict[str, Any]:
    payload = _mapping_payload(config.get("identity"))
    display_name = _optional_text(config.get("display_name"))
    if display_name is not None and payload.get("display_name") is None:
        payload["display_name"] = display_name
    return payload


def _llm_routing_payload(config: Mapping[str, Any]) -> dict[str, Any]:
    payload = _mapping_payload(config.get("llm_routing_policy"))
    model_profile_id = _optional_text(config.get("model_profile_id"))
    default_llm_id = _optional_text(config.get("default_llm_id"))
    if payload.get("default_llm_id") is None and model_profile_id is not None:
        payload["default_llm_id"] = model_profile_id
    if payload.get("default_llm_id") is None and default_llm_id is not None:
        payload["default_llm_id"] = default_llm_id
    return payload


def _runtime_preferences_payload(config: Mapping[str, Any]) -> dict[str, Any]:
    payload = _mapping_payload(config.get("runtime_preferences"))
    if not payload:
        payload = _mapping_payload(config.get("runtime"))
    attrs = dict(payload["attrs"]) if isinstance(payload.get("attrs"), Mapping) else {}
    _set_attr(
        attrs, "instructions_path", _optional_text(config.get("instructions_path"))
    )
    _set_attr(attrs, "model_profile_id", _optional_text(config.get("model_profile_id")))
    tool_ids = _text_tuple(config.get("tool_ids"))
    skill_ids = _text_tuple(config.get("skill_ids"))
    if tool_ids:
        attrs["tool_ids"] = list(tool_ids)
    if skill_ids:
        attrs["skill_ids"] = list(skill_ids)
    memory_space = _memory_space(config)
    _set_attr(attrs, "memory_space", memory_space)
    if memory_space is not None and payload.get("memory_space_id") is None:
        payload["memory_space_id"] = memory_space
    payload["attrs"] = attrs
    return payload


def _set_attr(attrs: dict[str, Any], key: str, value: str | None) -> None:
    if value is not None:
        attrs[key] = value


def _memory_sidecar_files(memory_space: str | None) -> dict[str, str]:
    if memory_space is None:
        return {}
    payload = {"space_id": memory_space}
    content = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    return {_MEMORY_BINDING_SIDECAR_PATH: content}


def _mapping_payload(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, tuple | list):
        values = tuple(str(item) for item in value)
    else:
        values = ()
    return tuple(dict.fromkeys(item.strip() for item in values if item.strip()))


def _memory_space(config: Mapping[str, Any]) -> str | None:
    return _optional_text(config.get("memory_space") or config.get("memory_space_id"))


def _required_text(value: object, field_name: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise ValueError(f"{field_name} is required.")
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _bool_value(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
