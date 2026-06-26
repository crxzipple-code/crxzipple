from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from crxzipple.core.config_agent_profile_models import AgentProfileSettings
from crxzipple.core.config_env import (
    coerce_object_payload,
    deep_merge_dicts,
    load_structured_config,
)
from crxzipple.core.config_paths import PROJECT_ROOT

DEFAULT_AGENT_PROFILE_DIR = PROJECT_ROOT / "config" / "agent_profiles"


def load_agent_profile_settings() -> tuple[AgentProfileSettings, ...]:
    profile_payloads: list[dict[str, Any]] = []
    merged_defaults: dict[str, Any] = {}

    for config_path in _iter_agent_profile_config_paths():
        defaults_payload, profiles_payload = _load_agent_profile_payloads_from_path(
            config_path,
        )
        merged_defaults = deep_merge_dicts(merged_defaults, defaults_payload)
        profile_payloads.extend(profiles_payload)

    raw = os.getenv("APP_AGENT_PROFILES")
    if raw is not None and raw.strip():
        payload = json.loads(raw)
        if not isinstance(payload, list):
            raise ValueError("APP_AGENT_PROFILES must decode to a JSON list.")
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError(
                    "APP_AGENT_PROFILES items must decode to JSON objects.",
                )
            profile_payloads.append(dict(item))

    profiles_by_id: dict[str, AgentProfileSettings] = {}
    for raw_profile in profile_payloads:
        merged_profile = deep_merge_dicts(merged_defaults, raw_profile)
        profile = _build_agent_profile_settings(
            merged_profile,
            source_description="agent profile configuration",
        )
        profiles_by_id[profile.id] = profile

    return tuple(profiles_by_id.values())


def _iter_agent_profile_config_paths() -> tuple[Path, ...]:
    raw = os.getenv("APP_AGENT_PROFILE_PATHS", "").strip()
    if raw:
        configured_paths = [
            Path(part.strip()).expanduser()
            for part in raw.split(os.pathsep)
            if part.strip()
        ]
    elif DEFAULT_AGENT_PROFILE_DIR.exists():
        configured_paths = [DEFAULT_AGENT_PROFILE_DIR]
    else:
        configured_paths = []

    resolved_files: list[Path] = []
    for path in configured_paths:
        if path.is_dir():
            resolved_files.extend(
                candidate
                for pattern in ("*.yaml", "*.yml", "*.json")
                for candidate in sorted(path.glob(pattern))
                if candidate.is_file()
            )
            continue
        if path.is_file():
            resolved_files.append(path)

    unique_files: list[Path] = []
    seen: set[Path] = set()
    for path in resolved_files:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_files.append(resolved)
    return tuple(unique_files)


def _load_agent_profile_payloads_from_path(
    config_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = load_structured_config(config_path)
    source_description = str(config_path)

    if isinstance(payload, list):
        profiles = [
            dict(item)
            for item in payload
            if isinstance(item, dict)
        ]
        if len(profiles) != len(payload):
            raise ValueError(
                f"Agent profile config '{source_description}' list items must decode to objects.",
            )
        return {}, profiles

    if not isinstance(payload, dict):
        raise ValueError(
            f"Agent profile config '{source_description}' must decode to an object or list.",
        )

    if "profiles" in payload or "defaults" in payload:
        return _agent_profile_bundle_payloads(
            payload,
            source_description=source_description,
        )

    return {}, [dict(payload)]


def _agent_profile_bundle_payloads(
    payload: dict[str, object],
    *,
    source_description: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    defaults_payload = payload.get("defaults", {})
    if defaults_payload is None:
        defaults_payload = {}
    if not isinstance(defaults_payload, dict):
        raise ValueError(
            f"Agent profile config '{source_description}' defaults must decode to an object.",
        )

    profiles_payload = payload.get("profiles", [])
    if profiles_payload is None:
        profiles_payload = []
    if not isinstance(profiles_payload, list):
        raise ValueError(
            f"Agent profile config '{source_description}' profiles must decode to a list.",
        )

    normalized_profiles: list[dict[str, Any]] = []
    for item in profiles_payload:
        if not isinstance(item, dict):
            raise ValueError(
                f"Agent profile config '{source_description}' profile items must decode to objects.",
            )
        normalized_profiles.append(dict(item))

    return dict(defaults_payload), normalized_profiles


def _build_agent_profile_settings(
    raw: object,
    *,
    source_description: str,
) -> AgentProfileSettings:
    if not isinstance(raw, dict):
        raise ValueError(
            f"{source_description} items must decode to JSON/YAML objects.",
        )

    profile_id = str(raw.get("id", "")).strip()
    name = str(raw.get("name", "")).strip()
    if not profile_id:
        raise ValueError(f"{source_description} agent profile id cannot be empty.")
    if not name:
        raise ValueError(
            f"Agent profile '{profile_id}' must define name.",
        )

    return AgentProfileSettings(
        id=profile_id,
        name=name,
        enabled=bool(raw.get("enabled", True)),
        identity=_agent_profile_object_payload(raw, profile_id, "identity"),
        instruction_policy=_agent_profile_object_payload(
            raw,
            profile_id,
            "instruction_policy",
        ),
        llm_routing_policy=_agent_profile_object_payload(
            raw,
            profile_id,
            "llm_routing_policy",
        ),
        llm_policy=_agent_profile_object_payload(raw, profile_id, "llm_policy"),
        execution_policy=_agent_profile_object_payload(
            raw,
            profile_id,
            "execution_policy",
        ),
        runtime_preferences=_agent_profile_object_payload(
            raw,
            profile_id,
            "runtime_preferences",
        ),
        memory=_agent_profile_object_payload(raw, profile_id, "memory"),
    )


def _agent_profile_object_payload(
    raw: dict[str, object],
    profile_id: str,
    field_name: str,
) -> dict[str, Any]:
    return coerce_object_payload(
        raw.get(field_name, {}),
        source_description=f"Agent profile '{profile_id}' {field_name}",
    )
