from __future__ import annotations

import json
from collections.abc import Callable, Mapping

from crxzipple.modules.session.application import EnsureSessionInput, ResolveSessionInput
from crxzipple.modules.session.domain import (
    SessionOrigin,
    SessionReply,
    SessionResetPolicy,
    SessionRouteContext,
    SessionRuntimeBinding,
)


SessionInterfaceErrorFactory = Callable[[str], Exception]


def parse_json_object(
    raw: str | None,
    *,
    option_name: str,
    error_factory: SessionInterfaceErrorFactory,
) -> dict[str, object]:
    if raw is None or not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise error_factory(f"{option_name} must be valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise error_factory(f"{option_name} must decode to a JSON object.")
    return dict(payload)


def resolve_runtime_binding(
    *,
    runtime_binding_payload: Mapping[str, object] | None = None,
    agent_id: str | None = None,
    error_factory: SessionInterfaceErrorFactory,
) -> SessionRuntimeBinding:
    binding = SessionRuntimeBinding.from_payload(dict(runtime_binding_payload or {}))
    resolved_agent_id = (binding.agent_id or agent_id or "").strip()
    if not resolved_agent_id:
        raise error_factory("Session runtime binding agent_id is required.")
    return SessionRuntimeBinding(
        agent_id=resolved_agent_id,
        workspace=binding.workspace,
    )


def build_session_origin(
    payload: Mapping[str, object] | None,
) -> SessionOrigin | None:
    if payload is None:
        return None
    return SessionOrigin.from_payload(dict(payload))


def build_session_reply(
    payload: Mapping[str, object] | None,
) -> SessionReply | None:
    if payload is None:
        return None
    return SessionReply.from_payload(dict(payload))


def build_reset_policy(
    *,
    idle_minutes: int | None,
    daily_reset_hour_utc: int | None,
) -> SessionResetPolicy | None:
    if idle_minutes is None and daily_reset_hour_utc is None:
        return None
    return SessionResetPolicy(
        idle_minutes=idle_minutes,
        daily_reset_hour_utc=daily_reset_hour_utc,
    )


def build_ensure_session_input(
    *,
    key: str,
    runtime_binding_payload: Mapping[str, object] | None = None,
    agent_id: str | None = None,
    status: str = "active",
    channel: str | None = None,
    chat_type: str | None = None,
    origin_payload: Mapping[str, object] | None = None,
    reply_payload: Mapping[str, object] | None = None,
    metadata: Mapping[str, object] | None = None,
    active_session_id: str | None = None,
    error_factory: SessionInterfaceErrorFactory,
) -> EnsureSessionInput:
    binding = resolve_runtime_binding(
        runtime_binding_payload=runtime_binding_payload,
        agent_id=agent_id,
        error_factory=error_factory,
    )
    return EnsureSessionInput(
        key=key,
        agent_id=binding.agent_id or "",
        workspace=binding.workspace,
        status=status,
        channel=channel,
        chat_type=chat_type,
        origin=build_session_origin(origin_payload),
        reply=build_session_reply(reply_payload),
        metadata=dict(metadata or {}),
        active_session_id=active_session_id,
    )


def build_resolve_session_input(
    *,
    agent_id: str,
    channel: str | None = None,
    chat_type: str = "direct",
    peer_id: str | None = None,
    conversation_id: str | None = None,
    thread_id: str | None = None,
    account_id: str | None = None,
    label: str | None = None,
    surface: str | None = None,
    main_key: str = "main",
    direct_scope,
    status: str = "active",
    metadata: Mapping[str, object] | None = None,
    ensure: bool = False,
    touch_activity: bool = True,
    reset_policy: SessionResetPolicy | None = None,
) -> ResolveSessionInput:
    return ResolveSessionInput(
        context=SessionRouteContext(
            agent_id=agent_id,
            channel=channel,
            chat_type=chat_type,
            peer_id=peer_id,
            conversation_id=conversation_id,
            thread_id=thread_id,
            account_id=account_id,
            label=label,
            surface=surface,
            main_key=main_key,
            direct_scope=direct_scope,
            status=status,
            metadata=dict(metadata or {}),
        ),
        ensure=ensure,
        touch_activity=touch_activity,
        reset_policy=reset_policy,
    )
