"""Tool module app assembly."""

from __future__ import annotations

from typing import Any

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ActivationTask, ApplicationFactory, AssemblyTarget
from crxzipple.modules.tool.application import (
    DEFAULT_TOOL_CAPABILITY_CATALOG,
    ToolDependencyBinding,
    ToolFunctionCommandService,
    ToolSourceCommandService,
    ToolSourceQueryService,
    tool_settings_bootstrap_config_from_settings,
)
from crxzipple.modules.tool.infrastructure import (
    LocalAsyncToolExecutor,
    LocalToolRuntimeRegistry,
    RemoteAsyncToolExecutor,
    SandboxAsyncToolExecutor,
    ToolDiscoveryRegistry,
    ToolRuntimeRegistry,
    ToolRuntimeRouter,
    build_sandbox_backend,
)
from crxzipple.app.assembly.tool_service_graph import (
    ToolExecutionServicesAssembly,
    build_tool_execution_services,
    build_tool_execution_services_from_context,
    build_tool_queue_services,
)


def _activate_tool_packages(ctx) -> None:
    from crxzipple.app.assembly.tool_packages import (
        activate_tool_packages_from_context,
    )

    activate_tool_packages_from_context(ctx)


def _activate_configured_tool_provider_runtimes(ctx) -> None:
    from crxzipple.app.assembly.tool_sources.configured_providers import (
        activate_configured_tool_provider_runtimes,
    )

    activate_configured_tool_provider_runtimes(ctx)


def _build_tool_configured_runtime_activator(ctx):
    from crxzipple.app.assembly.tool_sources.configured_providers import (
        build_tool_configured_runtime_activator,
    )

    return build_tool_configured_runtime_activator(ctx)


def _build_tool_source_discovery_service(ctx):
    from crxzipple.app.assembly.tool_sources.configured_providers import (
        build_tool_source_discovery_service,
    )

    return build_tool_source_discovery_service(ctx)


def _sync_bundled_tool_source_catalog(ctx) -> None:
    from crxzipple.app.assembly.tool_sources.configured_providers import (
        sync_bundled_tool_source_catalog,
    )

    sync_bundled_tool_source_catalog(ctx)


def _sync_configured_tool_provider_source_catalog(ctx) -> None:
    from crxzipple.app.assembly.tool_sources.configured_providers import (
        sync_configured_tool_provider_source_catalog,
    )

    sync_configured_tool_provider_source_catalog(ctx)


TOOL_QUEUE_SERVICE_TARGETS: tuple[AssemblyTarget, ...] = (
    AssemblyTarget.TOOL_SCHEDULER,
    AssemblyTarget.OPERATIONS_OBSERVER,
    AssemblyTarget.EVENT_RELAY_WORKER,
    AssemblyTarget.CHANNEL_RUNTIME,
)

TOOL_ORCHESTRATION_QUEUE_SERVICE_TARGETS: tuple[AssemblyTarget, ...] = (
    AssemblyTarget.ORCHESTRATION_SCHEDULER,
)

TOOL_EXECUTION_SERVICE_TARGETS: tuple[AssemblyTarget, ...] = (
    AssemblyTarget.API,
    AssemblyTarget.CLI_ADMIN,
    AssemblyTarget.ORCHESTRATION_EXECUTOR,
    AssemblyTarget.TOOL_WORKER,
    AssemblyTarget.TEST,
)


def tool_factories() -> tuple[ApplicationFactory, ...]:
    """Build Tool catalog/runtime services without applying tool packages."""

    return tool_core_factories() + tool_queue_factories(
        provide_application_service=True,
    )


def tool_request_preview_factories() -> tuple[ApplicationFactory, ...]:
    """Build Tool services needed to render provider request schemas.

    The request-preview assembly is read-only. It can resolve enabled tool
    functions from the owner catalog and expose Tool's orchestration port for
    schema rendering, but it does not configure executable runtimes or run tool
    activation tasks.
    """

    return (
        ApplicationFactory(
            key="tool.bootstrap_config",
            provides=(AppKey.TOOL_BOOTSTRAP_CONFIG,),
            requires=(AppKey.SETTINGS_MATERIALIZER,),
            build=_build_tool_bootstrap_config,
        ),
        ApplicationFactory(
            key="tool.capability_catalog",
            provides=(AppKey.TOOL_CAPABILITY_CATALOG,),
            build=lambda _ctx: DEFAULT_TOOL_CAPABILITY_CATALOG,
        ),
        ApplicationFactory(
            key="tool.source_services",
            provides=(
                AppKey.TOOL_FUNCTION_COMMAND_SERVICE,
                AppKey.TOOL_SOURCE_COMMAND_SERVICE,
                AppKey.TOOL_SOURCE_QUERY_SERVICE,
            ),
            requires=(AppKey.UNIT_OF_WORK_FACTORY,),
            build=lambda ctx: {
                AppKey.TOOL_FUNCTION_COMMAND_SERVICE: ToolFunctionCommandService(
                    ctx.require(AppKey.UNIT_OF_WORK_FACTORY),
                ),
                AppKey.TOOL_SOURCE_COMMAND_SERVICE: ToolSourceCommandService(
                    ctx.require(AppKey.UNIT_OF_WORK_FACTORY),
                ),
                AppKey.TOOL_SOURCE_QUERY_SERVICE: ToolSourceQueryService(
                    ctx.require(AppKey.UNIT_OF_WORK_FACTORY),
                ),
            },
        ),
        ApplicationFactory(
            key="tool.runtime_infrastructure",
            provides=(
                AppKey.TOOL_PACKAGE_PLANS,
                AppKey.TOOL_LOCAL_RUNTIME_REGISTRY,
                AppKey.TOOL_DISCOVERY_REGISTRY,
                AppKey.TOOL_REMOTE_RUNTIME_REGISTRY,
                AppKey.TOOL_SANDBOX_RUNTIME_REGISTRY,
                AppKey.TOOL_RUNTIME_GATEWAY,
                AppKey.TOOL_CLEANUP_CALLBACKS,
            ),
            requires=(
                AppKey.CORE_SETTINGS,
                AppKey.TOOL_BOOTSTRAP_CONFIG,
            ),
            build=_build_tool_request_preview_runtime_infrastructure,
        ),
        ApplicationFactory(
            key="tool.capability_bindings",
            provides=(AppKey.TOOL_CAPABILITY_BINDINGS,),
            requires=(
                AppKey.CORE_SETTINGS,
                AppKey.ACCESS_SERVICE,
            ),
            build=_build_tool_capability_bindings,
        ),
    ) + tool_queue_factories(
        provide_application_service=True,
        provide_orchestration_port=True,
    )


def tool_core_factories() -> tuple[ApplicationFactory, ...]:
    """Build Tool catalogs, runtime registries and capability declarations."""

    return (
        ApplicationFactory(
            key="tool.bootstrap_config",
            provides=(AppKey.TOOL_BOOTSTRAP_CONFIG,),
            requires=(AppKey.SETTINGS_MATERIALIZER,),
            build=_build_tool_bootstrap_config,
        ),
        ApplicationFactory(
            key="tool.capability_catalog",
            provides=(AppKey.TOOL_CAPABILITY_CATALOG,),
            build=lambda _ctx: DEFAULT_TOOL_CAPABILITY_CATALOG,
        ),
        ApplicationFactory(
            key="tool.source_services",
            provides=(
                AppKey.TOOL_FUNCTION_COMMAND_SERVICE,
                AppKey.TOOL_SOURCE_COMMAND_SERVICE,
                AppKey.TOOL_SOURCE_QUERY_SERVICE,
            ),
            requires=(AppKey.UNIT_OF_WORK_FACTORY,),
            build=lambda ctx: {
                AppKey.TOOL_FUNCTION_COMMAND_SERVICE: ToolFunctionCommandService(
                    ctx.require(AppKey.UNIT_OF_WORK_FACTORY),
                ),
                AppKey.TOOL_SOURCE_COMMAND_SERVICE: ToolSourceCommandService(
                    ctx.require(AppKey.UNIT_OF_WORK_FACTORY),
                ),
                AppKey.TOOL_SOURCE_QUERY_SERVICE: ToolSourceQueryService(
                    ctx.require(AppKey.UNIT_OF_WORK_FACTORY),
                ),
            },
        ),
        ApplicationFactory(
            key="tool.runtime_infrastructure",
            provides=(
                AppKey.TOOL_PACKAGE_PLANS,
                AppKey.TOOL_LOCAL_RUNTIME_REGISTRY,
                AppKey.TOOL_DISCOVERY_REGISTRY,
                AppKey.TOOL_REMOTE_RUNTIME_REGISTRY,
                AppKey.TOOL_SANDBOX_RUNTIME_REGISTRY,
                AppKey.TOOL_RUNTIME_GATEWAY,
                AppKey.TOOL_CLEANUP_CALLBACKS,
            ),
            requires=(
                AppKey.CORE_SETTINGS,
                AppKey.TOOL_BOOTSTRAP_CONFIG,
            ),
            build=_build_tool_runtime_infrastructure,
        ),
        ApplicationFactory(
            key="tool.source_discovery_service",
            provides=(AppKey.TOOL_SOURCE_DISCOVERY_SERVICE,),
            requires=(AppKey.TOOL_PACKAGE_PLANS,),
            build=_build_tool_source_discovery_service,
        ),
        ApplicationFactory(
            key="tool.capability_bindings",
            provides=(AppKey.TOOL_CAPABILITY_BINDINGS,),
            requires=(
                AppKey.CORE_SETTINGS,
                AppKey.ACCESS_SERVICE,
            ),
            build=_build_tool_capability_bindings,
        ),
        ApplicationFactory(
            key="tool.configured_runtime_activator",
            provides=(AppKey.TOOL_CONFIGURED_RUNTIME_ACTIVATOR,),
            requires=(
                AppKey.RUNTIME_BOOTSTRAP_CONFIG,
                AppKey.ACCESS_SERVICE,
                AppKey.EVENTS_SERVICE,
                AppKey.UNIT_OF_WORK_FACTORY,
                AppKey.PROCESS_SERVICE,
                AppKey.TOOL_SOURCE_QUERY_SERVICE,
                AppKey.TOOL_REMOTE_RUNTIME_REGISTRY,
                AppKey.TOOL_CLEANUP_CALLBACKS,
            ),
            build=_build_tool_configured_runtime_activator,
        ),
    )


def tool_queue_factories(
    *,
    targets: tuple[AssemblyTarget, ...] = (),
    provide_application_service: bool = False,
    provide_orchestration_port: bool = False,
) -> tuple[ApplicationFactory, ...]:
    """Build queue services with only module-local Tool dependencies."""

    provides = (
        AppKey.TOOL_QUERY_SERVICE,
        AppKey.TOOL_RUNTIME_POOL_SERVICE,
        AppKey.TOOL_SCHEDULER_SERVICE,
        AppKey.TOOL_WORKER_REGISTRY_SERVICE,
    )
    if provide_application_service:
        provides = (AppKey.TOOL_SERVICE,) + provides
    if provide_orchestration_port:
        provides = provides + (AppKey.TOOL_ORCHESTRATION_PORT,)
    return (
        ApplicationFactory(
            key=_tool_queue_services_factory_key(
                provide_application_service=provide_application_service,
                provide_orchestration_port=provide_orchestration_port,
            ),
            provides=provides,
            requires=(
                AppKey.CORE_SETTINGS,
                AppKey.RUNTIME_BOOTSTRAP_CONFIG,
                AppKey.UNIT_OF_WORK_FACTORY,
                AppKey.DISPATCH_SERVICE,
                AppKey.ACCESS_SERVICE,
                AppKey.TOOL_RUNTIME_GATEWAY,
                AppKey.TOOL_REMOTE_RUNTIME_REGISTRY,
                AppKey.TOOL_SOURCE_QUERY_SERVICE,
            ),
            build=lambda ctx: build_tool_queue_services(
                ctx,
                provide_application_service=provide_application_service,
                provide_orchestration_port=provide_orchestration_port,
            ),
            targets=targets,
        ),
    )


def tool_execution_factories() -> tuple[ApplicationFactory, ...]:
    """Build executable Tool queue services with app-level runtime integrations."""

    return (
        ApplicationFactory(
            key="tool.execution_services",
            provides=(
                AppKey.TOOL_SERVICE,
                AppKey.TOOL_QUERY_SERVICE,
                AppKey.TOOL_RUN_CONTROL_SERVICE,
                AppKey.TOOL_RUNTIME_POOL_SERVICE,
                AppKey.TOOL_ORCHESTRATION_PORT,
                AppKey.TOOL_SCHEDULER_SERVICE,
                AppKey.TOOL_WORKER_REGISTRY_SERVICE,
                AppKey.TOOL_WORKER_SERVICE,
            ),
            requires=(
                AppKey.CORE_SETTINGS,
                AppKey.RUNTIME_BOOTSTRAP_CONFIG,
                AppKey.UNIT_OF_WORK_FACTORY,
                AppKey.DISPATCH_SERVICE,
                AppKey.ACCESS_SERVICE,
                AppKey.DAEMON_SERVICE,
                AppKey.ARTIFACT_SERVICE,
                AppKey.TOOL_RUNTIME_GATEWAY,
                AppKey.TOOL_REMOTE_RUNTIME_REGISTRY,
                AppKey.TOOL_SOURCE_QUERY_SERVICE,
            ),
            build=build_tool_execution_services_from_context,
            targets=TOOL_EXECUTION_SERVICE_TARGETS,
        ),
    )


def tool_activation_tasks() -> tuple[ActivationTask, ...]:
    return (
        ActivationTask(
            key="tool.sync_bundled_source_catalog",
            requires=(
                AppKey.TOOL_PACKAGE_PLANS,
                AppKey.TOOL_SOURCE_COMMAND_SERVICE,
                AppKey.TOOL_SOURCE_QUERY_SERVICE,
                AppKey.TOOL_SOURCE_DISCOVERY_SERVICE,
                AppKey.UNIT_OF_WORK_FACTORY,
            ),
            run=_sync_bundled_tool_source_catalog,
            targets=(
                AssemblyTarget.API,
                AssemblyTarget.CLI_ADMIN,
                AssemblyTarget.ORCHESTRATION_EXECUTOR,
                AssemblyTarget.TOOL_WORKER,
                AssemblyTarget.TEST,
            ),
        ),
        ActivationTask(
            key="tool.sync_configured_provider_source_catalog",
            requires=(
                AppKey.TOOL_BOOTSTRAP_CONFIG,
                AppKey.TOOL_SOURCE_COMMAND_SERVICE,
                AppKey.TOOL_SOURCE_DISCOVERY_SERVICE,
            ),
            run=_sync_configured_tool_provider_source_catalog,
            targets=(
                AssemblyTarget.API,
                AssemblyTarget.CLI_ADMIN,
                AssemblyTarget.ORCHESTRATION_EXECUTOR,
                AssemblyTarget.TOOL_WORKER,
                AssemblyTarget.TEST,
            ),
        ),
        ActivationTask(
            key="tool.activate_packages",
            requires=(
                AppKey.CORE_SETTINGS,
                AppKey.RUNTIME_BOOTSTRAP_CONFIG,
                AppKey.TOOL_PACKAGE_PLANS,
                AppKey.TOOL_LOCAL_RUNTIME_REGISTRY,
                AppKey.TOOL_REMOTE_RUNTIME_REGISTRY,
                AppKey.TOOL_SANDBOX_RUNTIME_REGISTRY,
                AppKey.TOOL_DISCOVERY_REGISTRY,
                AppKey.TOOL_CAPABILITY_BINDINGS,
                AppKey.TOOL_CAPABILITY_CATALOG,
                AppKey.TOOL_SOURCE_QUERY_SERVICE,
            ),
            run=_activate_tool_packages,
            targets=(
                AssemblyTarget.API,
                AssemblyTarget.CLI_ADMIN,
                AssemblyTarget.ORCHESTRATION_EXECUTOR,
                AssemblyTarget.TOOL_WORKER,
                AssemblyTarget.TEST,
            ),
        ),
        ActivationTask(
            key="tool.activate_configured_provider_runtimes",
            requires=(
                AppKey.TOOL_CONFIGURED_RUNTIME_ACTIVATOR,
            ),
            run=_activate_configured_tool_provider_runtimes,
            targets=(
                AssemblyTarget.API,
                AssemblyTarget.CLI_ADMIN,
                AssemblyTarget.ORCHESTRATION_EXECUTOR,
                AssemblyTarget.TOOL_WORKER,
                AssemblyTarget.TEST,
            ),
        ),
    )


def _build_tool_bootstrap_config(ctx):
    materializer = ctx.require(AppKey.SETTINGS_MATERIALIZER)
    return tool_settings_bootstrap_config_from_settings(
        providers=materializer.tool_providers(),
        roots=materializer.tool_roots(),
    )


def _build_tool_runtime_infrastructure(ctx) -> dict[str, Any]:
    from crxzipple.app.assembly.tool_packages import validate_tool_package_plans
    from crxzipple.modules.tool.infrastructure import discover_tool_package_plans
    from crxzipple.app.assembly.tool_runtime import ToolCleanupCallbacks

    settings = ctx.require(AppKey.CORE_SETTINGS)

    local_runtime_registry = LocalToolRuntimeRegistry()
    discovery_registry = ToolDiscoveryRegistry()
    sandbox_runtime_registry = ToolRuntimeRegistry()
    remote_runtime_registry = ToolRuntimeRegistry()
    package_plans = discover_tool_package_plans()

    validate_tool_package_plans(package_plans)

    cleanup_callbacks = ToolCleanupCallbacks()

    runtime_gateway = ToolRuntimeRouter(
        LocalAsyncToolExecutor(local_runtime_registry),
        SandboxAsyncToolExecutor(
            sandbox_runtime_registry,
            build_sandbox_backend(settings),
        ),
        RemoteAsyncToolExecutor(remote_runtime_registry),
    )
    return {
        AppKey.TOOL_PACKAGE_PLANS: package_plans,
        AppKey.TOOL_LOCAL_RUNTIME_REGISTRY: local_runtime_registry,
        AppKey.TOOL_DISCOVERY_REGISTRY: discovery_registry,
        AppKey.TOOL_REMOTE_RUNTIME_REGISTRY: remote_runtime_registry,
        AppKey.TOOL_SANDBOX_RUNTIME_REGISTRY: sandbox_runtime_registry,
        AppKey.TOOL_RUNTIME_GATEWAY: runtime_gateway,
        AppKey.TOOL_CLEANUP_CALLBACKS: (cleanup_callbacks,),
    }


def _build_tool_request_preview_runtime_infrastructure(ctx) -> dict[str, Any]:
    settings = ctx.require(AppKey.CORE_SETTINGS)

    local_runtime_registry = LocalToolRuntimeRegistry()
    discovery_registry = ToolDiscoveryRegistry()
    sandbox_runtime_registry = ToolRuntimeRegistry()
    remote_runtime_registry = ToolRuntimeRegistry()
    runtime_gateway = ToolRuntimeRouter(
        LocalAsyncToolExecutor(local_runtime_registry),
        SandboxAsyncToolExecutor(
            sandbox_runtime_registry,
            build_sandbox_backend(settings),
        ),
        RemoteAsyncToolExecutor(remote_runtime_registry),
    )
    return {
        AppKey.TOOL_PACKAGE_PLANS: (),
        AppKey.TOOL_LOCAL_RUNTIME_REGISTRY: local_runtime_registry,
        AppKey.TOOL_DISCOVERY_REGISTRY: discovery_registry,
        AppKey.TOOL_REMOTE_RUNTIME_REGISTRY: remote_runtime_registry,
        AppKey.TOOL_SANDBOX_RUNTIME_REGISTRY: sandbox_runtime_registry,
        AppKey.TOOL_RUNTIME_GATEWAY: runtime_gateway,
        AppKey.TOOL_CLEANUP_CALLBACKS: (),
    }


def _build_tool_capability_bindings(ctx) -> dict[str, ToolDependencyBinding]:
    bindings = (
        ToolDependencyBinding(
            "credential_provider",
            ctx.require(AppKey.ACCESS_SERVICE),
            capability_ids=("credential.read", "access.readiness"),
            description="Access credential/readiness application service.",
        ),
        ToolDependencyBinding(
            "settings",
            ctx.require(AppKey.CORE_SETTINGS),
            capability_ids=("runtime_settings.read",),
            description="Effective runtime settings.",
        ),
    )
    return {binding.dependency_id: binding for binding in bindings}


def _tool_queue_services_factory_key(
    *,
    provide_application_service: bool,
    provide_orchestration_port: bool,
) -> str:
    if provide_application_service:
        return "tool.application_services"
    if provide_orchestration_port:
        return "tool.orchestration_queue_services"
    return "tool.queue_services"


__all__ = [
    "TOOL_EXECUTION_SERVICE_TARGETS",
    "TOOL_ORCHESTRATION_QUEUE_SERVICE_TARGETS",
    "TOOL_QUEUE_SERVICE_TARGETS",
    "ToolExecutionServicesAssembly",
    "build_tool_execution_services",
    "tool_activation_tasks",
    "tool_core_factories",
    "tool_execution_factories",
    "tool_factories",
    "tool_queue_factories",
    "tool_request_preview_factories",
]
