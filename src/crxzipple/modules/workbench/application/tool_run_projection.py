from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.orchestration.application.ports import OrchestrationRunQueryPort
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.tool.domain import ToolRun
from crxzipple.modules.workbench.application.projection_helpers import (
    metadata_str,
    optional_text,
)


@dataclass(frozen=True, slots=True)
class DisplayToolRun:
    source_run: OrchestrationRun
    tool_run: ToolRun


def safe_list_tool_runs_for_runs(
    tool_query: Any | None,
    run_ids: tuple[str, ...],
) -> list[ToolRun] | None:
    if tool_query is None:
        return []
    normalized_ids = tuple(dict.fromkeys(run_id for run_id in run_ids if run_id))
    if not normalized_ids:
        return []
    scoped_list = getattr(tool_query, "list_tool_runs_for_orchestration_runs", None)
    if callable(scoped_list):
        try:
            return scoped_list(normalized_ids)
        except Exception:
            return None
    return safe_list_tool_runs(tool_query)


def safe_list_tool_runs(tool_query: Any | None) -> list[ToolRun] | None:
    if tool_query is None:
        return []
    try:
        return tool_query.list_tool_runs()
    except Exception:
        return None


def display_tool_runs(
    run_query: OrchestrationRunQueryPort,
    tool_query: Any | None,
    run: OrchestrationRun,
    *,
    candidate_runs: list[OrchestrationRun] | None = None,
    tool_runs: list[ToolRun] | None = None,
) -> tuple[DisplayToolRun, ...]:
    return tool_runs_for_runs(
        run_query,
        tool_query,
        display_source_runs(run_query, run, candidate_runs=candidate_runs),
        tool_runs=tool_runs,
    )


def display_source_runs(
    run_query: OrchestrationRunQueryPort,
    run: OrchestrationRun,
    *,
    candidate_runs: list[OrchestrationRun] | None = None,
) -> tuple[OrchestrationRun, ...]:
    runs = [run]
    seen = {run.id}
    for child_run in linked_child_runs(
        run_query,
        run,
        candidate_runs=candidate_runs,
    ):
        if child_run.id in seen:
            continue
        runs.append(child_run)
        seen.add(child_run.id)
    return tuple(runs)


def tool_scope_run_ids(
    run_query: OrchestrationRunQueryPort,
    runs: tuple[OrchestrationRun, ...],
    *,
    candidate_runs: list[OrchestrationRun] | None = None,
) -> tuple[str, ...]:
    scoped_ids: list[str] = []
    for run in runs:
        for source_run in display_source_runs(
            run_query,
            run,
            candidate_runs=candidate_runs,
        ):
            scoped_ids.append(source_run.id)
    return tuple(dict.fromkeys(scoped_ids))


def linked_child_runs(
    run_query: OrchestrationRunQueryPort,
    run: OrchestrationRun,
    *,
    candidate_runs: list[OrchestrationRun] | None = None,
) -> tuple[OrchestrationRun, ...]:
    children: list[OrchestrationRun] = []
    seen: set[str] = set()
    for child_run_id in linked_child_run_ids(run):
        if child_run_id == run.id or child_run_id in seen:
            continue
        try:
            children.append(run_query.get_run(child_run_id))
            seen.add(child_run_id)
        except Exception:
            continue
    candidates = candidate_runs
    if candidates is not None:
        for candidate in candidates:
            followup_payload = candidate.metadata.get("sessions_spawn_followup")
            if not isinstance(followup_payload, dict):
                continue
            requester_run_id = optional_text(followup_payload.get("requester_run_id"))
            if requester_run_id != run.id:
                continue
            child_run_id = optional_text(followup_payload.get("child_run_id"))
            if child_run_id is None or child_run_id == run.id or child_run_id in seen:
                continue
            try:
                children.append(run_query.get_run(child_run_id))
                seen.add(child_run_id)
            except Exception:
                continue
    if candidate_runs is None:
        try:
            candidates = run_query.list_runs()
        except Exception:
            candidates = []
    else:
        candidates = candidate_runs
    for candidate in candidates:
        if candidate.id == run.id or candidate.id in seen:
            continue
        spawn_payload = candidate.metadata.get("sessions_spawn")
        if not isinstance(spawn_payload, dict):
            continue
        requester_run_id = optional_text(spawn_payload.get("requester_run_id"))
        if requester_run_id != run.id:
            continue
        children.append(candidate)
        seen.add(candidate.id)
    return tuple(
        sorted(
            children,
            key=lambda item: item.started_at or item.created_at,
        ),
    )


def linked_child_run_ids(run: OrchestrationRun) -> tuple[str, ...]:
    ids: list[str] = []
    followup_payload = run.metadata.get("sessions_spawn_followup")
    if isinstance(followup_payload, dict):
        child_run_id = optional_text(followup_payload.get("child_run_id"))
        if child_run_id is not None:
            ids.append(child_run_id)
    child_run_id = metadata_str(run, "child_run_id")
    if child_run_id is not None:
        ids.append(child_run_id)
    return tuple(dict.fromkeys(ids))


def tool_runs_for_runs(
    run_query: OrchestrationRunQueryPort,
    tool_query: Any | None,
    runs: tuple[OrchestrationRun, ...],
    *,
    tool_runs: list[ToolRun] | None = None,
) -> tuple[DisplayToolRun, ...]:
    if tool_query is None:
        return ()
    if tool_runs is None:
        try:
            tool_runs = tool_query.list_tool_runs()
        except Exception:
            return ()
    if not tool_runs:
        return ()
    run_by_id = {run.id: run for run in runs}
    related: list[DisplayToolRun] = []
    seen_tool_run_ids: set[str] = set()
    for tool_run in tool_runs:
        metadata_run_id = tool_run_orchestration_run_id(tool_run)
        source_run = run_by_id.get(metadata_run_id or "")
        if source_run is None or tool_run.id in seen_tool_run_ids:
            continue
        related.append(DisplayToolRun(source_run=source_run, tool_run=tool_run))
        seen_tool_run_ids.add(tool_run.id)
    return tuple(
        sorted(
            related,
            key=lambda item: item.tool_run.started_at or item.tool_run.created_at,
        ),
    )


def tool_run_orchestration_run_id(tool_run: ToolRun) -> str | None:
    value = tool_run.metadata.get("orchestration_run_id")
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
