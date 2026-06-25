from __future__ import annotations

from typing import Callable

from crxzipple.modules.session.application.item_append import (
    AppendSessionItemInput,
    AppendSessionItemsInput,
    build_session_item,
)
from crxzipple.modules.session.application.item_events import session_item_fact_payload
from crxzipple.modules.session.application.reset_policy import evaluate_session_reset
from crxzipple.modules.session.application.session_instance_lifecycle import (
    build_session_entity,
    build_session_instance,
    ensure_session_instance_exists,
    infer_session_kind,
    next_session_instance_sequence,
    runtime_binding_payload,
    sync_instance_runtime_binding,
)
from crxzipple.modules.session.application.session_lifecycle import (
    EnsureSessionInput,
    ResetSessionInput,
    RoutedSessionResult,
    SessionResolutionResult,
    SyncRoutedSessionInput,
)
from crxzipple.modules.session.application.session_metadata import (
    MergeSessionItemMetadataInput,
    merge_session_item_metadata,
)
from crxzipple.modules.session.application.session_queries import (
    BuildSessionMaintenanceWindowInput,
    BuildSessionReplayWindowInput,
    GetSessionContextFrontierInput,
    GetSessionItemBySourceInput,
    ListSessionInstancesInput,
    ListSessionItemRangeInput,
    ListSessionItemsInput,
    ListSessionSegmentHandlesInput,
)
from crxzipple.modules.session.application.segment_compaction import (
    CompactSessionSegmentInput,
    CompactSessionSegmentResult,
    archive_through_sequence_no,
    build_compacted_item,
    compacted_segment_metadata,
    compacted_segment_result,
    ensure_summary_item_belongs_to_segment,
    normalize_segment_compaction_input,
)
from crxzipple.modules.session.application.session_windows import (
    SessionContextFrontier,
    SessionItemRange,
    SessionItemsBundle,
    SessionReplayWindow,
    SessionSegmentHandles,
    build_context_frontier,
    build_item_range,
    build_replay_window,
    build_segment_handle,
)
from crxzipple.modules.session.application.unit_of_work import SessionUnitOfWork
from crxzipple.modules.session.domain.entities import Session, SessionInstance
from crxzipple.modules.session.domain.exceptions import (
    SessionInstanceNotFoundError,
    SessionItemNotFoundError,
    SessionNotFoundError,
    SessionValidationError,
)
from crxzipple.modules.session.domain.value_objects import (
    SessionItem,
    SessionOrigin,
    SessionReply,
    utcnow,
)
from crxzipple.shared.domain.events import Event


class SessionApplicationService:
    def __init__(
        self,
        uow_factory: Callable[[], SessionUnitOfWork],
        *,
        workspace_defaults_resolver: Callable[[str], str | None] | None = None,
        append_sequence_conflict_detector: Callable[[Exception], bool] | None = None,
        append_sequence_retry_limit: int = 2,
    ) -> None:
        self.uow_factory = uow_factory
        self.workspace_defaults_resolver = workspace_defaults_resolver
        self.append_sequence_conflict_detector = (
            append_sequence_conflict_detector or (lambda exc: False)
        )
        self.append_sequence_retry_limit = max(0, append_sequence_retry_limit)

    def ensure_session(self, data: EnsureSessionInput) -> Session:
        with self.uow_factory() as uow:
            session = uow.sessions.get(data.key)
            if session is None:
                session = build_session_entity(
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
                instance = build_session_instance(
                    session=session,
                    sequence_no=1,
                    kind=infer_session_kind(
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
                            **runtime_binding_payload(session),
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
                ensure_session_instance_exists(
                    uow,
                    session=session,
                    kind=infer_session_kind(
                        session.id,
                        chat_type=session.chat_type,
                    ),
                )
                active_instance = uow.session_instances.get(session.active_session_id)
                if active_instance is not None:
                    sync_instance_runtime_binding(active_instance, session=session)
                    uow.session_instances.add(active_instance)
                session.record_event(
                    Event(
                        name="session.updated",
                        payload={
                            "session_key": session.id,
                            "active_session_id": session.active_session_id,
                            **runtime_binding_payload(session),
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
                session = build_session_entity(
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
                active_instance = build_session_instance(
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
                            **runtime_binding_payload(session),
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

            reset_decision = evaluate_session_reset(
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
                next_sequence = next_session_instance_sequence(uow, session.id)
                active_instance = build_session_instance(
                    session=session,
                    sequence_no=next_sequence,
                    kind=data.key_resolution.kind,
                    opened_at=session.last_reset_at,
                    instance_id=session.active_session_id,
                )
                uow.session_instances.add(active_instance)
            else:
                sync_instance_runtime_binding(active_instance, session=session)
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
                    else next_session_instance_sequence(uow, session.id)
                )
                active_instance = build_session_instance(
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
                            **runtime_binding_payload(session),
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
                            **runtime_binding_payload(session),
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
                sync_instance_runtime_binding(active_instance, session=session)
                uow.session_instances.add(active_instance)
            session.record_event(
                Event(
                    name="session.updated",
                    payload={
                        "session_key": session.id,
                        "active_session_id": session.active_session_id,
                        **runtime_binding_payload(session),
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

    def list_item_range(
        self,
        data: ListSessionItemRangeInput,
    ) -> SessionItemRange:
        from_sequence_no = data.from_sequence_no
        to_sequence_no = data.to_sequence_no
        if from_sequence_no is not None and from_sequence_no <= 0:
            raise SessionValidationError("from_sequence_no must be greater than zero.")
        if to_sequence_no is not None and to_sequence_no <= 0:
            raise SessionValidationError("to_sequence_no must be greater than zero.")
        if (
            from_sequence_no is not None
            and to_sequence_no is not None
            and from_sequence_no > to_sequence_no
        ):
            raise SessionValidationError(
                "from_sequence_no cannot be greater than to_sequence_no.",
            )
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
            items = tuple(
                uow.session_items.list(
                    session_key=session.id,
                    session_id=data.session_id,
                    limit=data.limit,
                    after_sequence_no=(
                        from_sequence_no - 1
                        if from_sequence_no is not None
                        else None
                    ),
                    before_sequence_no=(
                        to_sequence_no + 1 if to_sequence_no is not None else None
                    ),
                ),
            )
            return build_item_range(
                session=session,
                session_id=data.session_id,
                items=items,
                from_sequence_no=from_sequence_no,
                to_sequence_no=to_sequence_no,
            )

    def list_segment_handles(
        self,
        data: ListSessionSegmentHandlesInput,
    ) -> SessionSegmentHandles:
        if data.limit is not None and data.limit <= 0:
            raise SessionValidationError("limit must be greater than zero.")
        with self.uow_factory() as uow:
            session = uow.sessions.get(data.session_key)
            if session is None:
                raise SessionNotFoundError(
                    f"Session '{data.session_key}' was not found.",
                )
            instances = tuple(uow.session_instances.list(session_key=session.id))
            selected_instances = tuple(
                instance
                for instance in instances
                if data.include_active or instance.id != session.active_session_id
            )
            if data.limit is not None:
                selected_instances = selected_instances[-data.limit:]
            return SessionSegmentHandles(
                session=session,
                active_session_id=session.active_session_id,
                handles=tuple(
                    build_segment_handle(instance) for instance in selected_instances
                ),
            )

    def get_context_frontier(
        self,
        data: GetSessionContextFrontierInput,
    ) -> SessionContextFrontier:
        active_item_limit = data.active_item_limit
        historical_instance_limit = data.historical_instance_limit
        if active_item_limit is not None and active_item_limit <= 0:
            raise SessionValidationError("active_item_limit must be greater than zero.")
        if historical_instance_limit is not None and historical_instance_limit <= 0:
            raise SessionValidationError(
                "historical_instance_limit must be greater than zero.",
            )
        with self.uow_factory() as uow:
            session = uow.sessions.get(data.session_key)
            if session is None:
                raise SessionNotFoundError(
                    f"Session '{data.session_key}' was not found.",
                )
            active_instance = uow.session_instances.get(session.active_session_id)
            if active_instance is None:
                raise SessionInstanceNotFoundError(
                    f"Session instance '{session.active_session_id}' was not found.",
                )
            instances = tuple(uow.session_instances.list(session_key=session.id))
            active_items = tuple(
                uow.session_items.list(
                    session_key=session.id,
                    session_id=active_instance.id,
                    limit=active_item_limit,
                ),
            )
            return build_context_frontier(
                session=session,
                active_instance=active_instance,
                instances=instances,
                active_items=active_items,
                historical_instance_limit=historical_instance_limit,
            )

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

    def get_items(self, item_ids: tuple[str, ...]) -> dict[str, SessionItem]:
        normalized_ids = tuple(
            dict.fromkeys(item_id.strip() for item_id in item_ids if item_id.strip()),
        )
        if not normalized_ids:
            return {}
        with self.uow_factory() as uow:
            return {
                item.id: item
                for item in uow.session_items.get_many(normalized_ids)
            }

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
            updated_item = merge_session_item_metadata(item, data.metadata)
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
        attempts = self.append_sequence_retry_limit + 1
        for attempt in range(attempts):
            try:
                return self._append_items_once(data)
            except Exception as exc:
                if (
                    not self.append_sequence_conflict_detector(exc)
                    or attempt >= self.append_sequence_retry_limit
                ):
                    raise
        raise RuntimeError("Session append retry loop exited unexpectedly.")

    def _append_items_once(
        self,
        data: AppendSessionItemsInput,
    ) -> tuple[SessionItem, ...]:
        with self.uow_factory() as uow:
            first = data.items[0]
            session = uow.sessions.get(first.session_key)
            if session is None:
                raise SessionNotFoundError(
                    f"Session '{first.session_key}' was not found.",
                )
            target_session_id = first.session_id or session.active_session_id
            target_instance = uow.session_instances.get(target_session_id)
            if target_instance is None:
                raise SessionInstanceNotFoundError(
                    f"Session instance '{target_session_id}' was not found.",
                )
            if (
                target_instance.id != session.active_session_id
                or target_instance.status != "active"
            ):
                raise SessionValidationError(
                    "Session items can only be appended to the active session instance.",
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
                session_item = build_session_item(
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
                        payload=session_item_fact_payload(item),
                    ),
                )
            uow.collect(session)
            uow.commit()
            return tuple(items)

    def compact_active_segment(
        self,
        data: CompactSessionSegmentInput,
    ) -> CompactSessionSegmentResult:
        compaction = normalize_segment_compaction_input(data)

        with self.uow_factory() as uow:
            session = uow.sessions.get(data.session_key)
            if session is None:
                raise SessionNotFoundError(
                    f"Session '{data.session_key}' was not found.",
                )
            if compaction.session_id != session.active_session_id:
                raise SessionValidationError(
                    "Session segment compaction requires the current active session_id.",
                )
            current_instance = uow.session_instances.get(compaction.session_id)
            if current_instance is None:
                raise SessionInstanceNotFoundError(
                    f"Session instance '{compaction.session_id}' was not found.",
                )
            if current_instance.status != "active":
                raise SessionValidationError(
                    "Session segment compaction requires an active session instance.",
                )
            summary_item = uow.session_items.get(compaction.summary_item_id)
            if summary_item is None:
                raise SessionItemNotFoundError(
                    f"Session item '{compaction.summary_item_id}' was not found.",
                )
            ensure_summary_item_belongs_to_segment(
                session=session,
                summary_item=summary_item,
                compaction=compaction,
            )

            archive_through_item = archive_through_sequence_no(
                compaction=compaction,
                summary_item=summary_item,
            )
            archived_item_count = 0
            if archive_through_item is not None:
                items = uow.session_items.list(
                    session_key=session.id,
                    session_id=compaction.session_id,
                )
                for item in items:
                    archived_item = build_compacted_item(
                        item,
                        compaction=compaction,
                        archived_through_item_sequence_no=archive_through_item,
                    )
                    if archived_item is None:
                        continue
                    uow.session_items.add(archived_item)
                    archived_item_count += 1

            compacted_at = utcnow()
            current_instance.close(
                reason=compaction.reason,
                closed_at=compacted_at,
            )
            instance_metadata = dict(current_instance.metadata)
            instance_metadata["segment"] = compacted_segment_metadata(
                compaction=compaction,
                archived_item_count=archived_item_count,
                archived_through_item_sequence_no=archive_through_item,
                compacted_at=compacted_at,
            )
            current_instance.metadata = instance_metadata
            uow.session_instances.add(current_instance)

            session.reset(
                status=session.status,
                happened_at=compacted_at,
            )
            next_instance = build_session_instance(
                session=session,
                sequence_no=next_session_instance_sequence(uow, session.id),
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
                        "closed_session_id": compaction.session_id,
                        "active_session_id": session.active_session_id,
                        "archived_item_count": archived_item_count,
                        "compaction_run_id": compaction.compaction_run_id,
                    },
                ),
            )
            uow.sessions.add(session)
            uow.collect(session)
            uow.commit()
            return compacted_segment_result(
                session=session,
                compaction=compaction,
                archived_item_count=archived_item_count,
                archived_through_item_sequence_no=archive_through_item,
                compacted_at=compacted_at,
            )

    def list_items(
        self,
        data: ListSessionItemsInput,
    ) -> list[SessionItem]:
        return list(self.get_session_with_items(data).items)

    def build_replay_window(
        self,
        data: BuildSessionReplayWindowInput,
    ) -> SessionReplayWindow:
        return self._build_window(
            session_key=data.session_key,
            limit=data.limit,
            active_session_only=data.active_session_only,
            after_sequence_no=data.after_sequence_no,
            before_sequence_no=data.before_sequence_no,
        )

    def build_maintenance_window(
        self,
        data: BuildSessionMaintenanceWindowInput,
    ) -> SessionReplayWindow:
        return self._build_window(
            session_key=data.session_key,
            limit=data.limit,
            active_session_only=data.active_session_only,
            after_sequence_no=data.after_sequence_no,
            before_sequence_no=data.before_sequence_no,
        )

    def _build_window(
        self,
        *,
        session_key: str,
        limit: int | None,
        active_session_only: bool,
        after_sequence_no: int | None,
        before_sequence_no: int | None,
    ) -> SessionReplayWindow:
        bundle = self.get_session_with_items(
            ListSessionItemsInput(
                session_key=session_key,
                limit=limit,
                active_session_only=active_session_only,
                after_sequence_no=after_sequence_no,
                before_sequence_no=before_sequence_no,
            ),
        )
        return build_replay_window(
            bundle,
            active_session_only=active_session_only,
        )

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
            next_instance = build_session_instance(
                session=session,
                sequence_no=next_session_instance_sequence(uow, session.id),
                kind=infer_session_kind(
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
                        **runtime_binding_payload(session),
                        "reason": data.reason or "manual",
                    },
                ),
            )
            uow.sessions.add(session)
            uow.collect(session)
            uow.commit()
            return session

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
