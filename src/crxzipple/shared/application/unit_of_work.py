from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from crxzipple.shared.domain.aggregates import AggregateRoot


class UnitOfWork(ABC):
    @abstractmethod
    def __enter__(self) -> "UnitOfWork":
        raise NotImplementedError

    @abstractmethod
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def collect(self, aggregate: AggregateRoot[Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def rollback(self) -> None:
        raise NotImplementedError
