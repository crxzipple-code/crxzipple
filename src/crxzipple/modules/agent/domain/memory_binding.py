from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.agent.domain.exceptions import AgentValidationError
from crxzipple.modules.agent.domain.value_common import (
    bool_value,
    normalize_optional_text,
)


_VALID_MEMORY_ACCESS = frozenset({"read", "read_write"})


@dataclass(frozen=True, slots=True)
class AgentMemoryBinding:
    enabled: bool = True
    scope_ref: str | None = None
    access: str = "read_write"

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope_ref", normalize_optional_text(self.scope_ref))
        normalized_access = _normalize_memory_access(self.access)
        object.__setattr__(self, "access", normalized_access)

    @property
    def writable(self) -> bool:
        return self.enabled and self.access == "read_write"

    def effective_scope_ref(self, agent_id: str) -> str:
        if self.scope_ref is None or self.scope_ref == "auto":
            return agent_id
        return self.scope_ref

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "enabled": self.enabled,
            "access": self.access,
        }
        if self.scope_ref is not None:
            payload["scope_ref"] = self.scope_ref
        return payload

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> "AgentMemoryBinding":
        payload = payload or {}
        scope_ref = payload.get("scope_ref")
        return cls(
            enabled=bool_value(payload.get("enabled"), default=True),
            scope_ref=str(scope_ref) if scope_ref is not None else None,
            access=str(payload.get("access") or "read_write"),
        )


def _normalize_memory_access(value: str | None) -> str:
    normalized = normalize_optional_text(value)
    if normalized is None:
        return "read_write"
    if normalized not in _VALID_MEMORY_ACCESS:
        raise AgentValidationError(
            f"Unsupported agent memory access '{normalized}'.",
        )
    return normalized


__all__ = ["AgentMemoryBinding"]
