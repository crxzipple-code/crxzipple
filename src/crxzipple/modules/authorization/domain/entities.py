from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from crxzipple.modules.authorization.domain.value_objects import (
    AuthorizationEffect,
    AuthorizationObligation,
    AuthorizationGrantScope,
)


@dataclass(frozen=True, slots=True)
class AuthorizationPolicy:
    id: str
    effect: AuthorizationEffect
    actions: tuple[str, ...]
    description: str = ""
    subject_type: str | None = None
    subject_id: str | None = None
    subject_match: dict[str, Any] = field(default_factory=dict)
    resource_kind: str | None = None
    resource_id: str | None = None
    resource_match: dict[str, Any] = field(default_factory=dict)
    context_match: dict[str, Any] = field(default_factory=dict)
    condition: dict[str, Any] | None = None
    obligations: tuple[AuthorizationObligation, ...] = ()
    priority: int = 0
    enabled: bool = True
    source_kind: str = "imported"


@dataclass(frozen=True, slots=True)
class TemporaryAuthorizationGrant:
    id: str
    scope: AuthorizationGrantScope
    created_at: datetime
    effect_ids: tuple[str, ...] = ()
    tool_ids: tuple[str, ...] = ()
    run_id: str | None = None
    session_key: str | None = None
    agent_id: str | None = None
    approval_request_id: str | None = None


@dataclass(frozen=True, slots=True)
class AuthorizationAuditRecord:
    id: str
    action: str
    status: str
    created_at: datetime
    actor_type: str | None = None
    actor_id: str | None = None
    target_policy_id: str | None = None
    reason: str = ""
    before_payload: dict[str, Any] = field(default_factory=dict)
    after_payload: dict[str, Any] = field(default_factory=dict)
    decision_payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
