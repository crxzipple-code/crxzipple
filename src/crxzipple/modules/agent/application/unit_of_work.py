from __future__ import annotations

from typing import Any, Protocol

from crxzipple.shared.domain.aggregates import AggregateRoot


class AgentUnitOfWork(Protocol):
    def __enter__(self) -> "AgentUnitOfWork":
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
