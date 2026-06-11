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
    SessionKind,
    SessionKeyResolution,
    SessionMessage,
    SessionMessageKind,
    SessionMessageVisibility,
    SessionOrigin,
    SessionReply,
    SessionResetDecision,
    SessionResetPolicy,
    utcnow,
)
from crxzipple.shared.content_blocks import content_blocks_from_payload
from crxzipple.shared.domain.aggregates import AggregateRoot
from crxzipple.shared.domain.events import Event
from crxzipple.shared.time import format_datetime_utc as _format_datetime_utc


def _session_message_fact_payload(message: SessionMessage) -> dict[str, object]:
    return {
        "message_id": message.id,
        "session_key": message.session_key,
        "session_id": message.session_id,
        "role": message.role,
        "kind": message.kind.value,
        "source_kind": message.source_kind,
        "source_id": message.source_id,
        "message": {
            **message.to_payload(),
            "created_at": _format_datetime_utc(message.created_at),
        },
    }


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
class AppendSessionMessageInput:
    session_key: str
    role: str
    kind: SessionMessageKind = SessionMessageKind.MESSAGE
    content_payload: dict[str, object] = field(default_factory=dict)
    source_kind: str | None = None
    source_id: str | None = None
    visibility: SessionMessageVisibility = SessionMessageVisibility.DEFAULT
    metadata: dict[str, object] = field(default_factory=dict)
    session_id: str | None = None


@dataclass(frozen=True, slots=True)
class AppendSessionMessagesInput:
    messages: tuple[AppendSessionMessageInput, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ResetSessionInput:
    session_key: str
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
class MergeSessionMessageMetadataInput:
    message_id: str
    metadata: dict[str, object] = field(default_factory=dict)
    touch_activity: bool = False


@dataclass(frozen=True, slots=True)
class ListSessionMessagesInput:
    session_key: str
    limit: int | None = None
    active_session_only: bool = False
    include_archived: bool = True
    after_sequence_no: int | None = None
    before_sequence_no: int | None = None


@dataclass(frozen=True, slots=True)
class SessionMessagesBundle:
    session: Session
    messages: tuple[SessionMessage, ...]


@dataclass(frozen=True, slots=True)
class ArchiveSessionMessagesInput:
    session_key: str
    session_id: str
    max_sequence_no: int | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class CompactSessionSegmentInput:
    session_key: str
    session_id: str
    summary_message_id: str
    summary_text: str
    compaction_run_id: str
    archived_through_sequence_no: int | None = None
    reason: str | None = "compaction"


@dataclass(frozen=True, slots=True)
class CompactSessionSegmentResult:
    session: Session
    compacted_session_id: str
    active_session_id: str
    archived_message_count: int
    archived_through_sequence_no: int | None = None
    compacted_at: str | None = None


@dataclass(frozen=True, slots=True)
class ListSessionInstancesInput:
    session_key: str


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

    def flush(self) -> None:
        ...

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...


class SessionApplicationService:
    def __init__(
        self,
        uow_factory: Callable[[], SessionUnitOfWork],
        *,
        workspace_defaults_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        self.uow_factory = uow_factory
        self.workspace_defaults_resolver = workspace_defaults_resolver

    def ensure_session(self, data: EnsureSessionInput) -> Session:
        with self.uow_factory() as uow:
            session = uow.sessions.get(data.key)
            if session is None:
                session = self._build_session(
                    key=data.key,
                    agent_id=data.agent_id,
                    workspace=self._resolve_new_session_workspace(
                        agent_id=data.agent_id,
                        workspace=data.workspace,
                    ),
                    status=data.status,
                    channel=data.channel,
                    chat_type=data.chat_type,
                    origin=data.origin or SessionOrigin(),
                    reply=data.reply or SessionReply(),
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
                uow.sessions.add(session)
                uow.flush()
                uow.session_instances.add(instance)
                session.record_event(
                    Event(
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
                    status=data.status,
                    channel=data.channel,
                    chat_type=data.chat_type,
                    origin=data.origin,
                    reply=data.reply,
                    metadata=data.metadata,
                    workspace=data.workspace,
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
                    Event(
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
                    workspace=self._resolve_new_session_workspace(
                        agent_id=data.agent_id,
                        workspace=data.workspace,
                    ),
                    status=data.status,
                    channel=data.key_resolution.channel,
                    chat_type=data.key_resolution.chat_type,
                    origin=data.origin,
                    reply=data.reply,
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
                uow.sessions.add(session)
                uow.flush()
                uow.session_instances.add(active_instance)
                session.record_event(
                    Event(
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
                status=data.status,
                channel=data.key_resolution.channel,
                chat_type=data.key_resolution.chat_type,
                origin=data.origin,
                reply=data.reply,
                metadata=data.metadata,
                workspace=data.workspace,
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
                    status=data.status,
                    metadata=data.metadata,
                    workspace=data.workspace,
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
                    Event(
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
                    Event(
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
                Event(
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

    def merge_message_metadata(
        self,
        data: MergeSessionMessageMetadataInput,
    ) -> SessionMessage:
        with self.uow_factory() as uow:
            message = uow.session_messages.get(data.message_id)
            if message is None:
                raise SessionMessageNotFoundError(
                    f"Session message '{data.message_id}' was not found.",
                )
            metadata = dict(message.metadata)
            metadata.update(data.metadata)
            updated_message = replace(message, metadata=metadata)
            uow.session_messages.add(updated_message)
            session = uow.sessions.get(updated_message.session_key)
            if session is not None and data.touch_activity:
                session.apply_updates(updated_at=utcnow())
                uow.sessions.add(session)
                uow.collect(session)
            uow.commit()
            return updated_message

    def append_message(self, data: AppendSessionMessageInput) -> SessionMessage:
        return self.append_messages(
            AppendSessionMessagesInput(messages=(data,)),
        )[0]

    def append_messages(
        self,
        data: AppendSessionMessagesInput,
    ) -> tuple[SessionMessage, ...]:
        if not data.messages:
            return ()
        with self.uow_factory() as uow:
            first = data.messages[0]
            session = uow.sessions.get(first.session_key)
            if session is None:
                raise SessionNotFoundError(
                    f"Session '{first.session_key}' was not found.",
                )
            target_session_id = first.session_id or session.active_session_id
            if uow.session_instances.get(target_session_id) is None:
                raise SessionInstanceNotFoundError(
                    f"Session instance '{target_session_id}' was not found.",
                )
            next_sequence_no = self._next_message_sequence(
                uow,
                session_key=session.id,
                session_id=target_session_id,
            )
            messages: list[SessionMessage] = []
            for offset, item in enumerate(data.messages):
                if item.session_key != session.id:
                    raise SessionValidationError(
                        "Batched session messages must share a session_key.",
                    )
                item_session_id = item.session_id or session.active_session_id
                if item_session_id != target_session_id:
                    raise SessionValidationError(
                        "Batched session messages must share a session_id.",
                    )
                message = self._build_message(
                    item,
                    session_key=session.id,
                    session_id=target_session_id,
                    sequence_no=next_sequence_no + offset,
                )
                messages.append(message)
            uow.session_messages.add_many_new(tuple(messages))
            if messages:
                session.updated_at = messages[-1].created_at
                uow.sessions.touch_updated_at(
                    session_key=session.id,
                    updated_at=session.updated_at,
                )
            for message in messages:
                session.record_event(
                    Event(
                        name="session.message.appended",
                        payload=_session_message_fact_payload(message),
                    ),
                )
            uow.collect(session)
            uow.commit()
            return tuple(messages)

    def _build_message(
        self,
        data: AppendSessionMessageInput,
        *,
        session_key: str,
        session_id: str,
        sequence_no: int,
    ) -> SessionMessage:
        content_payload = dict(data.content_payload)
        content_blocks = content_blocks_from_payload(content_payload)
        is_function_call_message = (
            data.kind is SessionMessageKind.MESSAGE
            and content_payload.get("type") == "function_call"
        )
        if (
            not content_blocks
            and data.kind is SessionMessageKind.MESSAGE
            and not is_function_call_message
        ):
            raise SessionValidationError(
                "Session message content_payload.blocks is required for message content.",
            )
        return SessionMessage(
            id=str(uuid4()),
            session_key=session_key,
            session_id=session_id,
            sequence_no=sequence_no,
            role=data.role,
            kind=data.kind,
            content_payload=content_payload,
            source_kind=data.source_kind,
            source_id=data.source_id,
            visibility=data.visibility,
            metadata=dict(data.metadata),
        )

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
                    Event(
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

    def compact_active_segment(
        self,
        data: CompactSessionSegmentInput,
    ) -> CompactSessionSegmentResult:
        normalized_session_id = data.session_id.strip()
        normalized_summary_message_id = data.summary_message_id.strip()
        normalized_summary_text = data.summary_text.strip()
        normalized_compaction_run_id = data.compaction_run_id.strip()
        normalized_reason = (data.reason or "compaction").strip() or "compaction"
        if not normalized_session_id:
            raise SessionValidationError("Compaction session_id cannot be empty.")
        if not normalized_summary_message_id:
            raise SessionValidationError(
                "Compaction summary_message_id cannot be empty.",
            )
        if not normalized_summary_text:
            raise SessionValidationError("Compaction summary_text cannot be empty.")
        if not normalized_compaction_run_id:
            raise SessionValidationError("Compaction run id cannot be empty.")
        if (
            data.archived_through_sequence_no is not None
            and data.archived_through_sequence_no < 0
        ):
            raise SessionValidationError(
                "Compaction archived_through_sequence_no cannot be negative.",
            )

        with self.uow_factory() as uow:
            session = uow.sessions.get(data.session_key)
            if session is None:
                raise SessionNotFoundError(
                    f"Session '{data.session_key}' was not found.",
                )
            if normalized_session_id != session.active_session_id:
                raise SessionValidationError(
                    "Session segment compaction requires the current active session_id.",
                )
            current_instance = uow.session_instances.get(normalized_session_id)
            if current_instance is None:
                raise SessionInstanceNotFoundError(
                    f"Session instance '{normalized_session_id}' was not found.",
                )
            summary_message = uow.session_messages.get(normalized_summary_message_id)
            if summary_message is None:
                raise SessionMessageNotFoundError(
                    f"Session message '{normalized_summary_message_id}' was not found.",
                )
            if (
                summary_message.session_key != session.id
                or summary_message.session_id != normalized_session_id
            ):
                raise SessionValidationError(
                    "Compaction summary message must belong to the active session segment.",
                )

            archive_through = (
                data.archived_through_sequence_no
                if data.archived_through_sequence_no is not None
                else max(summary_message.sequence_no - 1, 0)
            )
            messages = uow.session_messages.list(
                session_key=session.id,
                session_id=normalized_session_id,
            )
            archived_count = 0
            for message in messages:
                if message.id == summary_message.id:
                    continue
                if message.sequence_no > archive_through:
                    continue
                if message.visibility is SessionMessageVisibility.ARCHIVED:
                    continue
                metadata = dict(message.metadata)
                metadata["archived_reason"] = normalized_reason
                metadata["archived_by_compaction_run_id"] = normalized_compaction_run_id
                archived = replace(
                    message,
                    visibility=SessionMessageVisibility.ARCHIVED,
                    metadata=metadata,
                )
                uow.session_messages.add(archived)
                archived_count += 1

            compacted_at = utcnow()
            current_instance.close(
                reason=normalized_reason,
                closed_at=compacted_at,
            )
            instance_metadata = dict(current_instance.metadata)
            instance_metadata["segment"] = {
                "kind": "compacted",
                "summary_message_id": summary_message.id,
                "summary_text": normalized_summary_text,
                "compaction_run_id": normalized_compaction_run_id,
                "archived_message_count": archived_count,
                "archived_through_sequence_no": archive_through,
                "compacted_at": _format_datetime_utc(compacted_at),
                "reason": normalized_reason,
            }
            current_instance.metadata = instance_metadata
            uow.session_instances.add(current_instance)

            session.reset(
                status=session.status,
                happened_at=compacted_at,
            )
            next_instance = self._build_instance(
                session=session,
                sequence_no=self._next_instance_sequence(uow, session.id),
                kind=current_instance.kind,
                instance_id=session.active_session_id,
                opened_at=session.last_reset_at,
            )
            uow.session_instances.add(next_instance)
            session.record_event(
                Event(
                    name="session.segment.compacted",
                    payload={
                        "session_key": session.id,
                        "closed_session_id": normalized_session_id,
                        "active_session_id": session.active_session_id,
                        "archived_message_count": archived_count,
                        "compaction_run_id": normalized_compaction_run_id,
                    },
                ),
            )
            uow.sessions.add(session)
            uow.collect(session)
            uow.commit()
            return CompactSessionSegmentResult(
                session=session,
                compacted_session_id=normalized_session_id,
                active_session_id=session.active_session_id,
                archived_message_count=archived_count,
                archived_through_sequence_no=archive_through,
                compacted_at=_format_datetime_utc(compacted_at),
            )

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
        return list(self.get_session_with_messages(data).messages)

    def get_session_with_messages(
        self,
        data: ListSessionMessagesInput,
    ) -> SessionMessagesBundle:
        with self.uow_factory() as uow:
            session = uow.sessions.get(data.session_key)
            if session is None:
                raise SessionNotFoundError(
                    f"Session '{data.session_key}' was not found.",
                )
            session_id = session.active_session_id if data.active_session_only else None
            messages = uow.session_messages.list(
                session_key=session.id,
                session_id=session_id,
                limit=data.limit,
                include_archived=data.include_archived,
                after_sequence_no=data.after_sequence_no,
                before_sequence_no=data.before_sequence_no,
            )
            return SessionMessagesBundle(
                session=session,
                messages=tuple(messages),
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
                Event(
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
        if binding.workspace is not None:
            metadata["workspace"] = binding.workspace
        return metadata

    @staticmethod
    def _runtime_binding_payload(session: Session) -> dict[str, object]:
        binding = session.runtime_binding()
        payload: dict[str, object] = {}
        if binding.agent_id is not None:
            payload["agent_id"] = binding.agent_id
        if binding.workspace is not None:
            payload["workspace"] = binding.workspace
        return payload

    def _sync_instance_runtime_binding(
        self,
        instance: SessionInstance,
        *,
        session: Session,
    ) -> None:
        metadata = dict(instance.metadata)
        metadata.pop("llm_id", None)
        metadata.update(self._build_runtime_binding_metadata(session))
        instance.metadata = metadata

    def _resolve_new_session_workspace(
        self,
        *,
        agent_id: str,
        workspace: str | None,
    ) -> str | None:
        if workspace is not None:
            return workspace.strip() or None
        return self._resolve_default_workspace(agent_id)

    def _resolve_default_workspace(self, agent_id: str) -> str | None:
        if self.workspace_defaults_resolver is None:
            return None
        resolved = self.workspace_defaults_resolver(agent_id)
        if resolved is None:
            return None
        return resolved.strip() or None

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
