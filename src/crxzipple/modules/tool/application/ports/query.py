from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from crxzipple.modules.tool.domain import Tool, ToolRun
    from crxzipple.modules.tool.domain.entities import (
        ToolRunAssignment,
        ToolWorkerRegistration,
    )


class ToolQueryPort(Protocol):
    @property
    def concurrency_policy(self) -> Any:
        ...

    def list_tools(self) -> list["Tool"]:
        ...

    def list_enabled_tools(
        self,
        *,
        runtime_context: Mapping[str, Any] | None = None,
    ) -> list["Tool"]:
        ...

    def get_tool(self, tool_id: str) -> "Tool":
        ...

    def list_tool_runs(
        self,
        *,
        tool_id: str | None = None,
        limit: int | None = None,
    ) -> list["ToolRun"]:
        ...

    def list_tool_runs_for_orchestration_runs(
        self,
        run_ids: tuple[str, ...],
    ) -> list["ToolRun"]:
        ...

    def get_tool_run(self, run_id: str) -> "ToolRun":
        ...

    def list_tool_workers(self) -> list["ToolWorkerRegistration"]:
        ...

    def list_tool_run_assignments(self) -> list["ToolRunAssignment"]:
        ...

    def check_readiness(
        self,
        tool_id: str,
        *,
        workspace_dir: str | None = None,
    ) -> dict[str, object]:
        ...

    def check_access_readiness(
        self,
        tool_id: str,
        *,
        workspace_dir: str | None = None,
    ) -> object:
        ...


__all__ = ["ToolQueryPort"]
