from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.tool.application.context_requirements import (
    check_tool_context_readiness,
)
from crxzipple.modules.tool.application.service_support import (
    ToolServiceBase,
    ToolServiceDependencies,
    build_tool_from_function,
)
from crxzipple.modules.tool.domain.entities import Tool
from crxzipple.modules.tool.domain.value_objects import (
    ToolFunctionStatus,
    ToolSourceStatus,
)


@dataclass(frozen=True, slots=True)
class ToolRuntimePool:
    tools: tuple[Tool, ...]
    excluded: tuple["ToolRuntimePoolExclusion", ...] = ()

    @property
    def enabled_tools(self) -> tuple[Tool, ...]:
        return tuple(tool for tool in self.tools if tool.enabled)


@dataclass(frozen=True, slots=True)
class ToolRuntimePoolContext:
    caller: str | None = None
    agent_id: str | None = None
    session_key: str | None = None
    workspace_dir: str | None = None
    attrs: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "ToolRuntimePoolContext":
        if value is None:
            return cls()
        return cls(
            caller=_optional_text(value.get("caller")),
            agent_id=_optional_text(value.get("agent_id")),
            session_key=_optional_text(value.get("session_key")),
            workspace_dir=_optional_text(value.get("workspace_dir")),
            attrs=dict(value),
        )


@dataclass(frozen=True, slots=True)
class ToolRuntimePoolExclusion:
    tool_id: str
    category: str
    status: str
    reason: str


class ToolRuntimePoolService(ToolServiceBase):
    def __init__(self, deps: ToolServiceDependencies) -> None:
        super().__init__(deps)

    def build_pool(
        self,
        *,
        runtime_context: ToolRuntimePoolContext | Mapping[str, Any] | None = None,
    ) -> ToolRuntimePool:
        context = _coerce_context(runtime_context)
        resolved, excluded = self._catalog_tool_map(runtime_context=context)
        return ToolRuntimePool(
            tools=tuple(resolved[tool_id] for tool_id in sorted(resolved)),
            excluded=tuple(excluded),
        )

    def list_tools(
        self,
        *,
        runtime_context: ToolRuntimePoolContext | Mapping[str, Any] | None = None,
    ) -> tuple[Tool, ...]:
        return self.build_pool(
            runtime_context=runtime_context,
        ).tools

    def list_enabled_tools(
        self,
        *,
        runtime_context: ToolRuntimePoolContext | Mapping[str, Any] | None = None,
    ) -> tuple[Tool, ...]:
        return self.build_pool(
            runtime_context=runtime_context,
        ).enabled_tools

    def _catalog_tool_map(
        self,
        *,
        runtime_context: ToolRuntimePoolContext,
    ) -> tuple[dict[str, Tool], list[ToolRuntimePoolExclusion]]:
        with self.uow_factory() as uow:
            functions = uow.tool_functions.list(status=ToolFunctionStatus.ACTIVE)
            source_ids = tuple(dict.fromkeys(function.source_id for function in functions))
            sources = uow.tool_sources.list_by_ids(source_ids)

        resolved: dict[str, Tool] = {}
        excluded: list[ToolRuntimePoolExclusion] = []
        for function in functions:
            source = sources.get(function.source_id)
            if source is None or source.status is not ToolSourceStatus.ACTIVE:
                excluded.append(
                    ToolRuntimePoolExclusion(
                        tool_id=function.function_id,
                        category="source",
                        status=(
                            source.status.value
                            if source is not None
                            else "missing"
                        ),
                        reason="Tool source is not active.",
                    ),
                )
                continue
            if not function.enabled:
                excluded.append(
                    ToolRuntimePoolExclusion(
                        tool_id=function.function_id,
                        category="function",
                        status="disabled",
                        reason="Tool function is disabled.",
                    ),
                )
                continue
            tool = build_tool_from_function(function)
            exclusion = self._runtime_exclusion(tool, runtime_context=runtime_context)
            if exclusion is not None:
                excluded.append(exclusion)
                continue
            resolved[function.function_id] = tool
        return resolved, excluded

    def _runtime_exclusion(
        self,
        tool: Tool,
        *,
        runtime_context: ToolRuntimePoolContext,
    ) -> ToolRuntimePoolExclusion | None:
        context_readiness = check_tool_context_readiness(
            tool,
            _context_payload(runtime_context),
        )
        if not bool(getattr(context_readiness, "ready", False)):
            return ToolRuntimePoolExclusion(
                tool_id=tool.id,
                category="context",
                status=_readiness_status(context_readiness),
                reason=_readiness_reason(context_readiness),
            )
        if (
            self.access_readiness is not None
            and runtime_context.caller != "orchestration"
        ):
            readiness = self.access_readiness.check_tool_access(tool)
            if not bool(getattr(readiness, "ready", False)):
                return ToolRuntimePoolExclusion(
                    tool_id=tool.id,
                    category="access",
                    status=_readiness_status(readiness),
                    reason=_readiness_reason(readiness),
                )
        if self.runtime_readiness is not None:
            readiness = self.runtime_readiness.check_tool_runtime(
                tool,
                workspace_dir=runtime_context.workspace_dir,
            )
            if not bool(getattr(readiness, "ready", False)):
                return ToolRuntimePoolExclusion(
                    tool_id=tool.id,
                    category="runtime",
                    status=_readiness_status(readiness),
                    reason=_readiness_reason(readiness),
                )
        return None

def _coerce_context(
    runtime_context: ToolRuntimePoolContext | Mapping[str, Any] | None,
) -> ToolRuntimePoolContext:
    if isinstance(runtime_context, ToolRuntimePoolContext):
        return runtime_context
    return ToolRuntimePoolContext.from_mapping(runtime_context)


def _context_payload(runtime_context: ToolRuntimePoolContext) -> dict[str, Any]:
    payload = dict(runtime_context.attrs)
    if runtime_context.agent_id is not None:
        payload["agent_id"] = runtime_context.agent_id
    if runtime_context.session_key is not None:
        payload["session_key"] = runtime_context.session_key
    if runtime_context.workspace_dir is not None:
        payload["workspace_dir"] = runtime_context.workspace_dir
    return payload


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _readiness_status(readiness: object) -> str:
    payload = _readiness_payload(readiness)
    status = payload.get("status")
    if isinstance(status, str) and status.strip():
        return status.strip()
    value = getattr(getattr(readiness, "status", None), "value", None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    normalized = str(getattr(readiness, "status", "") or "").strip()
    return normalized or "not_ready"


def _readiness_reason(readiness: object) -> str:
    payload = _readiness_payload(readiness)
    reason = payload.get("reason")
    if isinstance(reason, str) and reason.strip():
        return reason.strip()
    normalized = str(getattr(readiness, "reason", "") or "").strip()
    return normalized or "Tool runtime pool readiness check failed."


def _readiness_payload(readiness: object) -> dict[str, Any]:
    to_payload = getattr(readiness, "to_payload", None)
    if callable(to_payload):
        payload = to_payload()
        if isinstance(payload, dict):
            return dict(payload)
    return {}
