from __future__ import annotations

from crxzipple.modules.orchestration.domain import (
    ApprovalDecision,
    OrchestrationRun,
    PendingApprovalRequest,
)
from crxzipple.modules.tool.domain import ToolRunStatus


def recovery_contract_payload(
    run: OrchestrationRun,
) -> dict[str, object] | None:
    return (
        dict(run.recovery_contract_payload)
        if run.recovery_contract_payload is not None
        else None
    )


def approval_recovery_contract_payload(
    *,
    request: PendingApprovalRequest,
    state: str,
    decision: ApprovalDecision | None = None,
    pending_tool_run_ids: tuple[str, ...] = (),
    tool_result_item_ids: tuple[str, ...] = (),
    llm_invocation_id: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": "approval",
        "state": state,
        "request": request.to_payload(),
    }
    if llm_invocation_id is not None and llm_invocation_id.strip():
        payload["llm_invocation_id"] = llm_invocation_id.strip()
    if decision is not None:
        payload["decision"] = decision.value
    if pending_tool_run_ids:
        payload["pending_tool_run_ids"] = list(pending_tool_run_ids)
    if tool_result_item_ids:
        payload["tool_result_item_ids"] = list(tool_result_item_ids)
    return payload


def tool_wait_recovery_contract_payload(
    *,
    pending_tool_run_ids: tuple[str, ...],
    source: str,
) -> dict[str, object]:
    return {
        "kind": "tool_wait",
        "state": "waiting_on_tool",
        "source": source,
        "pending_tool_run_ids": list(pending_tool_run_ids),
    }


def resume_reason_from_tool_runs(tool_runs: tuple[object, ...]) -> str:
    for tool_run in tool_runs:
        status = getattr(tool_run, "status", None)
        if status is ToolRunStatus.FAILED:
            return "tool_failed_results_ready"
        if status in {
            ToolRunStatus.CANCELLED,
            ToolRunStatus.TIMED_OUT,
        }:
            return "tool_terminal_results_ready"
    return "tool_results_ready"


def tool_run_terminal_summary(tool_run: object) -> dict[str, object]:
    target = getattr(tool_run, "target", None)
    completed_at = getattr(tool_run, "completed_at", None)
    payload: dict[str, object] = {
        "tool_id": getattr(tool_run, "tool_id", None),
        "function_id": getattr(tool_run, "function_id", None),
        "source_id": getattr(tool_run, "source_id", None),
        "mode": enum_value(getattr(target, "mode", None)),
        "strategy": enum_value(getattr(target, "strategy", None)),
        "environment": enum_value(getattr(target, "environment", None)),
    }
    if completed_at is not None and hasattr(completed_at, "isoformat"):
        payload["completed_at"] = completed_at.isoformat()
    return {key: value for key, value in payload.items() if value is not None}


def enum_value(value: object) -> str:
    raw_value = getattr(value, "value", value)
    return raw_value if isinstance(raw_value, str) else str(raw_value)


def approval_llm_invocation_id(
    contract: dict[str, object],
) -> str | None:
    return optional_text(contract.get("llm_invocation_id"))


def optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
