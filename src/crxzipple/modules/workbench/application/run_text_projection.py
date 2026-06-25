from __future__ import annotations

from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.workbench.application.projection_helpers import (
    metadata_str,
    optional_text,
    truncate,
)
from crxzipple.shared.content_blocks import describe_content_for_text_fallback


def run_title(run: OrchestrationRun) -> str:
    for key in ("thread_title", "title", "summary"):
        value = metadata_str(run, key)
        if value is not None:
            return truncate(value, limit=72)
    return truncate(instruction_summary(run), limit=72) or run.id


def instruction_summary(run: OrchestrationRun) -> str:
    if run.inbound_instruction.source == "sessions_spawn_followup":
        followup_payload = run.metadata.get("sessions_spawn_followup")
        if isinstance(followup_payload, dict):
            child_session_key = optional_text(followup_payload.get("child_session_key"))
            child_run_id = optional_text(followup_payload.get("child_run_id"))
            if child_session_key is not None and child_run_id is not None:
                return f"Child session completed: {child_session_key} · {child_run_id}"
            if child_run_id is not None:
                return f"Child session completed: {child_run_id}"
        return "Child session completed."
    try:
        return describe_content_for_text_fallback(run.inbound_instruction.content)
    except Exception:
        return str(run.inbound_instruction.content or run.inbound_instruction.source)


def output_text(run: OrchestrationRun) -> str | None:
    if run.result_payload is None:
        return None
    value = run.result_payload.get("output_text")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
