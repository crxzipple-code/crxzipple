from __future__ import annotations

from typing import Callable

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
from crxzipple.modules.session.domain.value_objects import SessionItem


class SessionQueryReader:
    def __init__(self, uow_factory: Callable[[], SessionUnitOfWork]) -> None:
        self.uow_factory = uow_factory

    def get_session(self, session_key: str) -> Session:
        with self.uow_factory() as uow:
            session = uow.sessions.get(session_key)
            if session is None:
                raise SessionNotFoundError(f"Session '{session_key}' was not found.")
            return session

    def list_sessions(self, *, agent_id: str | None = None) -> list[Session]:
        with self.uow_factory() as uow:
            return uow.sessions.list(agent_id=agent_id)

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
                item.id: item for item in uow.session_items.get_many(normalized_ids)
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
