from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.observation_payloads import (
    optional_text,
    parse_datetime,
)
from crxzipple.shared.time import format_datetime_utc


@dataclass(frozen=True, slots=True)
class OperationsProjection:
    module: str
    kind: str
    query_key: str
    updated_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "kind": self.kind,
            "query_key": self.query_key,
            "updated_at": format_datetime_utc(self.updated_at),
            "payload": dict(self.payload),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "OperationsProjection | None":
        module = optional_text(payload.get("module"))
        kind = optional_text(payload.get("kind"))
        query_key = optional_text(payload.get("query_key")) or "default"
        updated_at = parse_datetime(payload.get("updated_at"))
        raw_payload = payload.get("payload")
        if module is None or kind is None or updated_at is None:
            return None
        if not isinstance(raw_payload, dict):
            return None
        return cls(
            module=module,
            kind=kind,
            query_key=query_key,
            updated_at=updated_at,
            payload=dict(raw_payload),
        )
