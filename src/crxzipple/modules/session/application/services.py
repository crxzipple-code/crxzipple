from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, time, timedelta, timezone
from typing import Any, Callable, Protocol
from uuid import uuid4

from crxzipple.modules.session.domain.entities import Session, SessionInstance
from crxzipple.modules.session.domain.exceptions import (
    SessionInstanceNotFoundError,
    SessionMessageNotFoundError,
    SessionNotFoundError,
    SessionValidationError,
)
from crxzipple.modules.session.domain.repositories import (
    SessionInstanceRepository,
    SessionMessageRepository,
    SessionRepository,
)
from crxzipple.modules.session.domain.value_objects import (
    SessionDelivery,
    SessionKind,
    SessionKeyResolution,
    SessionMessage,
    SessionMessageKind,
    SessionMessageVisibility,
    SessionOrigin,
    SessionResetDecision,
    SessionResetPolicy,
    utcnow,
)
from crxzipple.shared.domain.aggregates import AggregateRoot
from crxzipple.shared.domain.events import DomainEvent


@dataclass(frozen=True, slots=True)
class EnsureSessionInput:
    key: str
    agent_id: str
    llm_id: str
    status: str = "active"
    channel: str | None = None
    chat_type: str | None = None
    origin: SessionOrigin | None = None
    delivery: SessionDelivery | None = None
    metadata: dict[str, object] | None = None
    active_session_id: str | None = None


@dataclass(frozen=True, slots=True)
class AppendSessionMessageInput:
    session_key: str
    role: str
    content: str | None = None
    kind: SessionMessageKind = SessionMessageKind.MESSAGE
    content_payload: dict[str, object] = field(default_factory=dict)
    source_kind: str | None = None
    source_id: str | None = None
    visibility: SessionMessageVisibility = SessionMessageVisibility.DEFAULT
    metadata: dict[str, object] = field(default_factory=dict)
    session_id: str | None = None


@dataclass(frozen=True, slots=True)
class ResetSessionInput:
    session_key: str
    llm_id: str | None = None
    status: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    active_session_id: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class MergeSessionMetadataInput:
    session_key: str
    metadata: dict[str, object] = field(default_factory=dict)
    touch_activity: bool = True


@dataclass(frozen=True, slots=True)
class ListSessionMessagesInput:
    session_key: str
    limit: int | None = None
    active_session_only: bool = False
    include_archived: bool = True


@dataclass(frozen=True, slots=True)
class ArchiveSessionMessagesInput:
    session_key: str
    session_id: str
    max_sequence_no: int | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ListSessionInstancesInput:
    session_key: str


@dataclass(frozen=True, slots=True)
class SyncRoutedSessionInput:
    key_resolution: SessionKeyResolution
    agent_id: str
    llm_id: str
    status: str = "active"
    origin: SessionOrigin = field(default_factory=SessionOrigin)
    delivery: SessionDelivery = field(default_factory=SessionDelivery)
    metadata: dict[str, object] = field(default_factory=dict)
    ensure: bool = False
    touch_activity: bool = True
    reset_policy: SessionResetPolicy | None = None
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class RoutedSessionResult:
    resolution: SessionResolutionResult
    session: Session | None = None
    active_instance: SessionInstance | None = None


@dataclass(frozen=True, slots=True)
class SessionResolutionResult:
    key: str
    kind: SessionKind
    created: bool
    reset: bool
    reset_reason: str | None = None


class SessionUnitOfWork(Protocol):
    sessions: SessionRepository
    session_messages: SessionMessageRepository
    session_instances: SessionInstanceRepository

    def __enter__(self) -> "SessionUnitOfWork":
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        ...

    def collect(self, aggregate: AggregateRoot[Any]) -> None:
        ...

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...


class SessionApplicationService:
    def __init__(self, uow_factory: Callable[[], SessionUnitOfWork]) -> None:
        self.uow_factory = uow_factory

    def ensure_session(self, data: EnsureSessionInput) -> Session:
        with self.uow_factory() as uow:
            session = uow.sessions.get(data.key)
            if session is None:
                session = self._build_session(
                    key=data.key,
                    agent_id=data.agent_id,
                    llm_id=data.llm_id,
                    status=data.status,
                    channel=data.channel,
                    chat_type=data.chat_type,
                    origin=data.origin or SessionOrigin(),
                    delivery=data.delivery or SessionDelivery(),
                    metadata=data.metadata,
                    active_session_id=data.active_session_id,
                )
                instance = self._build_instance(
                    session=session,
                    sequence_no=1,
                    kind=self._infer_session_kind(
                        session.id,
                        chat_type=session.chat_type,
                    ),
                    instance_id=session.active_session_id,
                )
                uow.session_instances.add(instance)
                session.record_event(
                    DomainEvent(
                        name="session.started",
                        payload={
                            "session_key": session.id,
                            "active_session_id": session.active_session_id,
                            **self._runtime_binding_payload(session),
                        },
                    ),
                )
            else:
                session.apply_updates(
                    llm_id=data.llm_id,
                    status=data.status,
                    channel=data.channel,
                    chat_type=data.chat_type,
                    origin=data.origin,
                    delivery=data.delivery,
                    metadata=data.metadata,
                )
                self._ensure_instance_exists(
                    uow,
                    session=session,
                    kind=self._infer_session_kind(
                        session.id,
                        chat_type=session.chat_type,
                    ),
                )
                active_instance = uow.session_instances.get(session.active_session_id)
                if active_instance is not None:
                    self._sync_instance_runtime_binding(active_instance, session=session)
                    uow.session_instances.add(active_instance)
                session.record_event(
                    DomainEvent(
                        name="session.updated",
                        payload={
                            "session_key": session.id,
                            "active_session_id": session.active_session_id,
                            **self._runtime_binding_payload(session),
                        },
                    ),
                )
            uow.sessions.add(session)
            uow.collect(session)
            uow.commit()
            return session

    def sync_routed_session(
        self,
        data: SyncRoutedSessionInput,
    ) -> RoutedSessionResult:
        with self.uow_factory() as uow:
            now = data.now or utcnow()
            resolution = SessionResolutionResult(
                key=data.key_resolution.key,
                kind=data.key_resolution.kind,
                created=False,
                reset=False,
            )
            session = uow.sessions.get(data.key_resolution.key)
            active_instance: SessionInstance | None = None

            if session is not None:
                active_instance = uow.session_instances.get(session.active_session_id)
            next_sequence: int | None = None

            if not data.ensure:
                return RoutedSessionResult(
                    resolution=resolution,
                    session=session,
                    active_instance=active_instance,
                )

            if session is None:
                session = self._build_session(
                    key=data.key_resolution.key,
                    agent_id=data.agent_id,
                    llm_id=data.llm_id,
                    status=data.status,
                    channel=data.key_resolution.channel,
                    chat_type=data.key_resolution.chat_type,
                    origin=data.origin,
                    delivery=data.delivery,
                    metadata=data.metadata,
                    created_at=now,
                    updated_at=now,
                    last_reset_at=now,
                )
                active_instance = self._build_instance(
                    session=session,
                    sequence_no=1,
                    kind=data.key_resolution.kind,
                    opened_at=now,
                    instance_id=session.active_session_id,
                )
                uow.session_instances.add(active_instance)
                uow.sessions.add(session)
                session.record_event(
                    DomainEvent(
                        name="session.started",
                        payload={
                            "session_key": session.id,
                            "active_session_id": session.active_session_id,
                            **self._runtime_binding_payload(session),
                            "session_kind": data.key_resolution.kind.value,
                        },
                    ),
                )
                uow.collect(session)
                uow.commit()
                return RoutedSessionResult(
                    resolution=SessionResolutionResult(
                        key=data.key_resolution.key,
                        kind=data.key_resolution.kind,
                        created=True,
                        reset=False,
                    ),
                    session=session,
                    active_instance=active_instance,
                )

            reset_decision = _evaluate_session_reset(
                updated_at=session.updated_at,
                policy=data.reset_policy,
                now=now,
            )
            session.apply_updates(
                llm_id=data.llm_id,
                status=data.status,
                channel=data.key_resolution.channel,
                chat_type=data.key_resolution.chat_type,
                origin=data.origin,
                delivery=data.delivery,
                metadata=data.metadata,
                updated_at=now if data.touch_activity else session.updated_at,
            )
            if active_instance is None:
                next_sequence = self._next_instance_sequence(uow, session.id)
                active_instance = self._build_instance(
                    session=session,
                    sequence_no=next_sequence,
                    kind=data.key_resolution.kind,
                    opened_at=session.last_reset_at,
                    instance_id=session.active_session_id,
                )
                uow.session_instances.add(active_instance)
            else:
                self._sync_instance_runtime_binding(active_instance, session=session)
                uow.session_instances.add(active_instance)

            if reset_decision.should_reset:
                active_instance.close(
                    reason=reset_decision.reason,
                    closed_at=now,
                )
                uow.session_instances.add(active_instance)
                session.reset(
                    llm_id=data.llm_id,
                    status=data.status,
                    metadata=data.metadata,
                    happened_at=now,
                )
                next_sequence = (
                    next_sequence + 1
                    if next_sequence is not None
                    else self._next_instance_sequence(uow, session.id)
                )
                active_instance = self._build_instance(
                    session=session,
                    sequence_no=next_sequence,
                    kind=data.key_resolution.kind,
                    opened_at=now,
                    instance_id=session.active_session_id,
                )
                uow.session_instances.add(active_instance)
                session.record_event(
                    DomainEvent(
                        name="session.reset",
                        payload={
                            "session_key": session.id,
                            "active_session_id": session.active_session_id,
                            **self._runtime_binding_payload(session),
                            "reason": reset_decision.reason,
                        },
                    ),
                )
                resolution = SessionResolutionResult(
                    key=data.key_resolution.key,
                    kind=data.key_resolution.kind,
                    created=False,
                    reset=True,
                    reset_reason=reset_decision.reason,
                )
            else:
                session.record_event(
                    DomainEvent(
                        name="session.updated",
                        payload={
                            "session_key": session.id,
                            "active_session_id": session.active_session_id,
                            **self._runtime_binding_payload(session),
                            "session_kind": data.key_resolution.kind.value,
                        },
                    ),
                )
                resolution = SessionResolutionResult(
                    key=data.key_resolution.key,
                    kind=data.key_resolution.kind,
                    created=False,
                    reset=False,
                )

            uow.sessions.add(session)
            uow.collect(session)
            uow.commit()
            return RoutedSessionResult(
                resolution=resolution,
                session=session,
                active_instance=active_instance,
            )

    def get_session(self, session_key: str) -> Session:
        with self.uow_factory() as uow:
            session = uow.sessions.get(session_key)
            if session is None:
                raise SessionNotFoundError(f"Session '{session_key}' was not found.")
            return session

    def list_sessions(self, *, agent_id: str | None = None) -> list[Session]:
        with self.uow_factory() as uow:
            return uow.sessions.list(agent_id=agent_id)

    def merge_session_metadata(
        self,
        session_key: str,
        *,
        metadata: dict[str, object],
        touch_activity: bool = True,
    ) -> Session:
        with self.uow_factory() as uow:
            session = uow.sessions.get(session_key)
            if session is None:
                raise SessionNotFoundError(f"Session '{session_key}' was not found.")
            session.apply_updates(
                metadata=metadata,
                updated_at=utcnow() if touch_activity else session.updated_at,
            )
            active_instance = uow.session_instances.get(session.active_session_id)
            if active_instance is not None:
                self._sync_instance_runtime_binding(active_instance, session=session)
                uow.session_instances.add(active_instance)
            session.record_event(
                DomainEvent(
                    name="session.updated",
                    payload={
                        "session_key": session.id,
                        "active_session_id": session.active_session_id,
                        **self._runtime_binding_payload(session),
                    },
                ),
            )
            uow.sessions.add(session)
            uow.collect(session)
            uow.commit()
            return session

    def list_instances(
        self,
        data: ListSessionInstancesInput,
    ) -> list[SessionInstance]:
        with self.uow_factory() as uow:
            session = uow.sessions.get(data.session_key)
            if session is None:
                raise SessionNotFoundError(
                    f"Session '{data.session_key}' was not found.",
                )
            return uow.session_instances.list(session_key=session.id)

    def get_instance(self, instance_id: str) -> SessionInstance:
        with self.uow_factory() as uow:
            instance = uow.session_instances.get(instance_id)
            if instance is None:
                raise SessionInstanceNotFoundError(
                    f"Session instance '{instance_id}' was not found.",
                )
            return instance

    def get_message(self, message_id: str) -> SessionMessage:
        with self.uow_factory() as uow:
            message = uow.session_messages.get(message_id)
            if message is None:
                raise SessionMessageNotFoundError(
                    f"Session message '{message_id}' was not found.",
                )
            return message

    def append_message(self, data: AppendSessionMessageInput) -> SessionMessage:
        with self.uow_factory() as uow:
            session = uow.sessions.get(data.session_key)
            if session is None:
                raise SessionNotFoundError(
                    f"Session '{data.session_key}' was not found.",
                )
            target_session_id = data.session_id or session.active_session_id
            if uow.session_instances.get(target_session_id) is None:
                raise SessionInstanceNotFoundError(
                    f"Session instance '{target_session_id}' was not found.",
                )
            content_payload = dict(data.content_payload)
            if not content_payload and data.content is not None and data.content.strip():
                content_payload = {"text": data.content}
            message = SessionMessage(
                id=str(uuid4()),
                session_key=session.id,
                session_id=target_session_id,
                sequence_no=self._next_message_sequence(
                    uow,
                    session_key=session.id,
                    session_id=target_session_id,
                ),
                role=data.role,
                content=data.content,
                kind=data.kind,
                content_payload=content_payload,
                source_kind=data.source_kind,
                source_id=data.source_id,
                visibility=data.visibility,
                metadata=dict(data.metadata),
            )
            uow.session_messages.add(message)
            session.apply_updates(updated_at=message.created_at)
            session.record_event(
                DomainEvent(
                    name="session.message.appended",
                    payload={
                        "session_key": session.id,
                        "active_session_id": session.active_session_id,
                        "message_id": message.id,
                        "role": message.role,
                    },
                ),
            )
            uow.sessions.add(session)
            uow.collect(session)
            uow.commit()
            return message

    def archive_messages(self, data: ArchiveSessionMessagesInput) -> int:
        with self.uow_factory() as uow:
            session = uow.sessions.get(data.session_key)
            if session is None:
                raise SessionNotFoundError(
                    f"Session '{data.session_key}' was not found.",
                )
            if uow.session_instances.get(data.session_id) is None:
                raise SessionInstanceNotFoundError(
                    f"Session instance '{data.session_id}' was not found.",
                )
            messages = uow.session_messages.list(
                session_key=session.id,
                session_id=data.session_id,
            )
            archived_count = 0
            for message in messages:
                if (
                    data.max_sequence_no is not None
                    and message.sequence_no > data.max_sequence_no
                ):
                    continue
                if message.visibility is SessionMessageVisibility.ARCHIVED:
                    continue
                metadata = dict(message.metadata)
                if data.reason is not None and data.reason.strip():
                    metadata["archived_reason"] = data.reason.strip()
                archived = replace(
                    message,
                    visibility=SessionMessageVisibility.ARCHIVED,
                    metadata=metadata,
                )
                uow.session_messages.add(archived)
                archived_count += 1
            if archived_count > 0:
                session.apply_updates(updated_at=utcnow())
                session.record_event(
                    DomainEvent(
                        name="session.messages.archived",
                        payload={
                            "session_key": session.id,
                            "session_id": data.session_id,
                            "count": archived_count,
                        },
                    ),
                )
                uow.sessions.add(session)
                uow.collect(session)
            uow.commit()
            return archived_count

    def get_message_by_source(
        self,
        *,
        session_key: str,
        session_id: str,
        source_kind: str,
        source_id: str,
    ) -> SessionMessage | None:
        with self.uow_factory() as uow:
            session = uow.sessions.get(session_key)
            if session is None:
                raise SessionNotFoundError(
                    f"Session '{session_key}' was not found.",
                )
            if uow.session_instances.get(session_id) is None:
                raise SessionInstanceNotFoundError(
                    f"Session instance '{session_id}' was not found.",
                )
            return uow.session_messages.get_by_source(
                session_key=session.id,
                session_id=session_id,
                source_kind=source_kind,
                source_id=source_id,
            )

    def list_messages(
        self,
        data: ListSessionMessagesInput,
    ) -> list[SessionMessage]:
        with self.uow_factory() as uow:
            session = uow.sessions.get(data.session_key)
            if session is None:
                raise SessionNotFoundError(
                    f"Session '{data.session_key}' was not found.",
                )
            session_id = session.active_session_id if data.active_session_only else None
            return uow.session_messages.list(
                session_key=session.id,
                session_id=session_id,
                limit=data.limit,
                include_archived=data.include_archived,
            )

    def reset_session(self, data: ResetSessionInput) -> Session:
        with self.uow_factory() as uow:
            session = uow.sessions.get(data.session_key)
            if session is None:
                raise SessionNotFoundError(
                    f"Session '{data.session_key}' was not found.",
                )
            current_instance = uow.session_instances.get(session.active_session_id)
            if current_instance is not None:
                current_instance.close(
                    reason=data.reason or "manual",
                    closed_at=utcnow(),
                )
                uow.session_instances.add(current_instance)
            session.reset(
                active_session_id=data.active_session_id,
                llm_id=data.llm_id,
                status=data.status,
                metadata=data.metadata,
            )
            next_instance = self._build_instance(
                session=session,
                sequence_no=self._next_instance_sequence(uow, session.id),
                kind=self._infer_session_kind(
                    session.id,
                    chat_type=session.chat_type,
                ),
                instance_id=session.active_session_id,
                opened_at=session.last_reset_at,
            )
            uow.session_instances.add(next_instance)
            session.record_event(
                DomainEvent(
                    name="session.reset",
                    payload={
                        "session_key": session.id,
                        "active_session_id": session.active_session_id,
                        **self._runtime_binding_payload(session),
                        "reason": data.reason or "manual",
                    },
                ),
            )
            uow.sessions.add(session)
            uow.collect(session)
            uow.commit()
            return session

    def _build_session(
        self,
        *,
        key: str,
        agent_id: str,
        llm_id: str,
        status: str,
        channel: str | None,
        chat_type: str | None,
        origin: SessionOrigin,
        delivery: SessionDelivery,
        metadata: dict[str, object] | None,
        active_session_id: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        last_reset_at: datetime | None = None,
    ) -> Session:
        timestamp = created_at or utcnow()
        return Session(
            id=key,
            agent_id=agent_id,
            llm_id=llm_id,
            active_session_id=active_session_id or str(uuid4()),
            status=status,
            channel=(channel.strip() or None) if channel else None,
            chat_type=(chat_type.strip() or None) if chat_type else None,
            origin=origin,
            delivery=delivery,
            metadata=dict(metadata or {}),
            created_at=timestamp,
            updated_at=updated_at or timestamp,
            last_reset_at=last_reset_at or timestamp,
        )

    def _build_instance(
        self,
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
            metadata=self._build_runtime_binding_metadata(session),
        )

    def _ensure_instance_exists(
        self,
        uow: SessionUnitOfWork,
        *,
        session: Session,
        kind: SessionKind,
    ) -> None:
        if uow.session_instances.get(session.active_session_id) is not None:
            return
        instance = self._build_instance(
            session=session,
            sequence_no=self._next_instance_sequence(uow, session.id),
            kind=kind,
            instance_id=session.active_session_id,
            opened_at=session.last_reset_at,
        )
        uow.session_instances.add(instance)

    @staticmethod
    def _build_runtime_binding_metadata(session: Session) -> dict[str, object]:
        binding = session.runtime_binding()
        binding_payload = binding.to_payload()
        metadata: dict[str, object] = {
            "runtime_binding": binding_payload,
        }
        if binding.agent_id is not None:
            metadata["agent_id"] = binding.agent_id
        if binding.llm_id is not None:
            metadata["llm_id"] = binding.llm_id
        return metadata

    @staticmethod
    def _runtime_binding_payload(session: Session) -> dict[str, object]:
        binding = session.runtime_binding()
        payload: dict[str, object] = {}
        if binding.agent_id is not None:
            payload["agent_id"] = binding.agent_id
        if binding.llm_id is not None:
            payload["llm_id"] = binding.llm_id
        return payload

    def _sync_instance_runtime_binding(
        self,
        instance: SessionInstance,
        *,
        session: Session,
    ) -> None:
        metadata = dict(instance.metadata)
        metadata.update(self._build_runtime_binding_metadata(session))
        instance.metadata = metadata

    def _next_instance_sequence(
        self,
        uow: SessionUnitOfWork,
        session_key: str,
    ) -> int:
        return uow.session_instances.max_sequence_no(session_key=session_key) + 1

    def _next_message_sequence(
        self,
        uow: SessionUnitOfWork,
        *,
        session_key: str,
        session_id: str,
    ) -> int:
        return (
            uow.session_messages.max_sequence_no(
                session_key=session_key,
                session_id=session_id,
            )
            + 1
        )

    @staticmethod
    def _infer_session_kind(
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


def _idle_expiry(updated_at: datetime, idle_minutes: int) -> datetime:
    return updated_at + timedelta(minutes=idle_minutes)


def _daily_expiry(updated_at: datetime, daily_reset_hour_utc: int) -> datetime:
    normalized = updated_at.astimezone(timezone.utc)
    boundary = datetime.combine(
        normalized.date(),
        time(hour=daily_reset_hour_utc, tzinfo=timezone.utc),
    )
    if normalized >= boundary:
        boundary += timedelta(days=1)
    return boundary


def _evaluate_session_reset(
    *,
    updated_at: datetime,
    policy: SessionResetPolicy | None,
    now: datetime,
) -> SessionResetDecision:
    if policy is None:
        return SessionResetDecision(should_reset=False)

    candidates: list[tuple[str, datetime]] = []
    if policy.idle_minutes is not None:
        if policy.idle_minutes <= 0:
            raise SessionValidationError(
                "Session idle_minutes must be greater than zero.",
            )
        candidates.append(("idle", _idle_expiry(updated_at, policy.idle_minutes)))
    if policy.daily_reset_hour_utc is not None:
        if not 0 <= policy.daily_reset_hour_utc <= 23:
            raise SessionValidationError(
                "Session daily_reset_hour_utc must be between 0 and 23.",
            )
        candidates.append(
            ("daily", _daily_expiry(updated_at, policy.daily_reset_hour_utc)),
        )

    if not candidates:
        return SessionResetDecision(should_reset=False)

    reason, expires_at = min(candidates, key=lambda item: item[1])
    if now >= expires_at:
        return SessionResetDecision(
            should_reset=True,
            reason=reason,
            expires_at=expires_at,
        )
    return SessionResetDecision(
        should_reset=False,
        expires_at=expires_at,
    )
