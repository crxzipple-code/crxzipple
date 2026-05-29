"""Runtime container helpers for process entrypoints."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

from crxzipple.app import AppKey, AssemblyTarget, build_app_container
from crxzipple.app.container import AppContainer
from crxzipple.app.assembly.runtime import runtime_plan
from crxzipple.core.config import Settings


MEMORY_WATCHER_TARGETS: frozenset[AssemblyTarget] = frozenset(
    {
        AssemblyTarget.API,
        AssemblyTarget.ORCHESTRATION_SCHEDULER,
        AssemblyTarget.ORCHESTRATION_EXECUTOR,
    }
)


def memory_watchers_enabled_for_target(target: AssemblyTarget | str) -> bool:
    """Return whether a runtime target should own memory file watchers."""

    return AssemblyTarget.parse(target) in MEMORY_WATCHER_TARGETS


def build_runtime_container(
    settings: Settings,
    *,
    target: AssemblyTarget | str,
    enable_memory_watchers: bool | None = None,
) -> AppContainer:
    resolved_target = AssemblyTarget.parse(target)
    resolved_enable_memory_watchers = (
        memory_watchers_enabled_for_target(resolved_target)
        if enable_memory_watchers is None
        else enable_memory_watchers
    )
    return build_app_container(
        runtime_plan(enable_memory_watchers=resolved_enable_memory_watchers),
        target=resolved_target,
        overrides={AppKey.CORE_SETTINGS: settings},
    )


@contextmanager
def runtime_container(
    settings: Settings,
    *,
    target: AssemblyTarget | str,
    enable_memory_watchers: bool | None = None,
) -> Iterator[AppContainer]:
    """Build a runtime container for one process scope and always close it."""

    container = build_runtime_container(
        settings,
        target=target,
        enable_memory_watchers=enable_memory_watchers,
    )
    try:
        yield container
    finally:
        container.close()


def ensure_typer_runtime_container(
    ctx: Any,
    *,
    target: AssemblyTarget | str,
    key: str,
    settings: Settings | None = None,
    enable_memory_watchers: bool | None = None,
) -> AppContainer:
    """Return a root Typer context container, creating and closing it once."""

    root = ctx.find_root()
    if root.obj is None:
        root.obj = {}

    payload = root.obj
    if not isinstance(payload, dict):
        payload = {}
        root.obj = payload

    container = payload.get(key)
    if container is None:
        from crxzipple.core.config import load_settings

        container = build_runtime_container(
            settings or load_settings(),
            target=target,
            enable_memory_watchers=enable_memory_watchers,
        )
        payload[key] = container
        root.call_on_close(container.close)

    return cast(AppContainer, container)


__all__ = [
    "AppContainer",
    "AppKey",
    "AssemblyTarget",
    "MEMORY_WATCHER_TARGETS",
    "build_runtime_container",
    "ensure_typer_runtime_container",
    "memory_watchers_enabled_for_target",
    "runtime_container",
]
