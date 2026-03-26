from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AuthorizationEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class AuthorizationGrantScope(StrEnum):
    RUN = "run"
    SESSION = "session"


class AuthorizationDecisionCode(StrEnum):
    ALLOW = "allow"
    POLICY_DENIED = "policy_denied"
    NO_MATCH = "no_match"
    APPROVAL_REQUIRED = "approval_required"
    AUTHORIZATION_DISABLED = "authorization_disabled"


@dataclass(frozen=True, slots=True)
class AuthorizationSubject:
    type: str = "anonymous"
    id: str | None = None
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AuthorizationResource:
    kind: str
    id: str | None = None
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AuthorizationObligation:
    name: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    subject: AuthorizationSubject
    action: str
    resource: AuthorizationResource
    context: AuthorizationContext = field(default_factory=AuthorizationContext)


@dataclass(frozen=True, slots=True)
class ToolExecutionAuthorizationRequest:
    subject: AuthorizationSubject
    resource: AuthorizationResource
    context: AuthorizationContext = field(default_factory=AuthorizationContext)
    required_effect_ids: tuple[str, ...] = ()
    granted_tool_ids: tuple[str, ...] = ()
    granted_effect_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    code: AuthorizationDecisionCode = AuthorizationDecisionCode.ALLOW
    matched_policy_ids: tuple[str, ...] = ()
    obligations: tuple[AuthorizationObligation, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)
