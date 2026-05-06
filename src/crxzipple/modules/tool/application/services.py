from __future__ import annotations

from crxzipple.modules.tool.application.catalog_service import ToolCatalogService
from crxzipple.modules.tool.application.concurrency import ToolRunConcurrencyPolicy
from crxzipple.modules.tool.application.service_support import (
    ExecuteToolInput,
    RegisterToolInput,
    RegisterToolParameterInput,
    SetToolAvailabilityInput,
    ToolRuntimeGateway,
    ToolUnitOfWork,
)
from crxzipple.modules.tool.application.submission_service import ToolSubmissionService
from crxzipple.modules.tool.application.worker_service import ToolWorkerService
from crxzipple.modules.tool.domain.entities import (
    Tool,
    ToolRun,
    ToolRunAssignment,
    ToolWorkerRegistration,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.value_objects import ToolRunStatus


class ToolApplicationService:
    def __init__(
        self,
        *,
        catalog_service: ToolCatalogService,
        worker_service: ToolWorkerService,
        submission_service: ToolSubmissionService,
    ) -> None:
        self.catalog_service = catalog_service
        self.worker_service = worker_service
        self.submission_service = submission_service

    @property
    def dispatch_port(self):
        return self.submission_service.dispatch_port

    @property
    def discovery_gateway(self):
        return self.catalog_service.discovery_gateway

    @discovery_gateway.setter
    def discovery_gateway(self, value) -> None:
        self.catalog_service.deps.discovery_gateway = value

    @property
    def worker_lease_seconds(self) -> int:
        return self.submission_service.worker_lease_seconds

    @worker_lease_seconds.setter
    def worker_lease_seconds(self, value: int) -> None:
        self.submission_service.deps.worker_lease_seconds = value

    @property
    def worker_heartbeat_seconds(self) -> float:
        return self.submission_service.worker_heartbeat_seconds

    @worker_heartbeat_seconds.setter
    def worker_heartbeat_seconds(self, value: float) -> None:
        self.submission_service.deps.worker_heartbeat_seconds = value

    @property
    def details_max_chars(self) -> int:
        return self.submission_service.details_max_chars

    @details_max_chars.setter
    def details_max_chars(self, value: int) -> None:
        self.submission_service.deps.details_max_chars = max(int(value), 1)

    @property
    def concurrency_policy(self) -> ToolRunConcurrencyPolicy:
        return self.worker_service.concurrency_policy

    def register(self, data: RegisterToolInput) -> Tool:
        return self.catalog_service.register(data)

    def list_discovery_providers(self):
        return self.catalog_service.list_discovery_providers()

    def discover_tools(self, *, provider_name: str | None = None):
        return self.catalog_service.discover_tools(provider_name=provider_name)

    def discover_local_tools(self):
        return self.catalog_service.discover_local_tools()

    def set_availability(self, data: SetToolAvailabilityInput) -> Tool:
        return self.catalog_service.set_availability(data)

    def list_tools(self):
        return self.catalog_service.list_tools()

    def list_enabled_tools(self):
        return self.catalog_service.list_enabled_tools()

    def ensure_local_system_tools_registered(self):
        return self.catalog_service.ensure_local_system_tools_registered()

    def get_tool(self, tool_id: str) -> Tool:
        return self.catalog_service.get_tool(tool_id)

    def get_tool_run(self, run_id: str) -> ToolRun:
        return self.submission_service.get_tool_run(run_id)

    def list_tool_runs(self, *, tool_id: str | None = None) -> list[ToolRun]:
        return self.submission_service.list_tool_runs(tool_id=tool_id)

    def list_tool_workers(self) -> list[ToolWorkerRegistration]:
        return self.worker_service.list_workers()

    def prune_expired_workers(self, *, retention_seconds: int) -> dict[str, object]:
        return self.worker_service.prune_expired_workers(
            retention_seconds=retention_seconds,
        )

    def list_tool_run_assignments(self) -> list[ToolRunAssignment]:
        return self.worker_service.list_assignments()

    def cancel_tool_run(self, run_id: str) -> ToolRun:
        return self.worker_service.cancel_tool_run(run_id)

    async def retry_tool_run(self, run_id: str) -> ToolRun:
        original = self.get_tool_run(run_id)
        if not original.is_terminal() or original.status is ToolRunStatus.SUCCEEDED:
            raise ToolValidationError(
                f"Tool run '{run_id}' is not retryable.",
            )
        return await self.execute(
            ExecuteToolInput(
                tool_id=original.tool_id,
                arguments=dict(original.input_payload),
                mode=original.target.mode,
                strategy=original.target.strategy,
                environment=original.target.environment,
                execution_context=original.invocation_context,
            ),
        )

    async def execute(self, data: ExecuteToolInput) -> ToolRun:
        return await self.submission_service.execute(data)

    async def execute_many(
        self,
        items: tuple[ExecuteToolInput, ...],
    ) -> tuple[ToolRun, ...]:
        return await self.submission_service.execute_many(items)


__all__ = [
    "ExecuteToolInput",
    "RegisterToolInput",
    "RegisterToolParameterInput",
    "SetToolAvailabilityInput",
    "ToolApplicationService",
    "ToolRuntimeGateway",
    "ToolUnitOfWork",
]
