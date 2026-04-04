from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, TypeAlias


@dataclass(frozen=True, slots=True)
class BrowserControlRequest:
    profile_name: str
    kind: str
    target_id: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    timeout_ms: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_name", self.profile_name.strip())
        object.__setattr__(self, "kind", self.kind.strip())
        object.__setattr__(
            self,
            "target_id",
            (self.target_id.strip() if isinstance(self.target_id, str) else None) or None,
        )
        object.__setattr__(self, "payload", dict(self.payload))


@dataclass(frozen=True, slots=True)
class BrowserPageActionRequest:
    profile_name: str
    kind: str
    target_id: str | None = None
    ref: str | None = None
    selector: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    timeout_ms: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_name", self.profile_name.strip())
        object.__setattr__(self, "kind", self.kind.strip())
        object.__setattr__(
            self,
            "target_id",
            (self.target_id.strip() if isinstance(self.target_id, str) else None) or None,
        )
        object.__setattr__(
            self,
            "ref",
            (self.ref.strip() if isinstance(self.ref, str) else None) or None,
        )
        object.__setattr__(
            self,
            "selector",
            (self.selector.strip() if isinstance(self.selector, str) else None) or None,
        )
        object.__setattr__(self, "payload", dict(self.payload))


BrowserInterfaceRequest: TypeAlias = BrowserControlRequest | BrowserPageActionRequest

