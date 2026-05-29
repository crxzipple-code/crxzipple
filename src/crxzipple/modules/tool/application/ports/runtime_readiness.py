from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping, Protocol

if TYPE_CHECKING:
    from crxzipple.modules.tool.domain.entities import Tool


@dataclass(frozen=True, slots=True)
class ToolRuntimeReadinessCheck:
    requirement: str
    status: str
    ready: bool
    reason: str
    setup_available: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "requirement": self.requirement,
            "status": self.status,
            "ready": self.ready,
            "reason": self.reason,
            "setup_available": self.setup_available,
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True, slots=True)
class ToolRuntimeReadiness:
    ready: bool
    status: str
    reason: str
    checks: tuple[ToolRuntimeReadinessCheck, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "status": self.status,
            "reason": self.reason,
            "setup_available": any(
                check.setup_available for check in self.checks if not check.ready
            ),
            "checks": [check.to_payload() for check in self.checks],
        }


class ToolRuntimeReadinessPort(Protocol):
    def check_tool_runtime(
        self,
        tool: "Tool",
        *,
        workspace_dir: str | None = None,
    ) -> ToolRuntimeReadiness:
        ...
