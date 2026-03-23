from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class LlmStreamEvent:
    type: str
    sequence: int
    invocation_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "sequence": self.sequence,
            "invocation_id": self.invocation_id,
            "data": dict(self.data),
        }
