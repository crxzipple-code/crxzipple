from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping, Protocol

if TYPE_CHECKING:
    from crxzipple.modules.tool.domain.entities import Tool


@dataclass(frozen=True, slots=True)
class ToolAccessReadinessCheck:
    requirement: str
    status: str
    ready: bool
    reason: str
    setup_available: bool = False
    requirement_id: str | None = None
    binding_id: str | None = None
    expected_kind: str | None = None
    setup_flow: Mapping[str, Any] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "requirement": self.requirement,
            "status": self.status,
            "ready": self.ready,
            "reason": self.reason,
            "setup_available": self.setup_available,
        }
        if self.requirement_id:
            payload["requirement_id"] = self.requirement_id
        if self.binding_id:
            payload["binding_id"] = self.binding_id
        if self.expected_kind:
            payload["expected_kind"] = self.expected_kind
        if self.setup_flow:
            payload["setup_flow"] = dict(self.setup_flow)
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True, slots=True)
class ToolAccessReadiness:
    ready: bool
    status: str
    reason: str
    checks: tuple[ToolAccessReadinessCheck, ...] = ()

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


class ToolAccessReadinessPort(Protocol):
    def check_tool_access(
        self,
        tool: "Tool",
    ) -> ToolAccessReadiness:
        ...
