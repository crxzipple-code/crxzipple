from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, TypeAlias

from .exceptions import BrowserValidationError

BrowserProfileDriver: TypeAlias = Literal["managed", "existing-session"]
BrowserProfileMode: TypeAlias = Literal[
    "local-managed",
    "local-existing-session",
    "remote-cdp",
]
BrowserControlFamily: TypeAlias = Literal["cdp-control", "mcp-control"]
BrowserActionFamily: TypeAlias = Literal["cdp-backed-playwright", "mcp-backed"]
BrowserLaunchPolicy: TypeAlias = Literal["launch-if-missing", "attach-only"]
BrowserTabSelectionPolicy: TypeAlias = Literal[
    "sticky-last-target",
    "explicit-only",
]
BrowserTabType: TypeAlias = Literal["page", "background", "worker", "other"]
DEFAULT_BROWSER_MCP_COMMAND: tuple[str, ...] = (
    "npx",
    "-y",
    "chrome-devtools-mcp@latest",
    "--autoConnect",
    "--experimentalStructuredContent",
    "--experimental-page-id-routing",
)
BrowserControlKind: TypeAlias = Literal[
    "navigate",
    "open-tab",
    "focus-tab",
    "close-tab",
    "list-tabs",
    "reset",
]
BrowserPageActionKind: TypeAlias = Literal[
    "click",
    "type",
    "press",
    "hover",
    "drag",
    "batch",
    "resize",
    "scroll-into-view",
    "select",
    "fill",
    "wait",
    "snapshot",
    "screenshot",
    "pdf",
    "evaluate",
]


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


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


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


@dataclass(frozen=True, slots=True)
class BrowserProfileConfig:
    name: str
    driver: BrowserProfileDriver = "managed"
    cdp_url: str | None = None
    cdp_port: int | None = None
    user_data_dir: str | None = None
    attach_only: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _normalize_profile_name(self.name))
        object.__setattr__(self, "cdp_url", _normalize_optional_text(self.cdp_url))
        object.__setattr__(
            self,
            "user_data_dir",
            _normalize_optional_text(self.user_data_dir),
        )
        object.__setattr__(
            self,
            "cdp_port",
            _require_positive_port(self.cdp_port, label="cdp_port"),
        )
        if self.driver not in {"managed", "existing-session"}:
            raise BrowserValidationError(
                f"Unsupported browser profile driver '{self.driver}'.",
            )
        if self.driver == "existing-session" and self.cdp_url is not None:
            raise BrowserValidationError(
                "existing-session profiles must not define cdp_url.",
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
    mcp_command: tuple[str, ...] = DEFAULT_BROWSER_MCP_COMMAND
    mcp_timeout_seconds: int = 30

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
        normalized_command = tuple(
            str(item).strip()
            for item in self.mcp_command
            if str(item).strip()
        )
        if not normalized_command:
            raise BrowserValidationError("mcp_command must include at least one command part.")
        object.__setattr__(self, "mcp_command", normalized_command)
        timeout_seconds = int(self.mcp_timeout_seconds)
        if timeout_seconds < 1:
            raise BrowserValidationError(
                "mcp_timeout_seconds must be greater than or equal to 1.",
            )
        object.__setattr__(self, "mcp_timeout_seconds", timeout_seconds)


@dataclass(frozen=True, slots=True)
class ResolvedBrowserProfile:
    name: str
    driver: BrowserProfileDriver
    cdp_url: str | None
    cdp_port: int | None
    user_data_dir: str | None
    attach_only: bool
    is_loopback: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _normalize_profile_name(self.name))
        object.__setattr__(self, "cdp_url", _normalize_optional_text(self.cdp_url))
        object.__setattr__(
            self,
            "user_data_dir",
            _normalize_optional_text(self.user_data_dir),
        )
        object.__setattr__(
            self,
            "cdp_port",
            _require_positive_port(self.cdp_port, label="cdp_port"),
        )
        if self.driver not in {"managed", "existing-session"}:
            raise BrowserValidationError(
                f"Unsupported resolved browser profile driver '{self.driver}'.",
            )


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref", _normalize_ref_id(self.ref))
        selector = _normalize_optional_text(self.selector)
        scope_selector = _normalize_optional_text(self.scope_selector)
        uid = _normalize_optional_text(self.uid)
        role = _normalize_optional_text(self.role)
        if selector is None and uid is None and role is None:
            raise BrowserValidationError("stored refs require selector, uid, or role.")
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
