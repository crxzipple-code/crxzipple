from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from crxzipple.modules.tool.domain import ToolRun


class ToolRunControlPort(Protocol):
    def get_tool_run(self, run_id: str) -> "ToolRun":
        ...

    def cancel_tool_run(self, run_id: str) -> "ToolRun":
        ...

    async def retry_tool_run(self, run_id: str) -> "ToolRun":
        ...

    def prune_expired_workers(self, *, retention_seconds: int) -> dict[str, Any]:
        ...


__all__ = ["ToolRunControlPort"]
