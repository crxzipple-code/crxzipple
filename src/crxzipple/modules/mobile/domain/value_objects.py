from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, TypeAlias

from .exceptions import MobileValidationError

MobilePlatform: TypeAlias = Literal["android"]
MobileControlFamily: TypeAlias = Literal["adb-control"]
MobileActionFamily: TypeAlias = Literal["adb-backed"]
MobileControlKind: TypeAlias = Literal[
    "list-devices",
    "launch-app",
    "activate-app",
    "terminate-app",
]
MobileActionKind: TypeAlias = Literal[
    "snapshot",
    "screenshot",
    "tap",
    "swipe",
    "type",
    "press",
    "wait",
]
MobileSnapshotFormat: TypeAlias = Literal["interactive", "tree", "text", "interactive_text"]


def _normalize_name(value: str | None, *, label: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if any(part in normalized for part in ("/", "\\")):
        raise MobileValidationError(f"{label} must not contain path separators.")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _require_positive(value: int | None, *, label: str) -> int | None:
    if value is None:
        return None
    numeric = int(value)
    if numeric < 1:
        raise MobileValidationError(f"{label} must be greater than or equal to 1.")
    return numeric


@dataclass(frozen=True, slots=True)
class MobileDeviceConfig:
    name: str
    platform: MobilePlatform = "android"
    udid: str | None = None
    app_package: str | None = None
    app_activity: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _normalize_name(self.name, label="Device name"))
        object.__setattr__(self, "udid", _normalize_optional_text(self.udid))
        object.__setattr__(self, "app_package", _normalize_optional_text(self.app_package))
        object.__setattr__(self, "app_activity", _normalize_optional_text(self.app_activity))
        if self.platform != "android":
            raise MobileValidationError(
                f"Unsupported mobile platform '{self.platform}'.",
            )


@dataclass(frozen=True, slots=True)
class MobileSystemConfig:
    default_device: str | None = None
    devices: tuple[MobileDeviceConfig, ...] = ()
    adb_binary: str = "adb"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "default_device",
            _normalize_name(self.default_device, label="Default mobile device"),
        )
        object.__setattr__(self, "adb_binary", self.adb_binary.strip() or "adb")


@dataclass(frozen=True, slots=True)
class ResolvedMobileDevice:
    name: str
    platform: MobilePlatform
    udid: str | None = None
    app_package: str | None = None
    app_activity: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _normalize_name(self.name, label="Resolved mobile device"))
        object.__setattr__(self, "udid", _normalize_optional_text(self.udid))
        object.__setattr__(self, "app_package", _normalize_optional_text(self.app_package))
        object.__setattr__(self, "app_activity", _normalize_optional_text(self.app_activity))


@dataclass(frozen=True, slots=True)
class MobileDeviceCapabilities:
    mode: str
    control_family: MobileControlFamily
    action_family: MobileActionFamily
    supports_screenshot: bool = True
    supports_app_management: bool = True


@dataclass(frozen=True, slots=True)
class MobileActionTarget:
    ref: str | None = None
    selector: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref", _normalize_optional_text(self.ref))
        object.__setattr__(self, "selector", _normalize_optional_text(self.selector))


@dataclass(frozen=True, slots=True)
class MobileControlCommand:
    device_name: str | None
    kind: MobileControlKind
    payload: Mapping[str, Any] = field(default_factory=dict)
    timeout_ms: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "device_name",
            _normalize_name(self.device_name, label="Device name"),
        )
        object.__setattr__(self, "payload", dict(self.payload))
        object.__setattr__(self, "timeout_ms", _require_positive(self.timeout_ms, label="timeout_ms"))


@dataclass(frozen=True, slots=True)
class MobileActionCommand:
    device_name: str | None
    kind: MobileActionKind
    target: MobileActionTarget = field(default_factory=MobileActionTarget)
    payload: Mapping[str, Any] = field(default_factory=dict)
    timeout_ms: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "device_name",
            _normalize_name(self.device_name, label="Device name"),
        )
        object.__setattr__(self, "payload", dict(self.payload))
        object.__setattr__(self, "timeout_ms", _require_positive(self.timeout_ms, label="timeout_ms"))


MobileCommand: TypeAlias = MobileControlCommand | MobileActionCommand


@dataclass(frozen=True, slots=True)
class MobileExecutionPlan:
    system: MobileSystemConfig
    device: ResolvedMobileDevice | None
    capabilities: MobileDeviceCapabilities | None
    command: MobileCommand


@dataclass(frozen=True, slots=True)
class MobileStoredRef:
    ref: str
    generation: int
    source: str | None = None
    text: str | None = None
    content_desc: str | None = None
    resource_id: str | None = None
    class_name: str | None = None
    xpath: str | None = None
    bounds: tuple[int, int, int, int] | None = None
    clickable: bool = False
    focusable: bool = False
    focused: bool = False
    enabled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref", self.ref.strip().lower())
        object.__setattr__(self, "generation", max(int(self.generation), 1))
        object.__setattr__(self, "source", _normalize_optional_text(self.source))
        object.__setattr__(self, "text", _normalize_optional_text(self.text))
        object.__setattr__(self, "content_desc", _normalize_optional_text(self.content_desc))
        object.__setattr__(self, "resource_id", _normalize_optional_text(self.resource_id))
        object.__setattr__(self, "class_name", _normalize_optional_text(self.class_name))
        object.__setattr__(self, "xpath", _normalize_optional_text(self.xpath))
        if self.bounds is not None:
            object.__setattr__(self, "bounds", tuple(int(part) for part in self.bounds))


@dataclass(frozen=True, slots=True)
class MobileActionResult:
    ok: bool
    device_name: str | None
    message: str
    command: MobileCommand
    value: Any = None
