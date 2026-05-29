"""Tool module app assembly."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
import os
from typing import Any

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ActivationTask, ApplicationFactory, AssemblyTarget
from crxzipple.modules.tool.application import (
    DEFAULT_TOOL_CAPABILITY_CATALOG,
    ToolCatalogReconcileService,
    ToolDiscoveryAdapterRegistry,
    ToolDiscoveryService,
    ToolDependencyBinding,
    ToolFunctionCandidate,
    ToolFunctionCommandService,
    ToolFunctionRequirements,
    ToolFunctionRuntimeKind,
    ToolFunctionStatus,
    ToolSourceCatalogKind,
    ToolSourceCatalogRecord,
    ToolSourceCommandService,
    ToolSourceQueryService,
    ToolSourceStatus,
    tool_settings_bootstrap_config_from_settings,
)
from crxzipple.modules.tool.application.service_graph import build_tool_service_graph
from crxzipple.modules.tool.application.service_support import ToolServiceDependencies
from crxzipple.modules.tool.domain import Tool
from crxzipple.modules.tool.infrastructure import (
    LocalAsyncToolExecutor,
    LocalToolRuntimeRegistry,
    RemoteAsyncToolExecutor,
    SandboxAsyncToolExecutor,
    ToolPackageDiscoveryAdapter,
    ToolConfiguredProviderDiscoveryAdapter,
    ToolDiscoveryRegistry,
    ToolPackageApplyContext,
    ToolRuntimeRegistry,
    ToolRuntimeRouter,
    apply_tool_package_plans,
    build_sandbox_backend,
    discover_tool_package_plans,
    activate_configured_provider_runtimes,
    resolve_tool_package_activations,
    tool_source_records_from_configured_providers,
    tool_source_records_from_package_plans,
)
from crxzipple.modules.tool.infrastructure.adapters import (
    AccessServiceToolReadinessAdapter,
    DaemonServiceToolRuntimeReadinessAdapter,
    ToolRunDispatchAdapter,
)
from crxzipple.shared.runtime_metrics import get_runtime_metrics_registry


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


class ToolSourceDiscoveryRoutingAdapter:
    def __init__(
        self,
        *,
        package_adapter: ToolPackageDiscoveryAdapter,
        configured_adapter: ToolConfiguredProviderDiscoveryAdapter,
    ) -> None:
        self._package_adapter = package_adapter
        self._configured_adapter = configured_adapter

    def discover(self, source):
        source_kind = source.config.get("source")
        if source_kind == "bundled_tool_package":
            return self._package_adapter.discover(source)
        if source_kind == "configured_tool_provider":
            return self._configured_adapter.discover(source)
        raise ValueError(
            f"Tool source '{source.source_id}' has unsupported source marker '{source_kind}'.",
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


def tool_browser_activation_tasks() -> tuple[ActivationTask, ...]:
    """Register the CRXZipple-owned Browser source catalog integration."""

    return (
        ActivationTask(
            key="tool.register_browser_source_catalog",
            requires=(
                AppKey.BROWSER_INFRASTRUCTURE,
                AppKey.TOOL_SOURCE_COMMAND_SERVICE,
                AppKey.TOOL_SOURCE_QUERY_SERVICE,
                AppKey.TOOL_LOCAL_RUNTIME_REGISTRY,
                AppKey.UNIT_OF_WORK_FACTORY,
            ),
            run=_register_browser_tool_source_catalog,
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


def _validate_tool_package_plans(package_plans) -> None:
    resolve_tool_package_activations(
        ToolPackageApplyContext(
            capability_ids=DEFAULT_TOOL_CAPABILITY_CATALOG.capability_ids,
        ),
        package_plans,
        include_local=True,
        include_openapi=True,
        include_runtimes=True,
    )


def _build_tool_source_discovery_service(ctx) -> ToolDiscoveryService:
    adapter = ToolSourceDiscoveryRoutingAdapter(
        package_adapter=ToolPackageDiscoveryAdapter(
            ctx.require(AppKey.TOOL_PACKAGE_PLANS),
        ),
        configured_adapter=ToolConfiguredProviderDiscoveryAdapter(),
    )
    return ToolDiscoveryService(
        ToolDiscoveryAdapterRegistry(
            {
                ToolSourceCatalogKind.LOCAL_PACKAGE: adapter,
                ToolSourceCatalogKind.OPENAPI: adapter,
                ToolSourceCatalogKind.MCP: adapter,
                ToolSourceCatalogKind.CLI: adapter,
            },
        ),
    )


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


def _build_tool_configured_runtime_activator(ctx) -> ToolConfiguredRuntimeActivator:
    return ToolConfiguredRuntimeActivator(
        remote_default_max_concurrency=(
            ctx.require(AppKey.RUNTIME_BOOTSTRAP_CONFIG).tool_remote_default_max_concurrency
        ),
        source_query=ctx.require(AppKey.TOOL_SOURCE_QUERY_SERVICE),
        uow_factory=ctx.require(AppKey.UNIT_OF_WORK_FACTORY),
        remote_runtime_registry=ctx.require(AppKey.TOOL_REMOTE_RUNTIME_REGISTRY),
        credential_provider=ctx.require(AppKey.ACCESS_SERVICE),
        events_service=ctx.require(AppKey.EVENTS_SERVICE),
        process_service=ctx.require(AppKey.PROCESS_SERVICE),
        cleanup_callbacks=_tool_cleanup_callbacks(ctx),
    )


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


def build_tool_execution_capability_bindings(
    *,
    artifact_service: Any,
    browser_infrastructure: Any,
    mobile_infrastructure: Any,
    memory_runtime_service: Any,
    process_service: Any,
    session_service: Any,
    session_workspace_lookup: Callable[[str], str | None],
    session_runtime_control: Any,
    access_service: Any,
    skill_manager: Any,
) -> Mapping[str, ToolDependencyBinding]:
    bindings = (
        ToolDependencyBinding(
            "credential_provider",
            access_service,
            capability_ids=("credential.read", "access.readiness"),
        ),
        ToolDependencyBinding(
            "artifact_service",
            artifact_service,
            capability_ids=(
                "artifact.read",
                "artifact.write",
                "browser.artifact_write",
            ),
        ),
        ToolDependencyBinding(
            "browser_system_config",
            browser_infrastructure.system_config,
            capability_ids=("browser.profile_read", "runtime_settings.read"),
        ),
        ToolDependencyBinding(
            "browser_system_config_store",
            browser_infrastructure.system_config_store,
            capability_ids=("browser.profile_read", "runtime_settings.read"),
        ),
        ToolDependencyBinding(
            "browser_tool_application",
            browser_infrastructure.tool_application_service,
            capability_ids=("browser.control", "browser.page_action"),
        ),
        ToolDependencyBinding(
            "browser_profile_resolver",
            browser_infrastructure.profile_resolver,
            capability_ids=("browser.profile_read", "browser.runtime_readiness"),
        ),
        ToolDependencyBinding(
            "browser_capabilities_resolver",
            browser_infrastructure.capabilities_resolver,
            capability_ids=("browser.profile_read", "browser.runtime_readiness"),
        ),
        ToolDependencyBinding(
            "browser_runtime_state_store",
            browser_infrastructure.runtime_state_store,
            capability_ids=("browser.runtime_readiness",),
        ),
        ToolDependencyBinding(
            "browser_profile_probe_service",
            browser_infrastructure.profile_probe_service,
            capability_ids=("browser.runtime_readiness",),
        ),
        ToolDependencyBinding(
            "browser_profile_allocator_service",
            browser_infrastructure.profile_allocator_service,
            capability_ids=("browser.profile_read", "browser.runtime_readiness"),
        ),
        ToolDependencyBinding(
            "mobile_system_config",
            mobile_infrastructure.system_config,
            capability_ids=("mobile.device_read",),
        ),
        ToolDependencyBinding(
            "mobile_system_config_store",
            mobile_infrastructure.system_config_store,
            capability_ids=("mobile.device_read",),
        ),
        ToolDependencyBinding(
            "mobile_facade",
            mobile_infrastructure.facade,
            capability_ids=("mobile.device_read", "mobile.action", "mobile.screenshot"),
        ),
        ToolDependencyBinding(
            "mobile_result_serializer",
            mobile_infrastructure.result_serializer,
            capability_ids=("mobile.device_read", "mobile.action", "mobile.screenshot"),
        ),
        ToolDependencyBinding(
            "memory_runtime_service",
            memory_runtime_service,
            capability_ids=(
                "memory.context_lookup",
                "memory.search",
                "memory.read",
                "memory.write",
                "memory.flush_marker",
            ),
        ),
        ToolDependencyBinding(
            "process_service",
            process_service,
            capability_ids=("process.spawn", "process.manage"),
        ),
        ToolDependencyBinding(
            "session_service",
            session_service,
            capability_ids=("session.read", "session.write", "session.tree_read"),
        ),
        ToolDependencyBinding(
            "session_workspace_lookup",
            session_workspace_lookup,
            capability_ids=("workspace.lookup", "session.read"),
        ),
        ToolDependencyBinding(
            "session_runtime_control",
            session_runtime_control,
            capability_ids=(
                "session.read",
                "session.write",
                "session.tree_read",
                "session.route_enqueue",
                "session.tree_cancel",
                "run_control.yield",
            ),
        ),
        ToolDependencyBinding(
            "skill_manager",
            skill_manager,
            capability_ids=("skill.read",),
        ),
        ToolDependencyBinding(
            "skill_authoring_service",
            skill_manager,
            capability_ids=("skill.authoring",),
        ),
    )
    return {binding.dependency_id: binding for binding in bindings}


def _sync_bundled_tool_source_catalog(ctx) -> None:
    package_plans = ctx.require(AppKey.TOOL_PACKAGE_PLANS)
    sources = tool_source_records_from_package_plans(
        package_plans,
        include_openapi=_activate_bundled_openapi_packages(),
    )
    if not sources:
        return
    ctx.require(AppKey.TOOL_SOURCE_COMMAND_SERVICE).sync_sources(
        sources,
        discovery_service=ctx.require(AppKey.TOOL_SOURCE_DISCOVERY_SERVICE),
    )


def _sync_configured_tool_provider_source_catalog(ctx) -> None:
    bootstrap_config = ctx.require(AppKey.TOOL_BOOTSTRAP_CONFIG)
    sources = tool_source_records_from_configured_providers(
        openapi_providers=bootstrap_config.openapi_providers,
        mcp_providers=bootstrap_config.mcp_providers,
    )
    if not sources:
        return
    ctx.require(AppKey.TOOL_SOURCE_COMMAND_SERVICE).sync_sources(
        sources,
        discovery_service=ctx.require(AppKey.TOOL_SOURCE_DISCOVERY_SERVICE),
    )


def _register_browser_tool_source_catalog(ctx) -> None:
    sources = browser_source_records_from_system_config(
        ctx.require(AppKey.BROWSER_INFRASTRUCTURE).system_config,
    )
    if not sources:
        return
    command_service = ctx.require(AppKey.TOOL_SOURCE_COMMAND_SERVICE)
    query_service = ctx.require(AppKey.TOOL_SOURCE_QUERY_SERVICE)
    for source in sources:
        existing = query_service.get_source(source.source_id)
        if existing is not None:
            source = replace(
                source,
                last_discovered_at=existing.last_discovered_at,
                last_discovery_status=existing.last_discovery_status,
            )
        current = command_service.upsert_source(source).source
        if current.status in {ToolSourceStatus.DISABLED, ToolSourceStatus.DELETED}:
            continue
        _reconcile_browser_tool_functions(
            ctx.require(AppKey.UNIT_OF_WORK_FACTORY),
            source_id=current.source_id,
        )
        _register_browser_runtime_handlers(ctx)


_BROWSER_SOURCE_ID = "configured.browser"
_BROWSER_RUNTIME_REQUIREMENT = "browser-profile-runtime"


def browser_source_records_from_system_config(
    browser_system_config: Any,
) -> tuple[Any, ...]:
    del browser_system_config
    return (
        ToolSourceCatalogRecord(
            source_id=_BROWSER_SOURCE_ID,
            kind=ToolSourceCatalogKind.PROVIDER_BACKEND,
            display_name="Browser",
            description="CRXZipple Browser tools resolved through runtime profile context.",
            runtime_requirements=(_BROWSER_RUNTIME_REQUIREMENT,),
            config={
                "source": "configured_browser",
                "provider": "crxzipple.browser",
                "profile_mode": "runtime_context",
                "default_profile_source": "browser_system_config",
                "function_prefix": "browser.",
                "runtime_requirement": _BROWSER_RUNTIME_REQUIREMENT,
            },
        ),
    )


def browser_function_catalog_candidates(
    *,
    source_id: str = _BROWSER_SOURCE_ID,
) -> tuple[ToolFunctionCandidate, ...]:
    return tuple(
        _browser_function_candidate(source_id=source_id, **spec)
        for spec in _BROWSER_FUNCTION_SPECS
    )


def _reconcile_browser_tool_functions(
    uow_factory: Callable[[], Any],
    *,
    source_id: str,
) -> None:
    _reconcile_source_functions(
        uow_factory,
        source_id=source_id,
        candidates=browser_function_catalog_candidates(source_id=source_id),
    )


def _reconcile_source_functions(
    uow_factory: Callable[[], Any],
    *,
    source_id: str,
    candidates: tuple[ToolFunctionCandidate, ...],
) -> None:
    with uow_factory() as uow:
        ToolCatalogReconcileService(uow.tool_function_catalog).reconcile(
            source_id=source_id,
            candidates=candidates,
            deprecate_stale=True,
        )
        uow.commit()


def _browser_function_candidate(
    *,
    source_id: str,
    function_id: str,
    name: str,
    description: str,
    action: str,
    properties: Mapping[str, Any] | None = None,
    required: tuple[str, ...] = (),
    examples: tuple[Mapping[str, Any], ...] = (),
    mutates_state: bool = False,
    capabilities: tuple[str, ...] = (),
) -> ToolFunctionCandidate:
    return ToolFunctionCandidate(
        stable_key=function_id,
        source_id=source_id,
        function_id=function_id,
        name=name,
        description=description,
        input_schema=_browser_function_input_schema(
            dict(properties or {}),
            required=required,
            examples=examples,
        ),
        runtime_kind=ToolFunctionRuntimeKind.LOCAL,
        handler_ref=function_id,
        requirements=ToolFunctionRequirements(
            required_effect_ids=("local_tool_access",),
            runtime_requirement_sets=((_BROWSER_RUNTIME_REQUIREMENT,),),
        ),
        capabilities=capabilities or (
            "browser.control" if mutates_state else "browser.profile_read",
            "browser.page_action",
            "browser.runtime_readiness",
        ),
        metadata={
            "source": "configured_browser",
            "provider": "crxzipple.browser",
            "browser_runtime_action": action,
            "profile_mode": "runtime_context",
            "runtime_requirement": _BROWSER_RUNTIME_REQUIREMENT,
            "tool_kind": "function",
            "definition_origin": "local_discovery",
            "tags": ("browser", "builtin", "system-managed"),
            "execution_policy": {
                "timeout_seconds": 30,
                "requires_confirmation": False,
                "mutates_state": mutates_state,
            },
            "execution_support": {
                "supported_modes": ("inline",),
                "supported_strategies": ("async",),
                "supported_environments": ("local",),
            },
        },
    )


def _browser_function_input_schema(
    properties: dict[str, Any],
    *,
    required: tuple[str, ...] = (),
    examples: tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "profile": {
                "type": "string",
                "description": (
                    "Browser profile to use. Defaults to runtime/session/agent/"
                    "browser default profile."
                ),
            },
            "profile_pool": {
                "type": "string",
                "description": (
                    "Browser profile pool to allocate from. Use this for isolated "
                    "multi-profile browser work."
                ),
            },
            **properties,
        },
        "required": list(required),
        "additionalProperties": False,
    }
    if examples:
        schema["examples"] = [dict(example) for example in examples]
    return schema


def _register_browser_runtime_handlers(ctx) -> None:
    deps = _browser_tool_deps_from_context(ctx)
    handlers = _browser_runtime_handlers(deps)
    registry = ctx.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY)
    for runtime_key, handler in handlers.items():
        registry.register(
            Tool(
                id=runtime_key,
                name=runtime_key.replace(".", " ").title(),
                description="CRXZipple browser runtime handler.",
                runtime_key=runtime_key,
                required_effect_ids=("local_tool_access",),
                tags=("browser", "builtin", "system-managed"),
            ),
            handler,
            provider_name="crxzipple.browser",
        )


def _browser_tool_deps_from_context(ctx):
    from tools.browser.local import BrowserToolDeps

    browser = ctx.require(AppKey.BROWSER_INFRASTRUCTURE)
    return BrowserToolDeps(
        browser_tool_application=browser.tool_application_service,
        browser_system_config_store=browser.system_config_store,
        browser_profile_resolver=browser.profile_resolver,
        browser_capabilities_resolver=browser.capabilities_resolver,
        settings=ctx.require(AppKey.CORE_SETTINGS) if ctx.has(AppKey.CORE_SETTINGS) else None,
        artifact_service=(
            ctx.require(AppKey.ARTIFACT_SERVICE)
            if ctx.has(AppKey.ARTIFACT_SERVICE)
            else None
        ),
        browser_runtime_state_store=browser.runtime_state_store,
        browser_profile_probe_service=browser.profile_probe_service,
        browser_profile_allocator_service=browser.profile_allocator_service,
    )


def _browser_runtime_handlers(deps) -> dict[str, Any]:
    from tools.browser.local import (
        create_browser_context_handler,
        create_browser_control_handler,
        create_browser_network_handler,
        create_browser_page_action_handler,
        create_browser_snapshot_handler,
    )

    snapshot = create_browser_snapshot_handler(deps, tool_id="browser.snapshot")
    navigate = create_browser_control_handler(deps, tool_id="browser.navigate")
    click = create_browser_page_action_handler(deps, tool_id="browser.click")
    type_ = create_browser_page_action_handler(deps, tool_id="browser.type")
    evaluate = create_browser_page_action_handler(deps, tool_id="browser.evaluate")
    screenshot = create_browser_page_action_handler(deps, tool_id="browser.screenshot")
    dom_inspect = create_browser_page_action_handler(deps, tool_id="browser.dom.inspect")
    dom_box_model = create_browser_page_action_handler(deps, tool_id="browser.dom.box_model")
    dom_computed_style = create_browser_page_action_handler(
        deps,
        tool_id="browser.dom.computed_style",
    )
    dom_clickability = create_browser_page_action_handler(
        deps,
        tool_id="browser.dom.clickability",
    )
    dom_highlight = create_browser_page_action_handler(
        deps,
        tool_id="browser.dom.highlight",
    )
    dom_mutation_wait = create_browser_page_action_handler(
        deps,
        tool_id="browser.dom.mutation_wait",
    )
    storage_indexeddb_list = create_browser_page_action_handler(
        deps,
        tool_id="browser.storage.indexeddb.list",
    )
    storage_indexeddb_get = create_browser_page_action_handler(
        deps,
        tool_id="browser.storage.indexeddb.get",
    )
    storage_indexeddb_query = create_browser_page_action_handler(
        deps,
        tool_id="browser.storage.indexeddb.query",
    )
    storage_cache_list = create_browser_page_action_handler(
        deps,
        tool_id="browser.storage.cache.list",
    )
    storage_cache_get = create_browser_page_action_handler(
        deps,
        tool_id="browser.storage.cache.get",
    )
    service_worker_list = create_browser_page_action_handler(
        deps,
        tool_id="browser.service_worker.list",
    )
    service_worker_inspect = create_browser_page_action_handler(
        deps,
        tool_id="browser.service_worker.inspect",
    )
    emulation_set = create_browser_page_action_handler(
        deps,
        tool_id="browser.emulation.set",
    )
    emulation_reset = create_browser_page_action_handler(
        deps,
        tool_id="browser.emulation.reset",
    )
    permissions_grant = create_browser_page_action_handler(
        deps,
        tool_id="browser.permissions.grant",
    )
    permissions_clear = create_browser_page_action_handler(
        deps,
        tool_id="browser.permissions.clear",
    )
    geolocation_set = create_browser_page_action_handler(
        deps,
        tool_id="browser.geolocation.set",
    )
    network_conditions_set = create_browser_page_action_handler(
        deps,
        tool_id="browser.network_conditions.set",
    )
    diagnostics_collect = create_browser_page_action_handler(
        deps,
        tool_id="browser.diagnostics.collect",
    )
    performance_metrics = create_browser_page_action_handler(
        deps,
        tool_id="browser.performance.metrics",
    )
    trace_start = create_browser_page_action_handler(
        deps,
        tool_id="browser.trace.start",
    )
    trace_stop = create_browser_page_action_handler(
        deps,
        tool_id="browser.trace.stop",
    )
    trace_export = create_browser_page_action_handler(
        deps,
        tool_id="browser.trace.export",
    )
    page_lifecycle = create_browser_page_action_handler(
        deps,
        tool_id="browser.page.lifecycle",
    )
    page_errors = create_browser_page_action_handler(
        deps,
        tool_id="browser.page.errors",
    )
    context_acquire = create_browser_context_handler(
        deps,
        tool_id="browser.context.acquire",
        action="acquire",
    )
    context_current = create_browser_context_handler(
        deps,
        tool_id="browser.context.current",
        action="current",
    )
    context_heartbeat = create_browser_context_handler(
        deps,
        tool_id="browser.context.heartbeat",
        action="heartbeat",
    )
    context_release = create_browser_context_handler(
        deps,
        tool_id="browser.context.release",
        action="release",
    )
    context_reconcile = create_browser_context_handler(
        deps,
        tool_id="browser.context.reconcile",
        action="reconcile",
    )
    tabs_list = create_browser_control_handler(deps, tool_id="browser.tabs.list")
    tabs_select = create_browser_control_handler(deps, tool_id="browser.tabs.select")
    tabs_close = create_browser_control_handler(deps, tool_id="browser.tabs.close")
    network_start_capture = create_browser_network_handler(
        deps,
        tool_id="browser.network.start_capture",
    )
    network_stop_capture = create_browser_network_handler(
        deps,
        tool_id="browser.network.stop_capture",
    )
    network_list_requests = create_browser_network_handler(
        deps,
        tool_id="browser.network.list_requests",
    )
    network_get_request = create_browser_network_handler(
        deps,
        tool_id="browser.network.get_request",
    )
    network_get_response_body = create_browser_network_handler(
        deps,
        tool_id="browser.network.get_response_body",
    )
    network_get_request_body = create_browser_network_handler(
        deps,
        tool_id="browser.network.get_request_body",
    )
    network_fetch_as_page = create_browser_network_handler(
        deps,
        tool_id="browser.network.fetch_as_page",
    )
    network_replay_request = create_browser_network_handler(
        deps,
        tool_id="browser.network.replay_request",
    )
    network_clear_capture = create_browser_network_handler(
        deps,
        tool_id="browser.network.clear_capture",
    )
    if any(
        handler is None
        for handler in (
            snapshot,
            navigate,
            click,
            type_,
            evaluate,
            screenshot,
            dom_inspect,
            dom_box_model,
            dom_computed_style,
            dom_clickability,
            dom_highlight,
            dom_mutation_wait,
            storage_indexeddb_list,
            storage_indexeddb_get,
            storage_indexeddb_query,
            storage_cache_list,
            storage_cache_get,
            service_worker_list,
            service_worker_inspect,
            emulation_set,
            emulation_reset,
            permissions_grant,
            permissions_clear,
            geolocation_set,
            network_conditions_set,
            diagnostics_collect,
            performance_metrics,
            trace_start,
            trace_stop,
            trace_export,
            page_lifecycle,
            page_errors,
            context_acquire,
            context_current,
            context_heartbeat,
            context_release,
            context_reconcile,
            tabs_list,
            tabs_select,
            tabs_close,
            network_start_capture,
            network_stop_capture,
            network_list_requests,
            network_get_request,
            network_get_response_body,
            network_get_request_body,
            network_fetch_as_page,
            network_replay_request,
            network_clear_capture,
        )
    ):
        raise RuntimeError("Browser runtime handlers could not be built.")
    return {
        "browser.snapshot": snapshot,
        "browser.navigate": _browser_navigate_handler(navigate),
        "browser.click": _browser_with_kind(click, "click"),
        "browser.type": _browser_with_kind(type_, "type"),
        "browser.evaluate": _browser_evaluate_handler(evaluate),
        "browser.screenshot": _browser_with_kind(screenshot, "screenshot"),
        "browser.dom.inspect": _browser_with_kind(dom_inspect, "dom-inspect"),
        "browser.dom.box_model": _browser_with_kind(dom_box_model, "dom-box-model"),
        "browser.dom.computed_style": _browser_with_kind(
            dom_computed_style,
            "dom-computed-style",
        ),
        "browser.dom.clickability": _browser_with_kind(
            dom_clickability,
            "dom-clickability",
        ),
        "browser.dom.highlight": _browser_with_kind(
            dom_highlight,
            "dom-highlight",
        ),
        "browser.dom.mutation_wait": _browser_with_kind(
            dom_mutation_wait,
            "dom-mutation-wait",
        ),
        "browser.storage.indexeddb.list": _browser_with_kind(
            storage_indexeddb_list,
            "storage-indexeddb-list",
        ),
        "browser.storage.indexeddb.get": _browser_with_kind(
            storage_indexeddb_get,
            "storage-indexeddb-get",
        ),
        "browser.storage.indexeddb.query": _browser_with_kind(
            storage_indexeddb_query,
            "storage-indexeddb-query",
        ),
        "browser.storage.cache.list": _browser_with_kind(
            storage_cache_list,
            "storage-cache-list",
        ),
        "browser.storage.cache.get": _browser_with_kind(
            storage_cache_get,
            "storage-cache-get",
        ),
        "browser.service_worker.list": _browser_with_kind(
            service_worker_list,
            "service-worker-list",
        ),
        "browser.service_worker.inspect": _browser_with_kind(
            service_worker_inspect,
            "service-worker-inspect",
        ),
        "browser.emulation.set": _browser_with_kind(
            emulation_set,
            "emulation-set",
        ),
        "browser.emulation.reset": _browser_with_kind(
            emulation_reset,
            "emulation-reset",
        ),
        "browser.permissions.grant": _browser_with_kind(
            permissions_grant,
            "permissions-grant",
        ),
        "browser.permissions.clear": _browser_with_kind(
            permissions_clear,
            "permissions-clear",
        ),
        "browser.geolocation.set": _browser_with_kind(
            geolocation_set,
            "geolocation-set",
        ),
        "browser.network_conditions.set": _browser_with_kind(
            network_conditions_set,
            "network-conditions-set",
        ),
        "browser.diagnostics.collect": _browser_with_kind(
            diagnostics_collect,
            "diagnostics-collect",
        ),
        "browser.performance.metrics": _browser_with_kind(
            performance_metrics,
            "performance-metrics",
        ),
        "browser.trace.start": _browser_with_kind(trace_start, "trace-start"),
        "browser.trace.stop": _browser_with_kind(trace_stop, "trace-stop"),
        "browser.trace.export": _browser_with_kind(trace_export, "trace-export"),
        "browser.page.lifecycle": _browser_with_kind(page_lifecycle, "page-lifecycle"),
        "browser.page.errors": _browser_with_kind(page_errors, "page-errors"),
        "browser.context.acquire": context_acquire,
        "browser.context.current": context_current,
        "browser.context.heartbeat": context_heartbeat,
        "browser.context.release": context_release,
        "browser.context.reconcile": context_reconcile,
        "browser.tabs.list": _browser_with_kind(tabs_list, "list-tabs"),
        "browser.tabs.select": _browser_with_kind(tabs_select, "focus-tab"),
        "browser.tabs.close": _browser_with_kind(tabs_close, "close-tab"),
        "browser.network.start_capture": network_start_capture,
        "browser.network.stop_capture": network_stop_capture,
        "browser.network.list_requests": network_list_requests,
        "browser.network.get_request": network_get_request,
        "browser.network.get_response_body": network_get_response_body,
        "browser.network.get_request_body": network_get_request_body,
        "browser.network.fetch_as_page": network_fetch_as_page,
        "browser.network.replay_request": network_replay_request,
        "browser.network.clear_capture": network_clear_capture,
    }


def _browser_with_kind(handler, kind: str):
    async def _handler(
        arguments: dict[str, Any],
        execution_context: Any | None = None,
    ):
        payload = dict(arguments)
        payload["kind"] = kind
        return await handler(payload, execution_context)

    return _handler


def _browser_navigate_handler(handler):
    async def _handler(
        arguments: dict[str, Any],
        execution_context: Any | None = None,
    ):
        payload = dict(arguments)
        payload["kind"] = "navigate" if payload.get("target_id") else "open-tab"
        return await handler(payload, execution_context)

    return _handler


def _browser_evaluate_handler(handler):
    async def _handler(
        arguments: dict[str, Any],
        execution_context: Any | None = None,
    ):
        payload = dict(arguments)
        payload["kind"] = "evaluate"
        script = payload.get("script")
        if isinstance(script, str) and script.strip():
            payload.setdefault("expression", script)
        return await handler(payload, execution_context)

    return _handler


_BROWSER_TARGET_ID_SCHEMA = {
    "type": "string",
    "description": "Optional live browser tab identifier.",
}
_BROWSER_TIMEOUT_SCHEMA = {
    "type": "integer",
    "description": "Optional timeout in milliseconds.",
}
_BROWSER_LEASE_ID_SCHEMA = {
    "type": "string",
    "description": "Browser context lease id. Alias of browser allocation id.",
}
_BROWSER_FUNCTION_SPECS: tuple[dict[str, Any], ...] = (
    {
        "function_id": "browser.snapshot",
        "name": "Browser Snapshot",
        "description": "Inspect the current browser tab and return structured page state.",
        "action": "snapshot",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "selector": {
                "type": "string",
                "description": "Optional CSS selector root for the snapshot.",
            },
            "format": {
                "type": "string",
                "description": (
                    "Snapshot format such as interactive, role, aria, text, title, "
                    "or url."
                ),
            },
            "active_overlay": {
                "type": "boolean",
                "description": "Prefer the currently visible popup, picker, or autocomplete overlay.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "examples": (
            {"format": "interactive", "active_overlay": True},
            {"target_id": "tab-123", "format": "text"},
        ),
        "capabilities": (
            "browser.profile_read",
            "browser.page_action",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.navigate",
        "name": "Browser Navigate",
        "description": "Navigate a browser tab to a URL.",
        "action": "navigate",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "url": {
                "type": "string",
                "description": "URL to navigate to.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "required": ("url",),
        "examples": (
            {"url": "https://example.com"},
            {"profile_pool": "collector-pool", "url": "https://example.com/search"},
        ),
        "mutates_state": True,
    },
    {
        "function_id": "browser.click",
        "name": "Browser Click",
        "description": "Click an element in the current browser tab.",
        "action": "click",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "selector": {
                "type": "string",
                "description": "CSS selector for the element to click.",
            },
            "ref": {
                "type": "string",
                "description": "Snapshot ref for the element to click.",
            },
            "x": {"type": "number", "description": "Viewport x coordinate."},
            "y": {"type": "number", "description": "Viewport y coordinate."},
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "examples": (
            {"ref": "r12"},
            {"selector": "#submit", "target_id": "tab-123"},
        ),
        "mutates_state": True,
    },
    {
        "function_id": "browser.type",
        "name": "Browser Type",
        "description": "Type text into an element in the current browser tab.",
        "action": "type",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "selector": {
                "type": "string",
                "description": "CSS selector for the element to receive text.",
            },
            "ref": {
                "type": "string",
                "description": "Snapshot ref for the element to receive text.",
            },
            "text": {"type": "string", "description": "Text to type."},
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "required": ("text",),
        "examples": (
            {"ref": "r3", "text": "Kunming"},
            {"selector": "input[name=q]", "text": "flight prices"},
        ),
        "mutates_state": True,
    },
    {
        "function_id": "browser.evaluate",
        "name": "Browser Evaluate",
        "description": "Evaluate JavaScript in the current browser tab.",
        "action": "evaluate",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "script": {"type": "string", "description": "JavaScript source to evaluate."},
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "required": ("script",),
        "examples": (
            {"script": "document.title"},
        ),
        "mutates_state": True,
    },
    {
        "function_id": "browser.screenshot",
        "name": "Browser Screenshot",
        "description": "Capture a screenshot from the current browser tab.",
        "action": "screenshot",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "full_page": {
                "type": "boolean",
                "description": "Capture the full page when supported.",
            },
            "selector": {
                "type": "string",
                "description": "Optional CSS selector to screenshot.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "examples": (
            {"full_page": True},
            {"selector": ".result-list"},
        ),
        "capabilities": (
            "browser.page_action",
            "browser.artifact_write",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.dom.inspect",
        "name": "Browser DOM Inspect",
        "description": "Inspect a page element by ref or selector and return DOM, layout, style, and clickability facts.",
        "action": "dom.inspect",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "selector": {
                "type": "string",
                "description": "CSS selector for the element to inspect.",
            },
            "ref": {
                "type": "string",
                "description": "Snapshot ref for the element to inspect.",
            },
            "properties": {
                "type": "array",
                "description": "Optional computed style properties to include.",
                "items": {"type": "string"},
            },
            "include_styles": {
                "type": "boolean",
                "description": "Include computed style fields.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "examples": (
            {"ref": "r12"},
            {"selector": ".calendar-panel", "properties": ["display", "z-index"]},
        ),
        "capabilities": (
            "browser.profile_read",
            "browser.page_action",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.dom.box_model",
        "name": "Browser DOM Box Model",
        "description": "Inspect an element's viewport box, click point, and visibility state.",
        "action": "dom.box_model",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "selector": {
                "type": "string",
                "description": "CSS selector for the element.",
            },
            "ref": {
                "type": "string",
                "description": "Snapshot ref for the element.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.page_action",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.dom.computed_style",
        "name": "Browser DOM Computed Style",
        "description": "Read selected computed style properties for an element.",
        "action": "dom.computed_style",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "selector": {
                "type": "string",
                "description": "CSS selector for the element.",
            },
            "ref": {
                "type": "string",
                "description": "Snapshot ref for the element.",
            },
            "properties": {
                "type": "array",
                "description": "Computed style properties to include.",
                "items": {"type": "string"},
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.page_action",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.dom.clickability",
        "name": "Browser DOM Clickability",
        "description": "Diagnose whether an element can be clicked and what blocks it.",
        "action": "dom.clickability",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "selector": {
                "type": "string",
                "description": "CSS selector for the element.",
            },
            "ref": {
                "type": "string",
                "description": "Snapshot ref for the element.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.page_action",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.dom.highlight",
        "name": "Browser DOM Highlight",
        "description": "Temporarily highlight a page element so the user and agent can verify the target.",
        "action": "dom.highlight",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "selector": {
                "type": "string",
                "description": "CSS selector for the element.",
            },
            "ref": {
                "type": "string",
                "description": "Snapshot ref for the element.",
            },
            "duration_ms": {
                "type": "integer",
                "description": "How long to keep the highlight visible.",
            },
            "color": {
                "type": "string",
                "description": "CSS color for the highlight outline.",
            },
            "label": {
                "type": "string",
                "description": "Optional short label displayed near the highlight.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.page_action",
            "browser.runtime_readiness",
        ),
        "mutates_state": True,
    },
    {
        "function_id": "browser.dom.mutation_wait",
        "name": "Browser DOM Mutation Wait",
        "description": "Wait for DOM mutations below an element, useful for autocomplete, picker, and async panel updates.",
        "action": "dom.mutation_wait",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "selector": {
                "type": "string",
                "description": "CSS selector for the root element to observe.",
            },
            "ref": {
                "type": "string",
                "description": "Snapshot ref for the root element to observe.",
            },
            "quiet_ms": {
                "type": "integer",
                "description": "Quiet period after the last mutation before returning.",
            },
            "subtree": {
                "type": "boolean",
                "description": "Observe descendant mutations.",
            },
            "child_list": {
                "type": "boolean",
                "description": "Observe child list mutations.",
            },
            "attributes": {
                "type": "boolean",
                "description": "Observe attribute mutations.",
            },
            "character_data": {
                "type": "boolean",
                "description": "Observe text node mutations.",
            },
            "attribute_filter": {
                "type": "array",
                "description": "Optional attribute names to observe.",
                "items": {"type": "string"},
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.page_action",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.storage.indexeddb.list",
        "name": "Browser IndexedDB List",
        "description": "List IndexedDB databases and object stores for the current page origin.",
        "action": "storage.indexeddb.list",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "origin": {"type": "string", "description": "Optional security origin override."},
            "include_metadata": {
                "type": "boolean",
                "description": "Include database and object store metadata.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.page_action",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.storage.indexeddb.query",
        "name": "Browser IndexedDB Query",
        "description": "Read a bounded page of entries from an IndexedDB object store.",
        "action": "storage.indexeddb.query",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "origin": {"type": "string", "description": "Optional security origin override."},
            "database_name": {"type": "string", "description": "IndexedDB database name."},
            "object_store_name": {"type": "string", "description": "Object store name."},
            "index_name": {"type": "string", "description": "Optional index name."},
            "skip": {"type": "integer", "description": "Number of entries to skip."},
            "limit": {"type": "integer", "description": "Maximum entries to return."},
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "required": ("database_name", "object_store_name"),
        "capabilities": (
            "browser.profile_read",
            "browser.page_action",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.storage.indexeddb.get",
        "name": "Browser IndexedDB Get",
        "description": "Read the first IndexedDB entry matching a key from a bounded object store page.",
        "action": "storage.indexeddb.get",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "origin": {"type": "string", "description": "Optional security origin override."},
            "database_name": {"type": "string", "description": "IndexedDB database name."},
            "object_store_name": {"type": "string", "description": "Object store name."},
            "index_name": {"type": "string", "description": "Optional index name."},
            "key": {"description": "Key or primary key to match."},
            "limit": {"type": "integer", "description": "Maximum entries to scan."},
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "required": ("database_name", "object_store_name", "key"),
        "capabilities": (
            "browser.profile_read",
            "browser.page_action",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.storage.cache.list",
        "name": "Browser CacheStorage List",
        "description": "List CacheStorage caches for the current page origin.",
        "action": "storage.cache.list",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "origin": {"type": "string", "description": "Optional security origin override."},
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.page_action",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.storage.cache.get",
        "name": "Browser CacheStorage Get",
        "description": "Read bounded CacheStorage entries and an optional cached response body.",
        "action": "storage.cache.get",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "origin": {"type": "string", "description": "Optional security origin override."},
            "cache_id": {"type": "string", "description": "CacheStorage cache id."},
            "cache_name": {"type": "string", "description": "Cache name when cache id is unknown."},
            "request_url": {"type": "string", "description": "Optional cached request URL."},
            "skip": {"type": "integer", "description": "Number of entries to skip."},
            "limit": {"type": "integer", "description": "Maximum entries to return."},
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.page_action",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.service_worker.list",
        "name": "Browser Service Worker List",
        "description": "List service worker registrations visible to the current page.",
        "action": "service_worker.list",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "scope_url": {"type": "string", "description": "Optional scope URL filter."},
            "script_url": {"type": "string", "description": "Optional script URL filter."},
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.page_action",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.service_worker.inspect",
        "name": "Browser Service Worker Inspect",
        "description": "Inspect one service worker registration visible to the current page.",
        "action": "service_worker.inspect",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "scope_url": {"type": "string", "description": "Optional scope URL filter."},
            "script_url": {"type": "string", "description": "Optional script URL filter."},
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.page_action",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.emulation.set",
        "name": "Browser Emulation Set",
        "description": "Set target-scoped viewport, user-agent, timezone, or locale emulation.",
        "action": "emulation.set",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "width": {"type": "integer", "description": "Viewport width."},
            "height": {"type": "integer", "description": "Viewport height."},
            "device_scale_factor": {
                "type": "number",
                "description": "Device scale factor.",
            },
            "is_mobile": {"type": "boolean", "description": "Use mobile metrics."},
            "has_touch": {"type": "boolean", "description": "Expose touch support."},
            "user_agent": {"type": "string", "description": "User-Agent override."},
            "timezone_id": {"type": "string", "description": "IANA timezone id."},
            "locale": {"type": "string", "description": "Locale override."},
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.environment_control",
            "browser.runtime_readiness",
        ),
        "mutates_state": True,
    },
    {
        "function_id": "browser.emulation.reset",
        "name": "Browser Emulation Reset",
        "description": "Reset target-scoped emulation controls such as viewport, timezone, locale, geolocation, network conditions, permissions, and user-agent where supported.",
        "action": "emulation.reset",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "device_metrics": {
                "type": "boolean",
                "description": "Reset viewport/device metrics.",
            },
            "geolocation": {"type": "boolean", "description": "Reset geolocation."},
            "network_conditions": {
                "type": "boolean",
                "description": "Reset network throttling.",
            },
            "permissions": {"type": "boolean", "description": "Clear permissions."},
            "timezone": {"type": "boolean", "description": "Reset timezone."},
            "locale": {"type": "boolean", "description": "Reset locale."},
            "user_agent": {
                "type": "boolean",
                "description": "Reset user-agent when browser default is available.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.environment_control",
            "browser.runtime_readiness",
        ),
        "mutates_state": True,
    },
    {
        "function_id": "browser.permissions.grant",
        "name": "Browser Permissions Grant",
        "description": "Grant browser permissions to the active browser context.",
        "action": "permissions.grant",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "permissions": {
                "type": "array",
                "description": "Permission names such as geolocation or notifications.",
                "items": {"type": "string"},
            },
            "origin": {"type": "string", "description": "Optional origin scope."},
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "required": ("permissions",),
        "capabilities": (
            "browser.profile_read",
            "browser.environment_control",
            "browser.runtime_readiness",
        ),
        "mutates_state": True,
    },
    {
        "function_id": "browser.permissions.clear",
        "name": "Browser Permissions Clear",
        "description": "Clear browser permission grants for the active browser context.",
        "action": "permissions.clear",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "origin": {"type": "string", "description": "Optional origin hint."},
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.environment_control",
            "browser.runtime_readiness",
        ),
        "mutates_state": True,
    },
    {
        "function_id": "browser.geolocation.set",
        "name": "Browser Geolocation Set",
        "description": "Set target-scoped browser geolocation coordinates.",
        "action": "geolocation.set",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "latitude": {"type": "number", "description": "Latitude."},
            "longitude": {"type": "number", "description": "Longitude."},
            "accuracy": {
                "type": "number",
                "description": "Accuracy in meters.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "required": ("latitude", "longitude"),
        "capabilities": (
            "browser.profile_read",
            "browser.environment_control",
            "browser.runtime_readiness",
        ),
        "mutates_state": True,
    },
    {
        "function_id": "browser.network_conditions.set",
        "name": "Browser Network Conditions Set",
        "description": "Set target-scoped network throttling or offline mode.",
        "action": "network_conditions.set",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "offline": {"type": "boolean", "description": "Emulate offline mode."},
            "latency_ms": {
                "type": "number",
                "description": "Artificial latency in milliseconds.",
            },
            "download_kbps": {
                "type": "number",
                "description": "Download throughput in kilobits per second.",
            },
            "upload_kbps": {
                "type": "number",
                "description": "Upload throughput in kilobits per second.",
            },
            "connection_type": {
                "type": "string",
                "description": "Optional CDP connection type.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.environment_control",
            "browser.runtime_readiness",
        ),
        "mutates_state": True,
    },
    {
        "function_id": "browser.diagnostics.collect",
        "name": "Browser Diagnostics Collect",
        "description": "Collect page lifecycle, console error, page JS exception, and performance diagnostic facts.",
        "action": "diagnostics.collect",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "include_entries": {
                "type": "boolean",
                "description": "Include performance entry details.",
            },
            "console_limit": {
                "type": "integer",
                "description": "Maximum console messages to inspect.",
            },
            "page_error_limit": {
                "type": "integer",
                "description": "Maximum page JavaScript exceptions to inspect.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "examples": (
            {"include_entries": True, "console_limit": 100, "page_error_limit": 100},
        ),
        "capabilities": (
            "browser.profile_read",
            "browser.diagnostics_read",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.performance.metrics",
        "name": "Browser Performance Metrics",
        "description": "Read CDP performance metrics and optional browser performance entries.",
        "action": "performance.metrics",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "include_entries": {
                "type": "boolean",
                "description": "Include performance entry details.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.diagnostics_read",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.trace.start",
        "name": "Browser Trace Start",
        "description": "Start Playwright browser tracing for the active browser context.",
        "action": "trace.start",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "trace_id": {"type": "string", "description": "Optional trace id."},
            "title": {"type": "string", "description": "Optional trace title."},
            "screenshots": {
                "type": "boolean",
                "description": "Capture screenshots in the trace.",
            },
            "snapshots": {
                "type": "boolean",
                "description": "Capture DOM snapshots in the trace.",
            },
            "sources": {
                "type": "boolean",
                "description": "Capture source files in the trace.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.diagnostics_read",
            "browser.runtime_readiness",
        ),
        "mutates_state": True,
    },
    {
        "function_id": "browser.trace.stop",
        "name": "Browser Trace Stop",
        "description": "Stop Playwright browser tracing and return a trace zip artifact.",
        "action": "trace.stop",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "trace_id": {"type": "string", "description": "Optional trace id."},
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.diagnostics_read",
            "browser.artifact_write",
            "browser.runtime_readiness",
        ),
        "mutates_state": True,
    },
    {
        "function_id": "browser.trace.export",
        "name": "Browser Trace Export",
        "description": "Export the most recently stopped browser trace artifact.",
        "action": "trace.export",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "trace_id": {"type": "string", "description": "Optional trace id."},
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.diagnostics_read",
            "browser.artifact_write",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.page.lifecycle",
        "name": "Browser Page Lifecycle",
        "description": "Read page lifecycle and navigation history diagnostics.",
        "action": "page.lifecycle",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.diagnostics_read",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.page.errors",
        "name": "Browser Page Errors",
        "description": "Read buffered page console errors, assertion failures, and JavaScript exceptions.",
        "action": "page.errors",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "limit": {
                "type": "integer",
                "description": "Maximum errors to return.",
            },
            "console_limit": {
                "type": "integer",
                "description": "Maximum console messages to inspect.",
            },
            "page_error_limit": {
                "type": "integer",
                "description": "Maximum page JavaScript exceptions to inspect.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "examples": (
            {"limit": 20, "console_limit": 100, "page_error_limit": 100},
        ),
        "capabilities": (
            "browser.profile_read",
            "browser.diagnostics_read",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.context.acquire",
        "name": "Browser Context Acquire",
        "description": "Acquire a browser context lease for a profile or profile pool.",
        "action": "context.acquire",
        "properties": {
            "lease_id": _BROWSER_LEASE_ID_SCHEMA,
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "url": {
                "type": "string",
                "description": "Optional URL to open inside the acquired context.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "examples": (
            {"profile_pool": "collector-pool", "url": "https://example.com"},
            {"profile": "crxzipple", "lease_id": "flight-search"},
        ),
        "capabilities": (
            "browser.profile_read",
            "browser.context_control",
            "browser.runtime_readiness",
        ),
        "mutates_state": True,
    },
    {
        "function_id": "browser.context.current",
        "name": "Browser Context Current",
        "description": "Read the active browser context lease from input or runtime context.",
        "action": "context.current",
        "properties": {
            "lease_id": _BROWSER_LEASE_ID_SCHEMA,
        },
        "examples": (
            {"lease_id": "flight-search"},
        ),
        "capabilities": (
            "browser.profile_read",
            "browser.context_control",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.context.heartbeat",
        "name": "Browser Context Heartbeat",
        "description": "Extend an active browser context lease.",
        "action": "context.heartbeat",
        "properties": {
            "lease_id": _BROWSER_LEASE_ID_SCHEMA,
            "ttl_seconds": {
                "type": "integer",
                "description": "Optional lease TTL extension in seconds.",
            },
        },
        "examples": (
            {"target_id": "tab-123", "capture_id": "search-api"},
        ),
        "capabilities": (
            "browser.profile_read",
            "browser.context_control",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.context.release",
        "name": "Browser Context Release",
        "description": "Release a browser context lease and optionally close owned targets.",
        "action": "context.release",
        "properties": {
            "lease_id": _BROWSER_LEASE_ID_SCHEMA,
            "reason": {"type": "string", "description": "Release reason."},
            "close_owned_targets": {
                "type": "boolean",
                "description": "Close browser targets owned by this lease.",
            },
        },
        "examples": (
            {"capture_id": "search-api", "keyword": "flight", "limit": 20},
        ),
        "capabilities": (
            "browser.profile_read",
            "browser.context_control",
            "browser.runtime_readiness",
        ),
        "mutates_state": True,
    },
    {
        "function_id": "browser.context.reconcile",
        "name": "Browser Context Reconcile",
        "description": "Reconcile browser context leases against live browser targets.",
        "action": "context.reconcile",
        "properties": {
            "lease_id": _BROWSER_LEASE_ID_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.context_control",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.network.start_capture",
        "name": "Browser Network Start Capture",
        "description": "Start a scoped browser network capture for the current tab.",
        "action": "network.start_capture",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "capture_id": {
                "type": "string",
                "description": "Optional caller-provided capture identifier.",
            },
            "max_requests": {
                "type": "integer",
                "description": "Maximum requests to retain in the capture ring buffer.",
            },
            "max_body_bytes": {
                "type": "integer",
                "description": "Maximum stored bytes per captured body.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.network_read",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.network.stop_capture",
        "name": "Browser Network Stop Capture",
        "description": "Stop a browser network capture.",
        "action": "network.stop_capture",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "capture_id": {
                "type": "string",
                "description": "Network capture identifier.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "required": ("capture_id",),
        "capabilities": (
            "browser.profile_read",
            "browser.network_read",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.network.list_requests",
        "name": "Browser Network List Requests",
        "description": "List requests observed by a browser network capture.",
        "action": "network.list_requests",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "capture_id": {
                "type": "string",
                "description": "Network capture identifier. Defaults to active capture.",
            },
            "resource_type": {"type": "string", "description": "Resource type filter."},
            "domain": {"type": "string", "description": "Domain substring filter."},
            "path": {"type": "string", "description": "Path substring filter."},
            "method": {"type": "string", "description": "HTTP method filter."},
            "status": {"type": "integer", "description": "HTTP status filter."},
            "mime_type": {"type": "string", "description": "MIME type filter."},
            "keyword": {"type": "string", "description": "Search text filter."},
            "limit": {"type": "integer", "description": "Maximum requests to return."},
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "capabilities": (
            "browser.profile_read",
            "browser.network_read",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.network.get_request",
        "name": "Browser Network Get Request",
        "description": "Read a single captured browser network request.",
        "action": "network.get_request",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "capture_id": {
                "type": "string",
                "description": "Network capture identifier.",
            },
            "request_id": {
                "type": "string",
                "description": "Captured request identifier.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "required": ("capture_id", "request_id"),
        "capabilities": (
            "browser.profile_read",
            "browser.network_read",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.network.get_response_body",
        "name": "Browser Network Get Response Body",
        "description": "Read a stored response body from a browser network capture.",
        "action": "network.get_response_body",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "capture_id": {
                "type": "string",
                "description": "Network capture identifier.",
            },
            "request_id": {
                "type": "string",
                "description": "Captured request identifier.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "required": ("capture_id", "request_id"),
        "capabilities": (
            "browser.profile_read",
            "browser.network_sensitive_read",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.network.get_request_body",
        "name": "Browser Network Get Request Body",
        "description": "Read a stored request body from a browser network capture.",
        "action": "network.get_request_body",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "capture_id": {
                "type": "string",
                "description": "Network capture identifier.",
            },
            "request_id": {
                "type": "string",
                "description": "Captured request identifier.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "required": ("capture_id", "request_id"),
        "capabilities": (
            "browser.profile_read",
            "browser.network_sensitive_read",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.network.fetch_as_page",
        "name": "Browser Network Fetch As Page",
        "description": "Fetch an http(s) URL from the current page context with browser credentials.",
        "action": "network.fetch_as_page",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "url": {
                "type": "string",
                "description": "Absolute or page-relative URL to fetch.",
            },
            "method": {
                "type": "string",
                "description": "HTTP method. Mutating methods require allow_mutating.",
            },
            "headers": {
                "type": "object",
                "description": "Optional non-sensitive request headers.",
                "additionalProperties": {"type": "string"},
            },
            "body": {"type": "string", "description": "Optional request body."},
            "json": {"description": "Optional JSON request body."},
            "allow_cross_origin": {
                "type": "boolean",
                "description": "Allow a fetch to a different origin from the current page.",
            },
            "allow_mutating": {
                "type": "boolean",
                "description": "Allow POST, PUT, PATCH, or DELETE.",
            },
            "max_body_bytes": {
                "type": "integer",
                "description": "Maximum response body bytes returned in the result.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "required": ("url",),
        "examples": (
            {"url": "/api/search", "max_body_bytes": 8192},
        ),
        "capabilities": (
            "browser.profile_read",
            "browser.network_sensitive_read",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.network.replay_request",
        "name": "Browser Network Replay Request",
        "description": "Replay a captured request from the current page context.",
        "action": "network.replay_request",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "capture_id": {
                "type": "string",
                "description": "Network capture identifier.",
            },
            "request_id": {
                "type": "string",
                "description": "Captured request identifier.",
            },
            "headers": {
                "type": "object",
                "description": "Optional header overrides.",
                "additionalProperties": {"type": "string"},
            },
            "body": {"type": "string", "description": "Optional body override."},
            "json": {"description": "Optional JSON body override."},
            "allow_cross_origin": {
                "type": "boolean",
                "description": "Allow replay to a different origin from the current page.",
            },
            "allow_mutating": {
                "type": "boolean",
                "description": "Allow replay of POST, PUT, PATCH, or DELETE.",
            },
            "max_body_bytes": {
                "type": "integer",
                "description": "Maximum response body bytes returned in the result.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "required": ("capture_id", "request_id"),
        "capabilities": (
            "browser.profile_read",
            "browser.network_sensitive_read",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.network.clear_capture",
        "name": "Browser Network Clear Capture",
        "description": "Clear a browser network capture and its stored bodies.",
        "action": "network.clear_capture",
        "properties": {
            "target_id": _BROWSER_TARGET_ID_SCHEMA,
            "capture_id": {
                "type": "string",
                "description": "Network capture identifier.",
            },
            "timeout_ms": _BROWSER_TIMEOUT_SCHEMA,
        },
        "required": ("capture_id",),
        "capabilities": (
            "browser.profile_read",
            "browser.network_read",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.tabs.list",
        "name": "Browser Tabs List",
        "description": "List tabs for the resolved browser profile.",
        "action": "tabs.list",
        "properties": {},
        "capabilities": (
            "browser.profile_read",
            "browser.runtime_readiness",
        ),
    },
    {
        "function_id": "browser.tabs.select",
        "name": "Browser Tabs Select",
        "description": "Select the active tab for the resolved browser profile.",
        "action": "tabs.select",
        "properties": {
            "target_id": {
                "type": "string",
                "description": "Live browser tab identifier to select.",
            },
        },
        "required": ("target_id",),
        "mutates_state": True,
    },
    {
        "function_id": "browser.tabs.close",
        "name": "Browser Tabs Close",
        "description": "Close a tab for the resolved browser profile.",
        "action": "tabs.close",
        "properties": {
            "target_id": {
                "type": "string",
                "description": "Live browser tab identifier to close.",
            },
        },
        "required": ("target_id",),
        "mutates_state": True,
    },
)


def _activate_configured_tool_provider_runtimes(ctx) -> None:
    ctx.require(AppKey.TOOL_CONFIGURED_RUNTIME_ACTIVATOR).activate_all()


def _active_local_function_refs_by_namespace(
    ctx,
) -> Mapping[str, tuple[str, ...]]:
    prefix = "bundled.local_package."
    refs_by_namespace: dict[str, list[str]] = {}
    for function in ctx.require(AppKey.TOOL_SOURCE_QUERY_SERVICE).list_functions(
        status=ToolFunctionStatus.ACTIVE,
    ):
        if not function.source_id.startswith(prefix):
            continue
        namespace = function.source_id.removeprefix(prefix)
        refs_by_namespace.setdefault(namespace, []).append(function.handler_ref)
    return {
        namespace: tuple(dict.fromkeys(refs))
        for namespace, refs in refs_by_namespace.items()
    }


def _tool_cleanup_callbacks(ctx) -> ToolCleanupCallbacks:
    for callback in ctx.require(AppKey.TOOL_CLEANUP_CALLBACKS):
        if isinstance(callback, ToolCleanupCallbacks):
            return callback
    raise RuntimeError("Tool cleanup callback registry is not configured.")


def _activate_tool_packages(ctx) -> None:
    dependency_bindings = _tool_activation_bindings_from_context(
        ctx,
        ctx.require(AppKey.TOOL_CAPABILITY_BINDINGS),
    )
    activate_tool_packages(
        settings=ctx.require(AppKey.CORE_SETTINGS),
        runtime_bootstrap_config=ctx.require(AppKey.RUNTIME_BOOTSTRAP_CONFIG),
        package_plans=ctx.require(AppKey.TOOL_PACKAGE_PLANS),
        local_runtime_registry=ctx.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY),
        remote_tool_registry=ctx.require(AppKey.TOOL_REMOTE_RUNTIME_REGISTRY),
        sandbox_tool_registry=ctx.require(AppKey.TOOL_SANDBOX_RUNTIME_REGISTRY),
        tool_discovery_registry=ctx.require(AppKey.TOOL_DISCOVERY_REGISTRY),
        dependency_bindings=dependency_bindings,
        local_function_refs_by_namespace=(
            _active_local_function_refs_by_namespace(ctx)
        ),
        capability_ids=ctx.require(AppKey.TOOL_CAPABILITY_CATALOG).capability_ids,
    )


def activate_tool_packages(
    *,
    settings: Any,
    runtime_bootstrap_config: Any,
    package_plans: tuple[Any, ...],
    local_runtime_registry: Any,
    remote_tool_registry: Any,
    sandbox_tool_registry: Any,
    tool_discovery_registry: Any,
    dependency_bindings: Mapping[str, ToolDependencyBinding],
    local_function_refs_by_namespace: Mapping[str, tuple[str, ...]] | None = None,
    capability_ids: tuple[str, ...] | None = None,
    include_openapi: bool | None = None,
) -> None:
    resolved_bindings = dict(dependency_bindings)
    _ensure_tool_activation_binding(
        resolved_bindings,
        ToolDependencyBinding(
            "settings",
            settings,
            capability_ids=("runtime_settings.read",),
        ),
    )
    apply_tool_package_plans(
        ToolPackageApplyContext(
            local_runtime_registry=local_runtime_registry,
            remote_tool_registry=remote_tool_registry,
            sandbox_tool_registry=sandbox_tool_registry,
            tool_discovery_registry=tool_discovery_registry,
            local_function_refs_by_namespace=local_function_refs_by_namespace,
            settings=settings,
            dependency_bindings=resolved_bindings,
            config={
                "tool_remote_default_max_concurrency": (
                    runtime_bootstrap_config.tool_remote_default_max_concurrency
                ),
            },
            capability_ids=(
                capability_ids or DEFAULT_TOOL_CAPABILITY_CATALOG.capability_ids
            ),
        ),
        package_plans,
        include_openapi=(
            _activate_bundled_openapi_packages()
            if include_openapi is None
            else include_openapi
        ),
    )


def _ensure_tool_activation_binding(
    bindings: dict[str, ToolDependencyBinding],
    binding: ToolDependencyBinding,
) -> None:
    bindings.setdefault(binding.dependency_id, binding)


def _tool_activation_bindings_from_context(
    ctx,
    base_bindings: Mapping[str, ToolDependencyBinding],
) -> Mapping[str, ToolDependencyBinding]:
    bindings = dict(base_bindings)
    _ensure_tool_activation_binding(
        bindings,
        ToolDependencyBinding(
            "credential_provider",
            ctx.require(AppKey.ACCESS_SERVICE),
            capability_ids=("credential.read", "access.readiness"),
        ),
    )
    if ctx.has(AppKey.ARTIFACT_SERVICE):
        artifact_service = ctx.require(AppKey.ARTIFACT_SERVICE)
        _ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "artifact_service",
                artifact_service,
                capability_ids=(
                    "artifact.read",
                    "artifact.write",
                    "browser.artifact_write",
                ),
            ),
        )
    if ctx.has(AppKey.BROWSER_INFRASTRUCTURE):
        browser = ctx.require(AppKey.BROWSER_INFRASTRUCTURE)
        _ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "browser_system_config",
                browser.system_config,
                capability_ids=("browser.profile_read", "runtime_settings.read"),
            ),
        )
        _ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "browser_system_config_store",
                browser.system_config_store,
                capability_ids=("browser.profile_read", "runtime_settings.read"),
            ),
        )
        _ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "browser_tool_application",
                browser.tool_application_service,
                capability_ids=("browser.control", "browser.page_action"),
            ),
        )
        _ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "browser_profile_resolver",
                browser.profile_resolver,
                capability_ids=("browser.profile_read", "browser.runtime_readiness"),
            ),
        )
        _ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "browser_capabilities_resolver",
                browser.capabilities_resolver,
                capability_ids=("browser.profile_read", "browser.runtime_readiness"),
            ),
        )
        _ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "browser_runtime_state_store",
                browser.runtime_state_store,
                capability_ids=("browser.runtime_readiness",),
            ),
        )
        _ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "browser_profile_probe_service",
                browser.profile_probe_service,
                capability_ids=("browser.runtime_readiness",),
            ),
        )
        _ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "browser_profile_allocator_service",
                browser.profile_allocator_service,
                capability_ids=("browser.profile_read", "browser.runtime_readiness"),
            ),
        )
    if ctx.has(AppKey.MOBILE_INFRASTRUCTURE):
        mobile = ctx.require(AppKey.MOBILE_INFRASTRUCTURE)
        _ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "mobile_system_config",
                mobile.system_config,
                capability_ids=("mobile.device_read",),
            ),
        )
        _ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "mobile_system_config_store",
                mobile.system_config_store,
                capability_ids=("mobile.device_read",),
            ),
        )
        _ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "mobile_facade",
                mobile.facade,
                capability_ids=("mobile.device_read", "mobile.action", "mobile.screenshot"),
            ),
        )
        _ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "mobile_result_serializer",
                mobile.result_serializer,
                capability_ids=("mobile.device_read", "mobile.action", "mobile.screenshot"),
            ),
        )
    if ctx.has(AppKey.MEMORY_RUNTIME_SERVICE):
        _ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "memory_runtime_service",
                ctx.require(AppKey.MEMORY_RUNTIME_SERVICE),
                capability_ids=(
                    "memory.context_lookup",
                    "memory.search",
                    "memory.read",
                    "memory.write",
                    "memory.flush_marker",
                ),
            ),
        )
    if ctx.has(AppKey.PROCESS_SERVICE):
        _ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "process_service",
                ctx.require(AppKey.PROCESS_SERVICE),
                capability_ids=("process.spawn", "process.manage"),
            ),
        )
    if ctx.has(AppKey.SESSION_SERVICE):
        _ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "session_service",
                ctx.require(AppKey.SESSION_SERVICE),
                capability_ids=("session.read", "session.write", "session.tree_read"),
            ),
        )
    if ctx.has(AppKey.SESSION_WORKSPACE_LOOKUP):
        _ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "session_workspace_lookup",
                ctx.require(AppKey.SESSION_WORKSPACE_LOOKUP),
                capability_ids=("workspace.lookup", "session.read"),
            ),
        )
    if ctx.has(AppKey.SESSION_RUNTIME_CONTROL):
        _ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "session_runtime_control",
                ctx.require(AppKey.SESSION_RUNTIME_CONTROL),
                capability_ids=(
                    "session.read",
                    "session.write",
                    "session.tree_read",
                    "session.route_enqueue",
                    "session.tree_cancel",
                    "run_control.yield",
                ),
            ),
        )
    if ctx.has(AppKey.SKILL_MANAGER):
        skill_manager = ctx.require(AppKey.SKILL_MANAGER)
        _ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "skill_manager",
                skill_manager,
                capability_ids=("skill.read",),
            ),
        )
        _ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "skill_authoring_service",
                skill_manager,
                capability_ids=("skill.authoring",),
            ),
        )
    return bindings


def _activate_bundled_openapi_packages() -> bool:
    return os.getenv("APP_TOOL_OPENAPI_PROVIDER_PATHS") is None


__all__ = [
    "TOOL_EXECUTION_SERVICE_TARGETS",
    "TOOL_ORCHESTRATION_QUEUE_SERVICE_TARGETS",
    "TOOL_QUEUE_SERVICE_TARGETS",
    "ToolExecutionServicesAssembly",
    "activate_tool_packages",
    "browser_function_catalog_candidates",
    "browser_source_records_from_system_config",
    "build_tool_execution_capability_bindings",
    "build_tool_execution_services",
    "tool_activation_tasks",
    "tool_browser_activation_tasks",
    "tool_core_factories",
    "tool_execution_factories",
    "tool_factories",
    "tool_queue_factories",
]
