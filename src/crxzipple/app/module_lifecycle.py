"""App assembly module lifecycle primitives.

Lifecycle order:
    construct -> export -> plan -> resolve -> apply -> readiness -> activate

These types are intentionally kept at the app assembly boundary. They describe
explicit module capabilities and activation dependencies, but they do not own
module runtime behavior and must not be passed down to handlers as a service
locator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class DependencyKind(StrEnum):
    """Activation dependency classes understood by app assembly."""

    SERVICE_DEPENDENCY = "service_dependency"
    EXTERNAL_REQUIREMENT = "external_requirement"
    OPTIONAL_DEPENDENCY = "optional_dependency"


class ReadinessStatus(StrEnum):
    """Readiness states emitted by activation plan resolution."""

    READY = "ready"
    SETUP_REQUIRED = "setup_required"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ModulePortExport:
    """A stable capability exported by one module for app assembly wiring."""

    name: str
    provider_module: str
    value: object
    contract: type[object] | None = None


@dataclass(frozen=True)
class ModuleDependency:
    """A dependency declared by a module activation plan."""

    port_name: str
    kind: DependencyKind = DependencyKind.SERVICE_DEPENDENCY
    reason: str = ""


@dataclass(frozen=True)
class ReadinessIssue:
    """A non-fatal readiness issue observed while resolving a plan."""

    module_name: str
    dependency_name: str
    kind: DependencyKind
    status: ReadinessStatus
    message: str


@dataclass(frozen=True)
class ReadinessReport:
    """Readiness summary for a resolved activation plan."""

    module_name: str
    issues: tuple[ReadinessIssue, ...] = ()

    @property
    def status(self) -> ReadinessStatus:
        if any(issue.status is ReadinessStatus.BLOCKED for issue in self.issues):
            return ReadinessStatus.BLOCKED
        if any(issue.status is ReadinessStatus.SETUP_REQUIRED for issue in self.issues):
            return ReadinessStatus.SETUP_REQUIRED
        if self.issues:
            return ReadinessStatus.DEGRADED
        return ReadinessStatus.READY

    @property
    def is_ready(self) -> bool:
        return self.status is ReadinessStatus.READY


@dataclass(frozen=True)
class ModuleActivationPlan:
    """App assembly plan describing the ports a module needs before apply."""

    module_name: str
    dependencies: tuple[ModuleDependency, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedActivationPlan:
    """An activation plan after app assembly has resolved available ports."""

    module_name: str
    dependencies: Mapping[str, object]
    readiness: ReadinessReport
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "dependencies", MappingProxyType(dict(self.dependencies)))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class ModuleRuntimeHandle:
    """Final assembly handle for a constructed module runtime."""

    module_name: str
    ports: tuple[ModulePortExport, ...] = ()
    activation: ResolvedActivationPlan | None = None
    runtime: object | None = None
    readiness: ReadinessReport | None = None


class PortRegistryError(RuntimeError):
    """Base class for app assembly port registry errors."""


class DuplicatePortExportError(PortRegistryError):
    """Raised when two modules export the same port name."""


class MissingServiceDependencyError(PortRegistryError):
    """Raised when a required service dependency cannot be resolved."""

    def __init__(self, module_name: str, dependency_name: str) -> None:
        super().__init__(
            f"{module_name} requires missing service dependency {dependency_name!r}"
        )
        self.module_name = module_name
        self.dependency_name = dependency_name


class PortRegistry:
    """App assembly registry used to resolve activation plans."""

    def __init__(self) -> None:
        self._exports: dict[str, ModulePortExport] = {}

    def register(self, export: ModulePortExport) -> None:
        existing = self._exports.get(export.name)
        if existing is not None:
            raise DuplicatePortExportError(
                f"port {export.name!r} already exported by "
                f"{existing.provider_module!r}; duplicate from {export.provider_module!r}"
            )
        self._exports[export.name] = export

    def register_many(self, exports: tuple[ModulePortExport, ...]) -> None:
        for export in exports:
            self.register(export)

    def has(self, port_name: str) -> bool:
        return port_name in self._exports

    def export_for(self, port_name: str) -> ModulePortExport:
        try:
            return self._exports[port_name]
        except KeyError as exc:
            raise KeyError(f"unknown port {port_name!r}") from exc

    def value_for(self, port_name: str) -> object:
        return self.export_for(port_name).value

    def resolve(self, plan: ModuleActivationPlan) -> ResolvedActivationPlan:
        resolved: dict[str, object] = {}
        issues: list[ReadinessIssue] = []
        for dependency in plan.dependencies:
            if self.has(dependency.port_name):
                resolved[dependency.port_name] = self.value_for(dependency.port_name)
                continue
            if dependency.kind is DependencyKind.SERVICE_DEPENDENCY:
                raise MissingServiceDependencyError(plan.module_name, dependency.port_name)
            issues.append(_missing_readiness_issue(plan.module_name, dependency))

        readiness = ReadinessReport(module_name=plan.module_name, issues=tuple(issues))
        return ResolvedActivationPlan(
            module_name=plan.module_name,
            dependencies=resolved,
            readiness=readiness,
            metadata=plan.metadata,
        )

    def snapshot(self) -> Mapping[str, ModulePortExport]:
        return MappingProxyType(dict(self._exports))


def _missing_readiness_issue(
    module_name: str, dependency: ModuleDependency
) -> ReadinessIssue:
    if dependency.kind is DependencyKind.EXTERNAL_REQUIREMENT:
        status = ReadinessStatus.SETUP_REQUIRED
        default_message = (
            f"{module_name} needs external requirement {dependency.port_name!r} "
            "before full readiness."
        )
    else:
        status = ReadinessStatus.DEGRADED
        default_message = (
            f"{module_name} optional dependency {dependency.port_name!r} is unavailable."
        )
    return ReadinessIssue(
        module_name=module_name,
        dependency_name=dependency.port_name,
        kind=dependency.kind,
        status=status,
        message=dependency.reason or default_message,
    )


__all__ = [
    "DependencyKind",
    "DuplicatePortExportError",
    "MissingServiceDependencyError",
    "ModuleActivationPlan",
    "ModuleDependency",
    "ModulePortExport",
    "ModuleRuntimeHandle",
    "PortRegistry",
    "PortRegistryError",
    "ReadinessIssue",
    "ReadinessReport",
    "ReadinessStatus",
    "ResolvedActivationPlan",
]
