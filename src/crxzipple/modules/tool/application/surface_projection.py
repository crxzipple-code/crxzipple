from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.tool.application.surface_models import (
    ToolSurfaceFunction,
    ToolSurfaceGroup,
    ToolSurfaceSource,
)
from crxzipple.modules.tool.domain.entities import Tool, ToolFunction, ToolSource
from crxzipple.modules.tool.domain.value_objects import (
    ToolExecutionStrategy,
    ToolMode,
)


def surface_function(
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
        concurrency_key=policy.serial_group_key or serial_concurrency_key(tool),
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


def surface_source(
    source: ToolSource,
    *,
    functions: tuple[ToolSurfaceFunction, ...],
) -> ToolSurfaceSource:
    runtime_request = runtime_request_config(source)
    groups = surface_groups(
        source,
        runtime_request=runtime_request,
        functions=functions,
    )
    return ToolSurfaceSource(
        source_id=source.source_id,
        source_key=source.source_id,
        source_kind=source.kind.value,
        title=str(runtime_request.get("title") or source.display_name),
        summary=str(
            runtime_request.get("summary") or source.description or source.display_name,
        ),
        groups=groups,
        readiness={"ready": True, "status": "ready"},
        authorization={"mode": "not_evaluated"},
        runtime_requirements=tuple(dict(item) for item in source.runtime_requirements),
        runtime_request_metadata=dict(runtime_request),
        metadata={
            "revision": source.revision,
            "config_hash": source.config_hash,
            "function_count": len(functions),
        },
    )


def surface_groups(
    source: ToolSource,
    *,
    runtime_request: Mapping[str, Any],
    functions: tuple[ToolSurfaceFunction, ...],
) -> tuple[ToolSurfaceGroup, ...]:
    by_id = {function.function_id: function for function in functions}
    raw_groups = runtime_request.get("groups")
    groups: list[tuple[int, int, ToolSurfaceGroup]] = []
    grouped: set[str] = set()
    if isinstance(raw_groups, Mapping):
        for index, (raw_key, raw_group) in enumerate(raw_groups.items()):
            group_key = str(raw_key).strip()
            if not group_key or not isinstance(raw_group, Mapping):
                continue
            function_refs = tuple(
                function_id
                for function_id in runtime_request_group_function_ids(raw_group)
                if function_id in by_id
            )
            if not function_refs:
                continue
            grouped.update(function_refs)
            order = int_value(raw_group.get("order"), fallback=1000 + index)
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


def group_key_for_function(function: ToolFunction, *, source: ToolSource | None) -> str:
    if source is not None:
        runtime_request = runtime_request_config(source)
        raw_groups = runtime_request.get("groups")
        if isinstance(raw_groups, Mapping):
            for raw_key, raw_group in raw_groups.items():
                group_key = str(raw_key).strip()
                if not group_key or not isinstance(raw_group, Mapping):
                    continue
                if function.function_id in runtime_request_group_function_ids(raw_group):
                    return group_key
            return "other"
    return "source"


def runtime_request_config(source: ToolSource) -> Mapping[str, Any]:
    raw_runtime_request = source.config.get("runtime_request")
    if isinstance(raw_runtime_request, Mapping):
        return dict(raw_runtime_request)
    provider = source.config.get("provider")
    if isinstance(provider, Mapping):
        provider_runtime_request = provider.get("runtime_request")
        if isinstance(provider_runtime_request, Mapping):
            return dict(provider_runtime_request)
    return {}


def runtime_request_group_function_ids(group: Mapping[str, Any]) -> tuple[str, ...]:
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


def serial_concurrency_key(tool: Tool) -> str | None:
    support = tool.execution_support
    if (
        ToolMode.BACKGROUND in support.supported_modes
        or ToolExecutionStrategy.PROCESS in support.supported_strategies
    ):
        return f"tool:{tool.id}"
    return None


def int_value(value: object, *, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
