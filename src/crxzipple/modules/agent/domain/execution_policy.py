from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentExecutionPolicy:
    timeout_seconds: int = 120
    max_turns: int = 99

    def to_payload(self) -> dict[str, object]:
        return {
            "timeout_seconds": self.timeout_seconds,
            "max_turns": self.max_turns,
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> "AgentExecutionPolicy":
        payload = payload or {}
        return cls(
            timeout_seconds=int(payload.get("timeout_seconds", 120)),
            max_turns=int(payload.get("max_turns", 99)),
        )


__all__ = ["AgentExecutionPolicy"]
