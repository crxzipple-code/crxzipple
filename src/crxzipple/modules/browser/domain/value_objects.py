from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, TypeAlias
from urllib.parse import urlsplit

from .exceptions import BrowserValidationError

BrowserProfileDriver: TypeAlias = Literal["managed", "existing-session"]
BrowserProfileProxyMode: TypeAlias = Literal["none", "static", "access_binding"]
BrowserProxyCredentialKind: TypeAlias = Literal["basic", "bearer_token"]
BrowserProfilePoolSelectionStrategy: TypeAlias = Literal[
    "round_robin",
    "least_busy",
    "sticky_session",
    "manual_only",
]
BrowserProfileMode: TypeAlias = Literal[
    "local-managed",
    "local-existing-session",
    "remote-cdp",
]
BrowserControlFamily: TypeAlias = Literal["cdp-control"]
BrowserActionFamily: TypeAlias = Literal["cdp-backed-playwright"]
BrowserLaunchPolicy: TypeAlias = Literal["launch-if-missing", "attach-only"]
BrowserTabSelectionPolicy: TypeAlias = Literal[
    "sticky-last-target",
    "explicit-only",
]
BrowserTabType: TypeAlias = Literal["page", "background", "worker", "other"]
BrowserControlKind: TypeAlias = Literal[
    "status",
    "start",
    "stop",
    "navigate",
    "open-tab",
    "focus-tab",
    "close-tab",
    "list-tabs",
    "reset",
]
BrowserPageActionKind: TypeAlias = Literal[
    "click",
    "console",
    "cookies",
    "dialog",
    "type",
    "press",
    "hover",
    "drag",
    "batch",
    "resize",
    "scroll-into-view",
    "select",
    "fill",
    "upload",
    "download",
    "wait-download",
    "wait",
    "snapshot",
    "screenshot",
    "pdf",
    "evaluate",
    "storage",
    "storage-indexeddb-list",
    "storage-indexeddb-get",
    "storage-indexeddb-query",
    "storage-cache-list",
    "storage-cache-get",
    "service-worker-list",
    "service-worker-inspect",
    "dom-inspect",
    "dom-box-model",
    "dom-computed-style",
    "dom-clickability",
    "dom-highlight",
    "dom-mutation-wait",
    "emulation-set",
    "emulation-reset",
    "permissions-grant",
    "permissions-clear",
    "geolocation-set",
    "network-conditions-set",
    "diagnostics-collect",
    "performance-metrics",
    "trace-start",
    "trace-stop",
    "trace-export",
    "page-lifecycle",
    "page-errors",
    "network-inspect",
    "network-start-capture",
    "network-stop-capture",
    "network-list-requests",
    "network-get-request",
    "network-get-response-body",
    "network-get-request-body",
    "network-fetch-as-page",
    "network-replay-request",
    "network-clear-capture",
    "action-trace",
    "runtime-inspect",
    "script-list",
    "script-find-request",
    "code-search",
    "script-inspect",
    "script-extract-request",
    "runtime-probe-client",
    "runtime-call-client",
    "cdp-raw",
]
BrowserNetworkCaptureStatus: TypeAlias = Literal["active", "stopped"]
BrowserNetworkBodyKind: TypeAlias = Literal["request", "response"]


def _normalize_ref_id(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise BrowserValidationError("ref is required.")
    return normalized


def _normalize_profile_name(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise BrowserValidationError("profile name is required.")
    return normalized


def _normalize_pool_id(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise BrowserValidationError("pool id is required.")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_required_text(value: str, *, label: str) -> str:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        raise BrowserValidationError(f"{label} is required.")
    return normalized


def _ensure_aware_utc(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    normalized = value.astimezone(timezone.utc)
    if normalized.year < 2000:
        raise BrowserValidationError(f"{label} is invalid.")
    return normalized


def _normalize_profile_directory(value: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    if "/" in normalized or "\\" in normalized:
        raise BrowserValidationError(
            "profile_directory must be a browser profile name, not a filesystem path.",
        )
    return normalized


def _normalize_proxy_bypass_list(value: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        entry = str(item).strip()
        if not entry or entry in seen:
            continue
        seen.add(entry)
        normalized.append(entry)
    return tuple(normalized)


def _proxy_server_has_credentials(value: str | None) -> bool:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return False
    parsed = urlsplit(normalized)
    return bool(parsed.username or parsed.password)


def _require_positive_port(value: int | None, *, label: str) -> int | None:
    if value is None:
        return None
    numeric = int(value)
    if numeric < 1:
        raise BrowserValidationError(f"{label} must be greater than or equal to 1.")
    return numeric


def _normalize_frame_path(value: tuple[int, ...] | list[int] | None) -> tuple[int, ...]:
    if value is None:
        return ()
    normalized: list[int] = []
    for index in value:
        numeric = int(index)
        if numeric < 0:
            raise BrowserValidationError("frame_path indexes must be greater than or equal to 0.")
        normalized.append(numeric)
    return tuple(normalized)


def _normalize_endpoint_map(value: Mapping[str, str] | None) -> dict[str, str] | None:
    if value is None:
        return None
    normalized: dict[str, str] = {}
    for key, item in value.items():
        normalized_key = str(key).strip()
        normalized_value = str(item).strip()
        if not normalized_key or not normalized_value:
            continue
        normalized[normalized_key] = normalized_value
    return normalized or None


def _normalize_text_tuple(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return tuple(normalized)


def _normalize_numeric_mapping(value: Mapping[str, Any] | None) -> dict[str, float] | None:
    if value is None:
        return None
    normalized: dict[str, float] = {}
    for key, item in value.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            continue
        try:
            normalized[normalized_key] = float(item)
        except (TypeError, ValueError) as exc:
            raise BrowserValidationError(f"{normalized_key} must be numeric.") from exc
    return normalized or None


def _normalize_confidence(value: float | int | None) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise BrowserValidationError("stored ref confidence must be numeric.") from exc
    if numeric < 0 or numeric > 1:
        raise BrowserValidationError("stored ref confidence must be between 0 and 1.")
    return numeric


def _normalize_profile_name_tuple(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in _normalize_text_tuple(values):
        name = _normalize_profile_name(value)
        if name in seen:
            continue
        seen.add(name)
        normalized.append(name)
    return tuple(normalized)


def _normalize_target_hosts(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in _normalize_text_tuple(values):
        host = value.lower()
        if host in seen:
            continue
        seen.add(host)
        normalized.append(host)
    return tuple(normalized)


def _require_positive_int(value: int | None, *, label: str) -> int | None:
    if value is None:
        return None
    numeric = int(value)
    if numeric < 1:
        raise BrowserValidationError(f"{label} must be greater than or equal to 1.")
    return numeric


def _require_non_negative_int(value: int, *, label: str) -> int:
    numeric = int(value)
    if numeric < 0:
        raise BrowserValidationError(f"{label} must be greater than or equal to 0.")
    return numeric


def _normalize_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    return dict(value)


def _normalize_header_mapping(value: Mapping[str, Any] | None) -> dict[str, str]:
    if value is None:
        return {}
    normalized: dict[str, str] = {}
    for key, item in value.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            continue
        normalized[normalized_key] = "" if item is None else str(item)
    return normalized


def _normalize_status_code(value: int | None, *, label: str) -> int | None:
    if value is None:
        return None
    numeric = int(value)
    if numeric < 0 or numeric > 999:
        raise BrowserValidationError(f"{label} must be between 0 and 999.")
    return numeric


def _normalize_network_capture_status(value: str) -> str:
    normalized = _normalize_required_text(value, label="capture status").lower()
    if normalized not in {"active", "stopped"}:
        raise BrowserValidationError("capture status must be one of: active, stopped.")
    return normalized


def _normalize_network_body_kind(value: str) -> str:
    normalized = _normalize_required_text(value, label="body kind").lower()
    if normalized not in {"request", "response"}:
        raise BrowserValidationError("body kind must be one of: request, response.")
    return normalized


def _normalize_network_resource_type(value: str | None) -> str:
    return (_normalize_optional_text(value) or "other").lower()


def _normalize_network_method(value: str) -> str:
    return _normalize_required_text(value, label="method").upper()


def _normalize_network_filter_domain(value: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    return normalized.lower() if normalized is not None else None


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
        object.__setattr__(self, "proxy_server", _normalize_optional_text(self.proxy_server))
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
            raise BrowserValidationError("proxy_server is required when proxy_mode is static.")
        if self.proxy_mode == "static" and _proxy_server_has_credentials(self.proxy_server):
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
        object.__setattr__(self, "display_name", _normalize_optional_text(self.display_name))
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
        if strategy not in {"round_robin", "least_busy", "sticky_session", "manual_only"}:
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
        object.__setattr__(self, "health_policy", _normalize_mapping(self.health_policy))
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
        object.__setattr__(self, "proxy_server", _normalize_optional_text(self.proxy_server))
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
        if self.proxy_mode == "static" and _proxy_server_has_credentials(self.proxy_server):
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


@dataclass(frozen=True, slots=True)
class BrowserTab:
    target_id: str
    url: str = ""
    title: str = ""
    type: BrowserTabType = "page"
    ws_url: str | None = None
    json_endpoints: dict[str, str] | None = None

    def __post_init__(self) -> None:
        normalized_target_id = self.target_id.strip()
        if not normalized_target_id:
            raise BrowserValidationError("target_id is required.")
        object.__setattr__(self, "target_id", normalized_target_id)
        object.__setattr__(self, "url", self.url.strip())
        object.__setattr__(self, "title", self.title.strip())
        object.__setattr__(self, "ws_url", _normalize_optional_text(self.ws_url))
        object.__setattr__(
            self,
            "json_endpoints",
            _normalize_endpoint_map(self.json_endpoints),
        )


@dataclass(frozen=True, slots=True)
class BrowserActionTarget:
    target_id: str | None = None
    ref: str | None = None
    selector: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_id", _normalize_optional_text(self.target_id))
        object.__setattr__(
            self,
            "ref",
            (_normalize_ref_id(self.ref) if self.ref is not None else None),
        )
        object.__setattr__(self, "selector", _normalize_optional_text(self.selector))


@dataclass(frozen=True, slots=True)
class BrowserStoredRef:
    ref: str
    selector: str | None = None
    scope_selector: str | None = None
    uid: str | None = None
    nth: int | None = None
    generation: int = 1
    snapshot_format: str | None = None
    frame_path: tuple[int, ...] = ()
    label: str | None = None
    role: str | None = None
    text: str | None = None
    tag: str | None = None
    frame_id: str | None = None
    backend_node_id: int | None = None
    bbox: Mapping[str, Any] | None = None
    evidence: tuple[str, ...] = ()
    confidence: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref", _normalize_ref_id(self.ref))
        selector = _normalize_optional_text(self.selector)
        scope_selector = _normalize_optional_text(self.scope_selector)
        uid = _normalize_optional_text(self.uid)
        role = _normalize_optional_text(self.role)
        if selector is None and uid is None and role is None and self.backend_node_id is None:
            raise BrowserValidationError(
                "stored refs require selector, uid, role, or backend_node_id.",
            )
        object.__setattr__(self, "selector", selector)
        object.__setattr__(self, "scope_selector", scope_selector)
        object.__setattr__(self, "uid", uid)
        if self.nth is None:
            object.__setattr__(self, "nth", None)
        else:
            nth = int(self.nth)
            if nth < 0:
                raise BrowserValidationError("stored ref nth must be greater than or equal to 0.")
            object.__setattr__(self, "nth", nth)
        generation = int(self.generation)
        if generation < 1:
            raise BrowserValidationError("stored ref generation must be greater than or equal to 1.")
        object.__setattr__(self, "generation", generation)
        object.__setattr__(
            self,
            "snapshot_format",
            _normalize_optional_text(self.snapshot_format),
        )
        object.__setattr__(self, "frame_path", _normalize_frame_path(self.frame_path))
        object.__setattr__(self, "label", _normalize_optional_text(self.label))
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "text", _normalize_optional_text(self.text))
        object.__setattr__(self, "tag", _normalize_optional_text(self.tag))
        object.__setattr__(self, "frame_id", _normalize_optional_text(self.frame_id))
        if self.backend_node_id is None:
            object.__setattr__(self, "backend_node_id", None)
        else:
            backend_node_id = int(self.backend_node_id)
            if backend_node_id < 1:
                raise BrowserValidationError(
                    "stored ref backend_node_id must be greater than or equal to 1.",
                )
            object.__setattr__(self, "backend_node_id", backend_node_id)
        object.__setattr__(self, "bbox", _normalize_numeric_mapping(self.bbox))
        object.__setattr__(self, "evidence", _normalize_text_tuple(self.evidence))
        object.__setattr__(self, "confidence", _normalize_confidence(self.confidence))


@dataclass(frozen=True, slots=True)
class BrowserNetworkCapture:
    profile_name: str
    target_id: str
    capture_id: str
    status: BrowserNetworkCaptureStatus = "active"
    max_requests: int = 200
    max_body_bytes: int = 262_144
    request_count: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    stopped_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "profile_name",
            _normalize_profile_name(self.profile_name),
        )
        object.__setattr__(
            self,
            "target_id",
            _normalize_required_text(self.target_id, label="target_id"),
        )
        object.__setattr__(
            self,
            "capture_id",
            _normalize_required_text(self.capture_id, label="capture_id"),
        )
        object.__setattr__(
            self,
            "status",
            _normalize_network_capture_status(self.status),
        )
        object.__setattr__(
            self,
            "max_requests",
            _require_positive_int(self.max_requests, label="max_requests") or 200,
        )
        object.__setattr__(
            self,
            "max_body_bytes",
            _require_non_negative_int(self.max_body_bytes, label="max_body_bytes"),
        )
        object.__setattr__(
            self,
            "request_count",
            _require_non_negative_int(self.request_count, label="request_count"),
        )
        started_at = _ensure_aware_utc(self.started_at, label="started_at")
        object.__setattr__(self, "started_at", started_at)
        if self.stopped_at is not None:
            stopped_at = _ensure_aware_utc(self.stopped_at, label="stopped_at")
            if stopped_at < started_at:
                raise BrowserValidationError("stopped_at must not be before started_at.")
            object.__setattr__(self, "stopped_at", stopped_at)
        object.__setattr__(self, "metadata", _normalize_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class BrowserNetworkBody:
    profile_name: str
    target_id: str
    capture_id: str
    request_id: str
    body_ref: str
    kind: BrowserNetworkBodyKind
    body: str
    mime_type: str | None = None
    base64_encoded: bool = False
    size_bytes: int = 0
    stored_size_bytes: int = 0
    truncated: bool = False
    redacted: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "profile_name",
            _normalize_profile_name(self.profile_name),
        )
        object.__setattr__(
            self,
            "target_id",
            _normalize_required_text(self.target_id, label="target_id"),
        )
        object.__setattr__(
            self,
            "capture_id",
            _normalize_required_text(self.capture_id, label="capture_id"),
        )
        object.__setattr__(
            self,
            "request_id",
            _normalize_required_text(self.request_id, label="request_id"),
        )
        object.__setattr__(
            self,
            "body_ref",
            _normalize_required_text(self.body_ref, label="body_ref"),
        )
        object.__setattr__(self, "kind", _normalize_network_body_kind(self.kind))
        object.__setattr__(self, "body", str(self.body))
        object.__setattr__(self, "mime_type", _normalize_optional_text(self.mime_type))
        object.__setattr__(self, "base64_encoded", bool(self.base64_encoded))
        object.__setattr__(
            self,
            "size_bytes",
            _require_non_negative_int(self.size_bytes, label="size_bytes"),
        )
        object.__setattr__(
            self,
            "stored_size_bytes",
            _require_non_negative_int(
                self.stored_size_bytes,
                label="stored_size_bytes",
            ),
        )
        object.__setattr__(self, "truncated", bool(self.truncated))
        object.__setattr__(self, "redacted", bool(self.redacted))
        object.__setattr__(
            self,
            "created_at",
            _ensure_aware_utc(self.created_at, label="created_at"),
        )


@dataclass(frozen=True, slots=True)
class BrowserNetworkRequest:
    request_id: str
    capture_id: str
    profile_name: str
    target_id: str
    url: str
    method: str
    frame_id: str | None = None
    loader_id: str | None = None
    resource_type: str = "other"
    request_headers: Mapping[str, Any] = field(default_factory=dict)
    request_post_data_preview: str | None = None
    status: int | None = None
    response_headers: Mapping[str, Any] = field(default_factory=dict)
    mime_type: str | None = None
    timing: Mapping[str, Any] = field(default_factory=dict)
    initiator: Mapping[str, Any] = field(default_factory=dict)
    body_ref: str | None = None
    request_body_ref: str | None = None
    failure_text: str | None = None
    encoded_data_length: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _normalize_required_text(self.request_id, label="request_id"),
        )
        object.__setattr__(
            self,
            "capture_id",
            _normalize_required_text(self.capture_id, label="capture_id"),
        )
        object.__setattr__(
            self,
            "profile_name",
            _normalize_profile_name(self.profile_name),
        )
        object.__setattr__(
            self,
            "target_id",
            _normalize_required_text(self.target_id, label="target_id"),
        )
        object.__setattr__(self, "url", _normalize_required_text(self.url, label="url"))
        object.__setattr__(self, "method", _normalize_network_method(self.method))
        object.__setattr__(self, "frame_id", _normalize_optional_text(self.frame_id))
        object.__setattr__(self, "loader_id", _normalize_optional_text(self.loader_id))
        object.__setattr__(
            self,
            "resource_type",
            _normalize_network_resource_type(self.resource_type),
        )
        object.__setattr__(
            self,
            "request_headers",
            _normalize_header_mapping(self.request_headers),
        )
        object.__setattr__(
            self,
            "request_post_data_preview",
            _normalize_optional_text(self.request_post_data_preview),
        )
        object.__setattr__(
            self,
            "status",
            _normalize_status_code(self.status, label="status"),
        )
        object.__setattr__(
            self,
            "response_headers",
            _normalize_header_mapping(self.response_headers),
        )
        object.__setattr__(self, "mime_type", _normalize_optional_text(self.mime_type))
        object.__setattr__(self, "timing", _normalize_mapping(self.timing))
        object.__setattr__(self, "initiator", _normalize_mapping(self.initiator))
        object.__setattr__(self, "body_ref", _normalize_optional_text(self.body_ref))
        object.__setattr__(
            self,
            "request_body_ref",
            _normalize_optional_text(self.request_body_ref),
        )
        object.__setattr__(
            self,
            "failure_text",
            _normalize_optional_text(self.failure_text),
        )
        if self.encoded_data_length is not None:
            object.__setattr__(
                self,
                "encoded_data_length",
                _require_non_negative_int(
                    self.encoded_data_length,
                    label="encoded_data_length",
                ),
            )
        created_at = _ensure_aware_utc(self.created_at, label="created_at")
        object.__setattr__(self, "created_at", created_at)
        if self.completed_at is not None:
            completed_at = _ensure_aware_utc(self.completed_at, label="completed_at")
            if completed_at < created_at:
                raise BrowserValidationError("completed_at must not be before created_at.")
            object.__setattr__(self, "completed_at", completed_at)


@dataclass(frozen=True, slots=True)
class BrowserNetworkRequestFilter:
    resource_type: str | None = None
    domain: str | None = None
    path: str | None = None
    method: str | None = None
    status: int | None = None
    status_min: int | None = None
    status_max: int | None = None
    initiator: str | None = None
    mime_type: str | None = None
    keyword: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "resource_type",
            _normalize_network_resource_type(self.resource_type)
            if self.resource_type is not None
            else None,
        )
        object.__setattr__(
            self,
            "domain",
            _normalize_network_filter_domain(self.domain),
        )
        object.__setattr__(self, "path", _normalize_optional_text(self.path))
        object.__setattr__(
            self,
            "method",
            (
                _normalize_network_method(self.method)
                if self.method is not None
                else None
            ),
        )
        object.__setattr__(
            self,
            "status",
            _normalize_status_code(self.status, label="status"),
        )
        object.__setattr__(
            self,
            "status_min",
            _normalize_status_code(self.status_min, label="status_min"),
        )
        object.__setattr__(
            self,
            "status_max",
            _normalize_status_code(self.status_max, label="status_max"),
        )
        if (
            self.status_min is not None
            and self.status_max is not None
            and self.status_max < self.status_min
        ):
            raise BrowserValidationError("status_max must not be less than status_min.")
        object.__setattr__(self, "initiator", _normalize_optional_text(self.initiator))
        object.__setattr__(self, "mime_type", _normalize_optional_text(self.mime_type))
        object.__setattr__(self, "keyword", _normalize_optional_text(self.keyword))
        if self.created_after is not None:
            object.__setattr__(
                self,
                "created_after",
                _ensure_aware_utc(self.created_after, label="created_after"),
            )
        if self.created_before is not None:
            object.__setattr__(
                self,
                "created_before",
                _ensure_aware_utc(self.created_before, label="created_before"),
            )
        if (
            self.created_after is not None
            and self.created_before is not None
            and self.created_before < self.created_after
        ):
            raise BrowserValidationError(
                "created_before must not be before created_after.",
            )
        object.__setattr__(
            self,
            "limit",
            _require_positive_int(self.limit, label="limit"),
        )

    def matches(self, request: BrowserNetworkRequest) -> bool:
        if self.resource_type is not None and request.resource_type != self.resource_type:
            return False
        parsed = urlsplit(request.url)
        if self.domain is not None and self.domain not in parsed.netloc.lower():
            return False
        if self.path is not None and self.path not in parsed.path:
            return False
        if self.method is not None and request.method != self.method:
            return False
        if self.status is not None and request.status != self.status:
            return False
        if self.status_min is not None and (
            request.status is None or request.status < self.status_min
        ):
            return False
        if self.status_max is not None and (
            request.status is None or request.status > self.status_max
        ):
            return False
        if self.initiator is not None and self.initiator.lower() not in str(
            request.initiator,
        ).lower():
            return False
        if self.mime_type is not None and (
            request.mime_type is None
            or self.mime_type.lower() not in request.mime_type.lower()
        ):
            return False
        if self.created_after is not None and request.created_at < self.created_after:
            return False
        if self.created_before is not None and request.created_at > self.created_before:
            return False
        if self.keyword is not None and self.keyword.lower() not in _request_search_text(
            request,
        ):
            return False
        return True


def _request_search_text(request: BrowserNetworkRequest) -> str:
    parts: list[str] = [
        request.request_id,
        request.url,
        request.method,
        request.resource_type,
        str(request.status or ""),
        request.mime_type or "",
        request.request_post_data_preview or "",
        request.failure_text or "",
        str(request.initiator),
    ]
    parts.extend(request.request_headers.keys())
    parts.extend(request.response_headers.keys())
    return "\n".join(parts).lower()


@dataclass(frozen=True, slots=True)
class BrowserControlCommand:
    profile_name: str
    kind: BrowserControlKind
    target_id: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    timeout_ms: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "profile_name",
            _normalize_profile_name(self.profile_name),
        )
        object.__setattr__(self, "target_id", _normalize_optional_text(self.target_id))
        object.__setattr__(self, "payload", dict(self.payload))
        if self.timeout_ms is not None and int(self.timeout_ms) < 1:
            raise BrowserValidationError("timeout_ms must be greater than or equal to 1.")


@dataclass(frozen=True, slots=True)
class BrowserPageActionCommand:
    profile_name: str
    kind: BrowserPageActionKind
    target: BrowserActionTarget = field(default_factory=BrowserActionTarget)
    payload: Mapping[str, Any] = field(default_factory=dict)
    timeout_ms: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "profile_name",
            _normalize_profile_name(self.profile_name),
        )
        object.__setattr__(self, "payload", dict(self.payload))
        if self.timeout_ms is not None and int(self.timeout_ms) < 1:
            raise BrowserValidationError("timeout_ms must be greater than or equal to 1.")


BrowserCommand: TypeAlias = BrowserControlCommand | BrowserPageActionCommand


@dataclass(frozen=True, slots=True)
class BrowserExecutionPlan:
    command: BrowserCommand
    system: BrowserSystemConfig
    profile: ResolvedBrowserProfile
    capabilities: BrowserProfileCapabilities
    control_family: BrowserControlFamily
    action_family: BrowserActionFamily
    launch_policy: BrowserLaunchPolicy
    tab_selection_policy: BrowserTabSelectionPolicy

    def __post_init__(self) -> None:
        if self.profile.name != self.command.profile_name:
            raise BrowserValidationError(
                "Browser execution plan profile must match command.profile_name.",
            )


@dataclass(frozen=True, slots=True)
class BrowserActionResult:
    command: BrowserCommand
    ok: bool
    target_id: str | None = None
    value: Any | None = None
    message: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_id", _normalize_optional_text(self.target_id))
        object.__setattr__(self, "message", self.message.strip())
