from __future__ import annotations

import json
from dataclasses import dataclass, field
import os
from pathlib import Path
import tempfile
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OPENAPI_PROVIDER_DIR = PROJECT_ROOT / "config" / "tool_providers"
DEFAULT_LLM_PROFILE_DIR = PROJECT_ROOT / "config" / "llm_profiles"
DEFAULT_AGENT_PROFILE_DIR = PROJECT_ROOT / "config" / "agent_profiles"
DEFAULT_AUTHORIZATION_POLICY_DIR = PROJECT_ROOT / "config" / "authorization_policies"
DEFAULT_AUTHORIZATION_RUNTIME_POLICY_PATH = (
    PROJECT_ROOT / ".crxzipple" / "authorization_runtime.yaml"
)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class OpenApiCredentialBinding:
    scheme_name: str
    source: str | None = None
    username_source: str | None = None
    password_source: str | None = None


@dataclass(frozen=True, slots=True)
class OpenApiProviderSettings:
    name: str
    spec_location: str
    base_url: str | None = None
    description: str = ""
    timeout_seconds: int = 30
    credential_bindings: tuple[OpenApiCredentialBinding, ...] = ()
    default_effect_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class McpProviderSettings:
    name: str
    command: tuple[str, ...]
    description: str = ""
    timeout_seconds: int = 30
    default_effect_ids: tuple[str, ...] = ()


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
    credential_binding: str | None = None
    timeout_seconds: int = 60
    source_kind: str = "imported"
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class AgentProfileDefaultsSettings:
    description: str = ""
    enabled: bool = True
    identity: dict[str, Any] = field(default_factory=dict)
    instruction_policy: dict[str, Any] = field(default_factory=dict)
    llm_routing_policy: dict[str, Any] = field(default_factory=dict)
    execution_policy: dict[str, Any] = field(default_factory=dict)
    runtime_preferences: dict[str, Any] = field(default_factory=dict)
    tool_preferences: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentProfileSettings:
    id: str
    name: str
    description: str = ""
    enabled: bool = True
    identity: dict[str, Any] = field(default_factory=dict)
    instruction_policy: dict[str, Any] = field(default_factory=dict)
    llm_routing_policy: dict[str, Any] = field(default_factory=dict)
    execution_policy: dict[str, Any] = field(default_factory=dict)
    runtime_preferences: dict[str, Any] = field(default_factory=dict)
    tool_preferences: dict[str, Any] = field(default_factory=dict)


def _load_openapi_provider_settings() -> tuple[OpenApiProviderSettings, ...]:
    providers_by_name: dict[str, OpenApiProviderSettings] = {}

    for config_path in _iter_openapi_provider_config_paths():
        for provider in _load_openapi_provider_settings_from_path(config_path):
            providers_by_name[provider.name] = provider

    raw = os.getenv("APP_TOOL_OPENAPI_PROVIDERS")
    if raw is None or not raw.strip():
        return tuple(providers_by_name.values())

    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("APP_TOOL_OPENAPI_PROVIDERS must decode to a JSON list.")

    for item in payload:
        provider = _build_openapi_provider_settings(
            item,
            source_description="APP_TOOL_OPENAPI_PROVIDERS",
        )
        providers_by_name[provider.name] = provider

    return tuple(providers_by_name.values())


def _iter_openapi_provider_config_paths() -> tuple[Path, ...]:
    raw = os.getenv("APP_TOOL_OPENAPI_PROVIDER_PATHS", "").strip()
    if raw:
        configured_paths = [
            Path(part.strip()).expanduser()
            for part in raw.split(os.pathsep)
            if part.strip()
        ]
    elif DEFAULT_OPENAPI_PROVIDER_DIR.exists():
        configured_paths = [DEFAULT_OPENAPI_PROVIDER_DIR]
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

    # Keep first occurrence order while removing duplicates.
    unique_files: list[Path] = []
    seen: set[Path] = set()
    for path in resolved_files:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_files.append(resolved)
    return tuple(unique_files)


def _load_openapi_provider_settings_from_path(
    config_path: Path,
) -> tuple[OpenApiProviderSettings, ...]:
    payload = _load_structured_config(config_path)
    if isinstance(payload, dict):
        items = [payload]
    elif isinstance(payload, list):
        items = payload
    else:
        raise ValueError(
            f"OpenAPI provider config '{config_path}' must decode to an object or list.",
        )

    providers: list[OpenApiProviderSettings] = []
    for item in items:
        providers.append(
            _build_openapi_provider_settings(
                item,
                source_path=config_path,
                source_description=str(config_path),
            ),
        )
    return tuple(providers)


def _load_structured_config(path: Path) -> Any:
    raw = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(raw)
    if suffix in {".yaml", ".yml"}:
        return yaml.safe_load(raw)
    raise ValueError(
        f"Unsupported structured config extension '{path.suffix}' for '{path}'.",
    )


def _build_openapi_provider_settings(
    raw: object,
    *,
    source_path: Path | None = None,
    source_description: str,
) -> OpenApiProviderSettings:
    if not isinstance(raw, dict):
        raise ValueError(
            f"{source_description} items must decode to JSON/YAML objects.",
        )

    name = str(raw.get("name", "")).strip()
    spec_location = str(
        raw.get("spec_location") or raw.get("spec_url") or raw.get("spec_path") or "",
    ).strip()
    if not name:
        raise ValueError("OpenAPI provider name cannot be empty.")
    if not spec_location:
        raise ValueError(
            f"OpenAPI provider '{name}' must define spec_location/spec_url/spec_path.",
        )

    return OpenApiProviderSettings(
        name=name,
        spec_location=_resolve_openapi_spec_location(
            spec_location,
            source_path=source_path,
        ),
        base_url=(
            str(raw["base_url"]).strip()
            if raw.get("base_url") is not None
            else None
        ),
        description=str(raw.get("description", "")).strip(),
        timeout_seconds=max(int(raw.get("timeout_seconds", 30)), 1),
        credential_bindings=_load_openapi_credential_bindings(
            raw.get("credentials", {}),
            provider_name=name,
        ),
        default_effect_ids=tuple(
            str(item).strip()
            for item in raw.get("default_effect_ids", []) or []
            if str(item).strip()
        ),
    )


def _resolve_openapi_spec_location(
    spec_location: str,
    *,
    source_path: Path | None,
) -> str:
    if source_path is None:
        return spec_location
    if "://" in spec_location or spec_location.startswith("file:"):
        return spec_location
    candidate = Path(spec_location).expanduser()
    if candidate.is_absolute():
        return str(candidate)
    return str((source_path.parent / candidate).resolve())


def _load_openapi_credential_bindings(
    raw: object,
    *,
    provider_name: str,
) -> tuple[OpenApiCredentialBinding, ...]:
    if raw in (None, {}):
        return ()
    if not isinstance(raw, dict):
        raise ValueError(
            f"OpenAPI provider '{provider_name}' credentials must decode to a JSON object.",
        )

    bindings: list[OpenApiCredentialBinding] = []
    for scheme_name, value in raw.items():
        normalized_scheme_name = str(scheme_name).strip()
        if not normalized_scheme_name:
            raise ValueError(
                f"OpenAPI provider '{provider_name}' credential bindings require non-empty scheme names.",
            )

        if isinstance(value, str):
            source = value.strip()
            if not source:
                raise ValueError(
                    f"OpenAPI provider '{provider_name}' credential binding '{normalized_scheme_name}' cannot be empty.",
                )
            bindings.append(
                OpenApiCredentialBinding(
                    scheme_name=normalized_scheme_name,
                    source=source,
                ),
            )
            continue

        if not isinstance(value, dict):
            raise ValueError(
                f"OpenAPI provider '{provider_name}' credential binding '{normalized_scheme_name}' must be a string or object.",
            )

        source = (
            str(value["source"]).strip()
            if value.get("source") is not None
            else None
        )
        username_source = (
            str(value.get("username_source") or value.get("username") or "").strip()
            or None
        )
        password_source = (
            str(value.get("password_source") or value.get("password") or "").strip()
            or None
        )

        if source is None and (username_source is None or password_source is None):
            raise ValueError(
                f"OpenAPI provider '{provider_name}' credential binding '{normalized_scheme_name}' must define source or username/password sources.",
            )

        bindings.append(
            OpenApiCredentialBinding(
                scheme_name=normalized_scheme_name,
                source=source,
                username_source=username_source,
                password_source=password_source,
            ),
        )

    return tuple(bindings)


def _load_mcp_provider_settings() -> tuple[McpProviderSettings, ...]:
    raw = os.getenv("APP_TOOL_MCP_PROVIDERS")
    if raw is None or not raw.strip():
        return ()

    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("APP_TOOL_MCP_PROVIDERS must decode to a JSON list.")

    providers: list[McpProviderSettings] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError(
                "APP_TOOL_MCP_PROVIDERS items must decode to JSON objects.",
            )

        name = str(item.get("name", "")).strip()
        if not name:
            raise ValueError("MCP provider name cannot be empty.")

        command = item.get("command")
        args = item.get("args", [])
        command_parts: tuple[str, ...]
        if isinstance(command, list):
            command_parts = tuple(str(part).strip() for part in command if str(part).strip())
        elif isinstance(command, str) and command.strip():
            if not isinstance(args, list):
                raise ValueError(
                    f"MCP provider '{name}' args must decode to a JSON list.",
                )
            command_parts = (
                command.strip(),
                *(str(part).strip() for part in args if str(part).strip()),
            )
        else:
            raise ValueError(
                f"MCP provider '{name}' must define command as a string or list.",
            )

        if not command_parts:
            raise ValueError(f"MCP provider '{name}' command cannot be empty.")

        providers.append(
            McpProviderSettings(
                name=name,
                command=command_parts,
                description=str(item.get("description", "")).strip(),
                timeout_seconds=max(int(item.get("timeout_seconds", 30)), 1),
                default_effect_ids=tuple(
                    str(part).strip()
                    for part in item.get("default_effect_ids", []) or []
                    if str(part).strip()
                ),
            ),
        )

    return tuple(providers)


def _load_llm_profile_settings() -> tuple[LlmProfileSettings, ...]:
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
    payload = _load_structured_config(config_path)
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
        credential_binding=(
            str(raw["credential_binding"]).strip()
            if raw.get("credential_binding") is not None
            else None
        ),
        timeout_seconds=max(int(raw.get("timeout_seconds", 60)), 1),
        source_kind=str(raw.get("source_kind", "imported")).strip() or "imported",
        enabled=bool(raw.get("enabled", True)),
    )


def _load_agent_profile_settings() -> tuple[AgentProfileSettings, ...]:
    profile_payloads: list[dict[str, Any]] = []
    merged_defaults: dict[str, Any] = {}

    for config_path in _iter_agent_profile_config_paths():
        defaults_payload, profiles_payload = _load_agent_profile_payloads_from_path(
            config_path,
        )
        merged_defaults = _deep_merge_dicts(merged_defaults, defaults_payload)
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
        merged_profile = _deep_merge_dicts(merged_defaults, raw_profile)
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
    payload = _load_structured_config(config_path)
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

    return {}, [dict(payload)]


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

    identity = _coerce_object_payload(
        raw.get("identity", {}),
        source_description=(
            f"Agent profile '{profile_id}' identity"
        ),
    )
    instruction_policy = _coerce_object_payload(
        raw.get("instruction_policy", {}),
        source_description=(
            f"Agent profile '{profile_id}' instruction_policy"
        ),
    )
    llm_routing_policy = _coerce_object_payload(
        raw.get("llm_routing_policy", {}),
        source_description=(
            f"Agent profile '{profile_id}' llm_routing_policy"
        ),
    )
    execution_policy = _coerce_object_payload(
        raw.get("execution_policy", {}),
        source_description=(
            f"Agent profile '{profile_id}' execution_policy"
        ),
    )
    runtime_preferences = _coerce_object_payload(
        raw.get("runtime_preferences", {}),
        source_description=(
            f"Agent profile '{profile_id}' runtime_preferences"
        ),
    )
    tool_preferences = _coerce_object_payload(
        raw.get("tool_preferences", {}),
        source_description=(f"Agent profile '{profile_id}' tool_preferences"),
    )

    return AgentProfileSettings(
        id=profile_id,
        name=name,
        description=str(raw.get("description", "")).strip(),
        enabled=bool(raw.get("enabled", True)),
        identity=identity,
        instruction_policy=instruction_policy,
        llm_routing_policy=llm_routing_policy,
        execution_policy=execution_policy,
        runtime_preferences=runtime_preferences,
        tool_preferences=tool_preferences,
    )


def _coerce_object_payload(
    raw: object,
    *,
    source_description: str,
) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{source_description} must decode to an object.")
    return dict(raw)


def _deep_merge_dicts(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dicts(existing, value)
            continue
        merged[key] = value
    return merged


def _iter_authorization_policy_paths() -> tuple[Path, ...]:
    raw = os.getenv("APP_AUTHORIZATION_POLICY_PATHS", "").strip()
    if raw:
        configured_paths = [
            Path(part.strip()).expanduser()
            for part in raw.split(os.pathsep)
            if part.strip()
        ]
    elif DEFAULT_AUTHORIZATION_POLICY_DIR.exists():
        configured_paths = [DEFAULT_AUTHORIZATION_POLICY_DIR]
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
    runtime_path = _authorization_runtime_policy_path().resolve()
    if runtime_path not in seen:
        unique_files.append(runtime_path)
    return tuple(unique_files)


def _authorization_runtime_policy_path() -> Path:
    raw = os.getenv("APP_AUTHORIZATION_RUNTIME_POLICY_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_AUTHORIZATION_RUNTIME_POLICY_PATH


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    environment: str
    database_url: str
    sandbox_base_dir: str
    sandbox_backend: str
    sandbox_docker_binary: str
    sandbox_docker_image: str
    log_level: str
    log_json: bool
    tool_local_paths: tuple[str, ...] = ()
    tool_openapi_providers: tuple[OpenApiProviderSettings, ...] = ()
    tool_mcp_providers: tuple[McpProviderSettings, ...] = ()
    llm_profiles: tuple[LlmProfileSettings, ...] = ()
    agent_profiles: tuple[AgentProfileSettings, ...] = ()
    authorization_enabled: bool = False
    authorization_policy_paths: tuple[str, ...] = ()
    authorization_runtime_policy_path: str = str(DEFAULT_AUTHORIZATION_RUNTIME_POLICY_PATH)
    prompt_system_max_chars: int = 120_000
    prompt_system_max_tokens: int = 30_000
    prompt_system_context_window_ratio: float = 0.15
    orchestration_run_lease_seconds: int = 30
    orchestration_run_heartbeat_seconds: float = 5.0
    orchestration_auto_compaction_enabled: bool = True
    orchestration_auto_compaction_transcript_chars: int = 48_000
    orchestration_auto_compaction_transcript_tokens: int = 12_000
    orchestration_auto_compaction_reserve_tokens: int = 20_000
    orchestration_auto_compaction_soft_threshold_tokens: int = 4_000
    tool_run_max_attempts: int = 3
    tool_run_lease_seconds: int = 30
    tool_run_heartbeat_seconds: float = 5.0


def load_settings() -> Settings:
    return Settings(
        app_name=os.getenv("APP_NAME", "crxzipple"),
        environment=os.getenv("APP_ENV", "local"),
        database_url=os.getenv("APP_DATABASE_URL", "sqlite:///./crxzipple.db"),
        tool_local_paths=tuple(
            path.strip()
            for path in os.getenv("APP_TOOL_LOCAL_PATHS", "").split(os.pathsep)
            if path.strip()
        ),
        tool_openapi_providers=_load_openapi_provider_settings(),
        tool_mcp_providers=_load_mcp_provider_settings(),
        llm_profiles=_load_llm_profile_settings(),
        agent_profiles=_load_agent_profile_settings(),
        authorization_enabled=_env_flag("APP_AUTHORIZATION_ENABLED", default=False),
        authorization_policy_paths=tuple(
            str(path) for path in _iter_authorization_policy_paths()
        ),
        authorization_runtime_policy_path=str(_authorization_runtime_policy_path()),
        prompt_system_max_chars=max(
            int(os.getenv("APP_PROMPT_SYSTEM_MAX_CHARS", "120000")),
            1,
        ),
        prompt_system_max_tokens=max(
            int(os.getenv("APP_PROMPT_SYSTEM_MAX_TOKENS", "30000")),
            1,
        ),
        prompt_system_context_window_ratio=max(
            float(os.getenv("APP_PROMPT_SYSTEM_CONTEXT_WINDOW_RATIO", "0.15")),
            0.01,
        ),
        orchestration_run_lease_seconds=max(
            int(os.getenv("APP_ORCHESTRATION_RUN_LEASE_SECONDS", "30")),
            1,
        ),
        orchestration_run_heartbeat_seconds=max(
            float(os.getenv("APP_ORCHESTRATION_RUN_HEARTBEAT_SECONDS", "5")),
            0.1,
        ),
        orchestration_auto_compaction_enabled=_env_flag(
            "APP_ORCHESTRATION_AUTO_COMPACTION_ENABLED",
            default=True,
        ),
        orchestration_auto_compaction_transcript_chars=max(
            int(
                os.getenv(
                    "APP_ORCHESTRATION_AUTO_COMPACTION_TRANSCRIPT_CHARS",
                    "48000",
                ),
            ),
            1,
        ),
        orchestration_auto_compaction_transcript_tokens=max(
            int(
                os.getenv(
                    "APP_ORCHESTRATION_AUTO_COMPACTION_TRANSCRIPT_TOKENS",
                    "12000",
                ),
            ),
            1,
        ),
        orchestration_auto_compaction_reserve_tokens=max(
            int(
                os.getenv(
                    "APP_ORCHESTRATION_AUTO_COMPACTION_RESERVE_TOKENS",
                    "20000",
                ),
            ),
            0,
        ),
        orchestration_auto_compaction_soft_threshold_tokens=max(
            int(
                os.getenv(
                    "APP_ORCHESTRATION_AUTO_COMPACTION_SOFT_THRESHOLD_TOKENS",
                    "4000",
                ),
            ),
            0,
        ),
        tool_run_max_attempts=max(int(os.getenv("APP_TOOL_RUN_MAX_ATTEMPTS", "3")), 1),
        tool_run_lease_seconds=max(int(os.getenv("APP_TOOL_RUN_LEASE_SECONDS", "30")), 1),
        tool_run_heartbeat_seconds=max(
            float(os.getenv("APP_TOOL_RUN_HEARTBEAT_SECONDS", "5")),
            0.1,
        ),
        sandbox_base_dir=os.getenv(
            "APP_SANDBOX_BASE_DIR",
            os.path.join(tempfile.gettempdir(), "crxzipple-sandboxes"),
        ),
        sandbox_backend=os.getenv("APP_SANDBOX_BACKEND", "subprocess").strip().lower(),
        sandbox_docker_binary=os.getenv("APP_SANDBOX_DOCKER_BINARY", "docker"),
        sandbox_docker_image=os.getenv(
            "APP_SANDBOX_DOCKER_IMAGE",
            "python:3.11-slim",
        ),
        log_level=os.getenv("APP_LOG_LEVEL", "INFO").upper(),
        log_json=_env_flag("APP_LOG_JSON", default=False),
    )
