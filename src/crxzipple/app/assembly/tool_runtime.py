"""Tool runtime lifecycle assembly helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from crxzipple.app.keys import AppKey
from crxzipple.modules.tool.application import (
    ToolFunctionStatus,
    ToolSourceCatalogKind,
    ToolSourceStatus,
)
from crxzipple.modules.tool.infrastructure import activate_configured_provider_runtimes


class ToolCleanupCallbacks:
    def __init__(self) -> None:
        self._callbacks: list[Callable[[], None]] = []
        self._keyed_callbacks: dict[str, Callable[[], None]] = {}
        self._closed = False

    def add(
        self,
        callback: Callable[[], None],
        *,
        key: str | None = None,
    ) -> None:
        if self._closed:
            callback()
            return
        if key is not None:
            previous = self._keyed_callbacks.pop(key, None)
            if previous is not None:
                previous()
            self._keyed_callbacks[key] = callback
            return
        self._callbacks.append(callback)

    def __call__(self) -> None:
        if self._closed:
            return
        self._closed = True
        callbacks = (*self._callbacks, *self._keyed_callbacks.values())
        self._callbacks.clear()
        self._keyed_callbacks.clear()
        for callback in callbacks:
            callback()


@dataclass(slots=True)
class ToolConfiguredRuntimeActivator:
    remote_default_max_concurrency: int
    source_query: Any
    uow_factory: Any
    remote_runtime_registry: Any
    credential_provider: Any
    events_service: Any
    process_service: Any
    cleanup_callbacks: ToolCleanupCallbacks

    def activate_all(self) -> None:
        sources = self._configured_sources()
        if sources:
            self._activate(tuple(sources))

    def activate_source(self, source_id: str) -> None:
        source = self.source_query.get_source(source_id)
        if (
            source is None
            or source.status is not ToolSourceStatus.ACTIVE
            or source.kind
            not in {
                ToolSourceCatalogKind.OPENAPI,
                ToolSourceCatalogKind.MCP,
                ToolSourceCatalogKind.CLI,
            }
        ):
            return
        self._activate((source,))

    def _configured_sources(self):
        return (
            *self.source_query.list_sources(
                kind=ToolSourceCatalogKind.OPENAPI,
                status=ToolSourceStatus.ACTIVE,
            ),
            *self.source_query.list_sources(
                kind=ToolSourceCatalogKind.MCP,
                status=ToolSourceStatus.ACTIVE,
            ),
            *self.source_query.list_sources(
                kind=ToolSourceCatalogKind.CLI,
                status=ToolSourceStatus.ACTIVE,
            ),
        )

    def _activate(self, sources) -> None:
        activate_configured_provider_runtimes(
            sources=tuple(sources),
            functions_by_source=self._functions_by_source(sources),
            remote_runtime_registry=self.remote_runtime_registry,
            credential_provider=self.credential_provider,
            events_service=self.events_service,
            process_service=self.process_service,
            default_max_concurrency=self.remote_default_max_concurrency,
            add_cleanup_callback=self._add_source_cleanup_callback,
            replace_existing=True,
        )

    def _add_source_cleanup_callback(self, source, callback: Callable[[], None]) -> None:
        self.cleanup_callbacks.add(
            callback,
            key=f"configured_provider:{source.source_id}",
        )

    def _functions_by_source(self, sources):
        source_ids = tuple(source.source_id for source in sources)
        with self.uow_factory() as uow:
            return {
                source_id: tuple(
                    function
                    for function in uow.tool_function_catalog.list_by_source(
                        source_id,
                    )
                    if function.status is ToolFunctionStatus.ACTIVE
                )
                for source_id in source_ids
            }


def tool_cleanup_callbacks(ctx) -> ToolCleanupCallbacks:
    for callback in ctx.require(AppKey.TOOL_CLEANUP_CALLBACKS):
        if isinstance(callback, ToolCleanupCallbacks):
            return callback
    raise RuntimeError("Tool cleanup callback registry is not configured.")
