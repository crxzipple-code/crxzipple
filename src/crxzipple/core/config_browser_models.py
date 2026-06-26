from __future__ import annotations

from dataclasses import dataclass
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
            normalize_browser_profile_name(
                self.name,
                label="Browser profile name",
            ),
        )
        object.__setattr__(self, "enabled", bool(self.enabled))
        driver = normalize_browser_profile_driver(
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
            normalize_browser_profile_color(self.color),
        )
        if driver == "existing-session" and not self.attach_only:
            object.__setattr__(self, "attach_only", True)
        if self.attach_only or driver == "existing-session":
            object.__setattr__(self, "autostart", False)
        if proxy_mode == "static" and not normalized_proxy_server:
            raise ValueError(
                f"Browser profile '{self.name}' proxy_server is required when proxy_mode is static.",
            )
        if proxy_mode == "static" and proxy_server_has_credentials(
            normalized_proxy_server,
        ):
            raise ValueError(
                f"Browser profile '{self.name}' proxy_server must not contain credentials; use proxy_mode access_binding.",
            )
        if proxy_mode == "access_binding" and not normalized_proxy_binding_id:
            raise ValueError(
                f"Browser profile '{self.name}' proxy_binding_id is required when proxy_mode is access_binding.",
            )


def normalize_browser_profile_name(value: str, *, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} must be a non-empty profile name.")
    if any(separator in normalized for separator in ("/", "\\")):
        raise ValueError(f"{label} must not contain path separators.")
    return normalized


def normalize_browser_profile_driver(value: str, *, label: str) -> str:
    normalized = value.strip().lower()
    if normalized in _ALLOWED_BROWSER_PROFILE_DRIVERS:
        return normalized
    raise ValueError(f"{label} must be one of: managed, existing-session.")


def normalize_browser_profile_color(value: str | None) -> str:
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


def proxy_server_has_credentials(value: str | None) -> bool:
    normalized = (value or "").strip()
    if not normalized:
        return False
    parsed = urlsplit(normalized)
    return bool(parsed.username or parsed.password)
