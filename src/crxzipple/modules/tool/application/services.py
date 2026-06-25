from __future__ import annotations

from collections.abc import Iterable

from crxzipple.modules.tool.application.catalog_service import ToolCatalogService
from crxzipple.modules.tool.application.concurrency import ToolRunConcurrencyPolicy
from crxzipple.modules.tool.application.provider_backend_service import (
    ToolProviderBackendReadinessEvaluator,
)
from crxzipple.modules.tool.application.service_support import (
    ExecuteToolInput,
    ToolRuntimeGateway,
    ToolUnitOfWork,
)
from crxzipple.modules.tool.application.context_requirements import (
    check_tool_context_readiness,
)
from crxzipple.modules.tool.application.surface import (
    ToolSurface,
    ToolSurfaceQueryService,
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
        runtime_pool_service: object,
        surface_query_service: ToolSurfaceQueryService,
    ) -> None:
        self.catalog_service = catalog_service
        self.worker_service = worker_service
        self.submission_service = submission_service
        self.runtime_pool_service = runtime_pool_service
        self.surface_query_service = surface_query_service
        self.provider_backend_readiness = ToolProviderBackendReadinessEvaluator()

    @property
    def dispatch_port(self):
        return self.submission_service.dispatch_port

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

    def list_tools(self):
        return self.catalog_service.list_tools()

    def list_enabled_tools(
        self,
        *,
        runtime_context: object | None = None,
    ):
        if runtime_context is not None:
            return self.runtime_pool_service.list_enabled_tools(
                runtime_context=runtime_context,
            )
        return self.catalog_service.list_enabled_tools()

    def list_runtime_pool_tools(
        self,
        *,
        runtime_context: object | None = None,
    ):
        return self.runtime_pool_service.list_enabled_tools(
            runtime_context=runtime_context,
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
    ) -> ToolSurface:
        return self.surface_query_service.build_surface(
            session_id=session_id,
            run_id=run_id,
            agent_id=agent_id,
            runtime_context=runtime_context,
            surface_id=surface_id,
            tool_ids=tool_ids,
            persist=persist,
        )

    def get_tool(self, tool_id: str) -> Tool:
        return self.catalog_service.get_tool(tool_id)

    def get_tools(self, tool_ids: Iterable[str]) -> dict[str, Tool]:
        return self.catalog_service.get_tools(tool_ids)

    def check_access_readiness(
        self,
        tool_id: str,
        *,
        workspace_dir: str | None = None,
    ):
        del workspace_dir
        tool = self.get_tool(tool_id)
        if self.submission_service.access_readiness is None:
            return None
        return self.submission_service.access_readiness.check_tool_access(
            tool,
        )

    def check_runtime_readiness(
        self,
        tool_id: str,
        *,
        workspace_dir: str | None = None,
    ):
        tool = self.get_tool(tool_id)
        if self.submission_service.runtime_readiness is None:
            return None
        return self.submission_service.runtime_readiness.check_tool_runtime(
            tool,
            workspace_dir=workspace_dir,
        )

    def check_context_readiness(
        self,
        tool_id: str,
        *,
        agent_id: str | None = None,
        run_id: str | None = None,
        session_key: str | None = None,
        active_session_id: str | None = None,
        workspace_dir: str | None = None,
    ):
        tool = self.get_tool(tool_id)
        if not tool.context_requirements:
            return None
        return check_tool_context_readiness(
            tool,
            {
                "agent_id": agent_id,
                "run_id": run_id,
                "session_key": session_key,
                "active_session_id": active_session_id,
                "workspace_dir": workspace_dir,
            },
        )

    def check_readiness(
        self,
        tool_id: str,
        *,
        agent_id: str | None = None,
        run_id: str | None = None,
        session_key: str | None = None,
        active_session_id: str | None = None,
        workspace_dir: str | None = None,
    ) -> dict[str, object]:
        return _combined_readiness_payload(
            context=self.check_context_readiness(
                tool_id,
                agent_id=agent_id,
                run_id=run_id,
                session_key=session_key,
                active_session_id=active_session_id,
                workspace_dir=workspace_dir,
            ),
            access=self.check_access_readiness(tool_id),
            runtime=self.check_runtime_readiness(tool_id, workspace_dir=workspace_dir),
        )

    def check_provider_backend_readiness(self, backend: object):
        backend_entity = (
            self._get_provider_backend(str(backend))
            if isinstance(backend, str)
            else backend
        )
        return self.provider_backend_readiness.check_backend_readiness(
            backend_entity,
            access_readiness=self.submission_service.access_readiness,
            runtime_readiness=self.submission_service.runtime_readiness,
        )

    def _get_provider_backend(self, backend_id: str):
        with self.submission_service.uow_factory() as uow:
            backend = uow.tool_provider_backends.get(backend_id)
            if backend is None:
                raise ToolValidationError(
                    f"Tool provider backend '{backend_id}' does not exist.",
                )
            return backend

    def get_tool_run(self, run_id: str) -> ToolRun:
        return self.submission_service.get_tool_run(run_id)

    def list_tool_runs(
        self,
        *,
        tool_id: str | None = None,
        limit: int | None = None,
    ) -> list[ToolRun]:
        return self.submission_service.list_tool_runs(tool_id=tool_id, limit=limit)

    def list_tool_runs_for_orchestration_runs(
        self,
        run_ids: tuple[str, ...],
    ) -> list[ToolRun]:
        return self.submission_service.list_tool_runs_for_orchestration_runs(run_ids)

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
                metadata=dict(original.metadata),
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


def _combined_readiness_payload(
    *,
    context: object | None,
    access: object | None,
    runtime: object | None,
) -> dict[str, object]:
    parts: list[tuple[str, dict[str, object]]] = []
    for category, readiness in (
        ("context", context),
        ("access", access),
        ("runtime", runtime),
    ):
        payload = _readiness_payload(readiness)
        if payload is not None:
            parts.append((category, payload))
    if not parts:
        return {
            "ready": True,
            "status": "ready",
            "reason": "No readiness checks are configured.",
            "setup_available": False,
            "checks": [],
            "parts": {},
        }

    checks: list[dict[str, object]] = []
    for category, payload in parts:
        raw_checks = payload.get("checks")
        if isinstance(raw_checks, list):
            checks.extend(
                {"category": category, **dict(raw_check)}
                for raw_check in raw_checks
                if isinstance(raw_check, dict)
            )

    blocked = tuple((category, payload) for category, payload in parts if not payload["ready"])
    if not blocked:
        return {
            "ready": True,
            "status": "ready",
            "reason": "All readiness checks are ready.",
            "setup_available": False,
            "checks": checks,
            "parts": {category: payload for category, payload in parts},
        }

    statuses = tuple(str(payload.get("status") or "") for _category, payload in blocked)
    if "unsupported" in statuses:
        status = "unsupported"
    elif "degraded" in statuses:
        status = "degraded"
    else:
        status = "setup_needed"
    reasons = tuple(
        dict.fromkeys(
            str(payload.get("reason") or "").strip()
            for _category, payload in blocked
            if str(payload.get("reason") or "").strip()
        )
    )
    return {
        "ready": False,
        "status": status,
        "reason": "; ".join(reasons) or "Tool readiness setup is required.",
        "setup_available": any(bool(payload.get("setup_available")) for _c, payload in blocked),
        "checks": checks,
        "parts": {category: payload for category, payload in parts},
    }


def _readiness_payload(readiness: object | None) -> dict[str, object] | None:
    if readiness is None:
        return None
    to_payload = getattr(readiness, "to_payload", None)
    if callable(to_payload):
        payload = to_payload()
        if isinstance(payload, dict):
            return dict(payload)
    return None


__all__ = [
    "ExecuteToolInput",
    "ToolApplicationService",
    "ToolRuntimeGateway",
    "ToolUnitOfWork",
]
