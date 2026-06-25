from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from crxzipple.modules.session.domain.entities import Session, SessionInstance
from crxzipple.modules.session.domain.value_objects import (
    SessionKeyResolution,
    SessionKind,
    SessionOrigin,
    SessionReply,
    SessionResetPolicy,
)


@dataclass(frozen=True, slots=True)
class EnsureSessionInput:
    key: str
    agent_id: str
    workspace: str | None = None
    status: str = "active"
    channel: str | None = None
    chat_type: str | None = None
    origin: SessionOrigin | None = None
    reply: SessionReply | None = None
    metadata: dict[str, object] | None = None
    active_session_id: str | None = None


@dataclass(frozen=True, slots=True)
class ResetSessionInput:
    session_key: str
    status: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    active_session_id: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class SyncRoutedSessionInput:
    key_resolution: SessionKeyResolution
    agent_id: str
    workspace: str | None = None
    status: str = "active"
    origin: SessionOrigin = field(default_factory=SessionOrigin)
    reply: SessionReply = field(default_factory=SessionReply)
    metadata: dict[str, object] = field(default_factory=dict)
    ensure: bool = False
    touch_activity: bool = True
    reset_policy: SessionResetPolicy | None = None
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class SessionResolutionResult:
    key: str
    kind: SessionKind
    created: bool
    reset: bool
    reset_reason: str | None = None


@dataclass(frozen=True, slots=True)
class RoutedSessionResult:
    resolution: SessionResolutionResult
    session: Session | None = None
    active_instance: SessionInstance | None = None
