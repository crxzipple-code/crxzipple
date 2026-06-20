"""Runtime application registry and assembly resolver."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from crxzipple.app.plan import (
    ActivationTask,
    ApplicationFactory,
    AssemblyPlan,
    AssemblyTarget,
)


class AssemblyError(RuntimeError):
    """Base class for app assembly failures."""


class DuplicateApplicationProviderError(AssemblyError):
    """Raised when two active factories provide the same application key."""


class MissingApplicationDependencyError(AssemblyError):
    """Raised when an active factory or task requires an unavailable key."""

    def __init__(self, owner_key: str, dependency_key: str) -> None:
        super().__init__(f"{owner_key!r} requires missing dependency {dependency_key!r}")
        self.owner_key = owner_key
        self.dependency_key = dependency_key


class ApplicationDependencyCycleError(AssemblyError):
    """Raised when factory requirements form a dependency cycle."""

    def __init__(self, cycle: tuple[str, ...]) -> None:
        path = " -> ".join(cycle)
        super().__init__(f"application dependency cycle detected: {path}")
        self.cycle = cycle


class UnknownApplicationError(KeyError):
    """Raised when runtime lookup requests an unknown application key."""

    def __init__(self, key: str) -> None:
        super().__init__(f"unknown application {key!r}")
        self.key = key


class ApplicationRegistry:
    """Read-only runtime lookup for already-built applications."""

    def __init__(self, applications: Mapping[str, object] | None = None) -> None:
        self._applications = dict(applications or {})

    def has(self, key: str) -> bool:
        return key in self._applications

    def get(self, key: str, default: object | None = None) -> object | None:
        return self._applications.get(key, default)

    def require(self, key: str) -> object:
        try:
            return self._applications[key]
        except KeyError as exc:
            raise UnknownApplicationError(key) from exc

    def snapshot(self) -> Mapping[str, object]:
        return MappingProxyType(dict(self._applications))


@dataclass(frozen=True, slots=True)
class AssemblyContext:
    """Context passed to application factories and activation tasks."""

    target: AssemblyTarget
    registry: ApplicationRegistry
    metadata: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))

    def has(self, key: str) -> bool:
        return self.registry.has(key)

    def require(self, key: str) -> object:
        return self.registry.require(key)


def build_application_registry(
    plan: AssemblyPlan,
    *,
    target: AssemblyTarget | str,
    overrides: Mapping[str, object] | None = None,
    run_activation_tasks: bool = True,
) -> ApplicationRegistry:
    """Build a registry for one target, failing before partial integration."""

    resolved_target = AssemblyTarget.parse(target)
    override_values = dict(overrides or {})
    factories = _factories_after_overrides(
        plan.factories_for(resolved_target),
        override_values,
    )
    activation_tasks = (
        plan.activation_tasks_for(resolved_target)
        if run_activation_tasks
        else ()
    )

    provider_by_key = _provider_map(factories)
    build_order = _resolve_factory_order(factories, provider_by_key, override_values)
    _validate_activation_tasks(activation_tasks, provider_by_key, override_values)

    applications = dict(override_values)
    for factory in build_order:
        context = AssemblyContext(
            target=resolved_target,
            registry=ApplicationRegistry(applications),
            metadata=plan.metadata,
        )
        built = factory.build(context)
        applications.update(_provided_values(factory, built))

    registry = ApplicationRegistry(applications)
    context = AssemblyContext(
        target=resolved_target,
        registry=registry,
        metadata=plan.metadata,
    )
    for task in activation_tasks:
        task.run(context)
    return registry


def _factories_after_overrides(
    factories: tuple[ApplicationFactory, ...],
    overrides: Mapping[str, object],
) -> tuple[ApplicationFactory, ...]:
    active: list[ApplicationFactory] = []
    for factory in factories:
        overridden = set(factory.provides).intersection(overrides)
        if not overridden:
            active.append(factory)
            continue
        if len(overridden) == len(factory.provides):
            continue
        overridden_list = ", ".join(repr(key) for key in sorted(overridden))
        raise DuplicateApplicationProviderError(
            f"override partially shadows factory {factory.key!r}: {overridden_list}"
        )
    return tuple(active)


def _provider_map(
    factories: tuple[ApplicationFactory, ...],
) -> dict[str, ApplicationFactory]:
    provider_by_key: dict[str, ApplicationFactory] = {}
    for factory in factories:
        for provided in factory.provides:
            existing = provider_by_key.get(provided)
            if existing is not None:
                raise DuplicateApplicationProviderError(
                    f"application {provided!r} is provided by both "
                    f"{existing.key!r} and {factory.key!r}"
                )
            provider_by_key[provided] = factory
    return provider_by_key


def _resolve_factory_order(
    factories: tuple[ApplicationFactory, ...],
    provider_by_key: Mapping[str, ApplicationFactory],
    overrides: Mapping[str, object],
) -> tuple[ApplicationFactory, ...]:
    factory_set = set(factories)
    state: dict[ApplicationFactory, str] = {}
    order: list[ApplicationFactory] = []
    stack: list[ApplicationFactory] = []

    def visit(factory: ApplicationFactory) -> None:
        current_state = state.get(factory)
        if current_state == "done":
            return
        if current_state == "visiting":
            raise ApplicationDependencyCycleError(_cycle_from_stack(stack, factory))

        state[factory] = "visiting"
        stack.append(factory)
        for dependency in factory.requires:
            if dependency in overrides:
                continue
            dependency_provider = provider_by_key.get(dependency)
            if dependency_provider is None:
                raise MissingApplicationDependencyError(factory.key, dependency)
            if dependency_provider in factory_set:
                visit(dependency_provider)
        stack.pop()
        state[factory] = "done"
        order.append(factory)

    for factory in factories:
        visit(factory)
    return tuple(order)


def _cycle_from_stack(
    stack: list[ApplicationFactory],
    factory: ApplicationFactory,
) -> tuple[str, ...]:
    start = stack.index(factory)
    cycle = [item.key for item in stack[start:]]
    cycle.append(factory.key)
    return tuple(cycle)


def _validate_activation_tasks(
    tasks: tuple[ActivationTask, ...],
    provider_by_key: Mapping[str, ApplicationFactory],
    overrides: Mapping[str, object],
) -> None:
    available = set(provider_by_key).union(overrides)
    for task in tasks:
        for dependency in task.requires:
            if dependency not in available:
                raise MissingApplicationDependencyError(task.key, dependency)


def _provided_values(
    factory: ApplicationFactory,
    built: object | Mapping[str, object],
) -> dict[str, object]:
    if len(factory.provides) == 1:
        if isinstance(built, Mapping):
            provided = factory.provides[0]
            if provided in built:
                return {provided: built[provided]}
        return {factory.provides[0]: built}

    if not isinstance(built, Mapping):
        raise AssemblyError(
            f"factory {factory.key!r} provides multiple applications and must "
            "return a mapping"
        )

    missing = [provided for provided in factory.provides if provided not in built]
    if missing:
        missing_list = ", ".join(repr(key) for key in missing)
        raise AssemblyError(
            f"factory {factory.key!r} did not return provided keys: {missing_list}"
        )
    return {provided: built[provided] for provided in factory.provides}


__all__ = [
    "ApplicationDependencyCycleError",
    "ApplicationRegistry",
    "AssemblyContext",
    "AssemblyError",
    "DuplicateApplicationProviderError",
    "MissingApplicationDependencyError",
    "UnknownApplicationError",
    "build_application_registry",
]
