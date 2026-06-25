from __future__ import annotations

from typing import Any, Protocol

from crxzipple.modules.tool.application.reconcile_service import (
    ToolFunctionCatalogRepository,
)
from crxzipple.modules.tool.domain.repositories import ToolSourceRepository
from crxzipple.shared.domain import AggregateRoot


class ToolSourceUnitOfWork(Protocol):
    tool_sources: ToolSourceRepository
    tool_source_discovery_runs: Any
    tool_function_catalog: ToolFunctionCatalogRepository
    tool_functions: Any
    tool_provider_backends: Any

    def __enter__(self) -> "ToolSourceUnitOfWork":
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        ...

    def commit(self) -> None:
        ...

    def collect(self, aggregate: AggregateRoot[Any]) -> None:
        ...


__all__ = ["ToolSourceUnitOfWork"]
