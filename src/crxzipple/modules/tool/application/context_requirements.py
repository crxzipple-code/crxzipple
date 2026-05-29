from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from crxzipple.modules.tool.application.ports import (
    ToolRuntimeReadiness,
    ToolRuntimeReadinessCheck,
)
from crxzipple.modules.tool.domain.entities import Tool


SUPPORTED_TOOL_CONTEXT_REQUIREMENTS: frozenset[str] = frozenset(
    {
        "agent_id",
        "run_id",
        "session_key",
        "active_session_id",
        "workspace_dir",
    },
)


@dataclass(frozen=True, slots=True)
class ToolContextReadinessInput:
    agent_id: str | None = None
    run_id: str | None = None
    session_key: str | None = None
    active_session_id: str | None = None
    workspace_dir: str | None = None
    attrs: Mapping[str, Any] | None = None

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any] | None,
    ) -> "ToolContextReadinessInput":
        attrs = dict(value or {})
        return cls(
            agent_id=_optional_text(attrs.get("agent_id")),
            run_id=_optional_text(attrs.get("run_id")),
            session_key=_optional_text(attrs.get("session_key")),
            active_session_id=_optional_text(attrs.get("active_session_id")),
            workspace_dir=_optional_text(attrs.get("workspace_dir")),
            attrs=attrs,
        )

    def value_for(self, requirement: str) -> str | None:
        normalized = _normalize_requirement(requirement)
        if normalized == "agent_id":
            return self.agent_id
        if normalized == "run_id":
            return self.run_id
        if normalized == "session_key":
            return self.session_key
        if normalized == "active_session_id":
            return self.active_session_id
        if normalized == "workspace_dir":
            return self.workspace_dir
        if self.attrs is None:
            return None
        return _optional_text(self.attrs.get(normalized))


def check_tool_context_readiness(
    tool: Tool,
    context: ToolContextReadinessInput | Mapping[str, Any] | None = None,
) -> ToolRuntimeReadiness:
    resolved_context = (
        context
        if isinstance(context, ToolContextReadinessInput)
        else ToolContextReadinessInput.from_mapping(context)
    )
    requirements = tuple(
        _normalize_requirement(requirement)
        for requirement in tool.context_requirements
        if _normalize_requirement(requirement)
    )
    if not requirements:
        return ToolRuntimeReadiness(
            ready=True,
            status="ready",
            reason="No tool context requirements are declared.",
        )
    checks = tuple(
        _check_requirement(requirement, context=resolved_context)
        for requirement in requirements
    )
    if all(check.ready for check in checks):
        return ToolRuntimeReadiness(
            ready=True,
            status="ready",
            reason="All tool context requirements are available.",
            checks=checks,
        )
    unsupported = any(check.status == "unsupported" for check in checks)
    reasons = tuple(
        dict.fromkeys(check.reason for check in checks if not check.ready and check.reason)
    )
    return ToolRuntimeReadiness(
        ready=False,
        status="unsupported" if unsupported else "setup_needed",
        reason="; ".join(reasons) or "Tool runtime context is incomplete.",
        checks=checks,
    )


def _check_requirement(
    requirement: str,
    *,
    context: ToolContextReadinessInput,
) -> ToolRuntimeReadinessCheck:
    if requirement not in SUPPORTED_TOOL_CONTEXT_REQUIREMENTS:
        return ToolRuntimeReadinessCheck(
            requirement=requirement,
            status="unsupported",
            ready=False,
            reason=f"Unsupported tool context requirement '{requirement}'.",
            metadata={"supported": sorted(SUPPORTED_TOOL_CONTEXT_REQUIREMENTS)},
        )
    value = context.value_for(requirement)
    if value is None:
        return ToolRuntimeReadinessCheck(
            requirement=requirement,
            status="setup_needed",
            ready=False,
            reason=f"Tool requires runtime context '{requirement}'.",
        )
    return ToolRuntimeReadinessCheck(
        requirement=requirement,
        status="ready",
        ready=True,
        reason=f"Runtime context '{requirement}' is available.",
    )


def _normalize_requirement(value: object) -> str:
    normalized = str(value or "").strip()
    if normalized.startswith("context:"):
        normalized = normalized.removeprefix("context:").strip()
    return normalized


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
