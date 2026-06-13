"""Tool module app assembly."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from crxzipple.app.assembly.tool_packages import (
    activate_tool_packages_from_context as _activate_tool_packages,
    validate_tool_package_plans as _validate_tool_package_plans,
)
from crxzipple.app.assembly.tool_runtime import ToolCleanupCallbacks
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
from crxzipple.modules.tool.application.service_graph import build_tool_service_graph
from crxzipple.modules.tool.application.service_support import ToolServiceDependencies
from crxzipple.modules.tool.infrastructure import (
    LocalAsyncToolExecutor,
    LocalToolRuntimeRegistry,
    RemoteAsyncToolExecutor,
    SandboxAsyncToolExecutor,
    ToolDiscoveryRegistry,
    ToolRuntimeRegistry,
    ToolRuntimeRouter,
    build_sandbox_backend,
    discover_tool_package_plans,
)
from crxzipple.modules.tool.infrastructure.adapters import (
    AccessServiceToolReadinessAdapter,
    DaemonServiceToolRuntimeReadinessAdapter,
    ToolRunDispatchAdapter,
)
from crxzipple.shared.runtime_metrics import get_runtime_metrics_registry
from crxzipple.app.assembly.tool_sources.configured_providers import (
    activate_configured_tool_provider_runtimes as _activate_configured_tool_provider_runtimes,
    build_tool_configured_runtime_activator as _build_tool_configured_runtime_activator,
    build_tool_source_discovery_service as _build_tool_source_discovery_service,
    sync_bundled_tool_source_catalog as _sync_bundled_tool_source_catalog,
    sync_configured_tool_provider_source_catalog as _sync_configured_tool_provider_source_catalog,
)


@dataclass(slots=True)
class ToolExecutionServicesAssembly:
    application_service: Any
    scheduler_service: Any
    worker_service: Any


@dataclass(slots=True)
class ToolQueryServiceAdapter:
    service: Any
    source_query: Any | None = None

    @property
    def concurrency_policy(self) -> Any:
        return self.service.concurrency_policy

    def list_tools(self):
        return self.service.list_tools()

    def list_enabled_tools(self, *, runtime_context: Mapping[str, Any] | None = None):
        return self.service.list_enabled_tools(runtime_context=runtime_context)

    def get_tool(self, tool_id: str):
        return self.service.get_tool(tool_id)

    def list_tool_runs(self, *, tool_id: str | None = None):
        return self.service.list_tool_runs(tool_id=tool_id)

    def get_tool_run(self, run_id: str):
        return self.service.get_tool_run(run_id)

    def list_tool_workers(self):
        return self.service.list_tool_workers()

    def list_tool_run_assignments(self):
        return self.service.list_tool_run_assignments()

    def check_readiness(
        self,
        tool_id: str,
        *,
        workspace_dir: str | None = None,
    ):
        return self.service.check_readiness(tool_id, workspace_dir=workspace_dir)

    def check_access_readiness(
        self,
        tool_id: str,
        *,
        workspace_dir: str | None = None,
    ):
        del workspace_dir
        return self.service.check_access_readiness(
            tool_id,
        )

    def list_sources(self):
        if self.source_query is None:
            return ()
        return self.source_query.list_sources()

    def list_functions(self):
        if self.source_query is None:
            return ()
        return self.source_query.list_functions()

    def list_provider_backends(self):
        if self.source_query is None:
            return ()
        return self.source_query.list_provider_backends()

    def check_provider_backend_readiness(self, backend):
        check_readiness = getattr(
            self.service,
            "check_provider_backend_readiness",
            None,
        )
        if not callable(check_readiness):
            return None
        return check_readiness(backend)

    def list_source_discovery_runs(self, source_id: str, *, limit: int = 20):
        if self.source_query is None:
            return ()
        return self.source_query.list_discovery_runs(source_id, limit=limit)


@dataclass(slots=True)
class ToolRunControlAdapter:
    service: Any

    def get_tool_run(self, run_id: str):
        return self.service.get_tool_run(run_id)

    def cancel_tool_run(self, run_id: str):
        return self.service.cancel_tool_run(run_id)

    async def retry_tool_run(self, run_id: str):
        return await self.service.retry_tool_run(run_id)

    def prune_expired_workers(self, *, retention_seconds: int):
        return self.service.prune_expired_workers(retention_seconds=retention_seconds)


@dataclass(slots=True)
class ToolOrchestrationPortAdapter:
    service: Any
    runtime_pool_service: Any

    def list_enabled_tools(self, *, runtime_context: Mapping[str, Any] | None = None):
        return list(
            self.runtime_pool_service.list_enabled_tools(
                runtime_context=runtime_context,
            ),
        )

    def build_tool_surface(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        agent_id: str | None = None,
        runtime_context: object | None = None,
        surface_id: str | None = None,
        tool_ids: tuple[str, ...] | None = None,
        persist: bool = False,
    ):
        return self.service.build_tool_surface(
            session_id=session_id,
            run_id=run_id,
            agent_id=agent_id,
            runtime_context=runtime_context,
            surface_id=surface_id,
            tool_ids=tool_ids,
            persist=persist,
        )

    async def execute(self, data):
        return await self.service.execute(data)

    async def execute_many(self, items):
        return await self.service.execute_many(items)

    def get_tool_run(self, run_id: str):
        return self.service.get_tool_run(run_id)

    def cancel_tool_run(self, run_id: str):
        return self.service.cancel_tool_run(run_id)


@dataclass(slots=True)
class ToolWorkerRegistrationAdapter:
    worker_service: Any

    def register_worker(
        self,
        *,
        worker_id: str,
        max_in_flight: int = 1,
        capabilities_payload: dict[str, Any] | None = None,
    ) -> object:
        return self.worker_service.register_worker(
            worker_id=worker_id,
            max_in_flight=max_in_flight,
            capabilities_payload=capabilities_payload,
        )


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
            build=lambda ctx: _build_tool_queue_services(
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
            build=_build_tool_execution_services,
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
    settings = ctx.require(AppKey.CORE_SETTINGS)

    local_runtime_registry = LocalToolRuntimeRegistry()
    discovery_registry = ToolDiscoveryRegistry()
    sandbox_runtime_registry = ToolRuntimeRegistry()
    remote_runtime_registry = ToolRuntimeRegistry()
    package_plans = discover_tool_package_plans()

    _validate_tool_package_plans(package_plans)

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


def _build_tool_queue_services(
    ctx,
    *,
    provide_application_service: bool,
    provide_orchestration_port: bool,
) -> dict[str, Any]:
    settings = ctx.require(AppKey.CORE_SETTINGS)
    runtime_bootstrap_config = ctx.require(AppKey.RUNTIME_BOOTSTRAP_CONFIG)
    graph = build_tool_service_graph(
        ToolServiceDependencies(
            uow_factory=ctx.require(AppKey.UNIT_OF_WORK_FACTORY),
            runtime_gateway=ctx.require(AppKey.TOOL_RUNTIME_GATEWAY),
            runtime_registry=ctx.require(AppKey.TOOL_REMOTE_RUNTIME_REGISTRY),
            dispatch_port=ToolRunDispatchAdapter(
                dispatch_service=ctx.require(AppKey.DISPATCH_SERVICE),
            ),
            access_readiness=AccessServiceToolReadinessAdapter(
                ctx.require(AppKey.ACCESS_SERVICE),
            ),
            runtime_readiness=None,
            artifact_service=None,
            default_max_attempts=runtime_bootstrap_config.tool_run_max_attempts,
            worker_lease_seconds=runtime_bootstrap_config.tool_run_lease_seconds,
            worker_heartbeat_seconds=runtime_bootstrap_config.tool_run_heartbeat_seconds,
            details_max_chars=settings.tool_details_max_chars,
            worker_default_run_concurrency=(
                runtime_bootstrap_config.tool_worker_default_run_concurrency
            ),
            worker_image_run_concurrency=(
                runtime_bootstrap_config.tool_worker_image_run_concurrency
            ),
            worker_shared_state_run_concurrency=(
                runtime_bootstrap_config.tool_worker_shared_state_run_concurrency
            ),
            metrics=get_runtime_metrics_registry(),
        ),
    )
    services: dict[str, Any] = {
        AppKey.TOOL_QUERY_SERVICE: ToolQueryServiceAdapter(
            graph.application_service,
            source_query=ctx.require(AppKey.TOOL_SOURCE_QUERY_SERVICE),
        ),
        AppKey.TOOL_RUNTIME_POOL_SERVICE: graph.runtime_pool_service,
        AppKey.TOOL_SCHEDULER_SERVICE: graph.scheduler_service,
        AppKey.TOOL_WORKER_REGISTRY_SERVICE: ToolWorkerRegistrationAdapter(
            graph.worker_service,
        ),
    }
    if provide_application_service:
        services[AppKey.TOOL_SERVICE] = graph.application_service
    if provide_orchestration_port:
        services[AppKey.TOOL_ORCHESTRATION_PORT] = ToolOrchestrationPortAdapter(
            graph.application_service,
            graph.runtime_pool_service,
        )
    return services


def _build_tool_execution_services(ctx) -> dict[str, Any]:
    execution = build_tool_execution_services(
        settings=ctx.require(AppKey.CORE_SETTINGS),
        runtime_bootstrap_config=ctx.require(AppKey.RUNTIME_BOOTSTRAP_CONFIG),
        uow_factory=ctx.require(AppKey.UNIT_OF_WORK_FACTORY),
        runtime_gateway=ctx.require(AppKey.TOOL_RUNTIME_GATEWAY),
        runtime_registry=ctx.require(AppKey.TOOL_REMOTE_RUNTIME_REGISTRY),
        dispatch_service=ctx.require(AppKey.DISPATCH_SERVICE),
        access_service=ctx.require(AppKey.ACCESS_SERVICE),
        daemon_service=ctx.require(AppKey.DAEMON_SERVICE),
        artifact_service=ctx.require(AppKey.ARTIFACT_SERVICE),
    )
    return {
        AppKey.TOOL_SERVICE: execution.application_service,
        AppKey.TOOL_QUERY_SERVICE: ToolQueryServiceAdapter(
            execution.application_service,
            source_query=ctx.require(AppKey.TOOL_SOURCE_QUERY_SERVICE),
        ),
        AppKey.TOOL_RUN_CONTROL_SERVICE: ToolRunControlAdapter(
            execution.application_service,
        ),
        AppKey.TOOL_RUNTIME_POOL_SERVICE: execution.application_service.runtime_pool_service,
        AppKey.TOOL_ORCHESTRATION_PORT: ToolOrchestrationPortAdapter(
            execution.application_service,
            execution.application_service.runtime_pool_service,
        ),
        AppKey.TOOL_SCHEDULER_SERVICE: execution.scheduler_service,
        AppKey.TOOL_WORKER_REGISTRY_SERVICE: ToolWorkerRegistrationAdapter(
            execution.worker_service,
        ),
        AppKey.TOOL_WORKER_SERVICE: execution.worker_service,
    }


def build_tool_execution_services(
    *,
    settings: Any,
    runtime_bootstrap_config: Any,
    uow_factory: Callable[[], Any],
    runtime_gateway: Any,
    runtime_registry: Any,
    dispatch_service: Any,
    access_service: Any,
    daemon_service: Any,
    artifact_service: Any,
) -> ToolExecutionServicesAssembly:
    graph = build_tool_service_graph(
        ToolServiceDependencies(
            uow_factory=uow_factory,
            runtime_gateway=runtime_gateway,
            runtime_registry=runtime_registry,
            dispatch_port=ToolRunDispatchAdapter(dispatch_service=dispatch_service),
            access_readiness=AccessServiceToolReadinessAdapter(access_service),
            runtime_readiness=DaemonServiceToolRuntimeReadinessAdapter(
                daemon_service,
                access_service=access_service,
            ),
            artifact_service=artifact_service,
            default_max_attempts=runtime_bootstrap_config.tool_run_max_attempts,
            worker_lease_seconds=runtime_bootstrap_config.tool_run_lease_seconds,
            worker_heartbeat_seconds=runtime_bootstrap_config.tool_run_heartbeat_seconds,
            details_max_chars=settings.tool_details_max_chars,
            worker_default_run_concurrency=(
                runtime_bootstrap_config.tool_worker_default_run_concurrency
            ),
            worker_image_run_concurrency=(
                runtime_bootstrap_config.tool_worker_image_run_concurrency
            ),
            worker_shared_state_run_concurrency=(
                runtime_bootstrap_config.tool_worker_shared_state_run_concurrency
            ),
            metrics=get_runtime_metrics_registry(),
        ),
    )
    return ToolExecutionServicesAssembly(
        application_service=graph.application_service,
        scheduler_service=graph.scheduler_service,
        worker_service=graph.worker_service,
    )


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
]
