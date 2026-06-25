"""Run continuation metadata payloads for Context Workspace."""

from __future__ import annotations

from crxzipple.modules.orchestration.domain import OrchestrationRun

from ._metadata import metadata_text
from .run_workspace_metadata_values import public_payload_summary


def build_execution_continuation_payload(
    run: OrchestrationRun,
) -> dict[str, object]:
    pending_tool_run_ids = tuple(run.pending_tool_run_ids)
    pending_approval = (
        dict(run.pending_approval_request_payload)
        if run.pending_approval_request_payload is not None
        else None
    )
    last_approval = (
        dict(run.last_approval_resolution_payload)
        if run.last_approval_resolution_payload is not None
        else None
    )
    recovery_contract = (
        dict(run.recovery_contract_payload)
        if run.recovery_contract_payload is not None
        else None
    )
    lines = [
        f"Run status: {run.status.value}",
        f"Run stage: {run.stage.value}",
    ]
    if run.waiting_reason:
        lines.append(f"Waiting reason: {run.waiting_reason}")
    if pending_tool_run_ids:
        lines.append(
            "Pending background tool runs: "
            + ", ".join(pending_tool_run_ids),
        )
    if pending_approval is not None:
        lines.append(
            "Pending approval: "
            + public_payload_summary(
                pending_approval,
                keys=("request_id", "effect_id", "label"),
            ),
        )
    if last_approval is not None:
        lines.append(
            "Last approval resolution: "
            + public_payload_summary(
                last_approval,
                keys=("request_id", "decision", "resolved_at"),
            ),
        )
    if recovery_contract is not None:
        lines.append(
            "Recovery contract: "
            + public_payload_summary(
                recovery_contract,
                keys=("kind", "state", "source", "reason"),
            ),
        )
    if len(lines) == 2:
        lines.append("No pending public continuation state.")
    return {
        "summary": _execution_continuation_summary(
            pending_tool_run_count=len(pending_tool_run_ids),
            pending_approval=pending_approval is not None,
            recovery_contract=recovery_contract is not None,
        ),
        "content": "\n".join(lines),
        "metadata": {
            "status": run.status.value,
            "stage": run.stage.value,
            "waiting_reason": run.waiting_reason,
            "pending_tool_run_count": len(pending_tool_run_ids),
            "pending_tool_run_ids": list(pending_tool_run_ids),
            "pending_approval_request_id": (
                metadata_text(pending_approval.get("request_id"))
                if pending_approval is not None
                else None
            ),
            "last_approval_decision": (
                metadata_text(last_approval.get("decision"))
                if last_approval is not None
                else None
            ),
            "recovery_contract_kind": (
                metadata_text(recovery_contract.get("kind"))
                if recovery_contract is not None
                else None
            ),
        },
    }


def _execution_continuation_summary(
    *,
    pending_tool_run_count: int,
    pending_approval: bool,
    recovery_contract: bool,
) -> str:
    if pending_approval:
        return "Run is waiting for a public approval decision before it can continue."
    if pending_tool_run_count:
        return f"Run is waiting for {pending_tool_run_count} background tool run(s)."
    if recovery_contract:
        return "Run has a public recovery contract for continuation handling."
    return "No pending public continuation state for this run."
