from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, TypeAlias


@dataclass(frozen=True, slots=True)
class MobileControlRequest:
    device_name: str | None
    kind: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    timeout_ms: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "device_name",
            (self.device_name.strip() if isinstance(self.device_name, str) else None) or None,
        )
        object.__setattr__(self, "kind", self.kind.strip())
        object.__setattr__(self, "payload", dict(self.payload))


@dataclass(frozen=True, slots=True)
class MobileActionRequest:
    device_name: str | None
    kind: str
    ref: str | None = None
    selector: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    timeout_ms: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "device_name",
            (self.device_name.strip() if isinstance(self.device_name, str) else None) or None,
        )
        object.__setattr__(self, "kind", self.kind.strip())
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


MobileInterfaceRequest: TypeAlias = MobileControlRequest | MobileActionRequest
