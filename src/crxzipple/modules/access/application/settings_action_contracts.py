from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


JsonObject = dict[str, Any]


class AccessSettingsActionRequest(Protocol):
    action_id: str
    resource_kind: str
    target_id: str | None
    intent: str
    changes: Mapping[str, Any]
    reason: str
    actor: str | None
    trace_context: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class AccessSettingsActionResult:
    status: str
    asset: JsonObject | None = None
    audit_ref: str | None = None
    validation: JsonObject | None = None
    warnings: tuple[str, ...] = ()
