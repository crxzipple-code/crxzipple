from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from crxzipple.modules.session.application.unit_of_work import SessionUnitOfWork
from crxzipple.modules.session.domain.entities import Session, SessionInstance
from crxzipple.modules.session.domain.value_objects import (
    SessionKind,
    SessionOrigin,
    SessionReply,
    utcnow,
)


def build_session_entity(
    *,
    key: str,
    agent_id: str,
    workspace: str | None,
    status: str,
    channel: str | None,
    chat_type: str | None,
    origin: SessionOrigin,
    reply: SessionReply,
    metadata: dict[str, object] | None,
    active_session_id: str | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    last_reset_at: datetime | None = None,
) -> Session:
    timestamp = created_at or utcnow()
    session = Session(
        id=key,
        agent_id=agent_id,
        active_session_id=active_session_id or str(uuid4()),
        status=status,
        channel=(channel.strip() or None) if channel else None,
        chat_type=(chat_type.strip() or None) if chat_type else None,
        origin=origin,
        reply=reply,
        metadata=dict(metadata or {}),
        created_at=timestamp,
        updated_at=updated_at or timestamp,
        last_reset_at=last_reset_at or timestamp,
    )
    session.sync_runtime_binding(
        agent_id=agent_id,
        workspace=workspace,
    )
    return session


def build_session_instance(
    *,
    session: Session,
    sequence_no: int,
    kind: SessionKind,
    instance_id: str | None = None,
    opened_at: datetime | None = None,
) -> SessionInstance:
    return SessionInstance(
        id=instance_id or str(uuid4()),
        session_key=session.id,
        sequence_no=sequence_no,
        kind=kind,
        opened_at=opened_at or utcnow(),
        metadata=build_runtime_binding_metadata(session),
    )


def ensure_session_instance_exists(
    uow: SessionUnitOfWork,
    *,
    session: Session,
    kind: SessionKind,
) -> None:
    if uow.session_instances.get(session.active_session_id) is not None:
        return
    instance = build_session_instance(
        session=session,
        sequence_no=next_session_instance_sequence(uow, session.id),
        kind=kind,
        instance_id=session.active_session_id,
        opened_at=session.last_reset_at,
    )
    uow.session_instances.add(instance)


def build_runtime_binding_metadata(session: Session) -> dict[str, object]:
    binding = session.runtime_binding()
    binding_payload = binding.to_payload()
    metadata: dict[str, object] = {
        "runtime_binding": binding_payload,
    }
    if binding.agent_id is not None:
        metadata["agent_id"] = binding.agent_id
    if binding.workspace is not None:
        metadata["workspace"] = binding.workspace
    return metadata


def runtime_binding_payload(session: Session) -> dict[str, object]:
    binding = session.runtime_binding()
    payload: dict[str, object] = {}
    if binding.agent_id is not None:
        payload["agent_id"] = binding.agent_id
    if binding.workspace is not None:
        payload["workspace"] = binding.workspace
    return payload


def sync_instance_runtime_binding(
    instance: SessionInstance,
    *,
    session: Session,
) -> None:
    metadata = dict(instance.metadata)
    metadata.pop("llm_id", None)
    metadata.update(build_runtime_binding_metadata(session))
    instance.metadata = metadata


def next_session_instance_sequence(
    uow: SessionUnitOfWork,
    session_key: str,
) -> int:
    return uow.session_instances.max_sequence_no(session_key=session_key) + 1


def infer_session_kind(
    session_key: str,
    *,
    chat_type: str | None = None,
) -> SessionKind:
    if ":thread:" in session_key:
        return SessionKind.THREAD
    if ":group:" in session_key:
        return SessionKind.GROUP
    if ":channel:" in session_key:
        return SessionKind.CHANNEL
    if ":dm:" in session_key:
        return SessionKind.DIRECT
    if chat_type == SessionKind.THREAD.value:
        return SessionKind.THREAD
    if chat_type == SessionKind.CHANNEL.value:
        return SessionKind.CHANNEL
    if chat_type == SessionKind.GROUP.value:
        return SessionKind.GROUP
    return SessionKind.MAIN
