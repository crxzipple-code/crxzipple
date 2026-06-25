from __future__ import annotations

from typing import Any, Protocol

from crxzipple.modules.session.domain.repositories import (
    SessionInstanceRepository,
    SessionItemRepository,
    SessionRepository,
)
from crxzipple.shared.domain.aggregates import AggregateRoot


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
