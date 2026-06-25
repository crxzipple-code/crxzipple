from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, TypeAlias

from .exceptions import BrowserValidationError
from .profile_value_objects import (
    BrowserProfileCapabilities,
    BrowserSystemConfig,
    ResolvedBrowserProfile,
)
from .tab_value_objects import BrowserActionTarget
from .value_helpers import _normalize_optional_text, _normalize_profile_name
from .value_types import (
    BrowserActionFamily,
    BrowserControlFamily,
    BrowserControlKind,
    BrowserLaunchPolicy,
    BrowserPageActionKind,
    BrowserTabSelectionPolicy,
)


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
            raise BrowserValidationError(
                "timeout_ms must be greater than or equal to 1."
            )


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
            raise BrowserValidationError(
                "timeout_ms must be greater than or equal to 1."
            )


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
