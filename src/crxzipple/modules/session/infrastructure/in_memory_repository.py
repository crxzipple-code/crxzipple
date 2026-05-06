from __future__ import annotations

from datetime import datetime

from crxzipple.modules.session.domain.entities import Session, SessionInstance
from crxzipple.modules.session.domain.value_objects import (
    SessionMessage,
    SessionMessageVisibility,
)


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._items: dict[str, Session] = {}

    def add(self, session: Session) -> None:
        self._items[session.id] = session

    def get(self, session_id: str) -> Session | None:
        return self._items.get(session_id)

    def list(self, *, agent_id: str | None = None) -> list[Session]:
        items = list(self._items.values())
        if agent_id is not None:
            normalized_agent_id = agent_id.strip()
            items = [
                item
                for item in items
                if item.runtime_binding().agent_id == normalized_agent_id
            ]
        return sorted(items, key=lambda item: (item.updated_at, item.id), reverse=True)

    def touch_updated_at(self, *, session_key: str, updated_at: datetime) -> None:
        session = self._items.get(session_key)
        if session is not None:
            session.updated_at = updated_at


class InMemorySessionMessageRepository:
    def __init__(self) -> None:
        self._items: list[SessionMessage] = []

    def add(self, message: SessionMessage) -> None:
        for index, item in enumerate(self._items):
            if item.id == message.id:
                self._items[index] = message
                return
        self._items.append(message)

    def add_new(self, message: SessionMessage) -> None:
        self._items.append(message)

    def add_many_new(self, messages: tuple[SessionMessage, ...]) -> None:
        self._items.extend(messages)

    def get(self, message_id: str) -> SessionMessage | None:
        for item in self._items:
            if item.id == message_id:
                return item
        return None

    def get_by_source(
        self,
        *,
        session_key: str,
        session_id: str,
        source_kind: str,
        source_id: str,
    ) -> SessionMessage | None:
        matches = [
            item
            for item in self._items
            if item.session_key == session_key
            and item.session_id == session_id
            and item.source_kind == source_kind
            and item.source_id == source_id
        ]
        if not matches:
            return None
        return sorted(
            matches,
            key=lambda item: (item.created_at, item.sequence_no, item.id),
        )[-1]

    def max_sequence_no(self, *, session_key: str, session_id: str) -> int:
        matches = [
            item.sequence_no
            for item in self._items
            if item.session_key == session_key and item.session_id == session_id
        ]
        return max(matches, default=0)

    def list(
        self,
        *,
        session_key: str,
        session_id: str | None = None,
        limit: int | None = None,
        include_archived: bool = True,
        after_sequence_no: int | None = None,
        before_sequence_no: int | None = None,
    ) -> list[SessionMessage]:
        items = [item for item in self._items if item.session_key == session_key]
        if session_id is not None:
            items = [item for item in items if item.session_id == session_id]
        if after_sequence_no is not None and after_sequence_no > 0:
            items = [
                item for item in items if item.sequence_no > after_sequence_no
            ]
        if before_sequence_no is not None and before_sequence_no > 0:
            items = [
                item for item in items if item.sequence_no < before_sequence_no
            ]
        if not include_archived:
            items = [
                item
                for item in items
                if item.visibility is not SessionMessageVisibility.ARCHIVED
            ]
        items = sorted(
            items,
            key=lambda item: (item.created_at, item.sequence_no, item.id),
        )
        if limit is None or limit <= 0:
            return items
        return items[-limit:]


class InMemorySessionInstanceRepository:
    def __init__(self) -> None:
        self._items: dict[str, SessionInstance] = {}

    def add(self, instance: SessionInstance) -> None:
        self._items[instance.id] = instance

    def get(self, instance_id: str) -> SessionInstance | None:
        return self._items.get(instance_id)

    def list(self, *, session_key: str) -> list[SessionInstance]:
        items = [item for item in self._items.values() if item.session_key == session_key]
        return sorted(items, key=lambda item: (item.sequence_no, item.id))

    def max_sequence_no(self, *, session_key: str) -> int:
        matches = [
            item.sequence_no
            for item in self._items.values()
            if item.session_key == session_key
        ]
        return max(matches, default=0)
