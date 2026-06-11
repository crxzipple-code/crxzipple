"""Tool context tree adapter."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

from crxzipple.modules.context_workspace.application import ContextChildrenRequest
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextEstimate,
    ContextNodeSeed,
    ContextNodeState,
)
from crxzipple.modules.tool.application import ToolPromptBundle, ToolPromptBundleGroup
from crxzipple.modules.tool.domain import Tool


TOOL_CONTEXT_PROMPT_REVISION = "2026-06-09.tool_prompt_budget.v1"


class ToolContextService(Protocol):
    def get_tool(self, tool_id: str) -> Tool:
        ...

    def get_tools(self, tool_ids: Iterable[str]) -> dict[str, Tool]:
        ...


class ToolPromptCatalog(Protocol):
    def list_prompt_bundles(
        self,
        function_ids: Iterable[str],
    ) -> tuple[ToolPromptBundle, ...]:
        ...


class ToolContextNodeProvider:
    owner = "tool"

    def __init__(
        self,
        tool_service: ToolContextService,
        prompt_catalog: ToolPromptCatalog,
    ) -> None:
        self._tool_service = tool_service
        self._prompt_catalog = prompt_catalog

    def children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        if request.node.id == "tools.available":
            bundles = _available_bundles(
                request.workspace.metadata,
                self._prompt_catalog,
            )
            return tuple(
                _tool_bundle_node_seed(
                    bundle,
                    parent_id=request.node.id,
                    display_order=index * 10,
                )
                for index, bundle in enumerate(bundles, start=1)
            )
        if request.node.kind not in {"tool_bundle", "tool_bundle_group"}:
            return ()
        source_id = _optional_text(request.node.owner_ref.get("source_id"))
        if source_id is None:
            return ()
        bundles = _available_bundles(
            request.workspace.metadata,
            self._prompt_catalog,
        )
        bundle = next(
            (item for item in bundles if item.source_id == source_id),
            None,
        )
        if bundle is None:
            return ()
        tools_by_id = _available_tools_by_id(
            request.workspace.metadata,
            self._tool_service,
        )
        if request.node.kind == "tool_bundle_group":
            group_key = _optional_text(request.node.owner_ref.get("group_key"))
            if group_key is None:
                return ()
            group = next(
                (item for item in bundle.groups if item.group_key == group_key),
                None,
            )
            if group is None:
                return ()
            return _tool_function_children(
                tools=_tools_for_function_ids(group.function_ids, tools_by_id),
                parent_id=request.node.id,
            )
        return _tool_bundle_children(
            bundle=bundle,
            tools_by_id=tools_by_id,
            parent_id=request.node.id,
        )


@dataclass(frozen=True, slots=True)
class _ToolGroup:
    key: str
    title: str
    description: str
    tools: tuple[Tool, ...]


_TOOL_ACTIONS = (
    ContextAction.EXPAND,
    ContextAction.COLLAPSE,
    ContextAction.PIN,
    ContextAction.UNPIN,
    ContextAction.ENABLE_TOOL_SCHEMA,
    ContextAction.DISABLE_TOOL_SCHEMA,
    ContextAction.ESTIMATE,
)

_TOOL_BUNDLE_ACTIONS = (
    ContextAction.EXPAND,
    ContextAction.COLLAPSE,
    ContextAction.PIN,
    ContextAction.UNPIN,
    ContextAction.ESTIMATE,
)


def _tool_bundle_node_seed(
    bundle: ToolPromptBundle,
    *,
    parent_id: str,
    display_order: int,
) -> ContextNodeSeed:
    summary = _bundle_summary(bundle)
    return ContextNodeSeed(
        node_id=_tool_bundle_node_id(bundle.source_id),
        parent_id=parent_id,
        owner="tool",
        kind="tool_bundle",
        title=bundle.title,
        summary=summary,
        state=ContextNodeState(
            collapsed=_bundle_collapsed(bundle),
            loaded=True,
        ),
        actions=_TOOL_BUNDLE_ACTIONS,
        owner_ref={
            "source_id": bundle.source_id,
            "bundle_key": bundle.source_id,
            "function_count": bundle.function_count,
        },
        estimate=_text_estimate(summary),
        revision=TOOL_CONTEXT_PROMPT_REVISION,
        display_order=display_order,
        metadata={
            "source_id": bundle.source_id,
            "source_kind": bundle.source_kind,
            "function_count": bundle.function_count,
            "credential_requirement_count": bundle.credential_requirement_count,
            "runtime_requirement_count": bundle.runtime_requirement_count,
            "capability_ids": list(bundle.capability_ids),
            **dict(bundle.metadata),
        },
    )


def _tool_bundle_group_node_seed(
    bundle: ToolPromptBundle,
    group: ToolPromptBundleGroup,
    *,
    parent_id: str,
    display_order: int,
) -> ContextNodeSeed:
    summary = _bundle_group_summary(group)
    return ContextNodeSeed(
        node_id=_tool_bundle_group_node_id(bundle.source_id, group.group_key),
        parent_id=parent_id,
        owner="tool",
        kind="tool_bundle_group",
        title=group.title,
        summary=summary,
        state=ContextNodeState(
            collapsed=_bundle_group_collapsed(bundle, group),
            loaded=True,
        ),
        actions=_TOOL_BUNDLE_ACTIONS,
        owner_ref={
            "source_id": bundle.source_id,
            "group_key": group.group_key,
            "function_count": group.function_count,
            "function_ids": list(group.function_ids),
        },
        estimate=_text_estimate(summary),
        revision=TOOL_CONTEXT_PROMPT_REVISION,
        display_order=display_order,
        metadata={
            "source_id": bundle.source_id,
            "source_kind": bundle.source_kind,
            "group_key": group.group_key,
            "function_count": group.function_count,
            "capability_ids": list(group.capability_ids),
            **dict(group.metadata),
        },
    )


def _bundle_summary(bundle: ToolPromptBundle) -> str:
    parts = [
        bundle.summary.strip(),
        f"Contains {bundle.function_count} tool "
        f"{'function' if bundle.function_count == 1 else 'functions'}.",
    ]
    if bundle.credential_requirement_count:
        parts.append(
            f"Credential slots: {bundle.credential_requirement_count}.",
        )
    if bundle.runtime_requirement_count:
        parts.append(
            f"Runtime requirements: {bundle.runtime_requirement_count}.",
        )
    return " ".join(part for part in parts if part)


def _bundle_group_summary(group: ToolPromptBundleGroup) -> str:
    parts = [
        group.summary.strip(),
        f"Contains {group.function_count} tool "
        f"{'function' if group.function_count == 1 else 'functions'}.",
    ]
    return " ".join(part for part in parts if part)


def _bundle_collapsed(bundle: ToolPromptBundle) -> bool:
    return not bundle.source_id.endswith(".context_tree")


def _bundle_group_collapsed(
    bundle: ToolPromptBundle,
    group: ToolPromptBundleGroup,
) -> bool:
    if (
        bundle.source_id.endswith(".context_tree")
        and bool(group.metadata.get("auto_source_group"))
    ):
        return False
    return True


def _tool_bundle_children(
    *,
    bundle: ToolPromptBundle,
    tools_by_id: dict[str, Tool],
    parent_id: str,
) -> tuple[ContextNodeSeed, ...]:
    explicit_groups = tuple(
        group for group in bundle.groups if not _is_auto_source_group(group)
    )
    if not explicit_groups:
        return _tool_function_children(
            tools=_tools_for_function_ids(bundle.function_ids, tools_by_id),
            parent_id=parent_id,
        )

    seeds: list[ContextNodeSeed] = []
    display_index = 1
    grouped_function_ids = {
        function_id for group in explicit_groups for function_id in group.function_ids
    }
    for group in explicit_groups:
        seeds.append(
            _tool_bundle_group_node_seed(
                bundle,
                group,
                parent_id=parent_id,
                display_order=display_index * 10,
            ),
        )
        display_index += 1

    ungrouped_tools = _tools_for_function_ids(
        tuple(
            function_id
            for function_id in bundle.function_ids
            if function_id not in grouped_function_ids
        ),
        tools_by_id,
    )
    direct_children = _tool_function_children(
        tools=ungrouped_tools,
        parent_id=parent_id,
        display_start=display_index,
    )
    return (*seeds, *direct_children)


def _is_auto_source_group(group: ToolPromptBundleGroup) -> bool:
    return bool(group.metadata.get("auto_source_group"))


def _tool_function_children(
    *,
    tools: tuple[Tool, ...],
    parent_id: str,
    display_start: int = 1,
) -> tuple[ContextNodeSeed, ...]:
    seeds: list[ContextNodeSeed] = []
    display_index = display_start
    cli_sources = _cli_source_groups(tools)
    for source in cli_sources:
        seeds.append(
            _cli_source_node_seed(
                source,
                parent_id=parent_id,
                display_order=display_index * 10,
            ),
        )
        display_index += 1
    for tool in _sort_tools(tool for tool in tools if not _is_cli_source_function(tool)):
        seeds.append(
            _tool_node_seed(
                tool,
                parent_id=parent_id,
                display_order=display_index * 10,
            ),
        )
        display_index += 1
    return tuple(seeds)


def _tools_for_function_ids(
    function_ids: tuple[str, ...],
    tools_by_id: dict[str, Tool],
) -> tuple[Tool, ...]:
    return tuple(
        tools_by_id[function_id]
        for function_id in function_ids
        if function_id in tools_by_id
    )


def _tool_node_seed(
    tool: Tool,
    *,
    parent_id: str,
    display_order: int,
) -> ContextNodeSeed:
    parameter_names = [parameter.name for parameter in tool.parameters]
    summary_parts = [tool.description]
    if parameter_names:
        summary_parts.append(f"Parameters: {', '.join(parameter_names)}")
    if tool.required_effect_ids:
        summary_parts.append(f"Effects: {', '.join(tool.required_effect_ids)}")
    if tool.access_requirements:
        summary_parts.append(f"Access: {', '.join(tool.access_requirements)}")
    summary = " ".join(part.strip() for part in summary_parts if part.strip())
    return ContextNodeSeed(
        node_id=f"tools.tool.{_node_token(tool.id)}",
        parent_id=parent_id,
        owner="tool",
        kind="tool_function",
        title=tool.id,
        summary=_truncate(summary, 520),
        state=ContextNodeState(
            schema_enabled=_schema_enabled_by_default(tool),
            loaded=True,
        ),
        actions=_TOOL_ACTIONS,
        owner_ref={
            "tool_id": tool.id,
            "tool_name": tool.name,
            "source_id": tool.source_id,
            "runtime_key": tool.resolved_runtime_key(),
        },
        estimate=_tool_estimate(tool, summary),
        revision=TOOL_CONTEXT_PROMPT_REVISION,
        display_order=display_order,
        metadata={
            "display_name": tool.name,
            "tags": list(tool.tags),
            "parameter_count": len(tool.parameters),
            "required_effect_ids": list(tool.required_effect_ids),
            "access_requirements": list(tool.access_requirements),
            "context_requirements": list(tool.context_requirements),
            "capability_ids": list(tool.capability_ids),
            "schema_default_enabled": _schema_enabled_by_default(tool),
            "provider_schema": _provider_tool_schema(tool),
        },
    )


def _cli_source_node_seed(
    source: _ToolGroup,
    *,
    parent_id: str,
    display_order: int,
) -> ContextNodeSeed:
    source_id = source.key
    hidden_function_ids = tuple(tool.id for tool in source.tools)
    title = _cli_source_title(source_id, source.tools)
    summary = (
        f"CLI source '{title}' is available as command-line guidance, not as "
        "provider tool functions. Use the Command Execution tools, especially "
        "exec, to inspect help, build arguments, run commands, and read output."
    )
    return ContextNodeSeed(
        node_id=f"tools.cli_source.{_node_token(source_id)}",
        parent_id=parent_id,
        owner="tool",
        kind="tool_cli_source",
        title=title,
        summary=summary,
        state=ContextNodeState(loaded=True),
        actions=(ContextAction.PIN, ContextAction.UNPIN, ContextAction.ESTIMATE),
        owner_ref={
            "source_id": source_id,
            "execution_tool_id": "exec",
            "hidden_function_ids": list(hidden_function_ids),
        },
        estimate=_text_estimate(summary),
        revision=TOOL_CONTEXT_PROMPT_REVISION,
        display_order=display_order,
        metadata={
            "source_kind": "cli",
            "source_id": source_id,
            "execution_path": "command_execution.exec",
            "hidden_function_ids": list(hidden_function_ids),
        },
    )


def _available_bundles(
    metadata: dict[str, object],
    prompt_catalog: ToolPromptCatalog,
) -> tuple[ToolPromptBundle, ...]:
    return prompt_catalog.list_prompt_bundles(_available_tool_names(metadata))


def _available_tools_by_id(
    metadata: dict[str, object],
    tool_service: ToolContextService,
) -> dict[str, Tool]:
    return tool_service.get_tools(_available_tool_names(metadata))


def _available_tool_names(metadata: dict[str, object]) -> tuple[str, ...]:
    raw_names = metadata.get("available_tool_names")
    if not isinstance(raw_names, Iterable) or isinstance(raw_names, (str, bytes)):
        return ()
    names: list[str] = []
    for item in raw_names:
        normalized = _optional_text(item)
        if normalized is not None and normalized not in names:
            names.append(normalized)
    return tuple(names)


def _cli_source_groups(tools: tuple[Tool, ...]) -> tuple[_ToolGroup, ...]:
    grouped: dict[str, list[Tool]] = {}
    for tool in tools:
        if not _is_cli_source_function(tool):
            continue
        grouped.setdefault(tool.source_id or "configured.cli", []).append(tool)
    return tuple(
        _ToolGroup(
            key=source_id,
            title=_cli_source_title(source_id, source_tools),
            description="CLI source command guidance.",
            tools=tuple(_sort_tools(source_tools)),
        )
        for source_id, source_tools in sorted(grouped.items())
    )


def _is_cli_source_function(tool: Tool) -> bool:
    tags = set(tool.tags)
    source_id = (tool.source_id or "").lower()
    return "cli" in tags or ".cli." in source_id


def _cli_source_title(source_id: str, tools: Iterable[Tool]) -> str:
    for tool in tools:
        for tag in tool.tags:
            if tag not in {"cli", "guided", "builtin", "system-managed"}:
                return tag
    normalized = source_id.rsplit(".", 1)[-1].strip()
    return normalized or "CLI Source"


def _sort_tools(tools: Iterable[Tool]) -> tuple[Tool, ...]:
    return tuple(sorted(tools, key=lambda tool: (tool.name.lower(), tool.id.lower())))


def _schema_enabled_by_default(tool: Tool) -> bool:
    return (
        tool.id.startswith("context_tree.")
        or tool.source_id.endswith(".context_tree")
        or "context_tree" in tool.tags
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _node_token(value: str) -> str:
    return quote(value.strip(), safe="")


def _tool_bundle_node_id(source_id: str) -> str:
    return f"tools.bundle.{_node_token(source_id)}"


def _tool_bundle_group_node_id(source_id: str, group_key: str) -> str:
    return f"{_tool_bundle_node_id(source_id)}.group.{_node_token(group_key)}"


def _tool_estimate(tool: Tool, summary: str) -> ContextEstimate:
    schema_chars = sum(
        len(parameter.name) + len(parameter.description) + len(parameter.data_type)
        for parameter in tool.parameters
    )
    return ContextEstimate(
        text_chars=len(summary),
        text_tokens=max((len(summary) + 3) // 4, 1) if summary else 0,
        tool_schema_tokens=max((schema_chars + 3) // 4, 1) if schema_chars else 0,
        provider_attachment_count=1,
    )


def _text_estimate(text: str) -> ContextEstimate:
    normalized = text or ""
    return ContextEstimate(
        text_chars=len(normalized),
        text_tokens=max((len(normalized) + 3) // 4, 1) if normalized else 0,
    )


def _provider_tool_schema(tool: Tool) -> dict[str, object]:
    properties: dict[str, object] = {}
    required: list[str] = []
    for parameter in tool.parameters:
        schema = _parameter_schema(parameter.data_type)
        schema["description"] = parameter.description
        properties[parameter.name] = schema
        if parameter.required:
            required.append(parameter.name)
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": True,
    }
    if required:
        input_schema["required"] = required
    return {
        "name": tool.id,
        "description": tool.description,
        "input_schema": input_schema,
    }


def _parameter_schema(data_type: str) -> dict[str, object]:
    normalized = data_type.strip().lower()
    if normalized.startswith("array[") and normalized.endswith("]"):
        item_type = normalized[6:-1].strip() or "string"
        return {
            "type": "array",
            "items": _parameter_schema(item_type),
        }
    if normalized in {"integer", "int"}:
        return {"type": "integer"}
    if normalized in {"number", "float", "double"}:
        return {"type": "number"}
    if normalized in {"boolean", "bool"}:
        return {"type": "boolean"}
    if normalized in {"object", "json"}:
        return {"type": "object"}
    return {"type": "string"}


def _truncate(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + "..."


__all__ = ["ToolContextNodeProvider"]
