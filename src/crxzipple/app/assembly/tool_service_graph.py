"""Tool service graph assembly helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from crxzipple.app.keys import AppKey
from crxzipple.modules.tool.application.service_graph import build_tool_service_graph
from crxzipple.modules.tool.application.service_support import ToolServiceDependencies
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

    def list_tool_runs(self, *, tool_id: str | None = None, limit: int | None = None):
        return self.service.list_tool_runs(tool_id=tool_id, limit=limit)

    def list_tool_runs_for_orchestration_runs(self, run_ids: tuple[str, ...]):
        return self.service.list_tool_runs_for_orchestration_runs(run_ids)

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


def build_tool_queue_services(
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


def build_tool_execution_services_from_context(ctx) -> dict[str, Any]:
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
    "ToolExecutionServicesAssembly",
    "ToolOrchestrationPortAdapter",
    "ToolQueryServiceAdapter",
    "ToolRunControlAdapter",
    "ToolWorkerRegistrationAdapter",
    "build_tool_execution_services",
    "build_tool_execution_services_from_context",
    "build_tool_queue_services",
]
