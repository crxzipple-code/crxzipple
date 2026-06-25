from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .exceptions import BrowserValidationError
from .value_helpers import (
    _normalize_mapping,
    _normalize_optional_text,
    _normalize_pool_id,
    _normalize_profile_directory,
    _normalize_profile_name,
    _normalize_profile_name_tuple,
    _normalize_proxy_bypass_list,
    _normalize_target_hosts,
    _proxy_server_has_credentials,
    _require_non_negative_int,
    _require_positive_int,
    _require_positive_port,
)
from .value_types import (
    BrowserActionFamily,
    BrowserControlFamily,
    BrowserProfileDriver,
    BrowserProfileMode,
    BrowserProfilePoolSelectionStrategy,
    BrowserProfileProxyMode,
    BrowserProxyCredentialKind,
)


@dataclass(frozen=True, slots=True)
class BrowserProfileConfig:
    name: str
    driver: BrowserProfileDriver = "managed"
    enabled: bool = True
    cdp_url: str | None = None
    cdp_port: int | None = None
    user_data_dir: str | None = None
    profile_directory: str | None = None
    attach_only: bool = False
    autostart: bool = True
    proxy_mode: BrowserProfileProxyMode = "none"
    proxy_server: str | None = None
    proxy_bypass_list: tuple[str, ...] = ()
    proxy_binding_id: str | None = None
    proxy_credential_kind: BrowserProxyCredentialKind = "basic"
    close_targets_on_release: bool = True
    close_targets_on_expire: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _normalize_profile_name(self.name))
        object.__setattr__(self, "enabled", bool(self.enabled))
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
        object.__setattr__(self, "cdp_url", _normalize_optional_text(self.cdp_url))
        object.__setattr__(
            self,
            "user_data_dir",
            _normalize_optional_text(self.user_data_dir),
        )
        object.__setattr__(
            self,
            "profile_directory",
            _normalize_profile_directory(self.profile_directory),
        )
        object.__setattr__(
            self,
            "cdp_port",
            _require_positive_port(self.cdp_port, label="cdp_port"),
        )
        proxy_mode = str(self.proxy_mode).strip().lower()
        if proxy_mode not in {"none", "static", "access_binding"}:
            raise BrowserValidationError(
                "proxy_mode must be one of: access_binding, none, static.",
            )
        object.__setattr__(self, "proxy_mode", proxy_mode)
        object.__setattr__(
            self, "proxy_server", _normalize_optional_text(self.proxy_server)
        )
        object.__setattr__(
            self,
            "proxy_bypass_list",
            _normalize_proxy_bypass_list(self.proxy_bypass_list),
        )
        object.__setattr__(
            self,
            "proxy_binding_id",
            _normalize_optional_text(self.proxy_binding_id),
        )
        proxy_credential_kind = str(self.proxy_credential_kind).strip().lower()
        if proxy_credential_kind == "bearer":
            proxy_credential_kind = "bearer_token"
        if proxy_credential_kind not in {"basic", "bearer_token"}:
            raise BrowserValidationError(
                "proxy_credential_kind must be one of: basic, bearer_token.",
            )
        object.__setattr__(self, "proxy_credential_kind", proxy_credential_kind)
        if self.driver not in {"managed", "existing-session"}:
            raise BrowserValidationError(
                f"Unsupported browser profile driver '{self.driver}'.",
            )
        if self.driver == "existing-session":
            object.__setattr__(self, "attach_only", True)
        if self.attach_only or self.driver == "existing-session":
            object.__setattr__(self, "autostart", False)
        if self.proxy_mode == "static" and self.proxy_server is None:
            raise BrowserValidationError(
                "proxy_server is required when proxy_mode is static."
            )
        if self.proxy_mode == "static" and _proxy_server_has_credentials(
            self.proxy_server
        ):
            raise BrowserValidationError(
                "proxy_server must not contain credentials; use proxy_mode access_binding.",
            )
        if self.proxy_mode == "access_binding" and self.proxy_binding_id is None:
            raise BrowserValidationError(
                "proxy_binding_id is required when proxy_mode is access_binding.",
            )


@dataclass(frozen=True, slots=True)
class BrowserSystemConfig:
    default_profile: str
    profiles: tuple[BrowserProfileConfig, ...] = ()
    headless: bool = False
    executable_path: str | None = None
    no_sandbox: bool = False
    managed_tab_limit: int | None = None
    cdp_host: str = "127.0.0.1"
    cdp_port_range_start: int = 9222
    cdp_port_range_end: int = 9322

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "default_profile",
            _normalize_profile_name(self.default_profile),
        )
        object.__setattr__(
            self,
            "executable_path",
            _normalize_optional_text(self.executable_path),
        )
        object.__setattr__(
            self,
            "cdp_host",
            _normalize_optional_text(self.cdp_host) or "127.0.0.1",
        )
        object.__setattr__(
            self,
            "managed_tab_limit",
            _require_positive_port(
                self.managed_tab_limit,
                label="managed_tab_limit",
            ),
        )
        object.__setattr__(
            self,
            "cdp_port_range_start",
            _require_positive_port(
                self.cdp_port_range_start,
                label="cdp_port_range_start",
            )
            or 9222,
        )
        object.__setattr__(
            self,
            "cdp_port_range_end",
            _require_positive_port(
                self.cdp_port_range_end,
                label="cdp_port_range_end",
            )
            or 9322,
        )
        if self.cdp_port_range_end < self.cdp_port_range_start:
            raise BrowserValidationError(
                "cdp_port_range_end must be greater than or equal to cdp_port_range_start.",
            )


@dataclass(frozen=True, slots=True)
class BrowserProfilePool:
    pool_id: str
    display_name: str | None = None
    enabled: bool = True
    profile_names: tuple[str, ...] = ()
    target_hosts: tuple[str, ...] = ()
    selection_strategy: BrowserProfilePoolSelectionStrategy = "least_busy"
    max_concurrency_per_profile: int = 1
    max_concurrency_total: int | None = None
    allocation_ttl_seconds: int = 900
    cooldown_seconds: int = 0
    failure_cooldown_seconds: int = 300
    allow_attach_only: bool = False
    close_targets_on_release: bool = True
    close_targets_on_expire: bool = True
    health_policy: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "pool_id", _normalize_pool_id(self.pool_id))
        object.__setattr__(
            self, "display_name", _normalize_optional_text(self.display_name)
        )
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(
            self,
            "profile_names",
            _normalize_profile_name_tuple(self.profile_names),
        )
        object.__setattr__(
            self,
            "target_hosts",
            _normalize_target_hosts(self.target_hosts),
        )
        strategy = str(self.selection_strategy).strip().lower()
        if strategy not in {
            "round_robin",
            "least_busy",
            "sticky_session",
            "manual_only",
        }:
            raise BrowserValidationError(
                "selection_strategy must be one of: least_busy, manual_only, round_robin, sticky_session.",
            )
        object.__setattr__(self, "selection_strategy", strategy)
        object.__setattr__(
            self,
            "max_concurrency_per_profile",
            _require_positive_int(
                self.max_concurrency_per_profile,
                label="max_concurrency_per_profile",
            )
            or 1,
        )
        object.__setattr__(
            self,
            "max_concurrency_total",
            _require_positive_int(
                self.max_concurrency_total,
                label="max_concurrency_total",
            ),
        )
        object.__setattr__(
            self,
            "allocation_ttl_seconds",
            _require_positive_int(
                self.allocation_ttl_seconds,
                label="allocation_ttl_seconds",
            )
            or 900,
        )
        object.__setattr__(
            self,
            "cooldown_seconds",
            _require_non_negative_int(self.cooldown_seconds, label="cooldown_seconds"),
        )
        object.__setattr__(
            self,
            "failure_cooldown_seconds",
            _require_non_negative_int(
                self.failure_cooldown_seconds,
                label="failure_cooldown_seconds",
            ),
        )
        object.__setattr__(self, "allow_attach_only", bool(self.allow_attach_only))
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
            self, "health_policy", _normalize_mapping(self.health_policy)
        )
        object.__setattr__(self, "metadata", _normalize_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class ResolvedBrowserProfile:
    name: str
    driver: BrowserProfileDriver
    cdp_url: str | None
    cdp_port: int | None
    user_data_dir: str | None
    attach_only: bool
    is_loopback: bool
    enabled: bool = True
    profile_directory: str | None = None
    autostart: bool = True
    proxy_mode: BrowserProfileProxyMode = "none"
    proxy_server: str | None = None
    proxy_bypass_list: tuple[str, ...] = ()
    proxy_binding_id: str | None = None
    proxy_credential_kind: BrowserProxyCredentialKind = "basic"

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _normalize_profile_name(self.name))
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(self, "cdp_url", _normalize_optional_text(self.cdp_url))
        object.__setattr__(
            self,
            "user_data_dir",
            _normalize_optional_text(self.user_data_dir),
        )
        object.__setattr__(
            self,
            "profile_directory",
            _normalize_profile_directory(self.profile_directory),
        )
        object.__setattr__(
            self,
            "cdp_port",
            _require_positive_port(self.cdp_port, label="cdp_port"),
        )
        proxy_mode = str(self.proxy_mode).strip().lower()
        if proxy_mode not in {"none", "static", "access_binding"}:
            raise BrowserValidationError(
                "proxy_mode must be one of: access_binding, none, static.",
            )
        object.__setattr__(self, "proxy_mode", proxy_mode)
        object.__setattr__(
            self, "proxy_server", _normalize_optional_text(self.proxy_server)
        )
        object.__setattr__(
            self,
            "proxy_bypass_list",
            _normalize_proxy_bypass_list(self.proxy_bypass_list),
        )
        object.__setattr__(
            self,
            "proxy_binding_id",
            _normalize_optional_text(self.proxy_binding_id),
        )
        proxy_credential_kind = str(self.proxy_credential_kind).strip().lower()
        if proxy_credential_kind == "bearer":
            proxy_credential_kind = "bearer_token"
        if proxy_credential_kind not in {"basic", "bearer_token"}:
            raise BrowserValidationError(
                "proxy_credential_kind must be one of: basic, bearer_token.",
            )
        object.__setattr__(self, "proxy_credential_kind", proxy_credential_kind)
        if self.proxy_mode == "static" and _proxy_server_has_credentials(
            self.proxy_server
        ):
            raise BrowserValidationError(
                "proxy_server must not contain credentials; use proxy_mode access_binding.",
            )
        if self.driver not in {"managed", "existing-session"}:
            raise BrowserValidationError(
                f"Unsupported resolved browser profile driver '{self.driver}'.",
            )
        if self.attach_only or self.driver == "existing-session":
            object.__setattr__(self, "autostart", False)


@dataclass(frozen=True, slots=True)
class BrowserProfileCapabilities:
    mode: BrowserProfileMode
    is_remote: bool
    control_family: BrowserControlFamily
    action_family: BrowserActionFamily
    can_launch: bool
    supports_reset: bool
    supports_per_tab_ws: bool
    supports_json_tab_endpoints: bool
    supports_managed_tab_limit: bool
