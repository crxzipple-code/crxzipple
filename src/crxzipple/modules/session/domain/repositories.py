from __future__ import annotations

from typing import Protocol

from crxzipple.modules.session.domain.entities import Session, SessionInstance
from crxzipple.modules.session.domain.value_objects import SessionMessage


class SessionRepository(Protocol):
    def add(self, session: Session) -> None:
        ...

    def get(self, session_key: str) -> Session | None:
        ...

    def list(self, *, agent_id: str | None = None) -> list[Session]:
        ...


class SessionMessageRepository(Protocol):
    def add(self, message: SessionMessage) -> None:
        ...

    def get_by_source(
        self,
        *,
        session_key: str,
        session_id: str,
        source_kind: str,
        source_id: str,
    ) -> SessionMessage | None:
        ...

    def max_sequence_no(self, *, session_key: str, session_id: str) -> int:
        ...

    def list(
        self,
        *,
        session_key: str,
        session_id: str | None = None,
        limit: int | None = None,
    ) -> list[SessionMessage]:
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
