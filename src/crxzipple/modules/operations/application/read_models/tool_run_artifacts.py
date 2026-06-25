from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.tool_run_artifact_refs import (
    tool_run_artifact_refs,
)
from crxzipple.modules.operations.application.read_models.tool_run_time import (
    tool_run_time,
)
from crxzipple.modules.tool.domain import ToolRun
from crxzipple.shared.time import format_datetime_utc


@dataclass(frozen=True, slots=True)
class ToolArtifactRunContext:
    tool_label: str
    trace: str
    trace_route: str


def recent_artifacts_section(
    runs: list[ToolRun],
    *,
    run_contexts: Mapping[str, ToolArtifactRunContext],
    artifact_service: Any | None,
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for run in sorted(runs, key=tool_run_time, reverse=True):
        context = run_contexts[run.id]
        for artifact in tool_run_artifact_refs(
            run,
            artifact_service=artifact_service,
        ):
            artifact_id = artifact["artifact_id"]
            rows.append(
                OperationsTableRowModel(
                    id=f"{run.id}:{artifact_id}",
                    cells={
                        "name": artifact["name"],
                        "kind": artifact["kind"],
                        "artifact_id": artifact_id,
                        "mime_type": artifact["mime_type"],
                        "size": artifact["size"],
                        "dimensions": artifact["dimensions"],
                        "tool": context.tool_label,
                        "run_id": run.id,
                        "time": format_datetime_utc(tool_run_time(run)),
                        "actions": "Open / Trace",
                        "route": (
                            artifact["preview_url"]
                            or artifact["download_url"]
                            or "-"
                        ),
                        "trace": context.trace,
                        "trace_route": context.trace_route,
                    },
                    status=artifact["kind"],
                    tone="info",
                ),
            )
    return OperationsTableSectionModel(
        id="recent_artifacts",
        title="Recent Artifacts",
        columns=_columns(
            ("name", "Name"),
            ("kind", "Kind"),
            ("artifact_id", "Artifact ID"),
            ("mime_type", "Mime Type"),
            ("size", "Size"),
            ("dimensions", "Dimensions"),
            ("tool", "Tool"),
            ("run_id", "Run ID"),
            ("time", "Time"),
            ("actions", "Actions"),
        ),
        rows=tuple(rows[:50]),
        total=len(rows),
        view_all_route="/operations/tool?tab=artifacts",
        empty_state="No tool artifacts observed.",
    )


def tool_run_artifacts_section(
    run: ToolRun,
    *,
    context: ToolArtifactRunContext,
    artifact_service: Any | None,
) -> OperationsTableSectionModel:
    rows = tuple(
        OperationsTableRowModel(
            id=f"{run.id}:{artifact['artifact_id']}",
            cells={
                "name": artifact["name"],
                "kind": artifact["kind"],
                "artifact_id": artifact["artifact_id"],
                "mime_type": artifact["mime_type"],
                "size": artifact["size"],
                "dimensions": artifact["dimensions"],
                "tool": context.tool_label,
                "actions": "Open",
                "route": artifact["preview_url"] or artifact["download_url"] or "-",
                "trace": context.trace,
                "trace_route": context.trace_route,
            },
            status=artifact["kind"],
            tone="info",
        )
        for artifact in tool_run_artifact_refs(
            run,
            artifact_service=artifact_service,
        )
    )
    return OperationsTableSectionModel(
        id="run_artifacts",
        title="Artifacts",
        columns=_columns(
            ("name", "Name"),
            ("kind", "Kind"),
            ("artifact_id", "Artifact ID"),
            ("mime_type", "Mime Type"),
            ("size", "Size"),
            ("dimensions", "Dimensions"),
            ("actions", "Actions"),
        ),
        rows=rows,
        total=len(rows),
        empty_state="No artifacts recorded for this run.",
    )


def _columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(
        OperationsTableColumnModel(key=key, label=label) for key, label in items
    )
