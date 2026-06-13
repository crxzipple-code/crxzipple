from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, time, timedelta, timezone
from typing import Any, Callable, Protocol
from uuid import uuid4

from crxzipple.modules.session.domain.entities import Session, SessionInstance
from crxzipple.modules.session.domain.exceptions import (
    SessionInstanceNotFoundError,
    SessionItemNotFoundError,
    SessionNotFoundError,
    SessionValidationError,
)
from crxzipple.modules.session.domain.repositories import (
    SessionInstanceRepository,
    SessionItemRepository,
    SessionRepository,
)
from crxzipple.modules.session.domain.value_objects import (
    SessionKind,
    SessionItem,
    SessionItemKind,
    SessionItemPhase,
    SessionItemVisibility,
    SessionKeyResolution,
    SessionOrigin,
    SessionReply,
    SessionResetDecision,
    SessionResetPolicy,
    utcnow,
)
from crxzipple.shared.domain.aggregates import AggregateRoot
from crxzipple.shared.domain.events import Event
from crxzipple.shared.time import format_datetime_utc as _format_datetime_utc


def _session_item_fact_payload(item: SessionItem) -> dict[str, object]:
    return {
        "item_id": item.id,
        "session_key": item.session_key,
        "session_id": item.session_id,
        "sequence_no": item.sequence_no,
        "kind": item.kind.value,
        "phase": item.phase.value,
        "role": item.role,
        "source_module": item.source_module,
        "source_kind": item.source_kind,
        "source_id": item.source_id,
        "provider_item_id": item.provider_item_id,
        "provider_item_type": item.provider_item_type,
        "call_id": item.call_id,
        "tool_name": item.tool_name,
        "visibility": item.visibility.to_payload(),
        "item": item.to_payload(),
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
class AppendSessionItemInput:
    session_key: str
    kind: SessionItemKind
    content_payload: dict[str, object] = field(default_factory=dict)
    role: str | None = None
    phase: SessionItemPhase = SessionItemPhase.UNKNOWN
    visibility: SessionItemVisibility = field(default_factory=SessionItemVisibility)
    source_module: str | None = None
    source_kind: str | None = None
    source_id: str | None = None
    provider_item_id: str | None = None
    provider_item_type: str | None = None
    call_id: str | None = None
    tool_name: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    session_id: str | None = None


@dataclass(frozen=True, slots=True)
class AppendSessionItemsInput:
    items: tuple[AppendSessionItemInput, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ListSessionItemsInput:
    session_key: str
    limit: int | None = None
    active_session_only: bool = False
    model_visible: bool | None = None
    user_visible: bool | None = None
    chat_visible: bool | None = None
    trace_visible: bool | None = None
    after_sequence_no: int | None = None
    before_sequence_no: int | None = None


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
class MergeSessionItemMetadataInput:
    item_id: str
    metadata: dict[str, object] = field(default_factory=dict)
    touch_activity: bool = False


@dataclass(frozen=True, slots=True)
class GetSessionItemBySourceInput:
    session_key: str
    session_id: str
    source_module: str
    source_kind: str
    source_id: str


@dataclass(frozen=True, slots=True)
class SessionItemsBundle:
    session: Session
    items: tuple[SessionItem, ...]


@dataclass(frozen=True, slots=True)
class CompactSessionSegmentInput:
    session_key: str
    session_id: str
    summary_text: str
    compaction_run_id: str
    summary_item_id: str | None = None
    archived_through_item_sequence_no: int | None = None
    reason: str | None = "compaction"


@dataclass(frozen=True, slots=True)
class CompactSessionSegmentResult:
    session: Session
    compacted_session_id: str
    active_session_id: str
    archived_item_count: int = 0
    archived_through_item_sequence_no: int | None = None
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
    session_items: SessionItemRepository
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

    def get_item(self, item_id: str) -> SessionItem:
        with self.uow_factory() as uow:
            item = uow.session_items.get(item_id)
            if item is None:
                raise SessionItemNotFoundError(
                    f"Session item '{item_id}' was not found.",
                )
            return item

    def get_item_by_source(
        self,
        data: GetSessionItemBySourceInput,
    ) -> SessionItem | None:
        with self.uow_factory() as uow:
            return uow.session_items.get_by_source(
                session_key=data.session_key,
                session_id=data.session_id,
                source_module=data.source_module,
                source_kind=data.source_kind,
                source_id=data.source_id,
            )

    def merge_item_metadata(
        self,
        data: MergeSessionItemMetadataInput,
    ) -> SessionItem:
        with self.uow_factory() as uow:
            item = uow.session_items.get(data.item_id)
            if item is None:
                raise SessionItemNotFoundError(
                    f"Session item '{data.item_id}' was not found.",
                )
            metadata = dict(item.metadata)
            metadata.update(data.metadata)
            updated_item = replace(item, metadata=metadata)
            uow.session_items.add(updated_item)
            session = uow.sessions.get(updated_item.session_key)
            if session is not None and data.touch_activity:
                session.apply_updates(updated_at=utcnow())
                uow.sessions.add(session)
                uow.collect(session)
            uow.commit()
            return updated_item

    def append_item(self, data: AppendSessionItemInput) -> SessionItem:
        return self.append_items(AppendSessionItemsInput(items=(data,)))[0]

    def append_items(
        self,
        data: AppendSessionItemsInput,
    ) -> tuple[SessionItem, ...]:
        if not data.items:
            return ()
        with self.uow_factory() as uow:
            first = data.items[0]
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
            repository = uow.session_items
            next_sequence_no = repository.max_sequence_no(
                session_key=session.id,
                session_id=target_session_id,
            ) + 1
            items: list[SessionItem] = []
            for offset, item in enumerate(data.items):
                if item.session_key != session.id:
                    raise SessionValidationError(
                        "Batched session items must share a session_key.",
                    )
                item_session_id = item.session_id or session.active_session_id
                if item_session_id != target_session_id:
                    raise SessionValidationError(
                        "Batched session items must share a session_id.",
                    )
                session_item = self._build_item(
                    item,
                    session_key=session.id,
                    session_id=target_session_id,
                    sequence_no=next_sequence_no + offset,
                )
                items.append(session_item)
            repository.add_many_new(tuple(items))
            if items:
                session.updated_at = items[-1].created_at
                uow.sessions.touch_updated_at(
                    session_key=session.id,
                    updated_at=session.updated_at,
                )
            for item in items:
                session.record_event(
                    Event(
                        name="session.item.appended",
                        payload=_session_item_fact_payload(item),
                    ),
                )
            uow.collect(session)
            uow.commit()
            return tuple(items)

    def _build_item(
        self,
        data: AppendSessionItemInput,
        *,
        session_key: str,
        session_id: str,
        sequence_no: int,
    ) -> SessionItem:
        return SessionItem(
            id=str(uuid4()),
            session_key=session_key,
            session_id=session_id,
            sequence_no=sequence_no,
            kind=data.kind,
            role=data.role,
            phase=data.phase,
            visibility=data.visibility,
            content_payload=dict(data.content_payload),
            source_module=data.source_module,
            source_kind=data.source_kind,
            source_id=data.source_id,
            provider_item_id=data.provider_item_id,
            provider_item_type=data.provider_item_type,
            call_id=data.call_id,
            tool_name=data.tool_name,
            metadata=dict(data.metadata),
        )

    def compact_active_segment(
        self,
        data: CompactSessionSegmentInput,
    ) -> CompactSessionSegmentResult:
        normalized_session_id = data.session_id.strip()
        normalized_summary_item_id = (data.summary_item_id or "").strip()
        normalized_summary_text = data.summary_text.strip()
        normalized_compaction_run_id = data.compaction_run_id.strip()
        normalized_reason = (data.reason or "compaction").strip() or "compaction"
        if not normalized_session_id:
            raise SessionValidationError("Compaction session_id cannot be empty.")
        if not normalized_summary_item_id:
            raise SessionValidationError(
                "Compaction summary item id cannot be empty.",
            )
        if not normalized_summary_text:
            raise SessionValidationError("Compaction summary_text cannot be empty.")
        if not normalized_compaction_run_id:
            raise SessionValidationError("Compaction run id cannot be empty.")
        if (
            data.archived_through_item_sequence_no is not None
            and data.archived_through_item_sequence_no < 0
        ):
            raise SessionValidationError(
                "Compaction archived_through_item_sequence_no cannot be negative.",
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
            summary_item: SessionItem | None = None
            summary_item = uow.session_items.get(normalized_summary_item_id)
            if summary_item is None:
                raise SessionItemNotFoundError(
                    f"Session item '{normalized_summary_item_id}' was not found.",
                )
            if (
                summary_item.session_key != session.id
                or summary_item.session_id != normalized_session_id
            ):
                raise SessionValidationError(
                    "Compaction summary item must belong to the active session segment.",
                )

            archive_through_item = data.archived_through_item_sequence_no
            if archive_through_item is None and summary_item is not None:
                archive_through_item = max(summary_item.sequence_no - 1, 0)
            archived_item_count = 0
            if archive_through_item is not None:
                items = uow.session_items.list(
                    session_key=session.id,
                    session_id=normalized_session_id,
                )
                for item in items:
                    if item.id == normalized_summary_item_id:
                        continue
                    if item.sequence_no > archive_through_item:
                        continue
                    metadata = dict(item.metadata)
                    metadata["archived_reason"] = normalized_reason
                    metadata["archived_by_compaction_run_id"] = (
                        normalized_compaction_run_id
                    )
                    metadata["compacted_segment_id"] = normalized_session_id
                    metadata["archived_through_item_sequence_no"] = (
                        archive_through_item
                    )
                    if normalized_summary_item_id:
                        metadata["summary_item_id"] = normalized_summary_item_id
                    archived_item = replace(item, metadata=metadata)
                    uow.session_items.add(archived_item)
                    archived_item_count += 1

            compacted_at = utcnow()
            current_instance.close(
                reason=normalized_reason,
                closed_at=compacted_at,
            )
            instance_metadata = dict(current_instance.metadata)
            segment_metadata: dict[str, object] = {
                "kind": "compacted",
                "summary_text": normalized_summary_text,
                "compaction_run_id": normalized_compaction_run_id,
                "archived_item_count": archived_item_count,
                "archived_through_item_sequence_no": archive_through_item,
                "compacted_at": _format_datetime_utc(compacted_at),
                "reason": normalized_reason,
            }
            if summary_item is not None:
                segment_metadata["summary_item_id"] = summary_item.id
            instance_metadata["segment"] = segment_metadata
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
                        "archived_item_count": archived_item_count,
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
                archived_item_count=archived_item_count,
                archived_through_item_sequence_no=archive_through_item,
                compacted_at=_format_datetime_utc(compacted_at),
            )

    def list_items(
        self,
        data: ListSessionItemsInput,
    ) -> list[SessionItem]:
        return list(self.get_session_with_items(data).items)

    def list_model_visible_items(
        self,
        data: ListSessionItemsInput,
    ) -> list[SessionItem]:
        return self.list_items(replace(data, model_visible=True))

    def list_chat_visible_items(
        self,
        data: ListSessionItemsInput,
    ) -> list[SessionItem]:
        return self.list_items(replace(data, chat_visible=True))

    def list_trace_visible_items(
        self,
        data: ListSessionItemsInput,
    ) -> list[SessionItem]:
        return self.list_items(replace(data, trace_visible=True))

    def get_session_with_items(
        self,
        data: ListSessionItemsInput,
    ) -> SessionItemsBundle:
        with self.uow_factory() as uow:
            session = uow.sessions.get(data.session_key)
            if session is None:
                raise SessionNotFoundError(
                    f"Session '{data.session_key}' was not found.",
                )
            session_id = session.active_session_id if data.active_session_only else None
            items = uow.session_items.list(
                session_key=session.id,
                session_id=session_id,
                limit=data.limit,
                model_visible=data.model_visible,
                user_visible=data.user_visible,
                chat_visible=data.chat_visible,
                trace_visible=data.trace_visible,
                after_sequence_no=data.after_sequence_no,
                before_sequence_no=data.before_sequence_no,
            )
            return SessionItemsBundle(session=session, items=tuple(items))

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
