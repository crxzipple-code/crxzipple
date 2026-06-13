from __future__ import annotations

from datetime import datetime
from typing import Protocol

from crxzipple.modules.session.domain.entities import Session, SessionInstance
from crxzipple.modules.session.domain.value_objects import SessionItem


class SessionRepository(Protocol):
    def add(self, session: Session) -> None:
        ...

    def get(self, session_key: str) -> Session | None:
        ...

    def list(self, *, agent_id: str | None = None) -> list[Session]:
        ...

    def touch_updated_at(self, *, session_key: str, updated_at: datetime) -> None:
        ...


class SessionItemRepository(Protocol):
    def add(self, item: SessionItem) -> None:
        ...

    def add_many_new(self, items: tuple[SessionItem, ...]) -> None:
        ...

    def get(self, item_id: str) -> SessionItem | None:
        ...

    def get_by_source(
        self,
        *,
        session_key: str,
        session_id: str,
        source_module: str,
        source_kind: str,
        source_id: str,
    ) -> SessionItem | None:
        ...

    def max_sequence_no(self, *, session_key: str, session_id: str) -> int:
        ...

    def list(
        self,
        *,
        session_key: str,
        session_id: str | None = None,
        limit: int | None = None,
        model_visible: bool | None = None,
        user_visible: bool | None = None,
        chat_visible: bool | None = None,
        trace_visible: bool | None = None,
        after_sequence_no: int | None = None,
        before_sequence_no: int | None = None,
    ) -> list[SessionItem]:
        ...


class SessionInstanceRepository(Protocol):
    def add(self, instance: SessionInstance) -> None:
        ...

    def get(self, instance_id: str) -> SessionInstance | None:
        ...

    def list(self, *, session_key: str) -> list[SessionInstance]:
        ...

    def max_sequence_no(self, *, session_key: str) -> int:
        ...
