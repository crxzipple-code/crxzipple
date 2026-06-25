from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.domain import LlmInvocation
from crxzipple.modules.operations.application.read_models.llm_run_context_execution import (
    execution_owner_context,
)
from crxzipple.modules.operations.application.read_models.routes import (
    workbench_trace_route,
)
from crxzipple.shared.time import format_datetime_utc


def invocation_run_contexts(
    run_query: Any | None,
    invocations: list[LlmInvocation],
) -> dict[str, dict[str, str]]:
    contexts: dict[str, dict[str, str]] = {}
    for invocation in invocations:
        runtime_context = _invocation_runtime_context(invocation)
        if runtime_context:
            contexts[invocation.id] = runtime_context
        if run_query is None or not hasattr(
            run_query,
            "find_execution_step_items_by_owner",
        ):
            continue
        execution_context = execution_owner_context(
            run_query,
            invocation.id,
        )
        if not execution_context:
            continue
        existing = contexts.get(invocation.id)
        if existing is None:
            contexts[invocation.id] = execution_context
            continue
        merged = dict(existing)
        merged.update(
            {
                key: value
                for key, value in execution_context.items()
                if value not in ("", "-")
            },
        )
        if execution_context.get("updated_at", "") > existing.get("updated_at", ""):
            merged["updated_at"] = execution_context.get("updated_at", "")
        contexts[invocation.id] = merged
    return {
        invocation_id: {
            key: value
            for key, value in context.items()
            if key != "updated_at"
        }
        for invocation_id, context in contexts.items()
    }


def _invocation_runtime_context(invocation: LlmInvocation) -> dict[str, str]:
    run_id = _text(invocation.run_id)
    if run_id is None:
        return {}
    trace_id = run_id
    return {
        "run_id": run_id,
        "turn_id": run_id,
        "trace_id": trace_id,
        "session_key": _text(invocation.session_key) or "-",
        "agent_id": _text(invocation.agent_id) or "-",
        "active_session_id": _text(invocation.active_session_id) or "-",
        "route": f"/ui/workbench/runs/{run_id}",
        "trace_route": workbench_trace_route(trace_id, focus_id=invocation.id),
        "chain_id": "-",
        "step_id": "-",
        "step_kind": "-",
        "step_status": "-",
        "item_status": "-",
        "updated_at": format_datetime_utc(invocation.created_at),
    }


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return str(value)
    return None

