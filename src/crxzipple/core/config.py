from __future__ import annotations

import json
from dataclasses import dataclass, field
import os
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit

import yaml

if TYPE_CHECKING:
    from crxzipple.modules.channels.domain.value_objects import (
        ChannelAccountProfile,
        ChannelProfile,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OPENAPI_PROVIDER_DIR = PROJECT_ROOT / "config" / "tool_providers"
DEFAULT_LLM_PROFILE_DIR = PROJECT_ROOT / "config" / "llm_profiles"
DEFAULT_AGENT_PROFILE_DIR = PROJECT_ROOT / "config" / "agent_profiles"
DEFAULT_CHANNEL_PROFILE_DIR = PROJECT_ROOT / "config" / "channel_profiles"
DEFAULT_AUTHORIZATION_POLICY_DIR = PROJECT_ROOT / "config" / "authorization_policies"
DEFAULT_AUTHORIZATION_RUNTIME_POLICY_PATH = (
    PROJECT_ROOT / ".crxzipple" / "authorization_runtime.yaml"
)
DEFAULT_WORKSPACE_TOOL_DIR = PROJECT_ROOT / ".crxzipple" / "tools"
DEFAULT_BUNDLED_TOOL_DIR = PROJECT_ROOT / "tools"
DEFAULT_BROWSER_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "browser"
DEFAULT_MOBILE_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "mobile"
DEFAULT_DAEMON_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "daemon"
DEFAULT_EVENTS_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "events"
DEFAULT_OPERATIONS_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "operations"
DEFAULT_CHANNELS_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "channels"
DEFAULT_ACCESS_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "access"
DEFAULT_MEMORY_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "memory"
DEFAULT_ARTIFACT_STORE_DIR = PROJECT_ROOT / ".crxzipple" / "artifacts"
DEFAULT_OCR_BACKEND = "local"
DEFAULT_OCR_PROVIDER = "host"
DEFAULT_OCR_HOST = "127.0.0.1"
DEFAULT_OCR_PORT = 18900
DEFAULT_BROWSER_DEFAULT_PROFILE_NAME = "crxzipple"
DEFAULT_BROWSER_USER_PROFILE_NAME = "user"
DEFAULT_BROWSER_USER_CDP_URL = "http://127.0.0.1:9222"
DEFAULT_BROWSER_PROFILE_COLOR = "#2563EB"
_ALLOWED_BROWSER_PROFILE_DRIVERS = {"managed", "existing-session"}
_ALLOWED_BROWSER_PROXY_CREDENTIAL_KINDS = {"basic", "bearer_token"}
_ALLOWED_MOBILE_PLATFORMS = {"android"}
_ALLOWED_EVENTS_BACKENDS = {"file", "redis"}
DEFAULT_EVENTS_BACKEND = "redis"
DEFAULT_EVENTS_REDIS_URL = "redis://127.0.0.1:6379/0"
ALLOW_SQLITE_RUNTIME_FALLBACK_ENV = "APP_ALLOW_SQLITE_RUNTIME_FALLBACK"


class RuntimeDatabaseGuardError(RuntimeError):
    """Raised when a long-running runtime is pointed at SQLite by default."""


def is_sqlite_database_url(database_url: str) -> bool:
    return urlsplit(database_url).scheme.startswith("sqlite")


def require_runtime_database(settings: "Settings", *, runtime_name: str) -> None:
    if not is_sqlite_database_url(settings.database_url):
        return
    if settings.allow_sqlite_runtime_fallback:
        return
    raise RuntimeDatabaseGuardError(
        f"Refusing to start {runtime_name} with SQLite. "
        "Source `scripts/dev/infra-env.sh` or set APP_DATABASE_URL to Postgres. "
        f"For an explicit one-off SQLite fallback, set {ALLOW_SQLITE_RUNTIME_FALLBACK_ENV}=1.",
    )


def _load_events_backend() -> Literal["file", "redis"]:
    raw = os.getenv("APP_EVENTS_BACKEND", DEFAULT_EVENTS_BACKEND).strip().lower()
    if not raw:
        return DEFAULT_EVENTS_BACKEND
    if raw == "redis":
        return "redis"
    if raw == "file":
        return "file"
    raise ValueError("APP_EVENTS_BACKEND must be one of: file, redis.")


def _load_ocr_backend() -> str:
    raw = os.getenv("APP_OCR_BACKEND", DEFAULT_OCR_BACKEND).strip().lower()
    if not raw:
        return DEFAULT_OCR_BACKEND
    if raw in {"local", "remote"}:
        return raw
    raise ValueError("APP_OCR_BACKEND must be one of: local, remote.")


def _load_ocr_provider() -> str:
    raw = os.getenv("APP_OCR_PROVIDER", DEFAULT_OCR_PROVIDER).strip().lower()
    if not raw:
        return DEFAULT_OCR_PROVIDER
    if raw in {"host", "ppstructurev3"}:
        return raw
    raise ValueError("APP_OCR_PROVIDER must be one of: host, ppstructurev3.")


def _resolve_ocr_base_url(*, backend: str, host: str, port: int) -> str:
    explicit = os.getenv("APP_OCR_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    if backend == "remote":
        raise ValueError(
            "APP_OCR_BASE_URL must be set when APP_OCR_BACKEND=remote.",
        )
    return f"http://{host}:{port}"


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _runtime_sqlite_fallback_enabled() -> bool:
    return os.getenv(ALLOW_SQLITE_RUNTIME_FALLBACK_ENV, "").strip() == "1"


def _optional_positive_int(value: object, *, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive integer.") from exc
    if parsed < 1:
        raise ValueError(f"{label} must be a positive integer.")
    return parsed


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip().lower()
        if not stripped:
            return None
        return stripped in {"1", "true", "yes", "on"}
    return bool(value)


def _optional_env_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


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


def _proxy_server_has_credentials(value: str | None) -> bool:
    normalized = (value or "").strip()
    if not normalized:
        return False
    parsed = urlsplit(normalized)
    return bool(parsed.username or parsed.password)


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


def _normalize_mobile_device_name(value: str, *, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} must be a non-empty device name.")
    if any(separator in normalized for separator in ("/", "\\")):
        raise ValueError(f"{label} must not contain path separators.")
    return normalized


def _normalize_mobile_platform(value: str, *, label: str) -> str:
    normalized = value.strip().lower()
    if normalized in _ALLOWED_MOBILE_PLATFORMS:
        return normalized
    raise ValueError(f"{label} must be one of: android.")


def _load_mobile_device_settings() -> tuple[MobileDeviceSettings, ...]:
    raw = os.getenv("APP_MOBILE_DEVICE_SPECS", "").strip()
    if not raw:
        return ()
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError(
            "APP_MOBILE_DEVICE_SPECS must decode to a JSON array of objects.",
        )
    resolved: list[MobileDeviceSettings] = []
    seen: set[str] = set()
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(
                f"APP_MOBILE_DEVICE_SPECS[{index}] must be a JSON object.",
            )
        raw_name = item.get("name")
        if not isinstance(raw_name, str):
            raise ValueError(
                f"APP_MOBILE_DEVICE_SPECS[{index}].name must be a non-empty string.",
            )
        name = _normalize_mobile_device_name(
            raw_name,
            label=f"APP_MOBILE_DEVICE_SPECS[{index}].name",
        )
        if name in seen:
            raise ValueError(
                f"APP_MOBILE_DEVICE_SPECS contains duplicate device '{name}'.",
            )
        seen.add(name)
        resolved.append(
            MobileDeviceSettings(
                name=name,
                platform=str(item.get("platform", "android")),
                udid=(
                    str(item["udid"]).strip()
                    if isinstance(item.get("udid"), str)
                    else None
                ),
                app_package=(
                    str(item["app_package"]).strip()
                    if isinstance(item.get("app_package"), str)
                    else None
                ),
                app_activity=(
                    str(item["app_activity"]).strip()
                    if isinstance(item.get("app_activity"), str)
                    else None
                ),
            )
        )
    return tuple(resolved)


def _load_browser_profile_settings() -> tuple[BrowserProfileSettings, ...]:
    raw = os.getenv("APP_BROWSER_PROFILE_SPECS", "").strip()
    if not raw:
        return _ensure_default_user_browser_profile_settings(
            (
                BrowserProfileSettings(name=DEFAULT_BROWSER_DEFAULT_PROFILE_NAME),
            ),
        )
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError(
            "APP_BROWSER_PROFILE_SPECS must decode to a JSON array of objects.",
        )
    resolved_profiles: list[BrowserProfileSettings] = []
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
        raw_enabled = item.get("enabled")
        if raw_enabled is not None and not isinstance(raw_enabled, bool):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].enabled must be a boolean when provided.",
            )
        raw_cdp_url = item.get("cdp_url")
        if raw_cdp_url is not None and not isinstance(raw_cdp_url, str):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].cdp_url must be a string when provided.",
            )
        normalized_cdp_url = raw_cdp_url.strip() if isinstance(raw_cdp_url, str) else None
        if "runtime_mode" in item:
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].runtime_mode has been removed; use driver, cdp_url, attach_only, autostart, and proxy_* fields.",
            )
        if "transport" in item:
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].transport has been removed; use driver, cdp_url, attach_only, autostart, and proxy_* fields.",
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
        raw_profile_directory = item.get("profile_directory")
        if raw_profile_directory is not None and not isinstance(raw_profile_directory, str):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].profile_directory must be a string when provided.",
            )
        if "executable_path" in item:
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].executable_path has been removed; use APP_BROWSER_EXECUTABLE_PATH for the Browser system executable.",
            )
        if "headless" in item:
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].headless has been removed; use APP_BROWSER_HEADLESS for the Browser system headless mode.",
            )
        raw_attach_only = item.get("attach_only")
        if raw_attach_only is not None and not isinstance(raw_attach_only, bool):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].attach_only must be a boolean when provided.",
            )
        raw_autostart = item.get("autostart")
        if raw_autostart is not None and not isinstance(raw_autostart, bool):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].autostart must be a boolean when provided.",
            )
        raw_proxy_mode = item.get("proxy_mode")
        if raw_proxy_mode is not None and not isinstance(raw_proxy_mode, str):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].proxy_mode must be a string when provided.",
            )
        raw_proxy_server = item.get("proxy_server")
        if raw_proxy_server is not None and not isinstance(raw_proxy_server, str):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].proxy_server must be a string when provided.",
            )
        raw_proxy_bypass_list = item.get("proxy_bypass_list")
        if raw_proxy_bypass_list is not None and not (
            isinstance(raw_proxy_bypass_list, list)
            and all(isinstance(entry, str) for entry in raw_proxy_bypass_list)
        ):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].proxy_bypass_list must be a string array when provided.",
            )
        raw_proxy_binding_id = item.get("proxy_binding_id")
        if raw_proxy_binding_id is not None and not isinstance(raw_proxy_binding_id, str):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].proxy_binding_id must be a string when provided.",
            )
        raw_proxy_credential_kind = item.get("proxy_credential_kind")
        if raw_proxy_credential_kind is not None and not isinstance(raw_proxy_credential_kind, str):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].proxy_credential_kind must be a string when provided.",
            )
        raw_close_targets_on_release = item.get("close_targets_on_release")
        if raw_close_targets_on_release is not None and not isinstance(raw_close_targets_on_release, bool):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].close_targets_on_release must be a boolean when provided.",
            )
        raw_close_targets_on_expire = item.get("close_targets_on_expire")
        if raw_close_targets_on_expire is not None and not isinstance(raw_close_targets_on_expire, bool):
            raise ValueError(
                f"APP_BROWSER_PROFILE_SPECS[{index}].close_targets_on_expire must be a boolean when provided.",
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
                profile_directory=raw_profile_directory,
                driver=driver,
                enabled=bool(raw_enabled) if raw_enabled is not None else True,
                attach_only=bool(raw_attach_only) if raw_attach_only is not None else False,
                autostart=bool(raw_autostart) if raw_autostart is not None else True,
                proxy_mode=raw_proxy_mode or "none",
                proxy_server=raw_proxy_server,
                proxy_bypass_list=tuple(raw_proxy_bypass_list or ()),
                proxy_binding_id=raw_proxy_binding_id,
                proxy_credential_kind=raw_proxy_credential_kind or "basic",
                close_targets_on_release=(
                    bool(raw_close_targets_on_release)
                    if raw_close_targets_on_release is not None
                    else True
                ),
                close_targets_on_expire=(
                    bool(raw_close_targets_on_expire)
                    if raw_close_targets_on_expire is not None
                    else True
                ),
                color=raw_color,
            ),
        )
    if not resolved_profiles:
        raise ValueError("APP_BROWSER_PROFILE_SPECS must contain at least one profile.")
    return _ensure_default_user_browser_profile_settings(
        tuple(resolved_profiles),
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
    credential_binding_id: str | None = None
    username_binding_id: str | None = None
    password_binding_id: str | None = None


@dataclass(frozen=True, slots=True)
class BrowserProxyEndpointSettings:
    profile: str
    base_url: str


@dataclass(frozen=True, slots=True)
class BrowserProfileSettings:
    name: str
    enabled: bool = True
    cdp_url: str | None = None
    cdp_port: int | None = None
    user_data_dir: str | None = None
    profile_directory: str | None = None
    driver: str = "managed"
    attach_only: bool = False
    autostart: bool = True
    proxy_mode: str = "none"
    proxy_server: str | None = None
    proxy_bypass_list: tuple[str, ...] = ()
    proxy_binding_id: str | None = None
    proxy_credential_kind: str = "basic"
    close_targets_on_release: bool = True
    close_targets_on_expire: bool = True
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
        object.__setattr__(self, "enabled", bool(self.enabled))
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
        normalized_profile_directory = (
            self.profile_directory.strip()
            if isinstance(self.profile_directory, str)
            else ""
        )
        if "/" in normalized_profile_directory or "\\" in normalized_profile_directory:
            raise ValueError(
                f"Browser profile '{self.name}' profile_directory must be a browser profile name.",
            )
        proxy_mode = self.proxy_mode.strip().lower()
        if proxy_mode not in {"none", "static", "access_binding"}:
            raise ValueError(
                f"Browser profile '{self.name}' proxy_mode must be one of: access_binding, none, static.",
            )
        normalized_proxy_server = (
            self.proxy_server.strip()
            if isinstance(self.proxy_server, str)
            else ""
        )
        normalized_proxy_binding_id = (
            self.proxy_binding_id.strip()
            if isinstance(self.proxy_binding_id, str)
            else ""
        )
        proxy_credential_kind = self.proxy_credential_kind.strip().lower()
        if proxy_credential_kind == "bearer":
            proxy_credential_kind = "bearer_token"
        if proxy_credential_kind not in _ALLOWED_BROWSER_PROXY_CREDENTIAL_KINDS:
            raise ValueError(
                f"Browser profile '{self.name}' proxy_credential_kind must be one of: basic, bearer_token.",
            )
        normalized_proxy_bypass_list = tuple(
            item.strip()
            for item in self.proxy_bypass_list
            if isinstance(item, str) and item.strip()
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
            "profile_directory",
            normalized_profile_directory or None,
        )
        object.__setattr__(self, "proxy_mode", proxy_mode)
        object.__setattr__(self, "proxy_server", normalized_proxy_server or None)
        object.__setattr__(
            self,
            "proxy_bypass_list",
            normalized_proxy_bypass_list,
        )
        object.__setattr__(
            self,
            "proxy_binding_id",
            normalized_proxy_binding_id or None,
        )
        object.__setattr__(self, "proxy_credential_kind", proxy_credential_kind)
        object.__setattr__(
            self,
            "close_targets_on_release",
            bool(self.close_targets_on_release),
        )
        object.__setattr__(
            self,
            "close_targets_on_expire",
            bool(self.close_targets_on_expire),
        )
        object.__setattr__(
            self,
            "color",
            _normalize_browser_profile_color(self.color),
        )
        if driver == "existing-session" and not self.attach_only:
            object.__setattr__(self, "attach_only", True)
        if self.attach_only or driver == "existing-session":
            object.__setattr__(self, "autostart", False)
        if proxy_mode == "static" and not normalized_proxy_server:
            raise ValueError(
                f"Browser profile '{self.name}' proxy_server is required when proxy_mode is static.",
            )
        if proxy_mode == "static" and _proxy_server_has_credentials(normalized_proxy_server):
            raise ValueError(
                f"Browser profile '{self.name}' proxy_server must not contain credentials; use proxy_mode access_binding.",
            )
        if proxy_mode == "access_binding" and not normalized_proxy_binding_id:
            raise ValueError(
                f"Browser profile '{self.name}' proxy_binding_id is required when proxy_mode is access_binding.",
            )


@dataclass(frozen=True, slots=True)
class MobileDeviceSettings:
    name: str
    platform: str = "android"
    udid: str | None = None
    app_package: str | None = None
    app_activity: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "name",
            _normalize_mobile_device_name(self.name, label="Mobile device name"),
        )
        object.__setattr__(
            self,
            "platform",
            _normalize_mobile_platform(
                self.platform,
                label=f"Mobile device '{self.name}' platform",
            ),
        )
        object.__setattr__(
            self,
            "udid",
            self.udid.strip() if isinstance(self.udid, str) and self.udid.strip() else None,
        )
        object.__setattr__(
            self,
            "app_package",
            self.app_package.strip()
            if isinstance(self.app_package, str) and self.app_package.strip()
            else None,
        )
        object.__setattr__(
            self,
            "app_activity",
            self.app_activity.strip()
            if isinstance(self.app_activity, str) and self.app_activity.strip()
            else None,
        )


def _ensure_default_user_browser_profile_settings(
    profiles: tuple[BrowserProfileSettings, ...],
) -> tuple[BrowserProfileSettings, ...]:
    resolved_profiles = profiles
    if not any(profile.name == DEFAULT_BROWSER_USER_PROFILE_NAME for profile in resolved_profiles):
        resolved_profiles = resolved_profiles + (
            BrowserProfileSettings(
                name=DEFAULT_BROWSER_USER_PROFILE_NAME,
                driver="existing-session",
                cdp_url=DEFAULT_BROWSER_USER_CDP_URL,
                attach_only=True,
            ),
        )
    return resolved_profiles


@dataclass(frozen=True, slots=True)
class OpenApiProviderSettings:
    name: str
    spec_location: str
    base_url: str | None = None
    description: str = ""
    timeout_seconds: int = 30
    max_concurrency: int | None = None
    credential_bindings: tuple[OpenApiCredentialBinding, ...] = ()
    default_effect_ids: tuple[str, ...] = ()
    runtime_requirements: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "runtime_requirements",
            tuple(
                dict.fromkeys(
                    str(requirement).strip()
                    for requirement in self.runtime_requirements
                    if str(requirement).strip()
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class McpProviderSettings:
    name: str
    command: tuple[str, ...] = ()
    transport: str = "stdio"
    endpoint_url: str | None = None
    description: str = ""
    timeout_seconds: int = 30
    max_concurrency: int | None = None
    default_effect_ids: tuple[str, ...] = ()
    runtime_requirements: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        transport = self.transport.strip().lower()
        if transport not in {"stdio", "http"}:
            raise ValueError(
                f"MCP provider '{self.name}' transport must be one of: http, stdio.",
            )
        command = tuple(part.strip() for part in self.command if part.strip())
        endpoint_url = self.endpoint_url.strip() if isinstance(self.endpoint_url, str) else ""
        if transport == "stdio" and not command:
            raise ValueError(f"MCP provider '{self.name}' command cannot be empty.")
        if transport == "http" and not endpoint_url:
            raise ValueError(f"MCP provider '{self.name}' endpoint_url cannot be empty.")
        object.__setattr__(self, "transport", transport)
        object.__setattr__(self, "command", command)
        object.__setattr__(self, "endpoint_url", endpoint_url or None)
        object.__setattr__(
            self,
            "runtime_requirements",
            tuple(
                dict.fromkeys(
                    str(requirement).strip()
                    for requirement in self.runtime_requirements
                    if str(requirement).strip()
                ),
            ),
        )


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
class AgentProfileDefaultsSettings:
    enabled: bool = True
    identity: dict[str, Any] = field(default_factory=dict)
    instruction_policy: dict[str, Any] = field(default_factory=dict)
    llm_routing_policy: dict[str, Any] = field(default_factory=dict)
    llm_policy: dict[str, Any] = field(default_factory=dict)
    execution_policy: dict[str, Any] = field(default_factory=dict)
    runtime_preferences: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentProfileSettings:
    id: str
    name: str
    enabled: bool = True
    identity: dict[str, Any] = field(default_factory=dict)
    instruction_policy: dict[str, Any] = field(default_factory=dict)
    llm_routing_policy: dict[str, Any] = field(default_factory=dict)
    llm_policy: dict[str, Any] = field(default_factory=dict)
    execution_policy: dict[str, Any] = field(default_factory=dict)
    runtime_preferences: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)


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
        if (
            self.reasoning_summary_default_visibility
            != "model_and_user_visible"
        ):
            payload["reasoning_summary_default_visibility"] = (
                self.reasoning_summary_default_visibility
            )
        if self.extra_body:
            payload["extra_body"] = dict(self.extra_body)
        return payload


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
        max_concurrency=_optional_positive_int(
            raw.get("max_concurrency"),
            label=f"OpenAPI provider '{name}' max_concurrency",
        ),
        credential_bindings=_load_openapi_credential_bindings(
            raw.get("credentials", {}),
            provider_name=name,
        ),
        default_effect_ids=tuple(
            str(item).strip()
            for item in raw.get("default_effect_ids", []) or []
            if str(item).strip()
        ),
        runtime_requirements=tuple(
            str(item).strip()
            for item in raw.get("runtime_requirements", []) or []
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
            credential_binding_id = value.strip()
            if not credential_binding_id:
                raise ValueError(
                    f"OpenAPI provider '{provider_name}' credential binding '{normalized_scheme_name}' cannot be empty.",
                )
            _reject_direct_openapi_credential_source(
                credential_binding_id,
                provider_name=provider_name,
                scheme_name=normalized_scheme_name,
                field_name="credential_binding_id",
            )
            bindings.append(
                OpenApiCredentialBinding(
                    scheme_name=normalized_scheme_name,
                    credential_binding_id=credential_binding_id,
                ),
            )
            continue

        if not isinstance(value, dict):
            raise ValueError(
                f"OpenAPI provider '{provider_name}' credential binding '{normalized_scheme_name}' must be a string or object.",
            )

        _reject_legacy_openapi_credential_fields(
            value,
            provider_name=provider_name,
            scheme_name=normalized_scheme_name,
        )
        credential_binding_id = _optional_mapping_text(
            value,
            "credential_binding_id",
        )
        username_binding_id = _optional_mapping_text(
            value,
            "username_binding_id",
        )
        password_binding_id = _optional_mapping_text(
            value,
            "password_binding_id",
        )

        if credential_binding_id is None and (
            username_binding_id is None or password_binding_id is None
        ):
            raise ValueError(
                f"OpenAPI provider '{provider_name}' credential binding '{normalized_scheme_name}' must define credential_binding_id or username/password binding ids.",
            )

        bindings.append(
            OpenApiCredentialBinding(
                scheme_name=normalized_scheme_name,
                credential_binding_id=credential_binding_id,
                username_binding_id=username_binding_id,
                password_binding_id=password_binding_id,
            ),
        )

    return tuple(bindings)


def _optional_mapping_text(value: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        raw = value.get(key)
        if raw is None:
            continue
        normalized = str(raw).strip()
        if normalized:
            return normalized
    return None


def _reject_legacy_openapi_credential_fields(
    value: dict[str, object],
    *,
    provider_name: str,
    scheme_name: str,
) -> None:
    legacy_fields = (
        "source",
        "username_source",
        "password_source",
        "username",
        "password",
        "credential_binding",
        "credential_binding_ref",
        "binding_id",
        "username_binding",
        "password_binding",
    )
    for field_name in legacy_fields:
        if value.get(field_name) is not None:
            raise ValueError(
                f"OpenAPI provider '{provider_name}' credential binding "
                f"'{scheme_name}' must use Access credential binding ids; "
                f"field '{field_name}' is no longer accepted.",
            )
    for field_name in (
        "credential_binding_id",
        "username_binding_id",
        "password_binding_id",
    ):
        candidate = value.get(field_name)
        if candidate is None:
            continue
        _reject_direct_openapi_credential_source(
            str(candidate),
            provider_name=provider_name,
            scheme_name=scheme_name,
            field_name=field_name,
        )


def _reject_direct_openapi_credential_source(
    value: str,
    *,
    provider_name: str,
    scheme_name: str,
    field_name: str,
) -> None:
    normalized = value.strip()
    if normalized.startswith(("env:", "file:", "codex_auth_json", "codex-cli")):
        raise ValueError(
            f"OpenAPI provider '{provider_name}' credential binding '{scheme_name}' "
            f"field '{field_name}' must reference an Access credential binding id, "
            "not a direct credential source.",
        )


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

        transport = str(item.get("transport") or "stdio").strip().lower()
        endpoint_url = item.get("endpoint_url")
        if endpoint_url is not None and not isinstance(endpoint_url, str):
            raise ValueError(
                f"MCP provider '{name}' endpoint_url must be a string when provided.",
            )
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
        elif transport == "http":
            command_parts = ()
        else:
            raise ValueError(
                f"MCP provider '{name}' must define command as a string or list.",
            )

        if transport == "stdio" and not command_parts:
            raise ValueError(f"MCP provider '{name}' command cannot be empty.")

        providers.append(
            McpProviderSettings(
                name=name,
                command=command_parts,
                transport=transport,
                endpoint_url=endpoint_url,
                description=str(item.get("description", "")).strip(),
                timeout_seconds=max(int(item.get("timeout_seconds", 30)), 1),
                max_concurrency=_optional_positive_int(
                    item.get("max_concurrency"),
                    label=f"MCP provider '{name}' max_concurrency",
                ),
                default_effect_ids=tuple(
                    str(part).strip()
                    for part in item.get("default_effect_ids", []) or []
                    if str(part).strip()
                ),
                runtime_requirements=tuple(
                    str(part).strip()
                    for part in item.get("runtime_requirements", []) or []
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


def _load_llm_request_defaults_settings() -> LlmRequestDefaultsSettings:
    raw = os.getenv("APP_LLM_REQUEST_DEFAULTS", "").strip()
    if not raw:
        return LlmRequestDefaultsSettings()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("APP_LLM_REQUEST_DEFAULTS must decode to a JSON object.")
    extra_body = _coerce_object_payload(
        payload.get("extra_body", {}),
        source_description="APP_LLM_REQUEST_DEFAULTS.extra_body",
    )
    return LlmRequestDefaultsSettings(
        max_output_tokens=_optional_positive_int(
            payload.get("max_output_tokens"),
            label="APP_LLM_REQUEST_DEFAULTS.max_output_tokens",
        ),
        reasoning_effort=_optional_env_text(payload.get("reasoning_effort")),
        service_tier=_optional_env_text(payload.get("service_tier")),
        prompt_cache_enabled=_optional_bool(payload.get("prompt_cache_enabled")),
        parallel_tool_calls=_optional_bool(payload.get("parallel_tool_calls")),
        trace_raw_provider_payload=bool(
            payload.get("trace_raw_provider_payload", False),
        ),
        reasoning_summary_default_visibility=(
            _optional_env_text(payload.get("reasoning_summary_default_visibility"))
            or "model_and_user_visible"
        ),
        extra_body=extra_body,
    )


def _load_channel_profile_settings() -> tuple[ChannelProfile, ...]:
    profiles_by_type: dict[str, ChannelProfile] = {}

    for config_path in _iter_channel_profile_config_paths():
        for profile in _load_channel_profile_settings_from_path(config_path):
            profiles_by_type[profile.channel_type.strip().lower()] = profile

    raw = os.getenv("APP_CHANNEL_PROFILES")
    if raw is None or not raw.strip():
        return tuple(profiles_by_type.values())

    payload = json.loads(raw)
    items = _coerce_channel_profile_items(
        payload,
        source_description="APP_CHANNEL_PROFILES",
    )
    for item in items:
        profile = _build_channel_profile_settings(
            item,
            source_description="APP_CHANNEL_PROFILES",
        )
        profiles_by_type[profile.channel_type.strip().lower()] = profile

    return tuple(profiles_by_type.values())


def _iter_channel_profile_config_paths() -> tuple[Path, ...]:
    raw = os.getenv("APP_CHANNEL_PROFILE_PATHS", "").strip()
    if raw:
        configured_paths = [
            Path(part.strip()).expanduser()
            for part in raw.split(os.pathsep)
            if part.strip()
        ]
    elif DEFAULT_CHANNEL_PROFILE_DIR.exists():
        configured_paths = [DEFAULT_CHANNEL_PROFILE_DIR]
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


def _load_channel_profile_settings_from_path(
    config_path: Path,
) -> tuple[ChannelProfile, ...]:
    payload = _load_structured_config(config_path)
    items = _coerce_channel_profile_items(payload, source_description=str(config_path))
    return tuple(
        _build_channel_profile_settings(item, source_description=str(config_path))
        for item in items
    )


def _coerce_channel_profile_items(
    payload: object,
    *,
    source_description: str,
) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if isinstance(payload.get("profiles"), list):
            items = payload.get("profiles") or []
        else:
            items = [payload]
    elif isinstance(payload, list):
        items = payload
    else:
        raise ValueError(
            f"{source_description} channel profile config must decode to an object or list.",
        )
    resolved: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(
                f"{source_description} channel profile items must decode to JSON/YAML objects.",
            )
        resolved.append(dict(item))
    return resolved


def _build_channel_profile_settings(
    raw: object,
    *,
    source_description: str,
) -> ChannelProfile:
    from crxzipple.modules.channels.domain.value_objects import (
        ChannelCapabilities,
        ChannelProfile,
    )

    if not isinstance(raw, dict):
        raise ValueError(
            f"{source_description} channel profile items must decode to JSON/YAML objects.",
        )
    channel_type = str(raw.get("channel_type") or "").strip()
    if not channel_type:
        raise ValueError(f"{source_description} channel profile must define channel_type.")

    raw_capabilities = raw.get("capabilities")
    if raw_capabilities is None:
        capabilities = ChannelCapabilities()
    elif isinstance(raw_capabilities, dict):
        capabilities = ChannelCapabilities.from_payload(dict(raw_capabilities))
    else:
        raise ValueError(
            f"{source_description} channel profile '{channel_type}' capabilities must decode to an object.",
        )

    raw_accounts = raw.get("accounts")
    if raw_accounts is None:
        accounts = ()
    elif isinstance(raw_accounts, list):
        accounts = tuple(
            _build_channel_account_profile_settings(
                item,
                source_description=source_description,
                channel_type=channel_type,
                index=index,
            )
            for index, item in enumerate(raw_accounts)
        )
    else:
        raise ValueError(
            f"{source_description} channel profile '{channel_type}' accounts must decode to a list.",
        )

    raw_metadata = raw.get("metadata")
    if raw_metadata is None:
        metadata: dict[str, Any] = {}
    elif isinstance(raw_metadata, dict):
        metadata = dict(raw_metadata)
    else:
        raise ValueError(
            f"{source_description} channel profile '{channel_type}' metadata must decode to an object.",
        )

    return ChannelProfile(
        channel_type=channel_type,
        enabled=bool(raw.get("enabled", True)),
        capabilities=capabilities,
        accounts=accounts,
        metadata=metadata,
    )


def _build_channel_account_profile_settings(
    raw: object,
    *,
    source_description: str,
    channel_type: str,
    index: int,
) -> ChannelAccountProfile:
    from crxzipple.modules.channels.domain.value_objects import ChannelAccountProfile

    if not isinstance(raw, dict):
        raise ValueError(
            f"{source_description} channel profile '{channel_type}' accounts[{index}] must decode to an object.",
        )
    account_id = str(raw.get("account_id") or "").strip()
    if not account_id:
        raise ValueError(
            f"{source_description} channel profile '{channel_type}' accounts[{index}] must define account_id.",
        )
    raw_metadata = raw.get("metadata")
    if raw_metadata is None:
        metadata: dict[str, Any] = {}
    elif isinstance(raw_metadata, dict):
        metadata = dict(raw_metadata)
    else:
        raise ValueError(
            f"{source_description} channel profile '{channel_type}' accounts[{index}] metadata must decode to an object.",
        )
    return ChannelAccountProfile.from_payload(
        {
            **raw,
            "account_id": account_id,
            "enabled": bool(raw.get("enabled", True)),
            "transport_mode": str(raw.get("transport_mode") or "push"),
            "metadata": metadata,
        },
        channel_type=channel_type,
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
        max_concurrency=_optional_positive_int(
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
    llm_policy = _coerce_object_payload(
        raw.get("llm_policy", {}),
        source_description=f"Agent profile '{profile_id}' llm_policy",
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
    memory = _coerce_object_payload(
        raw.get("memory", {}),
        source_description=f"Agent profile '{profile_id}' memory",
    )
    return AgentProfileSettings(
        id=profile_id,
        name=name,
        enabled=bool(raw.get("enabled", True)),
        identity=identity,
        instruction_policy=instruction_policy,
        llm_routing_policy=llm_routing_policy,
        llm_policy=llm_policy,
        execution_policy=execution_policy,
        runtime_preferences=runtime_preferences,
        memory=memory,
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
    allow_sqlite_runtime_fallback: bool = False
    tool_local_paths: tuple[str, ...] = ()
    tool_openapi_providers: tuple[OpenApiProviderSettings, ...] = ()
    tool_mcp_providers: tuple[McpProviderSettings, ...] = ()
    llm_profiles: tuple[LlmProfileSettings, ...] = ()
    llm_request_defaults: LlmRequestDefaultsSettings = field(
        default_factory=LlmRequestDefaultsSettings,
    )
    channel_profiles: tuple[ChannelProfile, ...] = ()
    agent_profiles: tuple[AgentProfileSettings, ...] = ()
    authorization_enabled: bool = True
    authorization_policy_paths: tuple[str, ...] = ()
    authorization_runtime_policy_path: str = str(DEFAULT_AUTHORIZATION_RUNTIME_POLICY_PATH)
    memory_retrieval_backend: str = "keyword"
    memory_storage_root: str = str(DEFAULT_MEMORY_STATE_DIR)
    memory_vector_provider: str = "local"
    memory_vector_model: str | None = None
    memory_vector_base_url: str | None = None
    memory_vector_credential_binding_id: str | None = None
    memory_vector_timeout_seconds: int = 30
    memory_watch_interval_seconds: float = 300.0
    browser_enabled: bool = True
    browser_profiles: tuple[BrowserProfileSettings, ...] = field(
        default_factory=lambda: (
            BrowserProfileSettings(name=DEFAULT_BROWSER_DEFAULT_PROFILE_NAME),
        ),
    )
    browser_proxy_base_urls: tuple[BrowserProxyEndpointSettings, ...] = ()
    browser_state_dir: str = str(DEFAULT_BROWSER_STATE_DIR)
    mobile_enabled: bool = True
    mobile_devices: tuple[MobileDeviceSettings, ...] = ()
    mobile_state_dir: str = str(DEFAULT_MOBILE_STATE_DIR)
    ocr_enabled: bool = True
    ocr_backend: str = DEFAULT_OCR_BACKEND
    ocr_provider: str = DEFAULT_OCR_PROVIDER
    ocr_host: str = DEFAULT_OCR_HOST
    ocr_port: int = DEFAULT_OCR_PORT
    ocr_base_url: str = f"http://{DEFAULT_OCR_HOST}:{DEFAULT_OCR_PORT}"
    ocr_language: str = "ch"
    ocr_use_gpu: bool = False
    ocr_request_timeout_seconds: float = 60.0
    daemon_state_dir: str = str(DEFAULT_DAEMON_STATE_DIR)
    events_state_dir: str = str(DEFAULT_EVENTS_STATE_DIR)
    operations_state_dir: str = str(DEFAULT_OPERATIONS_STATE_DIR)
    events_backend: Literal["file", "redis"] = "redis"
    events_file_sync_writes: bool = False
    events_redis_url: str | None = DEFAULT_EVENTS_REDIS_URL
    events_redis_key_prefix: str = "crx:events"
    events_redis_block_ms: int = 1000
    events_redis_dedupe_ttl_seconds: int = 3600
    channels_state_dir: str = str(DEFAULT_CHANNELS_STATE_DIR)
    access_state_dir: str = str(DEFAULT_ACCESS_STATE_DIR)
    mobile_adb_binary: str = "adb"
    artifact_store_dir: str = str(DEFAULT_ARTIFACT_STORE_DIR)
    artifact_image_preview_max_dimension: int = 1024
    artifact_image_llm_max_dimension: int = 1568
    artifact_image_llm_max_bytes: int = 1_500_000
    artifact_file_llm_max_bytes: int = 4_000_000
    artifact_text_file_llm_max_chars: int = 20_000
    tool_details_max_chars: int = 131_072
    tool_remote_default_max_concurrency: int = 16
    browser_executable_path: str | None = None
    browser_sandbox_executable_path: str | None = None
    browser_proxy_base_url: str | None = None
    browser_proxy_egress_check_url: str | None = None
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
    orchestration_executor_max_concurrent_assignments: int = 4
    orchestration_detailed_engine_metrics_enabled: bool = False
    orchestration_auto_compaction_enabled: bool = True
    orchestration_auto_compaction_reserve_tokens: int = 20_000
    orchestration_auto_compaction_soft_threshold_tokens: int = 4_000
    tool_run_max_attempts: int = 3
    tool_run_lease_seconds: int = 30
    tool_run_heartbeat_seconds: float = 5.0
    tool_worker_max_in_flight: int = 4
    tool_worker_default_run_concurrency: int = 4
    tool_worker_image_run_concurrency: int = 4
    tool_worker_shared_state_run_concurrency: int = 1

    def __post_init__(self) -> None:
        profiles = _ensure_default_user_browser_profile_settings(
            self.browser_profiles,
        )
        object.__setattr__(
            self,
            "browser_profiles",
            profiles,
        )

    @property
    def browser_profile_specs(self) -> tuple[BrowserProfileSettings, ...]:
        return self.browser_profiles


def load_settings() -> Settings:
    browser_profiles = _load_browser_profile_settings()
    ocr_backend = _load_ocr_backend()
    ocr_provider = _load_ocr_provider()
    ocr_host = os.getenv("APP_OCR_HOST", DEFAULT_OCR_HOST).strip() or DEFAULT_OCR_HOST
    ocr_port = max(int(os.getenv("APP_OCR_PORT", str(DEFAULT_OCR_PORT))), 1)
    tool_worker_max_in_flight = max(
        int(os.getenv("APP_TOOL_WORKER_MAX_IN_FLIGHT", "4")),
        1,
    )
    tool_worker_default_run_concurrency = max(
        int(
            os.getenv(
                "APP_TOOL_WORKER_DEFAULT_RUN_CONCURRENCY",
                str(tool_worker_max_in_flight),
            ),
        ),
        1,
    )
    tool_worker_image_run_concurrency = max(
        int(
            os.getenv(
                "APP_TOOL_WORKER_IMAGE_RUN_CONCURRENCY",
                str(tool_worker_max_in_flight),
            ),
        ),
        1,
    )
    tool_worker_shared_state_run_concurrency = max(
        int(os.getenv("APP_TOOL_WORKER_SHARED_STATE_RUN_CONCURRENCY", "1")),
        1,
    )
    if ocr_backend == "local" and ocr_provider != "host":
        raise ValueError(
            "APP_OCR_PROVIDER must be 'host' when APP_OCR_BACKEND=local.",
        )
    return Settings(
        app_name=os.getenv("APP_NAME", "crxzipple"),
        environment=os.getenv("APP_ENV", "local"),
        database_url=os.getenv("APP_DATABASE_URL", "sqlite:///./crxzipple.db"),
        allow_sqlite_runtime_fallback=_runtime_sqlite_fallback_enabled(),
        tool_local_paths=_load_tool_local_paths(),
        tool_openapi_providers=_load_openapi_provider_settings(),
        tool_mcp_providers=_load_mcp_provider_settings(),
        llm_profiles=_load_llm_profile_settings(),
        llm_request_defaults=_load_llm_request_defaults_settings(),
        channel_profiles=_load_channel_profile_settings(),
        agent_profiles=_load_agent_profile_settings(),
        authorization_enabled=_env_flag("APP_AUTHORIZATION_ENABLED", default=True),
        authorization_policy_paths=tuple(
            str(path) for path in _iter_authorization_policy_paths()
        ),
        authorization_runtime_policy_path=str(_authorization_runtime_policy_path()),
        memory_retrieval_backend=_load_memory_retrieval_backend(),
        memory_storage_root=os.getenv(
            "APP_MEMORY_STORAGE_ROOT",
            str(DEFAULT_MEMORY_STATE_DIR),
        ),
        memory_vector_provider=_load_memory_vector_provider(),
        memory_vector_model=(
            os.getenv("APP_MEMORY_VECTOR_MODEL", "").strip() or None
        ),
        memory_vector_base_url=(
            os.getenv("APP_MEMORY_VECTOR_BASE_URL", "").strip() or None
        ),
        memory_vector_credential_binding_id=(
            os.getenv("APP_MEMORY_VECTOR_CREDENTIAL_BINDING_ID", "").strip() or None
        ),
        memory_vector_timeout_seconds=_load_memory_vector_timeout_seconds(),
        memory_watch_interval_seconds=_load_memory_watch_interval_seconds(),
        browser_enabled=_env_flag("APP_BROWSER_ENABLED", default=True),
        browser_profiles=browser_profiles,
        browser_proxy_base_urls=tuple(
            BrowserProxyEndpointSettings(profile=profile, base_url=base_url)
            for profile, base_url in _load_browser_proxy_base_urls()
        ),
        browser_state_dir=os.getenv(
            "APP_BROWSER_STATE_DIR",
            str(DEFAULT_BROWSER_STATE_DIR),
        ),
        mobile_enabled=_env_flag("APP_MOBILE_ENABLED", default=True),
        mobile_devices=_load_mobile_device_settings(),
        mobile_state_dir=os.getenv(
            "APP_MOBILE_STATE_DIR",
            str(DEFAULT_MOBILE_STATE_DIR),
        ),
        ocr_enabled=_env_flag("APP_OCR_ENABLED", default=True),
        ocr_backend=ocr_backend,
        ocr_provider=ocr_provider,
        ocr_host=ocr_host,
        ocr_port=ocr_port,
        ocr_base_url=_resolve_ocr_base_url(
            backend=ocr_backend,
            host=ocr_host,
            port=ocr_port,
        ),
        ocr_language=os.getenv("APP_OCR_LANGUAGE", "ch").strip() or "ch",
        ocr_use_gpu=_env_flag("APP_OCR_USE_GPU", default=False),
        ocr_request_timeout_seconds=max(
            float(os.getenv("APP_OCR_REQUEST_TIMEOUT_SECONDS", "60")),
            0.1,
        ),
        daemon_state_dir=os.getenv(
            "APP_DAEMON_STATE_DIR",
            str(DEFAULT_DAEMON_STATE_DIR),
        ),
        events_state_dir=os.getenv(
            "APP_EVENTS_STATE_DIR",
            str(DEFAULT_EVENTS_STATE_DIR),
        ),
        operations_state_dir=os.getenv(
            "APP_OPERATIONS_STATE_DIR",
            str(DEFAULT_OPERATIONS_STATE_DIR),
        ),
        events_backend=_load_events_backend(),
        events_file_sync_writes=_env_flag(
            "APP_EVENTS_FILE_SYNC_WRITES",
            default=False,
        ),
        events_redis_url=(
            os.getenv(
                "APP_EVENTS_REDIS_URL",
                DEFAULT_EVENTS_REDIS_URL,
            ).strip()
            or DEFAULT_EVENTS_REDIS_URL
        ),
        events_redis_key_prefix=(
            os.getenv("APP_EVENTS_REDIS_KEY_PREFIX", "crx:events").strip()
            or "crx:events"
        ),
        events_redis_block_ms=max(
            int(os.getenv("APP_EVENTS_REDIS_BLOCK_MS", "1000")),
            1,
        ),
        events_redis_dedupe_ttl_seconds=max(
            int(os.getenv("APP_EVENTS_REDIS_DEDUPE_TTL_SECONDS", "3600")),
            1,
        ),
        channels_state_dir=os.getenv(
            "APP_CHANNELS_STATE_DIR",
            str(DEFAULT_CHANNELS_STATE_DIR),
        ),
        access_state_dir=os.getenv(
            "APP_ACCESS_STATE_DIR",
            str(DEFAULT_ACCESS_STATE_DIR),
        ),
        mobile_adb_binary=os.getenv("APP_MOBILE_ADB_BINARY", "adb").strip() or "adb",
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
        tool_remote_default_max_concurrency=max(
            int(os.getenv("APP_TOOL_REMOTE_DEFAULT_MAX_CONCURRENCY", "16")),
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
        browser_proxy_egress_check_url=(
            os.getenv("APP_BROWSER_PROXY_EGRESS_CHECK_URL", "").strip() or None
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
        orchestration_executor_max_concurrent_assignments=max(
            int(
                os.getenv(
                    "APP_ORCHESTRATION_EXECUTOR_MAX_CONCURRENT_ASSIGNMENTS",
                    "4",
                ),
            ),
            1,
        ),
        orchestration_detailed_engine_metrics_enabled=_env_flag(
            "APP_ORCHESTRATION_DETAILED_ENGINE_METRICS_ENABLED",
            default=False,
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
        tool_worker_max_in_flight=tool_worker_max_in_flight,
        tool_worker_default_run_concurrency=tool_worker_default_run_concurrency,
        tool_worker_image_run_concurrency=tool_worker_image_run_concurrency,
        tool_worker_shared_state_run_concurrency=tool_worker_shared_state_run_concurrency,
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
