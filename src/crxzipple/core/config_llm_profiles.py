from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from crxzipple.core.config_env import (
    coerce_object_payload,
    load_structured_config,
    optional_bool,
    optional_env_text,
    optional_positive_int,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LLM_PROFILE_DIR = PROJECT_ROOT / "config" / "llm_profiles"


@dataclass(frozen=True, slots=True)
class LlmProfileSettings:
    id: str
    provider: str
    api_family: str
    model_name: str
    context_window_tokens: int | None = None
    model_family: str = "general"
    capabilities: tuple[str, ...] = ()
    default_params: dict[str, Any] = field(default_factory=dict)
    base_url: str | None = None
    credential_binding_id: str | None = None
    timeout_seconds: int = 60
    max_concurrency: int | None = None
    concurrency_key: str | None = None
    source_kind: str = "imported"
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class LlmRequestDefaultsSettings:
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
    service_tier: str | None = None
    prompt_cache_enabled: bool | None = None
    parallel_tool_calls: bool | None = None
    trace_raw_provider_payload: bool = False
    reasoning_summary_default_visibility: str = "model_and_user_visible"
    extra_body: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.max_output_tokens is not None:
            payload["max_output_tokens"] = self.max_output_tokens
        if self.reasoning_effort is not None:
            payload["reasoning_effort"] = self.reasoning_effort
        if self.service_tier is not None:
            payload["service_tier"] = self.service_tier
        if self.prompt_cache_enabled is not None:
            payload["prompt_cache_enabled"] = self.prompt_cache_enabled
        if self.parallel_tool_calls is not None:
            payload["parallel_tool_calls"] = self.parallel_tool_calls
        if self.trace_raw_provider_payload:
            payload["trace_raw_provider_payload"] = self.trace_raw_provider_payload
        if self.reasoning_summary_default_visibility != "model_and_user_visible":
            payload["reasoning_summary_default_visibility"] = (
                self.reasoning_summary_default_visibility
            )
        if self.extra_body:
            payload["extra_body"] = dict(self.extra_body)
        return payload


def load_llm_profile_settings() -> tuple[LlmProfileSettings, ...]:
    profiles_by_id: dict[str, LlmProfileSettings] = {}

    for config_path in _iter_llm_profile_config_paths():
        for profile in _load_llm_profile_settings_from_path(config_path):
            profiles_by_id[profile.id] = profile

    raw = os.getenv("APP_LLM_PROFILES")
    if raw is None or not raw.strip():
        return tuple(profiles_by_id.values())

    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("APP_LLM_PROFILES must decode to a JSON list.")

    for item in payload:
        profile = _build_llm_profile_settings(
            item,
            source_description="APP_LLM_PROFILES",
        )
        profiles_by_id[profile.id] = profile

    return tuple(profiles_by_id.values())


def load_llm_request_defaults_settings() -> LlmRequestDefaultsSettings:
    raw = os.getenv("APP_LLM_REQUEST_DEFAULTS", "").strip()
    if not raw:
        return LlmRequestDefaultsSettings()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("APP_LLM_REQUEST_DEFAULTS must decode to a JSON object.")
    extra_body = coerce_object_payload(
        payload.get("extra_body", {}),
        source_description="APP_LLM_REQUEST_DEFAULTS.extra_body",
    )
    return LlmRequestDefaultsSettings(
        max_output_tokens=optional_positive_int(
            payload.get("max_output_tokens"),
            label="APP_LLM_REQUEST_DEFAULTS.max_output_tokens",
        ),
        reasoning_effort=optional_env_text(payload.get("reasoning_effort")),
        service_tier=optional_env_text(payload.get("service_tier")),
        prompt_cache_enabled=optional_bool(payload.get("prompt_cache_enabled")),
        parallel_tool_calls=optional_bool(payload.get("parallel_tool_calls")),
        trace_raw_provider_payload=bool(
            payload.get("trace_raw_provider_payload", False),
        ),
        reasoning_summary_default_visibility=(
            optional_env_text(payload.get("reasoning_summary_default_visibility"))
            or "model_and_user_visible"
        ),
        extra_body=extra_body,
    )


def _iter_llm_profile_config_paths() -> tuple[Path, ...]:
    raw = os.getenv("APP_LLM_PROFILE_PATHS", "").strip()
    if raw:
        configured_paths = [
            Path(part.strip()).expanduser()
            for part in raw.split(os.pathsep)
            if part.strip()
        ]
    elif DEFAULT_LLM_PROFILE_DIR.exists():
        configured_paths = [DEFAULT_LLM_PROFILE_DIR]
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


def _load_llm_profile_settings_from_path(
    config_path: Path,
) -> tuple[LlmProfileSettings, ...]:
    payload = load_structured_config(config_path)
    if isinstance(payload, dict):
        items = [payload]
    elif isinstance(payload, list):
        items = payload
    else:
        raise ValueError(
            f"LLM profile config '{config_path}' must decode to an object or list.",
        )

    profiles: list[LlmProfileSettings] = []
    for item in items:
        profiles.append(
            _build_llm_profile_settings(
                item,
                source_description=str(config_path),
            ),
        )
    return tuple(profiles)


def _build_llm_profile_settings(
    raw: object,
    *,
    source_description: str,
) -> LlmProfileSettings:
    if not isinstance(raw, dict):
        raise ValueError(
            f"{source_description} items must decode to JSON/YAML objects.",
        )

    profile_id = str(raw.get("id", "")).strip()
    provider = str(raw.get("provider", "")).strip()
    api_family = str(raw.get("api_family", "")).strip()
    model_name = str(raw.get("model_name", "")).strip()
    if not profile_id:
        raise ValueError(f"{source_description} llm profile id cannot be empty.")
    if not provider:
        raise ValueError(
            f"LLM profile '{profile_id}' must define provider.",
        )
    if not api_family:
        raise ValueError(
            f"LLM profile '{profile_id}' must define api_family.",
        )
    if not model_name:
        raise ValueError(
            f"LLM profile '{profile_id}' must define model_name.",
        )
    if raw.get("credential_binding") is not None:
        raise ValueError(
            f"LLM profile '{profile_id}' must use credential_binding_id, not credential_binding.",
        )

    capabilities_raw = raw.get("capabilities", [])
    if capabilities_raw is None:
        capabilities = ()
    elif isinstance(capabilities_raw, list):
        capabilities = tuple(
            str(item).strip() for item in capabilities_raw if str(item).strip()
        )
    else:
        raise ValueError(
            f"LLM profile '{profile_id}' capabilities must decode to a list.",
        )

    default_params_raw = raw.get("default_params", {})
    if default_params_raw is None:
        default_params = {}
    elif isinstance(default_params_raw, dict):
        default_params = dict(default_params_raw)
    else:
        raise ValueError(
            f"LLM profile '{profile_id}' default_params must decode to an object.",
        )

    return LlmProfileSettings(
        id=profile_id,
        provider=provider,
        api_family=api_family,
        model_name=model_name,
        context_window_tokens=(
            max(
                int(raw.get("context_window_tokens", raw.get("context_window"))),
                1,
            )
            if raw.get("context_window_tokens", raw.get("context_window")) is not None
            else None
        ),
        model_family=str(raw.get("model_family", "general")).strip() or "general",
        capabilities=capabilities,
        default_params=default_params,
        base_url=(
            str(raw["base_url"]).strip() if raw.get("base_url") is not None else None
        ),
        credential_binding_id=(
            str(raw["credential_binding_id"]).strip()
            if raw.get("credential_binding_id") is not None
            else None
        ),
        timeout_seconds=max(int(raw.get("timeout_seconds", 60)), 1),
        max_concurrency=optional_positive_int(
            raw.get("max_concurrency"),
            label=f"LLM profile '{profile_id}' max_concurrency",
        ),
        concurrency_key=(
            str(raw["concurrency_key"]).strip()
            if raw.get("concurrency_key") is not None
            else None
        ),
        source_kind=str(raw.get("source_kind", "imported")).strip() or "imported",
        enabled=bool(raw.get("enabled", True)),
    )
