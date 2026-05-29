from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from crxzipple.modules.agent.domain.entities import AgentProfile
from crxzipple.modules.agent.domain.exceptions import AgentValidationError
from crxzipple.modules.agent.domain.value_objects import (
    AgentExecutionPolicy,
    AgentIdentity,
    AgentInstructionPolicy,
    AgentLlmRoutingPolicy,
    AgentMemoryBinding,
    AgentRuntimePreferences,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def render_agent_home_config(profile: AgentProfile, *, root: Path) -> str:
    payload = build_agent_home_config_payload(profile, root=root)
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def write_agent_home_config(profile: AgentProfile, *, home_dir: str) -> Path:
    root = Path(home_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "agent.json"
    path.write_text(render_agent_home_config(profile, root=root), encoding="utf-8")
    return path


def load_agent_home_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser()
    if not config_path.exists():
        raise AgentValidationError(
            f"Agent home config '{config_path}' does not exist.",
        )
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AgentValidationError(
            f"Agent home config '{config_path}' is not valid JSON.",
        ) from exc
    if not isinstance(payload, dict):
        raise AgentValidationError(
            f"Agent home config '{config_path}' must contain a JSON object.",
        )
    return payload


def profile_from_agent_home_config_payload(
    payload: dict[str, Any],
    *,
    home_dir: str,
) -> AgentProfile:
    profile_id = _optional_text(payload.get("id"))
    if profile_id is None:
        raise AgentValidationError("Agent home config must define a non-empty id.")

    identity_payload = _section_payload(payload, "identity")
    instruction_payload = _section_payload(payload, "instruction_policy")
    llm_payload = _section_payload(payload, "llm_routing_policy")
    execution_payload = _section_payload(payload, "execution_policy")
    runtime_payload = _section_payload(payload, "runtime_preferences")
    memory_payload = _memory_payload(payload, runtime_payload)

    if not instruction_payload and _optional_text(payload.get("system_prompt")) is not None:
        instruction_payload = {
            "system_prompt": _optional_text(payload.get("system_prompt")) or "",
            "response_style": payload.get("response_style"),
            "thinking_default": payload.get("thinking_default"),
            "stream_by_default": payload.get("stream_by_default", False),
        }

    if not llm_payload and _optional_text(payload.get("default_llm_id")) is not None:
        llm_payload = {
            "default_llm_id": _optional_text(payload.get("default_llm_id")),
            "fallback_llm_ids": payload.get("fallback_llm_ids", ()),
            "image_llm_id": payload.get("image_llm_id"),
            "document_llm_id": payload.get("document_llm_id"),
        }

    if not execution_payload and (
        payload.get("timeout_seconds") is not None or payload.get("max_turns") is not None
    ):
        execution_payload = {
            "timeout_seconds": payload.get("timeout_seconds", 120),
            "max_turns": payload.get("max_turns", 99),
        }

    if not runtime_payload:
        runtime_payload = {
            "home_dir": home_dir,
            "workdir": _optional_text(payload.get("workdir")),
            "workspace": _optional_text(payload.get("workspace")),
            "sandbox_mode": _optional_text(payload.get("sandbox_mode")),
            "attrs": (
                dict(payload["attrs"])
                if isinstance(payload.get("attrs"), dict)
                else {}
            ),
        }
    else:
        runtime_payload = {
            "home_dir": _optional_text(runtime_payload.get("home_dir")) or home_dir,
            "workdir": _optional_text(runtime_payload.get("workdir")),
            "workspace": _optional_text(runtime_payload.get("workspace")),
            "sandbox_mode": _optional_text(runtime_payload.get("sandbox_mode")),
            "attrs": (
                dict(runtime_payload["attrs"])
                if isinstance(runtime_payload.get("attrs"), dict)
                else {}
            ),
        }

    created_at, updated_at = _profile_timestamps(payload, home_dir=home_dir)
    return AgentProfile(
        id=profile_id,
        name=_optional_text(payload.get("name")) or profile_id,
        enabled=bool(payload.get("enabled", True)),
        identity=AgentIdentity.from_payload(identity_payload),
        instruction_policy=AgentInstructionPolicy.from_payload(instruction_payload),
        llm_routing_policy=AgentLlmRoutingPolicy.from_payload(llm_payload),
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
    llm_payload = _section_payload(payload, "llm_routing_policy")
    execution_payload = _section_payload(payload, "execution_policy")
    raw_runtime_payload = _section_payload(payload, "runtime_preferences")
    memory_payload = _memory_payload(payload, raw_runtime_payload)
    runtime_payload = _merge_runtime_payload(
        profile,
        payload,
        home_dir=home_dir,
    )

    if not llm_payload and _optional_text(payload.get("default_llm_id")) is not None:
        llm_payload = {
            "default_llm_id": _optional_text(payload.get("default_llm_id")),
            "fallback_llm_ids": payload.get("fallback_llm_ids", ()),
            "image_llm_id": payload.get("image_llm_id"),
            "document_llm_id": payload.get("document_llm_id"),
        }

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
        "execution_policy": profile.execution_policy.to_payload(),
        "runtime_preferences": runtime_payload,
        "memory": profile.memory.to_payload(),
    }


def _section_payload(payload: dict[str, Any], key: str) -> dict[str, Any]:
    section = payload.get(key)
    if isinstance(section, dict):
        return dict(section)
    return {}


def _merge_runtime_payload(
    profile: AgentProfile,
    payload: dict[str, Any],
    *,
    home_dir: str,
) -> dict[str, object]:
    runtime_payload = _section_payload(payload, "runtime_preferences")
    merged_attrs = (
        dict(runtime_payload["attrs"])
        if isinstance(runtime_payload.get("attrs"), dict)
        else dict(profile.runtime_preferences.attrs)
    )
    if not runtime_payload and isinstance(payload.get("attrs"), dict):
        merged_attrs = dict(payload["attrs"])
    merged: dict[str, object] = {
        "home_dir": _optional_text(runtime_payload.get("home_dir")) or home_dir,
        "workdir": (
            _optional_text(runtime_payload.get("workdir"))
            or _optional_text(payload.get("workdir"))
            or profile.runtime_preferences.resolved_workdir
        ),
        "workspace": (
            _optional_text(runtime_payload.get("workspace"))
            or _optional_text(payload.get("workspace"))
            or profile.runtime_preferences.workspace
        ),
        "sandbox_mode": (
            _optional_text(runtime_payload.get("sandbox_mode"))
            or _optional_text(payload.get("sandbox_mode"))
            or profile.runtime_preferences.sandbox_mode
        ),
        "attrs": merged_attrs,
    }
    return merged


def _memory_payload(
    payload: dict[str, Any],
    runtime_payload: dict[str, Any],
) -> dict[str, Any]:
    del runtime_payload
    return _section_payload(payload, "memory")


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _profile_timestamps(
    payload: dict[str, Any],
    *,
    home_dir: str,
) -> tuple[datetime, datetime]:
    fallback = _agent_config_mtime(home_dir)
    parsed_created_at = _optional_datetime(payload.get("created_at"))
    parsed_updated_at = _optional_datetime(payload.get("updated_at"))
    created_at = parsed_created_at or parsed_updated_at or fallback
    updated_at = parsed_updated_at or fallback
    return created_at, updated_at


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return coerce_utc_datetime(value)
    normalized = str(value).strip()
    if not normalized:
        return None
    try:
        return coerce_utc_datetime(datetime.fromisoformat(normalized))
    except ValueError as exc:
        raise AgentValidationError(
            f"Agent home config timestamp '{normalized}' is not valid ISO datetime.",
        ) from exc


def _agent_config_mtime(home_dir: str) -> datetime:
    config_path = Path(home_dir).expanduser() / "agent.json"
    try:
        return datetime.fromtimestamp(config_path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return datetime.now(timezone.utc)
