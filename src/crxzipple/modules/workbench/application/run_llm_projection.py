from __future__ import annotations

from typing import Any

from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationRunStage,
    OrchestrationRunStatus,
)
from crxzipple.modules.workbench.application.projection_helpers import (
    metadata_str,
    optional_text,
)


def llm_id(run: OrchestrationRun) -> str | None:
    if run.result_payload is not None:
        value = run.result_payload.get("llm_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return metadata_str(run, "requested_llm_id")


def llm_summary(run: OrchestrationRun, *, llm_invocation: Any | None = None) -> str:
    invocation_usage = llm_invocation_token_total(llm_invocation)
    finish_reason = optional_text(
        getattr(getattr(llm_invocation, "result", None), "finish_reason", None),
    )
    if invocation_usage is not None and finish_reason is not None:
        return f"Model response used {invocation_usage} tokens and finished with {finish_reason}."
    if invocation_usage is not None:
        return f"Model response used {invocation_usage} tokens."
    invocation_status = getattr(getattr(llm_invocation, "status", None), "value", None)
    if isinstance(invocation_status, str) and invocation_status == "failed":
        error = getattr(llm_invocation, "error", None)
        message = optional_text(getattr(error, "message", None))
        return message or "Model invocation failed."
    if run.stage is OrchestrationRunStage.LLM:
        return "Model invocation is in progress."
    if run.status in {OrchestrationRunStatus.COMPLETED, OrchestrationRunStatus.WAITING}:
        return "Model response was processed by orchestration."
    return f"Run stage: {run.stage.value}."


def llm_invocation_token_total(invocation: Any | None) -> int | None:
    if invocation is None:
        return None
    result = getattr(invocation, "result", None)
    usage = getattr(result, "usage", None)
    if usage is None:
        return None
    total = getattr(usage, "total_tokens", None)
    if isinstance(total, int) and total >= 0:
        return total
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    parts = [item for item in (input_tokens, output_tokens) if isinstance(item, int)]
    return sum(parts) if parts else None


def llm_step_status(run: OrchestrationRun) -> str:
    if run.status is OrchestrationRunStatus.FAILED:
        return "failed"
    if run.stage is OrchestrationRunStage.LLM:
        return "running"
    if run.status is OrchestrationRunStatus.WAITING:
        return "success"
    if run.status is OrchestrationRunStatus.COMPLETED:
        return "success"
    return "running" if run.status is OrchestrationRunStatus.RUNNING else run.status.value
