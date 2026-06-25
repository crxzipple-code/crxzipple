from __future__ import annotations

from dataclasses import dataclass
from typing import Any


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class AccessQueryDegraded:
    reason: str
    missing_dependencies: tuple[str, ...] = ()

    def to_payload(self) -> JsonObject:
        return {
            "status": "degraded",
            "degraded": True,
            "degraded_reason": self.reason,
            "dependency_missing": list(self.missing_dependencies),
        }


@dataclass(frozen=True, slots=True)
class AccessQueryResult:
    payload: JsonObject
    degraded: AccessQueryDegraded | None = None

    def to_payload(self) -> JsonObject:
        if self.degraded is None:
            return {"status": "ready", "degraded": False, **self.payload}
        return {**self.degraded.to_payload(), **self.payload}
