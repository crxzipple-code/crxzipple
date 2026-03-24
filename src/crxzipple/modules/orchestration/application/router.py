from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.session.domain.exceptions import SessionValidationError
from crxzipple.modules.session.domain.value_objects import (
    DirectSessionScope,
    SessionDelivery,
    SessionKeyResolution,
    SessionKind,
    SessionOrigin,
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


def _default_segment(value: str | None, *, default: str) -> str:
    return _trimmed(value) or default


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


def resolve_bulk_key(context: SessionRouteContext) -> str:
    chat_type = _trimmed(context.chat_type) or SessionKind.DIRECT.value
    channel = _trimmed(context.channel)
    account_id = _trimmed(context.account_id)
    thread_id = _trimmed(context.thread_id)

    if chat_type == SessionKind.DIRECT.value:
        if context.direct_scope == DirectSessionScope.MAIN:
            main_key = _require_segment(context.main_key, field_name="main_key")
            bulk_key = (
                "conversation:main:"
                f"{_default_segment(channel, default='global')}:"
                f"{_default_segment(account_id, default='default')}:"
                f"{main_key}"
            )
        elif context.direct_scope == DirectSessionScope.PER_PEER:
            peer_id = _require_segment(context.peer_id, field_name="peer_id")
            bulk_key = (
                "conversation:dm:"
                f"{_default_segment(account_id, default='default')}:"
                f"{peer_id}"
            )
        else:
            peer_id = _require_segment(context.peer_id, field_name="peer_id")
            channel_segment = _require_segment(channel, field_name="channel")
            bulk_key = (
                "conversation:dm:"
                f"{channel_segment}:"
                f"{_default_segment(account_id, default='default')}:"
                f"{peer_id}"
            )
    else:
        channel_segment = _require_segment(channel, field_name="channel")
        conversation_id = _require_segment(
            context.conversation_id,
            field_name="conversation_id",
        )
        base_kind = (
            SessionKind.CHANNEL.value
            if chat_type == SessionKind.CHANNEL.value
            else SessionKind.GROUP.value
        )
        bulk_key = (
            "conversation:"
            f"{base_kind}:"
            f"{channel_segment}:"
            f"{_default_segment(account_id, default='default')}:"
            f"{conversation_id}"
        )

    if thread_id is not None:
        bulk_key = f"{bulk_key}:thread:{thread_id}"

    return bulk_key


def derive_origin(context: SessionRouteContext) -> SessionOrigin:
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


def derive_delivery(context: SessionRouteContext) -> SessionDelivery:
    return SessionDelivery(
        channel=_trimmed(context.channel),
        to_id=_trimmed(context.conversation_id) or _trimmed(context.peer_id),
        account_id=_trimmed(context.account_id),
        thread_id=_trimmed(context.thread_id),
    )


@dataclass(frozen=True, slots=True)
class SessionRoutingDecision:
    bulk_key: str
    key_resolution: SessionKeyResolution
    origin: SessionOrigin
    delivery: SessionDelivery
    lane_key: str


class OrchestrationRouter:
    def route_session(self, context: SessionRouteContext) -> SessionRoutingDecision:
        key_resolution = resolve_session_key(context)
        bulk_key = resolve_bulk_key(context)
        return SessionRoutingDecision(
            bulk_key=bulk_key,
            key_resolution=key_resolution,
            origin=derive_origin(context),
            delivery=derive_delivery(context),
            lane_key=f"bulk:{bulk_key}",
        )
