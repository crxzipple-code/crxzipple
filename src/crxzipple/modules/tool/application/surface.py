from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from crxzipple.modules.tool.application.runtime_pool_service import (
    ToolRuntimePoolContext,
    ToolRuntimePoolService,
)
from crxzipple.modules.tool.application.service_support import ToolServiceBase
from crxzipple.modules.tool.domain.entities import Tool, ToolFunction, ToolSource
from crxzipple.modules.tool.domain.value_objects import (
    ToolExecutionStrategy,
    ToolMode,
    ToolSourceStatus,
)


@dataclass(frozen=True, slots=True)
class ToolSurfaceFunction:
    function_id: str
    name: str
    title: str
    description: str
    input_schema: Mapping[str, Any]
    source_id: str
    group_key: str
    runtime_kind: str
    execution_modes: tuple[str, ...] = ()
    execution_strategies: tuple[str, ...] = ()
    execution_environments: tuple[str, ...] = ()
    requires_confirmation: bool = False
    mutates_state: bool = False
    supports_parallel: bool = True
    readiness: Mapping[str, Any] = field(default_factory=dict)
    authorization: Mapping[str, Any] = field(default_factory=dict)
    concurrency_key: str | None = None
    provider_schema_hints: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "function_id": self.function_id,
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "input_schema": dict(self.input_schema),
            "source_id": self.source_id,
            "group_key": self.group_key,
            "runtime_kind": self.runtime_kind,
            "execution_modes": list(self.execution_modes),
            "execution_strategies": list(self.execution_strategies),
            "execution_environments": list(self.execution_environments),
            "requires_confirmation": self.requires_confirmation,
            "mutates_state": self.mutates_state,
            "supports_parallel": self.supports_parallel,
            "readiness": dict(self.readiness),
            "authorization": dict(self.authorization),
            "provider_schema_hints": dict(self.provider_schema_hints),
            "metadata": dict(self.metadata),
        }
        if self.concurrency_key is not None:
            payload["concurrency_key"] = self.concurrency_key
        return payload


@dataclass(frozen=True, slots=True)
class ToolSurfaceGroup:
    group_key: str
    title: str
    summary: str
    function_refs: tuple[str, ...] = ()
    default_expanded: bool = False
    schema_enabled: bool = True
    estimate: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "group_key": self.group_key,
            "title": self.title,
            "summary": self.summary,
            "function_refs": list(self.function_refs),
            "default_expanded": self.default_expanded,
            "schema_enabled": self.schema_enabled,
            "estimate": dict(self.estimate),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ToolSurfaceSource:
    source_id: str
    source_key: str
    source_kind: str
    title: str
    summary: str
    groups: tuple[ToolSurfaceGroup, ...] = ()
    readiness: Mapping[str, Any] = field(default_factory=dict)
    authorization: Mapping[str, Any] = field(default_factory=dict)
    runtime_requirements: tuple[Mapping[str, Any], ...] = ()
    prompt_metadata: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_key": self.source_key,
            "source_kind": self.source_kind,
            "title": self.title,
            "summary": self.summary,
            "groups": [group.to_payload() for group in self.groups],
            "readiness": dict(self.readiness),
            "authorization": dict(self.authorization),
            "runtime_requirements": [
                dict(requirement) for requirement in self.runtime_requirements
            ],
            "prompt_metadata": dict(self.prompt_metadata),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ToolSurface:
    surface_id: str
    session_id: str | None = None
    run_id: str | None = None
    agent_id: str | None = None
    policy_version: str = "tool_surface.v1"
    sources: tuple[ToolSurfaceSource, ...] = ()
    functions: tuple[ToolSurfaceFunction, ...] = ()
    default_tool_choice: str = "auto"
    parallel_tool_calls: bool = True
    estimate: Mapping[str, Any] = field(default_factory=dict)
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_payload(self) -> dict[str, Any]:
        return {
            "surface_id": self.surface_id,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "policy_version": self.policy_version,
            "sources": [source.to_payload() for source in self.sources],
            "functions": [function.to_payload() for function in self.functions],
            "default_tool_choice": self.default_tool_choice,
            "parallel_tool_calls": self.parallel_tool_calls,
            "estimate": dict(self.estimate),
            "diagnostics": dict(self.diagnostics),
            "created_at": self.created_at.isoformat(),
        }


class ToolSurfaceQueryService(ToolServiceBase):
    def __init__(
        self,
        deps,
        *,
        runtime_pool_service: ToolRuntimePoolService,
    ) -> None:
        super().__init__(deps)
        self._runtime_pool_service = runtime_pool_service

    def build_surface(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        agent_id: str | None = None,
        runtime_context: ToolRuntimePoolContext | Mapping[str, Any] | None = None,
        surface_id: str | None = None,
        tool_ids: tuple[str, ...] | None = None,
        persist: bool = False,
    ) -> ToolSurface:
        context = _surface_runtime_context(
            runtime_context,
            agent_id=agent_id,
            session_id=session_id,
            run_id=run_id,
        )
        pool = self._runtime_pool_service.build_pool(runtime_context=context)
        requested_tool_ids = _normalized_tool_ids(tool_ids)
        tools_by_id = {
            tool.id: tool
            for tool in pool.enabled_tools
            if requested_tool_ids is None or tool.id in requested_tool_ids
        }
        with self.uow_factory() as uow:
            functions = uow.tool_functions.list_by_ids(tuple(tools_by_id))
            sources = uow.tool_sources.list_by_ids(
                tuple(
                    dict.fromkeys(
                        function.source_id
                        for function in functions.values()
                    ),
                ),
            )

        functions_by_source: dict[str, list[ToolSurfaceFunction]] = {}
        for tool_id, tool in sorted(tools_by_id.items()):
            function = functions.get(tool_id)
            if function is None:
                continue
            group_key = _group_key_for_function(function, source=sources.get(function.source_id))
            surface_function = _surface_function(tool, function, group_key=group_key)
            functions_by_source.setdefault(function.source_id, []).append(surface_function)

        sources_payload: list[ToolSurfaceSource] = []
        for source_id in sorted(functions_by_source):
            source = sources.get(source_id)
            if source is None or source.status is not ToolSourceStatus.ACTIVE:
                continue
            source_functions = tuple(functions_by_source[source_id])
            sources_payload.append(
                _surface_source(
                    source,
                    functions=source_functions,
                ),
            )

        functions_payload = tuple(
            function
            for source in sources_payload
            for function in functions_by_source.get(source.source_id, ())
        )
        surface = ToolSurface(
            surface_id=surface_id or f"tool_surface:{uuid4().hex}",
            session_id=_optional_text(session_id),
            run_id=_optional_text(run_id),
            agent_id=_optional_text(agent_id),
            sources=tuple(sources_payload),
            functions=functions_payload,
            parallel_tool_calls=all(function.supports_parallel for function in functions_payload),
            estimate={
                "source_count": len(sources_payload),
                "group_count": sum(len(source.groups) for source in sources_payload),
                "function_count": len(functions_payload),
            },
            diagnostics={
                "excluded_count": len(pool.excluded),
                "requested_tool_count": (
                    len(requested_tool_ids) if requested_tool_ids is not None else None
                ),
                "excluded": [
                    {
                        "tool_id": exclusion.tool_id,
                        "category": exclusion.category,
                        "status": exclusion.status,
                        "reason": exclusion.reason,
                    }
                    for exclusion in pool.excluded
                ],
            },
        )
        if persist:
            with self.uow_factory() as uow:
                uow.tool_surfaces.add(surface)
                uow.commit()
        return surface


def _normalized_tool_ids(tool_ids: tuple[str, ...] | None) -> frozenset[str] | None:
    if tool_ids is None:
        return None
    return frozenset(tool_id.strip() for tool_id in tool_ids if tool_id.strip())


def _surface_runtime_context(
    runtime_context: ToolRuntimePoolContext | Mapping[str, Any] | None,
    *,
    agent_id: str | None,
    session_id: str | None,
    run_id: str | None,
) -> ToolRuntimePoolContext:
    if isinstance(runtime_context, ToolRuntimePoolContext):
        base = dict(runtime_context.attrs)
        if session_id is not None:
            base.setdefault("session_id", session_id)
        if run_id is not None:
            base.setdefault("run_id", run_id)
        return ToolRuntimePoolContext(
            caller=runtime_context.caller,
            agent_id=runtime_context.agent_id or _optional_text(agent_id),
            session_key=runtime_context.session_key,
            workspace_dir=runtime_context.workspace_dir,
            attrs=base,
        )
    payload = dict(runtime_context or {})
    payload.setdefault("caller", "orchestration")
    if agent_id is not None:
        payload.setdefault("agent_id", agent_id)
    if session_id is not None:
        payload.setdefault("session_id", session_id)
    if run_id is not None:
        payload.setdefault("run_id", run_id)
    return ToolRuntimePoolContext.from_mapping(payload)


def _surface_function(
    tool: Tool,
    function: ToolFunction,
    *,
    group_key: str,
) -> ToolSurfaceFunction:
    policy = tool.execution_policy
    support = tool.execution_support
    return ToolSurfaceFunction(
        function_id=function.function_id,
        name=tool.id,
        title=tool.name,
        description=tool.description,
        input_schema=dict(function.input_schema),
        source_id=function.source_id,
        group_key=group_key,
        runtime_kind=function.runtime_kind.value,
        execution_modes=tuple(mode.value for mode in support.supported_modes),
        execution_strategies=tuple(
            strategy.value for strategy in support.supported_strategies
        ),
        execution_environments=tuple(
            environment.value for environment in support.supported_environments
        ),
        requires_confirmation=policy.requires_confirmation,
        mutates_state=policy.mutates_state,
        supports_parallel=policy.supports_parallel,
        readiness={"ready": True, "status": "ready"},
        authorization={
            "mode": "not_evaluated",
            "required_effect_ids": list(tool.required_effect_ids),
        },
        concurrency_key=policy.serial_group_key or _serial_concurrency_key(tool),
        provider_schema_hints={
            "schema_hash": function.schema_hash,
            "tool_name": tool.id,
        },
        metadata={
            "capability_ids": list(tool.capability_ids),
            "tags": list(tool.tags),
            "revision": function.revision,
        },
    )


def _surface_source(
    source: ToolSource,
    *,
    functions: tuple[ToolSurfaceFunction, ...],
) -> ToolSurfaceSource:
    prompt = _prompt_config(source)
    groups = _surface_groups(
        source,
        prompt=prompt,
        functions=functions,
    )
    return ToolSurfaceSource(
        source_id=source.source_id,
        source_key=source.source_id,
        source_kind=source.kind.value,
        title=str(prompt.get("title") or source.display_name),
        summary=str(prompt.get("summary") or source.description or source.display_name),
        groups=groups,
        readiness={"ready": True, "status": "ready"},
        authorization={"mode": "not_evaluated"},
        runtime_requirements=tuple(dict(item) for item in source.runtime_requirements),
        prompt_metadata=dict(prompt),
        metadata={
            "revision": source.revision,
            "config_hash": source.config_hash,
            "function_count": len(functions),
        },
    )


def _surface_groups(
    source: ToolSource,
    *,
    prompt: Mapping[str, Any],
    functions: tuple[ToolSurfaceFunction, ...],
) -> tuple[ToolSurfaceGroup, ...]:
    by_id = {function.function_id: function for function in functions}
    raw_groups = prompt.get("groups")
    groups: list[tuple[int, int, ToolSurfaceGroup]] = []
    grouped: set[str] = set()
    if isinstance(raw_groups, Mapping):
        for index, (raw_key, raw_group) in enumerate(raw_groups.items()):
            group_key = str(raw_key).strip()
            if not group_key or not isinstance(raw_group, Mapping):
                continue
            function_refs = tuple(
                function_id
                for function_id in _prompt_group_function_ids(raw_group)
                if function_id in by_id
            )
            if not function_refs:
                continue
            grouped.update(function_refs)
            order = _int_value(raw_group.get("order"), fallback=1000 + index)
            groups.append(
                (
                    order,
                    index,
                    ToolSurfaceGroup(
                        group_key=group_key,
                        title=str(
                            raw_group.get("title")
                            or group_key.replace("_", " ").title()
                        ),
                        summary=str(
                            raw_group.get("summary")
                            or f"Tool functions in the '{group_key}' group."
                        ),
                        function_refs=function_refs,
                        default_expanded=bool(raw_group.get("default_expanded", False)),
                        schema_enabled=bool(raw_group.get("schema_enabled", True)),
                        estimate={"function_count": len(function_refs)},
                        metadata={
                            "source_id": source.source_id,
                            "auto_source_group": False,
                        },
                    ),
                ),
            )
    ungrouped = tuple(
        function.function_id
        for function in functions
        if function.function_id not in grouped
    )
    if ungrouped:
        group_key = "source" if not groups else "other"
        groups.append(
            (
                10000 + len(groups),
                len(groups),
                ToolSurfaceGroup(
                    group_key=group_key,
                    title=group_key.replace("_", " ").title(),
                    summary=f"Tool functions from {source.display_name}.",
                    function_refs=ungrouped,
                    estimate={"function_count": len(ungrouped)},
                    metadata={
                        "source_id": source.source_id,
                        "auto_source_group": True,
                        "source_kind": source.kind.value,
                    },
                ),
            ),
        )
    return tuple(group for _, _, group in sorted(groups, key=lambda item: item[:2]))


def _group_key_for_function(function: ToolFunction, *, source: ToolSource | None) -> str:
    if source is not None:
        prompt = _prompt_config(source)
        raw_groups = prompt.get("groups")
        if isinstance(raw_groups, Mapping):
            for raw_key, raw_group in raw_groups.items():
                group_key = str(raw_key).strip()
                if not group_key or not isinstance(raw_group, Mapping):
                    continue
                if function.function_id in _prompt_group_function_ids(raw_group):
                    return group_key
            return "other"
    return "source"


def _prompt_config(source: ToolSource) -> Mapping[str, Any]:
    raw_prompt = source.config.get("prompt")
    if isinstance(raw_prompt, Mapping):
        return dict(raw_prompt)
    provider = source.config.get("provider")
    if isinstance(provider, Mapping):
        provider_prompt = provider.get("prompt")
        if isinstance(provider_prompt, Mapping):
            return dict(provider_prompt)
    return {}


def _prompt_group_function_ids(group: Mapping[str, Any]) -> tuple[str, ...]:
    raw_function_ids = group.get("function_ids")
    if raw_function_ids is None:
        raw_function_ids = group.get("tools")
    if not isinstance(raw_function_ids, (list, tuple)):
        return ()
    return tuple(
        dict.fromkeys(
            str(function_id).strip()
            for function_id in raw_function_ids
            if str(function_id).strip()
        ),
    )


def _serial_concurrency_key(tool: Tool) -> str | None:
    support = tool.execution_support
    if (
        ToolMode.BACKGROUND in support.supported_modes
        or ToolExecutionStrategy.PROCESS in support.supported_strategies
    ):
        return f"tool:{tool.id}"
    return None


def _int_value(value: object, *, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
