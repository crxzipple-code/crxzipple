from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crxzipple.modules.agent.domain.entities import AgentProfile
from crxzipple.modules.agent.domain.exceptions import AgentValidationError
from crxzipple.shared.time import coerce_utc_datetime


def runtime_payload_from_config_payload(
    payload: dict[str, Any],
    *,
    home_dir: str,
) -> dict[str, object]:
    runtime_payload = section_payload(payload, "runtime_preferences")
    if not runtime_payload:
        return {
            "home_dir": home_dir,
            "workdir": optional_text(payload.get("workdir")),
            "workspace": optional_text(payload.get("workspace")),
            "sandbox_mode": optional_text(payload.get("sandbox_mode")),
            "attrs": (
                dict(payload["attrs"])
                if isinstance(payload.get("attrs"), dict)
                else {}
            ),
        }
    return {
        "home_dir": optional_text(runtime_payload.get("home_dir")) or home_dir,
        "workdir": optional_text(runtime_payload.get("workdir")),
        "workspace": optional_text(runtime_payload.get("workspace")),
        "sandbox_mode": optional_text(runtime_payload.get("sandbox_mode")),
        "attrs": (
            dict(runtime_payload["attrs"])
            if isinstance(runtime_payload.get("attrs"), dict)
            else {}
        ),
    }


def section_payload(payload: dict[str, Any], key: str) -> dict[str, Any]:
    section = payload.get(key)
    if isinstance(section, dict):
        return dict(section)
    return {}


def instruction_payload(payload: dict[str, Any]) -> dict[str, Any]:
    section = section_payload(payload, "instruction_policy")
    if section or optional_text(payload.get("system_prompt")) is None:
        return section
    return {
        "system_prompt": optional_text(payload.get("system_prompt")) or "",
        "response_style": payload.get("response_style"),
        "thinking_default": payload.get("thinking_default"),
        "stream_by_default": payload.get("stream_by_default", False),
    }


def llm_routing_payload(payload: dict[str, Any]) -> dict[str, Any]:
    section = section_payload(payload, "llm_routing_policy")
    if section or optional_text(payload.get("default_llm_id")) is None:
        return section
    return {
        "default_llm_id": optional_text(payload.get("default_llm_id")),
        "fallback_llm_ids": payload.get("fallback_llm_ids", ()),
        "image_llm_id": payload.get("image_llm_id"),
        "document_llm_id": payload.get("document_llm_id"),
    }


def execution_payload(payload: dict[str, Any]) -> dict[str, Any]:
    section = section_payload(payload, "execution_policy")
    if section or (
        payload.get("timeout_seconds") is None and payload.get("max_turns") is None
    ):
        return section
    return {
        "timeout_seconds": payload.get("timeout_seconds", 120),
        "max_turns": payload.get("max_turns", 99),
    }


def merge_runtime_payload(
    profile: AgentProfile,
    payload: dict[str, Any],
    *,
    home_dir: str,
) -> dict[str, object]:
    runtime_payload = section_payload(payload, "runtime_preferences")
    merged_attrs = (
        dict(runtime_payload["attrs"])
        if isinstance(runtime_payload.get("attrs"), dict)
        else dict(profile.runtime_preferences.attrs)
    )
    if not runtime_payload and isinstance(payload.get("attrs"), dict):
        merged_attrs = dict(payload["attrs"])
    return {
        "home_dir": optional_text(runtime_payload.get("home_dir")) or home_dir,
        "workdir": (
            optional_text(runtime_payload.get("workdir"))
            or optional_text(payload.get("workdir"))
            or profile.runtime_preferences.resolved_workdir
        ),
        "workspace": (
            optional_text(runtime_payload.get("workspace"))
            or optional_text(payload.get("workspace"))
            or profile.runtime_preferences.workspace
        ),
        "sandbox_mode": (
            optional_text(runtime_payload.get("sandbox_mode"))
            or optional_text(payload.get("sandbox_mode"))
            or profile.runtime_preferences.sandbox_mode
        ),
        "attrs": merged_attrs,
    }


def memory_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return section_payload(payload, "memory")


def optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def profile_timestamps(
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


__all__ = [
    "execution_payload",
    "instruction_payload",
    "llm_routing_payload",
    "memory_payload",
    "merge_runtime_payload",
    "optional_text",
    "profile_timestamps",
    "runtime_payload_from_config_payload",
    "section_payload",
]
