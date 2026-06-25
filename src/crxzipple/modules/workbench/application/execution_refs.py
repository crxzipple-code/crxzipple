from __future__ import annotations

from typing import Any

from crxzipple.modules.orchestration.application.ports import OrchestrationRunQueryPort
from crxzipple.modules.orchestration.domain import ExecutionStepItem, OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionStepItemKind,
    OrchestrationRunStatus,
)
from crxzipple.modules.workbench.application.execution_bundles import (
    execution_step_bundles,
)
from crxzipple.modules.workbench.application.execution_status import optional_text
from crxzipple.modules.workbench.application.execution_summary import (
    execution_item_owner_id,
    execution_item_summary,
    summary_text,
)


def llm_invocation_id_from_execution_items(
    items: tuple[ExecutionStepItem, ...],
) -> str | None:
    for item in items:
        if item.kind is not ExecutionStepItemKind.LLM_INVOCATION:
            continue
        owner_id = execution_item_owner_id(item, owner_kind="llm_invocation")
        if owner_id is not None:
            return owner_id
        summary_id = summary_text(execution_item_summary(item), "llm_invocation_id")
        if summary_id is not None:
            return summary_id
    return None


def tool_names_from_execution_items(
    items: tuple[ExecutionStepItem, ...],
) -> tuple[str, ...]:
    names: list[str] = []
    for item in items:
        if item.kind not in {
            ExecutionStepItemKind.TOOL_CALL,
            ExecutionStepItemKind.TOOL_RUN,
        }:
            continue
        summary = execution_item_summary(item)
        name = summary_text(summary, "tool_name") or summary_text(summary, "tool_id")
        if name is not None and name not in names:
            names.append(name)
    return tuple(names)


def tool_call_names_from_execution_items(
    items: tuple[ExecutionStepItem, ...],
) -> tuple[str, ...]:
    names: list[str] = []
    for item in items:
        summary = execution_item_summary(item)
        raw_names = summary.get("tool_call_names")
        if isinstance(raw_names, list | tuple):
            for raw_name in raw_names:
                if not isinstance(raw_name, str):
                    continue
                name = raw_name.strip()
                if name and name not in names:
                    names.append(name)
    return tuple(names)


def assistant_progress_session_item_ids_from_execution_items(
    items: tuple[ExecutionStepItem, ...],
) -> tuple[str, ...]:
    ids: list[str] = []
    for item in items:
        summary = execution_item_summary(item)
        if summary_text(summary, "message_kind") != "assistant_progress":
            continue
        raw_ids = summary.get("assistant_progress_item_ids")
        if not isinstance(raw_ids, list | tuple):
            raw_ids = summary.get("session_item_ids")
        if isinstance(raw_ids, list | tuple):
            for raw_id in raw_ids:
                if not isinstance(raw_id, str):
                    continue
                item_id = raw_id.strip()
                if item_id and item_id not in ids:
                    ids.append(item_id)
        item_id = summary_text(summary, "session_item_id")
        if item_id is not None and item_id not in ids:
            ids.append(item_id)
    return tuple(ids)


def tool_call_session_item_ids_from_execution_items(
    items: tuple[ExecutionStepItem, ...],
) -> tuple[str, ...]:
    ids: list[str] = []
    for item in items:
        summary = execution_item_summary(item)
        raw_ids = summary.get("tool_call_session_item_ids")
        if not isinstance(raw_ids, list | tuple):
            continue
        for raw_id in raw_ids:
            if not isinstance(raw_id, str):
                continue
            item_id = raw_id.strip()
            if item_id and item_id not in ids:
                ids.append(item_id)
    return tuple(ids)


def execution_tool_item_summary(
    summary: dict[str, object],
    item: ExecutionStepItem,
) -> str:
    tool_name = summary_text(summary, "tool_name") or summary_text(summary, "tool_id")
    status = summary_text(summary, "status") or item.status.value
    if tool_name is not None:
        return f"{tool_name} · status: {status}"
    return f"Tool run status: {status}"


def execution_tool_run_ids_for_run(
    run_query: OrchestrationRunQueryPort,
    turn_id: str,
) -> tuple[str, ...]:
    ids: list[str] = []
    for bundle in execution_step_bundles(run_query, turn_id):
        for item in bundle.items:
            if item.kind is not ExecutionStepItemKind.TOOL_RUN:
                continue
            tool_run_id = execution_item_owner_id(item, owner_kind="tool_run")
            if tool_run_id is not None and tool_run_id not in ids:
                ids.append(tool_run_id)
    return tuple(ids)


def execution_llm_invocation_ids_for_run(
    run_query: OrchestrationRunQueryPort,
    turn_id: str,
) -> tuple[str, ...]:
    ids: list[str] = []
    for bundle in execution_step_bundles(run_query, turn_id):
        invocation_id = llm_invocation_id_from_execution_items(bundle.items)
        if invocation_id is not None and invocation_id not in ids:
            ids.append(invocation_id)
    return tuple(ids)


def safe_llm_invocation(
    llm_query: Any | None,
    invocation_id: str | None,
) -> Any | None:
    if invocation_id is None or llm_query is None:
        return None
    try:
        return llm_query.get_invocation(invocation_id)
    except Exception:
        return None


def llm_invocations_for_runs(
    run_query: OrchestrationRunQueryPort,
    llm_query: Any | None,
    runs: tuple[OrchestrationRun, ...],
) -> tuple[Any, ...]:
    if llm_query is None:
        return ()
    invocations: list[Any] = []
    seen: set[str] = set()
    for run in runs:
        if not run_may_have_execution_items(run):
            continue
        for invocation_id in execution_llm_invocation_ids_for_run(run_query, run.id):
            if invocation_id in seen:
                continue
            invocation = safe_llm_invocation(llm_query, invocation_id)
            resolved_invocation_id = optional_text(getattr(invocation, "id", None))
            if invocation is None or resolved_invocation_id is None:
                continue
            invocations.append(invocation)
            seen.add(resolved_invocation_id)
    return tuple(invocations)


def run_may_have_execution_items(run: OrchestrationRun) -> bool:
    if run.current_step > 0:
        return True
    if run.pending_tool_run_ids:
        return True
    return run.status not in {
        OrchestrationRunStatus.ACCEPTED,
        OrchestrationRunStatus.QUEUED,
    }
