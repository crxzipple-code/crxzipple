from __future__ import annotations

import json
import os
from pathlib import Path

from crxzipple.core.config_env import (
    coerce_object_payload,
    load_structured_config,
    optional_bool,
    optional_env_text,
    optional_positive_int,
)
from crxzipple.core.config_llm_profile_models import (
    LlmProfileSettings,
    LlmRequestDefaultsSettings,
)
from crxzipple.core.config_paths import PROJECT_ROOT

DEFAULT_LLM_PROFILE_DIR = PROJECT_ROOT / "config" / "llm_profiles"


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

    return LlmProfileSettings(
        id=profile_id,
        provider=provider,
        api_family=api_family,
        model_name=model_name,
        context_window_tokens=_optional_context_window_tokens(raw),
        model_family=str(raw.get("model_family", "general")).strip() or "general",
        capabilities=_profile_capabilities(raw, profile_id=profile_id),
        default_params=_profile_default_params(raw, profile_id=profile_id),
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


def _optional_context_window_tokens(raw: dict[str, object]) -> int | None:
    raw_value = raw.get("context_window_tokens", raw.get("context_window"))
    if raw_value is None:
        return None
    return max(int(raw_value), 1)


def _profile_capabilities(
    raw: dict[str, object],
    *,
    profile_id: str,
) -> tuple[str, ...]:
    capabilities_raw = raw.get("capabilities", [])
    if capabilities_raw is None:
        return ()
    if isinstance(capabilities_raw, list):
        return tuple(
            str(item).strip() for item in capabilities_raw if str(item).strip()
        )
    raise ValueError(
        f"LLM profile '{profile_id}' capabilities must decode to a list.",
    )


def _profile_default_params(
    raw: dict[str, object],
    *,
    profile_id: str,
) -> dict[str, object]:
    default_params_raw = raw.get("default_params", {})
    if default_params_raw is None:
        return {}
    if isinstance(default_params_raw, dict):
        return dict(default_params_raw)
    raise ValueError(
        f"LLM profile '{profile_id}' default_params must decode to an object.",
    )
