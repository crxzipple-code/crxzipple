from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class AccessActionRequest:
    action_id: str
    resource_kind: str
    target_id: str | None
    intent: str
    changes: JsonObject = field(default_factory=dict)
    reason: str = ""
    confirmation: str | None = None
    risk_acknowledged: bool = False
    actor: str | None = None
    trace_context: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AccessActionResult:
    status: str
    asset: JsonObject | None = None
    audit_ref: str | None = None
    validation: JsonObject = field(default_factory=dict)
    readiness: JsonObject | None = None
    warnings: tuple[str, ...] = ()
