"""App assembly primitives."""

from crxzipple.app.container import AppContainer, build_app_container
from crxzipple.app.keys import AppKey
from crxzipple.app.lifecycle import (
    RuntimeCleanupError,
    RuntimeCleanupFailure,
    RuntimeCleanupTask,
    run_runtime_cleanup_tasks,
)
from crxzipple.app.module_lifecycle import (
    DependencyKind,
    DuplicatePortExportError,
    MissingServiceDependencyError,
    ModuleActivationPlan,
    ModuleDependency,
    ModulePortExport,
    ModuleRuntimeHandle,
    PortRegistry,
    PortRegistryError,
    ReadinessIssue,
    ReadinessReport,
    ReadinessStatus,
    ResolvedActivationPlan,
)
from crxzipple.app.plan import (
    ActivationTask,
    ApplicationFactory,
    AssemblyPlan,
    AssemblyTarget,
)
from crxzipple.app.registry import (
    ApplicationDependencyCycleError,
    ApplicationRegistry,
    AssemblyContext,
    AssemblyError,
    DuplicateApplicationProviderError,
    MissingApplicationDependencyError,
    UnknownApplicationError,
    build_application_registry,
)

__all__ = [
    "ActivationTask",
    "AppContainer",
    "AppKey",
    "ApplicationDependencyCycleError",
    "ApplicationFactory",
    "ApplicationRegistry",
    "AssemblyContext",
    "AssemblyError",
    "AssemblyPlan",
    "AssemblyTarget",
    "DependencyKind",
    "DuplicateApplicationProviderError",
    "DuplicatePortExportError",
    "MissingServiceDependencyError",
    "MissingApplicationDependencyError",
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
    "RuntimeCleanupError",
    "RuntimeCleanupFailure",
    "RuntimeCleanupTask",
    "UnknownApplicationError",
    "build_app_container",
    "build_application_registry",
    "run_runtime_cleanup_tasks",
]
