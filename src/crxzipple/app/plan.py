"""Application assembly plan primitives.

The app assembly layer owns dependency declarations for concrete application
composition. Module application classes stay as ordinary Python objects.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crxzipple.app.registry import AssemblyContext


class AssemblyTarget(StrEnum):
    """Process targets supported by app assembly."""

    API = "api"
    DAEMON_SUPERVISOR = "daemon-supervisor"
    ORCHESTRATION_SCHEDULER = "orchestration-scheduler"
    ORCHESTRATION_EXECUTOR = "orchestration-executor"
    TOOL_SCHEDULER = "tool-scheduler"
    TOOL_WORKER = "tool-worker"
    OPERATIONS_OBSERVER = "operations-observer"
    EVENT_RELAY_WORKER = "event-relay-worker"
    CHANNEL_RUNTIME = "channel-runtime"
    CLI_ADMIN = "cli-admin"
    TEST = "test"

    @classmethod
    def parse(cls, value: AssemblyTarget | str) -> AssemblyTarget:
        if isinstance(value, cls):
            return value
        return cls(value)


ApplicationBuildResult = object | Mapping[str, object]
ApplicationBuild = Callable[["AssemblyContext"], ApplicationBuildResult]
ActivationRun = Callable[["AssemblyContext"], None]


@dataclass(frozen=True, slots=True)
class ApplicationFactory:
    """Explicit construction recipe for one or more application objects."""

    key: str
    provides: tuple[str, ...]
    build: ApplicationBuild
    requires: tuple[str, ...] = ()
    targets: tuple[AssemblyTarget, ...] = ()

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("application factory key must not be empty")
        if not self.provides:
            raise ValueError(f"application factory {self.key!r} must provide a key")
        _assert_unique(self.provides, label=f"factory {self.key!r} provides")
        _assert_unique(self.requires, label=f"factory {self.key!r} requires")

    def active_for(self, target: AssemblyTarget) -> bool:
        return not self.targets or target in self.targets


@dataclass(frozen=True, slots=True)
class ActivationTask:
    """Idempotent setup that runs after its declared requirements exist."""

    key: str
    run: ActivationRun
    requires: tuple[str, ...] = ()
    targets: tuple[AssemblyTarget, ...] = ()
    idempotent: bool = True

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("activation task key must not be empty")
        _assert_unique(self.requires, label=f"activation task {self.key!r} requires")

    def active_for(self, target: AssemblyTarget) -> bool:
        return not self.targets or target in self.targets


@dataclass(frozen=True, slots=True)
class AssemblyPlan:
    """A target-agnostic plan with deterministic assembly buckets."""

    module_local_factories: tuple[ApplicationFactory, ...] = ()
    integration_factories: tuple[ApplicationFactory, ...] = ()
    activation_tasks: tuple[ActivationTask, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def factories(self) -> tuple[ApplicationFactory, ...]:
        return self.module_local_factories + self.integration_factories

    def factories_for(self, target: AssemblyTarget) -> tuple[ApplicationFactory, ...]:
        return tuple(factory for factory in self.factories if factory.active_for(target))

    def activation_tasks_for(self, target: AssemblyTarget) -> tuple[ActivationTask, ...]:
        return tuple(task for task in self.activation_tasks if task.active_for(target))

    @classmethod
    def from_factories(
        cls,
        factories: Sequence[ApplicationFactory],
        *,
        activation_tasks: Sequence[ActivationTask] = (),
    ) -> AssemblyPlan:
        return cls(
            module_local_factories=tuple(factories),
            activation_tasks=tuple(activation_tasks),
        )


def _assert_unique(values: tuple[str, ...], *, label: str) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen:
            duplicates.append(value)
        seen.add(value)
    if duplicates:
        duplicate_list = ", ".join(repr(value) for value in duplicates)
        raise ValueError(f"{label} contains duplicate keys: {duplicate_list}")


__all__ = [
    "ActivationTask",
    "ApplicationBuild",
    "ApplicationBuildResult",
    "ApplicationFactory",
    "AssemblyPlan",
    "AssemblyTarget",
]
