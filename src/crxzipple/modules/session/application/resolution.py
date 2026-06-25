from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from crxzipple.modules.session.application.session_lifecycle import (
    RoutedSessionResult,
    SyncRoutedSessionInput,
)
from crxzipple.modules.session.application.services import SessionApplicationService
from crxzipple.modules.session.domain.entities import Session, SessionInstance
from crxzipple.modules.session.domain.exceptions import SessionValidationError
from crxzipple.modules.session.domain.value_objects import (
    DirectSessionScope,
    SessionKeyResolution,
    SessionKind,
    SessionOrigin,
    SessionReply,
    SessionResetPolicy,
    SessionRouteContext,
)


def _trimmed(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _require_segment(value: str | None, *, field_name: str) -> str:
    trimmed = _trimmed(value)
    if trimmed is None:
        raise SessionValidationError(f"Session route {field_name} cannot be empty.")
    return trimmed


def resolve_session_key(context: SessionRouteContext) -> SessionKeyResolution:
    chat_type = _trimmed(context.chat_type) or SessionKind.DIRECT.value
    channel = _trimmed(context.channel)
    thread_id = _trimmed(context.thread_id)

    if chat_type == SessionKind.DIRECT.value:
        if context.direct_scope == DirectSessionScope.MAIN:
            key = f"agent:{context.agent_id}:{context.main_key}"
            kind = SessionKind.MAIN
        elif context.direct_scope == DirectSessionScope.PER_PEER:
            peer_id = _require_segment(context.peer_id, field_name="peer_id")
            key = f"agent:{context.agent_id}:dm:{peer_id}"
            kind = SessionKind.DIRECT
        elif context.direct_scope == DirectSessionScope.PER_CHANNEL_PEER:
            peer_id = _require_segment(context.peer_id, field_name="peer_id")
            channel = _require_segment(channel, field_name="channel")
            key = f"agent:{context.agent_id}:{channel}:dm:{peer_id}"
            kind = SessionKind.DIRECT
        else:
            peer_id = _require_segment(context.peer_id, field_name="peer_id")
            channel = _require_segment(channel, field_name="channel")
            account_id = _trimmed(context.account_id) or "default"
            key = f"agent:{context.agent_id}:{channel}:{account_id}:dm:{peer_id}"
            kind = SessionKind.DIRECT
    else:
        channel = _require_segment(channel, field_name="channel")
        conversation_id = _require_segment(
            context.conversation_id,
            field_name="conversation_id",
        )
        base_kind = (
            SessionKind.CHANNEL
            if chat_type == SessionKind.CHANNEL.value
            else SessionKind.GROUP
        )
        key = f"agent:{context.agent_id}:{channel}:{base_kind.value}:{conversation_id}"
        kind = base_kind

    if thread_id is not None:
        key = f"{key}:thread:{thread_id}"
        kind = SessionKind.THREAD

    return SessionKeyResolution(
        key=key,
        kind=kind,
        channel=channel,
        chat_type=chat_type,
    )


def derive_session_origin(context: SessionRouteContext) -> SessionOrigin:
    return SessionOrigin(
        label=_trimmed(context.label),
        provider=_trimmed(context.channel),
        surface=_trimmed(context.surface),
        chat_type=_trimmed(context.chat_type),
        from_id=_trimmed(context.peer_id),
        to_id=_trimmed(context.conversation_id) or _trimmed(context.peer_id),
        account_id=_trimmed(context.account_id),
        thread_id=_trimmed(context.thread_id),
    )


def derive_session_reply(context: SessionRouteContext) -> SessionReply:
    return SessionReply(
        channel=_trimmed(context.channel),
        to_id=_trimmed(context.conversation_id) or _trimmed(context.peer_id),
        account_id=_trimmed(context.account_id),
        thread_id=_trimmed(context.thread_id),
    )


@dataclass(frozen=True, slots=True)
class SessionRoutingDecision:
    key_resolution: SessionKeyResolution
    origin: SessionOrigin
    reply: SessionReply


@dataclass(frozen=True, slots=True)
class ResolveSessionInput:
    context: SessionRouteContext
    ensure: bool = False
    touch_activity: bool = True
    reset_policy: SessionResetPolicy | None = None
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class ResolvedSessionBundle:
    routing: SessionRoutingDecision
    resolution: RoutedSessionResult
    session: Session | None = None
    active_instance: SessionInstance | None = None


@dataclass(slots=True)
class SessionResolutionService:
    session_service: SessionApplicationService

    def route(self, context: SessionRouteContext) -> SessionRoutingDecision:
        return SessionRoutingDecision(
            key_resolution=resolve_session_key(context),
            origin=derive_session_origin(context),
            reply=derive_session_reply(context),
        )

    def resolve(self, data: ResolveSessionInput) -> ResolvedSessionBundle:
        routing = self.route(data.context)
        resolved = self.session_service.sync_routed_session(
            SyncRoutedSessionInput(
                key_resolution=routing.key_resolution,
                agent_id=data.context.agent_id,
                status=data.context.status,
                origin=routing.origin,
                reply=routing.reply,
                metadata=data.context.metadata,
                ensure=data.ensure,
                touch_activity=data.touch_activity,
                reset_policy=data.reset_policy,
                now=data.now,
            ),
        )
        return ResolvedSessionBundle(
            routing=routing,
            resolution=resolved,
            session=resolved.session,
            active_instance=resolved.active_instance,
        )
