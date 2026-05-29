"""Runtime lifecycle assembly."""

from __future__ import annotations

from typing import Any

from crxzipple.app.keys import AppKey
from crxzipple.app.lifecycle import RuntimeCleanupTask
from crxzipple.app.plan import ApplicationFactory
from crxzipple.shared.infrastructure import close_async_http_clients_sync

TOOL_CLEANUP_ORDER = 10
BROWSER_CLEANUP_ORDER = 20
PROCESS_CLEANUP_ORDER = 30
MEMORY_WATCHER_CLEANUP_ORDER = 40
EVENTS_CLEANUP_ORDER = 50
HTTP_CLIENTS_CLEANUP_ORDER = 60
DATABASE_CLEANUP_ORDER = 70


def runtime_lifecycle_factories() -> tuple[ApplicationFactory, ...]:
    """Build cross-module runtime lifecycle tasks."""

    return (
        ApplicationFactory(
            key="runtime.cleanup_tasks",
            provides=(AppKey.RUNTIME_CLEANUP_TASKS,),
            requires=(
                AppKey.TOOL_CLEANUP_CALLBACKS,
                AppKey.BROWSER_INFRASTRUCTURE,
                AppKey.PROCESS_SERVICE,
                AppKey.MEMORY_WATCH_REGISTRY,
                AppKey.EVENTS_SERVICE,
                AppKey.DATABASE_ENGINE,
            ),
            build=_build_runtime_cleanup_tasks,
        ),
    )


def _build_runtime_cleanup_tasks(ctx) -> tuple[RuntimeCleanupTask, ...]:  # noqa: ANN001
    tasks: list[RuntimeCleanupTask] = []

    for index, callback in enumerate(ctx.require(AppKey.TOOL_CLEANUP_CALLBACKS) or ()):
        if callable(callback):
            tasks.append(
                RuntimeCleanupTask(
                    key=f"tool.cleanup.{index}",
                    order=TOOL_CLEANUP_ORDER,
                    callback=callback,
                ),
            )

    browser = ctx.require(AppKey.BROWSER_INFRASTRUCTURE)
    for index, callback in enumerate(getattr(browser, "cleanup_callbacks", ()) or ()):
        if callable(callback):
            tasks.append(
                RuntimeCleanupTask(
                    key=f"browser.cleanup.{index}",
                    order=BROWSER_CLEANUP_ORDER,
                    callback=callback,
                ),
            )

    _append_close_task(
        tasks,
        key="process.service.close",
        order=PROCESS_CLEANUP_ORDER,
        resource=ctx.require(AppKey.PROCESS_SERVICE),
    )
    _append_close_task(
        tasks,
        key="memory.watch_registry.close",
        order=MEMORY_WATCHER_CLEANUP_ORDER,
        resource=ctx.require(AppKey.MEMORY_WATCH_REGISTRY),
    )
    _append_close_task(
        tasks,
        key="events.service.close",
        order=EVENTS_CLEANUP_ORDER,
        resource=ctx.require(AppKey.EVENTS_SERVICE),
    )
    tasks.append(
        RuntimeCleanupTask(
            key="shared.http_clients.close",
            order=HTTP_CLIENTS_CLEANUP_ORDER,
            callback=close_async_http_clients_sync,
        ),
    )

    _append_method_task(
        tasks,
        key="database.engine.dispose",
        order=DATABASE_CLEANUP_ORDER,
        resource=ctx.require(AppKey.DATABASE_ENGINE),
        method_name="dispose",
    )
    return tuple(tasks)


def _append_close_task(
    tasks: list[RuntimeCleanupTask],
    *,
    key: str,
    order: int,
    resource: Any,
) -> None:
    _append_method_task(
        tasks,
        key=key,
        order=order,
        resource=resource,
        method_name="close",
    )


def _append_method_task(
    tasks: list[RuntimeCleanupTask],
    *,
    key: str,
    order: int,
    resource: Any,
    method_name: str,
) -> None:
    method = getattr(resource, method_name, None)
    if callable(method):
        tasks.append(
            RuntimeCleanupTask(
                key=key,
                order=order,
                callback=method,
            ),
        )


__all__ = [
    "BROWSER_CLEANUP_ORDER",
    "DATABASE_CLEANUP_ORDER",
    "EVENTS_CLEANUP_ORDER",
    "HTTP_CLIENTS_CLEANUP_ORDER",
    "MEMORY_WATCHER_CLEANUP_ORDER",
    "PROCESS_CLEANUP_ORDER",
    "TOOL_CLEANUP_ORDER",
    "runtime_lifecycle_factories",
]
