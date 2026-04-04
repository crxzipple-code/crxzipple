from __future__ import annotations

import json
from dataclasses import dataclass, field
import os
from pathlib import Path
import tempfile
from typing import Any
from urllib.parse import urlsplit

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OPENAPI_PROVIDER_DIR = PROJECT_ROOT / "config" / "tool_providers"
DEFAULT_LLM_PROFILE_DIR = PROJECT_ROOT / "config" / "llm_profiles"
DEFAULT_AGENT_PROFILE_DIR = PROJECT_ROOT / "config" / "agent_profiles"
DEFAULT_AUTHORIZATION_POLICY_DIR = PROJECT_ROOT / "config" / "authorization_policies"
DEFAULT_AUTHORIZATION_RUNTIME_POLICY_PATH = (
    PROJECT_ROOT / ".crxzipple" / "authorization_runtime.yaml"
)
DEFAULT_WORKSPACE_TOOL_DIR = PROJECT_ROOT / ".crxzipple" / "tools"
DEFAULT_BUNDLED_TOOL_DIR = PROJECT_ROOT / "tools"
DEFAULT_BROWSER_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "browser"
DEFAULT_ARTIFACT_STORE_DIR = PROJECT_ROOT / ".crxzipple" / "artifacts"
DEFAULT_BROWSER_DEFAULT_PROFILE_NAME = "crxzipple"
DEFAULT_BROWSER_USER_PROFILE_NAME = "user"
DEFAULT_BROWSER_USER_CDP_URL = "http://127.0.0.1:9222"
DEFAULT_BROWSER_PROFILE_COLOR = "#2563EB"
_ALLOWED_BROWSER_PROFILE_RUNTIME_MODES = {
    "host",
    "attached",
    "proxy",
    "sandbox",
    "remote-cdp",
}
_ALLOWED_BROWSER_PROFILE_TRANSPORTS = {"cdp", "proxy"}
_ALLOWED_BROWSER_PROFILE_DRIVERS = {"managed", "existing-session"}


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _load_memory_retrieval_backend() -> str:
    raw = os.getenv("APP_MEMORY_RETRIEVAL_BACKEND", "keyword").strip().lower()
    if not raw:
        return "keyword"
    if raw in {"keyword", "hybrid", "vector"}:
        return raw
    raise ValueError(
        "APP_MEMORY_RETRIEVAL_BACKEND must be one of: keyword, hybrid, vector.",
    )


def _load_memory_vector_provider() -> str:
    raw = os.getenv("APP_MEMORY_VECTOR_PROVIDER", "local").strip().lower()
    if not raw:
        return "local"
    if raw in {"local", "openai_compatible"}:
        return raw
    raise ValueError(
        "APP_MEMORY_VECTOR_PROVIDER must be one of: local, openai_compatible.",
    )


def _load_memory_vector_timeout_seconds() -> int:
    return max(int(os.getenv("APP_MEMORY_VECTOR_TIMEOUT_SECONDS", "30")), 1)


def _load_memory_watch_interval_seconds() -> float:
    return max(float(os.getenv("APP_MEMORY_WATCH_INTERVAL_SECONDS", "300")), 0.0)


def _normalize_browser_profile_name(value: str, *, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} must be a non-empty profile name.")
    if any(separator in normalized for separator in ("/", "\\")):
        raise ValueError(f"{label} must not contain path separators.")
    return normalized


def _normalize_browser_profile_runtime_mode(value: str, *, label: str) -> str:
    normalized = value.strip().lower()
    if normalized in _ALLOWED_BROWSER_PROFILE_RUNTIME_MODES:
        return normalized
    raise ValueError(
        f"{label} must be one of: host, attached, proxy, sandbox, remote-cdp.",
    )


def _normalize_browser_profile_transport(value: str, *, label: str) -> str:
    normalized = value.strip().lower()
    if normalized in _ALLOWED_BROWSER_PROFILE_TRANSPORTS:
        return normalized
    raise ValueError(f"{label} must be one of: cdp, proxy.")


def _normalize_browser_profile_driver(value: str, *, label: str) -> str:
    normalized = value.strip().lower()
    if normalized in _ALLOWED_BROWSER_PROFILE_DRIVERS:
        return normalized
    raise ValueError(f"{label} must be one of: managed, existing-session.")


def _normalize_browser_profile_color(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        return DEFAULT_BROWSER_PROFILE_COLOR
    candidate = normalized if normalized.startswith("#") else f"#{normalized}"
    if len(candidate) != 7:
        return DEFAULT_BROWSER_PROFILE_COLOR
    try:
        int(candidate[1:], 16)
    except ValueError:
        return DEFAULT_BROWSER_PROFILE_COLOR
    return candidate.upper()


def _load_browser_proxy_base_urls() -> tuple[tuple[str, str], ...]:
    raw = os.getenv("APP_BROWSER_PROXY_BASE_URLS", "").strip()
    if not raw:
        return ()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("APP_BROWSER_PROXY_BASE_URLS must decode to a JSON object.")
    resolved: list[tuple[str, str]] = []
    for key, value in payload.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(
                "APP_BROWSER_PROXY_BASE_URLS keys must be non-empty profile names.",
            )
        normalized_key = key.strip()
        if any(separator in normalized_key for separator in ("/", "\\")):
            raise ValueError(
                "APP_BROWSER_PROXY_BASE_URLS profile names must not contain path separators.",
            )
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"APP_BROWSER_PROXY_BASE_URLS entry for '{normalized_key}' must be a non-empty URL string.",
            )
        resolved.append((normalized_key, value.strip().rstrip("/")))
    return tuple(resolved)


def _derive_browser_profile_runtime_mode(
    *,
    driver: str,
    cdp_url: str | None,
    runtime_mode: str | None,
) -> str:
    if runtime_mode is not None:
        return _normalize_browser_profile_runtime_mode(
            runtime_mode,
            label="Browser profile runtime_mode",
        )
    if driver == "existing-session":
        return "attached"
    if isinstance(cdp_url, str) and cdp_url.strip():
        parsed = urlsplit(cdp_url.strip())
        host = (parsed.hostname or "").strip().lower()
        if host and host not in {"127.0.0.1", "localhost", "::1"}:
            return "remote-cdp"
    return "host"


def _load_browser_profile_settings() -> tuple[
    tuple[BrowserProfileSettings, ...],
    tuple[BrowserProfileRuntimeSettings, ...],
]:
    raw = os.getenv("APP_BROWSER_PROFILE_SPECS", "").strip()
    if not raw:
        return _ensure_default_user_browser_profile_settings(
            (
                BrowserProfileSettings(name=DEFAULT_BROWSER_DEFAULT_PROFILE_NAME),
            ),
            (),
        )
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError(
            "APP_BROWSER_PROFILE_SPECS must decode to a JSON array of objects.",
        )
    resolved_profiles: list[BrowserProfileSettings] = []
    resolved_runtime_settings: list[BrowserProfileRuntimeSettings] = []
    seen: set[str] = set()
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}] must be a JSON object.",
            )
        raw_name = item.get("name")
        if not isinstance(raw_name, str):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].name must be a non-empty string.",
            )
        name = _normalize_browser_profile_name(
            raw_name,
            label=f"APP_BROWSER_PROFILE_SPECS[{index}].name",
        )
        if name in seen:
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS contains duplicate profile '{name}'.",
            )
        seen.add(name)
        raw_driver = item.get("driver")
        if raw_driver is None:
            driver = "managed"
        else:
            if not isinstance(raw_driver, str):
                raise ValueError(
                    f"APP_BROWSER_PROFILE_SPECS[{index}].driver must be a string.",
                )
            driver = _normalize_browser_profile_driver(
                raw_driver,
                label=f"APP_BROWSER_PROFILE_SPECS[{index}].driver",
            )
        raw_cdp_url = item.get("cdp_url")
        if raw_cdp_url is not None and not isinstance(raw_cdp_url, str):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].cdp_url must be a string when provided.",
            )
        normalized_cdp_url = raw_cdp_url.strip() if isinstance(raw_cdp_url, str) else None
        raw_runtime_mode = item.get("runtime_mode")
        if raw_runtime_mode is not None and not isinstance(raw_runtime_mode, str):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].runtime_mode must be a string.",
            )
        runtime_mode = _derive_browser_profile_runtime_mode(
            driver=driver,
            cdp_url=normalized_cdp_url,
            runtime_mode=raw_runtime_mode,
        )
        if runtime_mode == "attached" and driver == "managed":
            driver = "existing-session"
        raw_transport = item.get("transport")
        if raw_transport is None:
            transport = "proxy" if runtime_mode == "proxy" else "cdp"
        else:
            if not isinstance(raw_transport, str):
                raise ValueError(
                    f"APP_BROWSER_PROFILE_SPECS[{index}].transport must be a string.",
                )
            transport = _normalize_browser_profile_transport(
                raw_transport,
                label=f"APP_BROWSER_PROFILE_SPECS[{index}].transport",
            )
        raw_cdp_port = item.get("cdp_port")
        if raw_cdp_port is not None and (
            not isinstance(raw_cdp_port, int) or isinstance(raw_cdp_port, bool)
        ):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].cdp_port must be an integer when provided.",
            )
        raw_user_data_dir = item.get("user_data_dir")
        if raw_user_data_dir is not None and not isinstance(raw_user_data_dir, str):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].user_data_dir must be a string when provided.",
            )
        raw_executable_path = item.get("executable_path")
        if raw_executable_path is not None and not isinstance(raw_executable_path, str):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].executable_path must be a string when provided.",
            )
        raw_headless = item.get("headless")
        if raw_headless is not None and not isinstance(raw_headless, bool):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].headless must be a boolean when provided.",
            )
        raw_attach_only = item.get("attach_only")
        if raw_attach_only is not None and not isinstance(raw_attach_only, bool):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].attach_only must be a boolean when provided.",
            )
        raw_color = item.get("color")
        if raw_color is not None and not isinstance(raw_color, str):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].color must be a string when provided.",
            )
        resolved_profiles.append(
            BrowserProfileSettings(
                name=name,
                cdp_url=normalized_cdp_url,
                cdp_port=raw_cdp_port,
                user_data_dir=raw_user_data_dir,
                driver=driver,
                attach_only=bool(raw_attach_only) if raw_attach_only is not None else False,
                color=raw_color,
            ),
        )
        resolved_runtime_settings.append(
            BrowserProfileRuntimeSettings(
                profile=name,
                runtime_mode=runtime_mode,
                transport=transport,
                executable_path=raw_executable_path,
                headless=raw_headless,
            ),
        )
    if not resolved_profiles:
        raise ValueError("APP_BROWSER_PROFILE_SPECS must contain at least one profile.")
    return _ensure_default_user_browser_profile_settings(
        tuple(resolved_profiles),
        tuple(resolved_runtime_settings),
    )


def _load_tool_local_paths() -> tuple[str, ...]:
    configured_paths = [
        DEFAULT_WORKSPACE_TOOL_DIR,
        DEFAULT_BUNDLED_TOOL_DIR,
    ]

    unique_paths: list[str] = []
    seen: set[Path] = set()
    for path in configured_paths:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_paths.append(str(resolved))
    return tuple(unique_paths)


@dataclass(frozen=True, slots=True)
class OpenApiCredentialBinding:
    scheme_name: str
    source: str | None = None
    username_source: str | None = None
    password_source: str | None = None


@dataclass(frozen=True, slots=True)
class BrowserProxyEndpointSettings:
    profile: str
    base_url: str


@dataclass(frozen=True, slots=True)
class BrowserProfileSettings:
    name: str
    cdp_url: str | None = None
    cdp_port: int | None = None
    user_data_dir: str | None = None
    driver: str = "managed"
    attach_only: bool = False
    color: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "name",
            _normalize_browser_profile_name(
                self.name,
                label="Browser profile name",
            ),
        )
        driver = _normalize_browser_profile_driver(
            self.driver,
            label=f"Browser profile '{self.name}' driver",
        )
        normalized_cdp_url = self.cdp_url.strip() if isinstance(self.cdp_url, str) else ""
        normalized_user_data_dir = (
            self.user_data_dir.strip()
            if isinstance(self.user_data_dir, str)
            else ""
        )
        cdp_port = self.cdp_port
        if cdp_port is not None and cdp_port < 0:
            raise ValueError(
                f"Browser profile '{self.name}' cdp_port must not be negative.",
            )
        if cdp_port is None and normalized_cdp_url:
            parsed = urlsplit(normalized_cdp_url)
            if parsed.port is not None:
                cdp_port = parsed.port
        object.__setattr__(self, "driver", driver)
        object.__setattr__(self, "cdp_url", normalized_cdp_url or None)
        object.__setattr__(self, "cdp_port", cdp_port)
        object.__setattr__(self, "user_data_dir", normalized_user_data_dir or None)
        object.__setattr__(
            self,
            "color",
            _normalize_browser_profile_color(self.color),
        )
        if driver == "existing-session" and not self.attach_only:
            object.__setattr__(self, "attach_only", True)


@dataclass(frozen=True, slots=True)
class BrowserProfileRuntimeSettings:
    profile: str
    runtime_mode: str = "host"
    transport: str = "cdp"
    executable_path: str | None = None
    headless: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "profile",
            _normalize_browser_profile_name(
                self.profile,
                label="Browser profile runtime binding profile",
            ),
        )
        runtime_mode = _normalize_browser_profile_runtime_mode(
            self.runtime_mode,
            label=f"Browser profile '{self.profile}' runtime_mode",
        )
        transport = _normalize_browser_profile_transport(
            self.transport,
            label=f"Browser profile '{self.profile}' transport",
        )
        if runtime_mode == "proxy" and transport != "proxy":
            raise ValueError(
                f"Browser profile '{self.profile}' must use transport 'proxy' when runtime_mode is 'proxy'.",
            )
        if runtime_mode != "proxy" and transport == "proxy":
            raise ValueError(
                f"Browser profile '{self.profile}' can only use transport 'proxy' when runtime_mode is 'proxy'.",
            )
        if runtime_mode == "remote-cdp" and transport != "cdp":
            raise ValueError(
                f"Browser profile '{self.profile}' must use transport 'cdp' when runtime_mode is 'remote-cdp'.",
            )
        normalized_executable_path = (
            self.executable_path.strip()
            if isinstance(self.executable_path, str)
            else ""
        )
        object.__setattr__(self, "runtime_mode", runtime_mode)
        object.__setattr__(self, "transport", transport)
        object.__setattr__(self, "executable_path", normalized_executable_path or None)


def _ensure_default_user_browser_profile_settings(
    profiles: tuple[BrowserProfileSettings, ...],
    runtime_settings: tuple[BrowserProfileRuntimeSettings, ...],
) -> tuple[tuple[BrowserProfileSettings, ...], tuple[BrowserProfileRuntimeSettings, ...]]:
    resolved_profiles = profiles
    resolved_runtime_settings = runtime_settings
    if not any(profile.name == DEFAULT_BROWSER_USER_PROFILE_NAME for profile in resolved_profiles):
        resolved_profiles = resolved_profiles + (
            BrowserProfileSettings(
                name=DEFAULT_BROWSER_USER_PROFILE_NAME,
                driver="existing-session",
                cdp_url=DEFAULT_BROWSER_USER_CDP_URL,
                attach_only=True,
            ),
        )
    if not any(
        runtime.profile == DEFAULT_BROWSER_USER_PROFILE_NAME
        for runtime in resolved_runtime_settings
    ):
        resolved_runtime_settings = resolved_runtime_settings + (
            BrowserProfileRuntimeSettings(
                profile=DEFAULT_BROWSER_USER_PROFILE_NAME,
                runtime_mode="attached",
                transport="cdp",
            ),
        )
    return resolved_profiles, resolved_runtime_settings


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
    authorization_enabled: bool = True
    authorization_policy_paths: tuple[str, ...] = ()
    authorization_runtime_policy_path: str = str(DEFAULT_AUTHORIZATION_RUNTIME_POLICY_PATH)
    memory_retrieval_backend: str = "keyword"
    memory_vector_provider: str = "local"
    memory_vector_model: str | None = None
    memory_vector_base_url: str | None = None
    memory_vector_credential_binding: str | None = None
    memory_vector_timeout_seconds: int = 30
    memory_watch_interval_seconds: float = 300.0
    browser_enabled: bool = True
    browser_profiles: tuple[BrowserProfileSettings, ...] = field(
        default_factory=lambda: (
            BrowserProfileSettings(name=DEFAULT_BROWSER_DEFAULT_PROFILE_NAME),
        ),
    )
    browser_profile_runtime_settings: tuple[BrowserProfileRuntimeSettings, ...] = ()
    browser_proxy_base_urls: tuple[BrowserProxyEndpointSettings, ...] = ()
    browser_state_dir: str = str(DEFAULT_BROWSER_STATE_DIR)
    artifact_store_dir: str = str(DEFAULT_ARTIFACT_STORE_DIR)
    artifact_image_preview_max_dimension: int = 1024
    artifact_image_llm_max_dimension: int = 1568
    artifact_image_llm_max_bytes: int = 1_500_000
    artifact_file_llm_max_bytes: int = 4_000_000
    artifact_text_file_llm_max_chars: int = 20_000
    tool_details_max_chars: int = 131_072
    browser_executable_path: str | None = None
    browser_sandbox_executable_path: str | None = None
    browser_proxy_base_url: str | None = None
    browser_cdp_host: str = "127.0.0.1"
    browser_cdp_port: int = 18800
    browser_headless: bool = False
    browser_start_timeout_seconds: int = 10
    browser_sandbox_docker_image: str = "python:3.11-slim"
    prompt_system_max_chars: int = 120_000
    prompt_system_max_tokens: int = 30_000
    prompt_system_context_window_ratio: float = 0.15
    orchestration_run_lease_seconds: int = 30
    orchestration_run_heartbeat_seconds: float = 5.0
    orchestration_auto_compaction_enabled: bool = True
    orchestration_auto_compaction_reserve_tokens: int = 20_000
    orchestration_auto_compaction_soft_threshold_tokens: int = 4_000
    tool_run_max_attempts: int = 3
    tool_run_lease_seconds: int = 30
    tool_run_heartbeat_seconds: float = 5.0

    def __post_init__(self) -> None:
        profiles, runtime_settings = _ensure_default_user_browser_profile_settings(
            self.browser_profiles,
            self.browser_profile_runtime_settings,
        )
        object.__setattr__(
            self,
            "browser_profiles",
            profiles,
        )
        object.__setattr__(
            self,
            "browser_profile_runtime_settings",
            runtime_settings,
        )

    @property
    def browser_profile_specs(self) -> tuple[BrowserProfileSettings, ...]:
        return self.browser_profiles


def load_settings() -> Settings:
    browser_profiles, browser_profile_runtime_settings = _load_browser_profile_settings()
    return Settings(
        app_name=os.getenv("APP_NAME", "crxzipple"),
        environment=os.getenv("APP_ENV", "local"),
        database_url=os.getenv("APP_DATABASE_URL", "sqlite:///./crxzipple.db"),
        tool_local_paths=_load_tool_local_paths(),
        tool_openapi_providers=_load_openapi_provider_settings(),
        tool_mcp_providers=_load_mcp_provider_settings(),
        llm_profiles=_load_llm_profile_settings(),
        agent_profiles=_load_agent_profile_settings(),
        authorization_enabled=_env_flag("APP_AUTHORIZATION_ENABLED", default=True),
        authorization_policy_paths=tuple(
            str(path) for path in _iter_authorization_policy_paths()
        ),
        authorization_runtime_policy_path=str(_authorization_runtime_policy_path()),
        memory_retrieval_backend=_load_memory_retrieval_backend(),
        memory_vector_provider=_load_memory_vector_provider(),
        memory_vector_model=(
            os.getenv("APP_MEMORY_VECTOR_MODEL", "").strip() or None
        ),
        memory_vector_base_url=(
            os.getenv("APP_MEMORY_VECTOR_BASE_URL", "").strip() or None
        ),
        memory_vector_credential_binding=(
            os.getenv("APP_MEMORY_VECTOR_CREDENTIAL_BINDING", "").strip() or None
        ),
        memory_vector_timeout_seconds=_load_memory_vector_timeout_seconds(),
        memory_watch_interval_seconds=_load_memory_watch_interval_seconds(),
        browser_enabled=_env_flag("APP_BROWSER_ENABLED", default=True),
        browser_profiles=browser_profiles,
        browser_profile_runtime_settings=browser_profile_runtime_settings,
        browser_proxy_base_urls=tuple(
            BrowserProxyEndpointSettings(profile=profile, base_url=base_url)
            for profile, base_url in _load_browser_proxy_base_urls()
        ),
        browser_state_dir=os.getenv(
            "APP_BROWSER_STATE_DIR",
            str(DEFAULT_BROWSER_STATE_DIR),
        ),
        artifact_store_dir=os.getenv(
            "APP_ARTIFACT_STORE_DIR",
            str(DEFAULT_ARTIFACT_STORE_DIR),
        ),
        artifact_image_preview_max_dimension=max(
            int(os.getenv("APP_ARTIFACT_IMAGE_PREVIEW_MAX_DIMENSION", "1024")),
            1,
        ),
        artifact_image_llm_max_dimension=max(
            int(os.getenv("APP_ARTIFACT_IMAGE_LLM_MAX_DIMENSION", "1568")),
            1,
        ),
        artifact_image_llm_max_bytes=max(
            int(os.getenv("APP_ARTIFACT_IMAGE_LLM_MAX_BYTES", "1500000")),
            1,
        ),
        artifact_file_llm_max_bytes=max(
            int(os.getenv("APP_ARTIFACT_FILE_LLM_MAX_BYTES", "4000000")),
            1,
        ),
        artifact_text_file_llm_max_chars=max(
            int(os.getenv("APP_ARTIFACT_TEXT_FILE_LLM_MAX_CHARS", "20000")),
            1,
        ),
        tool_details_max_chars=max(
            int(os.getenv("APP_TOOL_DETAILS_MAX_CHARS", "131072")),
            1,
        ),
        browser_executable_path=(
            os.getenv("APP_BROWSER_EXECUTABLE_PATH", "").strip() or None
        ),
        browser_sandbox_executable_path=(
            os.getenv("APP_BROWSER_SANDBOX_EXECUTABLE_PATH", "").strip() or None
        ),
        browser_proxy_base_url=(
            os.getenv("APP_BROWSER_PROXY_BASE_URL", "").strip() or None
        ),
        browser_cdp_host=os.getenv("APP_BROWSER_CDP_HOST", "127.0.0.1").strip()
        or "127.0.0.1",
        browser_cdp_port=max(int(os.getenv("APP_BROWSER_CDP_PORT", "18800")), 1),
        browser_headless=_env_flag("APP_BROWSER_HEADLESS", default=False),
        browser_start_timeout_seconds=max(
            int(os.getenv("APP_BROWSER_START_TIMEOUT_SECONDS", "10")),
            1,
        ),
        browser_sandbox_docker_image=os.getenv(
            "APP_BROWSER_SANDBOX_DOCKER_IMAGE",
            os.getenv(
                "APP_SANDBOX_DOCKER_IMAGE",
                "python:3.11-slim",
            ),
        ).strip()
        or os.getenv(
            "APP_SANDBOX_DOCKER_IMAGE",
            "python:3.11-slim",
        ).strip()
        or "python:3.11-slim",
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
