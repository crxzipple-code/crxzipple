from __future__ import annotations

from dataclasses import dataclass
import json
import os
from urllib.parse import urlsplit

DEFAULT_BROWSER_DEFAULT_PROFILE_NAME = "crxzipple"
DEFAULT_BROWSER_USER_PROFILE_NAME = "user"
DEFAULT_BROWSER_USER_CDP_URL = "http://127.0.0.1:9222"
DEFAULT_BROWSER_PROFILE_COLOR = "#2563EB"

_ALLOWED_BROWSER_PROFILE_DRIVERS = {"managed", "existing-session"}
_ALLOWED_BROWSER_PROXY_CREDENTIAL_KINDS = {"basic", "bearer_token"}


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


def load_browser_profile_settings() -> tuple[BrowserProfileSettings, ...]:
    raw = os.getenv("APP_BROWSER_PROFILE_SPECS", "").strip()
    if not raw:
        return ensure_default_user_browser_profile_settings(
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
        resolved_profiles.append(_browser_profile_from_item(item, index=index, seen=seen))
    if not resolved_profiles:
        raise ValueError("APP_BROWSER_PROFILE_SPECS must contain at least one profile.")
    return ensure_default_user_browser_profile_settings(tuple(resolved_profiles))


def load_browser_proxy_base_urls() -> tuple[tuple[str, str], ...]:
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


def ensure_default_user_browser_profile_settings(
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


def _browser_profile_from_item(
    item: dict[str, object],
    *,
    index: int,
    seen: set[str],
) -> BrowserProfileSettings:
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
    driver = _profile_driver_from_item(item, index=index)
    _reject_removed_profile_fields(item, index=index)
    return BrowserProfileSettings(
        name=name,
        cdp_url=_optional_profile_string(item, "cdp_url", index=index),
        cdp_port=_optional_profile_int(item, "cdp_port", index=index),
        user_data_dir=_optional_profile_string(item, "user_data_dir", index=index),
        profile_directory=_optional_profile_string(
            item,
            "profile_directory",
            index=index,
        ),
        driver=driver,
        enabled=_optional_profile_bool(item, "enabled", index=index, default=True),
        attach_only=_optional_profile_bool(
            item,
            "attach_only",
            index=index,
            default=False,
        ),
        autostart=_optional_profile_bool(
            item,
            "autostart",
            index=index,
            default=True,
        ),
        proxy_mode=_optional_profile_string(item, "proxy_mode", index=index) or "none",
        proxy_server=_optional_profile_string(item, "proxy_server", index=index),
        proxy_bypass_list=_optional_profile_string_tuple(
            item,
            "proxy_bypass_list",
            index=index,
        ),
        proxy_binding_id=_optional_profile_string(
            item,
            "proxy_binding_id",
            index=index,
        ),
        proxy_credential_kind=(
            _optional_profile_string(item, "proxy_credential_kind", index=index)
            or "basic"
        ),
        close_targets_on_release=_optional_profile_bool(
            item,
            "close_targets_on_release",
            index=index,
            default=True,
        ),
        close_targets_on_expire=_optional_profile_bool(
            item,
            "close_targets_on_expire",
            index=index,
            default=True,
        ),
        color=_optional_profile_string(item, "color", index=index),
    )


def _profile_driver_from_item(item: dict[str, object], *, index: int) -> str:
    raw_driver = item.get("driver")
    if raw_driver is None:
        return "managed"
    if not isinstance(raw_driver, str):
        raise ValueError(
            f"APP_BROWSER_PROFILE_SPECS[{index}].driver must be a string.",
        )
    return _normalize_browser_profile_driver(
        raw_driver,
        label=f"APP_BROWSER_PROFILE_SPECS[{index}].driver",
    )


def _reject_removed_profile_fields(item: dict[str, object], *, index: int) -> None:
    removed = {
        "runtime_mode": (
            "runtime_mode has been removed; use driver, cdp_url, attach_only, "
            "autostart, and proxy_* fields."
        ),
        "transport": (
            "transport has been removed; use driver, cdp_url, attach_only, "
            "autostart, and proxy_* fields."
        ),
        "executable_path": (
            "executable_path has been removed; use APP_BROWSER_EXECUTABLE_PATH "
            "for the Browser system executable."
        ),
        "headless": (
            "headless has been removed; use APP_BROWSER_HEADLESS for the Browser "
            "system headless mode."
        ),
    }
    for field_name, message in removed.items():
        if field_name in item:
            raise ValueError(f"APP_BROWSER_PROFILE_SPECS[{index}].{message}")


def _optional_profile_string(
    item: dict[str, object],
    field_name: str,
    *,
    index: int,
) -> str | None:
    raw = item.get(field_name)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError(
            f"APP_BROWSER_PROFILE_SPECS[{index}].{field_name} must be a string when provided.",
        )
    return raw.strip()


def _optional_profile_int(
    item: dict[str, object],
    field_name: str,
    *,
    index: int,
) -> int | None:
    raw = item.get(field_name)
    if raw is None:
        return None
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise ValueError(
            f"APP_BROWSER_PROFILE_SPECS[{index}].{field_name} must be an integer when provided.",
        )
    return raw


def _optional_profile_bool(
    item: dict[str, object],
    field_name: str,
    *,
    index: int,
    default: bool,
) -> bool:
    raw = item.get(field_name)
    if raw is None:
        return default
    if not isinstance(raw, bool):
        raise ValueError(
            f"APP_BROWSER_PROFILE_SPECS[{index}].{field_name} must be a boolean when provided.",
        )
    return raw


def _optional_profile_string_tuple(
    item: dict[str, object],
    field_name: str,
    *,
    index: int,
) -> tuple[str, ...]:
    raw = item.get(field_name)
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(entry, str) for entry in raw):
        raise ValueError(
            f"APP_BROWSER_PROFILE_SPECS[{index}].{field_name} must be a string array when provided.",
        )
    return tuple(raw)


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
