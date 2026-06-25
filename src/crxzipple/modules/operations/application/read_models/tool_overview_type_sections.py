from __future__ import annotations

from collections import Counter

from crxzipple.modules.operations.application.read_models.models import (
    OperationsChartSectionModel,
    OperationsChartSegmentModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    title_label,
)
from crxzipple.modules.tool.domain import Tool, ToolRun


def tool_types_section(
    tools: list[Tool],
    runs: list[ToolRun],
) -> OperationsChartSectionModel:
    tools_by_id = tool_lookup(tools)
    counts: Counter[str] = Counter()
    if runs:
        for run in runs:
            counts[run.tool_id] += 1
        total = len(runs)
        title = "Tool Call Share"
        segments = tool_call_share_segments(counts, tools_by_id=tools_by_id)
    else:
        for tool in tools:
            counts[tool.kind.value] += 1
        total = len(tools)
        title = "Tool Types by Catalog"
        segments = tuple(
            OperationsChartSegmentModel(
                id=kind,
                label=title_label(kind),
                value=count,
                tone=tone_for_kind(kind),
            )
            for kind, count in sorted(counts.items())
            if count > 0
        )
    return OperationsChartSectionModel(
        id="tool_types",
        title=title,
        kind="donut",
        total=total,
        segments=segments,
    )


def tool_call_share_segments(
    counts: Counter[str],
    *,
    tools_by_id: dict[str, Tool],
) -> tuple[OperationsChartSegmentModel, ...]:
    ranked = sorted(
        ((tool_id, count) for tool_id, count in counts.items() if count > 0),
        key=lambda item: (-item[1], tool_label_from_id(item[0], tools_by_id)),
    )
    visible = ranked[:7]
    hidden = ranked[7:]
    segments = [
        OperationsChartSegmentModel(
            id=tool_id,
            label=tool_display_name_from_id(tool_id, tools_by_id),
            value=count,
            tone=tone_for_tool_rank(index),
        )
        for index, (tool_id, count) in enumerate(visible)
    ]
    hidden_total = sum(count for _, count in hidden)
    if hidden_total:
        segments.append(
            OperationsChartSegmentModel(
                id="__other_tools",
                label="Other Tools",
                value=hidden_total,
                tone="neutral",
            ),
        )
    return tuple(segments)


def tool_label_from_id(
    tool_id: str | None,
    tools_by_id: dict[str, Tool],
) -> str:
    if tool_id is None:
        return "-"
    tool = tools_by_id.get(tool_id)
    if tool is None:
        return tool_id
    return tool.id if tool.id == tool.name else f"{tool.name} ({tool.id})"


def tool_display_name_from_id(
    tool_id: str | None,
    tools_by_id: dict[str, Tool],
) -> str:
    if tool_id is None:
        return "-"
    tool = tools_by_id.get(tool_id)
    if tool is None:
        return tool_id
    return tool.name


def tool_lookup(tools: list[Tool]) -> dict[str, Tool]:
    return {tool.id: tool for tool in tools}


def tone_for_kind(kind: str) -> str:
    return {
        "function": "info",
        "http": "success",
        "mcp": "warning",
        "workflow": "neutral",
        "unknown": "danger",
    }.get(kind, "neutral")


def tone_for_tool_rank(index: int) -> str:
    return ("info", "success", "warning", "neutral")[index % 4]
