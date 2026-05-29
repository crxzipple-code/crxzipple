"""Tool context tree adapter."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol
from urllib.parse import quote

from crxzipple.modules.context_workspace.application import ContextChildrenRequest
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextEstimate,
    ContextNodeSeed,
    ContextNodeState,
)
from crxzipple.modules.tool.domain import Tool, ToolError


class ToolContextService(Protocol):
    def get_tool(self, tool_id: str) -> Tool:
        ...


class ToolContextNodeProvider:
    owner = "tool"

    def __init__(self, tool_service: ToolContextService) -> None:
        self._tool_service = tool_service

    def children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        if request.node.id != "tools.available":
            return ()
        tool_names = _available_tool_names(request.workspace.metadata)
        if not tool_names:
            return ()
        tools: list[Tool] = []
        for name in tool_names:
            try:
                tools.append(self._tool_service.get_tool(name))
            except ToolError:
                continue
        return tuple(
            _tool_node_seed(tool, parent_id=request.node.id, display_order=index * 10)
            for index, tool in enumerate(tools, start=1)
        )


_TOOL_ACTIONS = (
    ContextAction.PIN,
    ContextAction.UNPIN,
    ContextAction.ENABLE_TOOL_SCHEMA,
    ContextAction.DISABLE_TOOL_SCHEMA,
    ContextAction.ESTIMATE,
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
        state=ContextNodeState(schema_enabled=True, loaded=True),
        actions=_TOOL_ACTIONS,
        owner_ref={
            "tool_id": tool.id,
            "tool_name": tool.name,
            "source_id": tool.source_id,
            "runtime_key": tool.resolved_runtime_key(),
        },
        estimate=_tool_estimate(tool, summary),
        display_order=display_order,
        metadata={
            "display_name": tool.name,
            "tags": list(tool.tags),
            "parameter_count": len(tool.parameters),
            "required_effect_ids": list(tool.required_effect_ids),
            "access_requirements": list(tool.access_requirements),
            "context_requirements": list(tool.context_requirements),
            "capability_ids": list(tool.capability_ids),
            "provider_schema": _provider_tool_schema(tool),
        },
    )


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


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _node_token(value: str) -> str:
    return quote(value.strip(), safe="")


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
