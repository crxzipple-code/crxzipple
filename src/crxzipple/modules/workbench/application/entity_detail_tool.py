from __future__ import annotations

from crxzipple.modules.workbench.application.entity_detail_values import (
    enum_or_text,
    iso_or_none,
    optional_dict,
)


def tool_run_detail_payload(tool_run: object) -> dict[str, object]:
    result = getattr(tool_run, "result", None)
    error = getattr(tool_run, "error", None)
    envelope = getattr(tool_run, "result_envelope_payload", None)
    envelope_payload = dict(envelope) if isinstance(envelope, dict) else None
    payload: dict[str, object] = {
        "id": getattr(tool_run, "id", None),
        "kind": "tool_run",
        "tool_id": getattr(tool_run, "tool_id", None),
        "call_id": getattr(tool_run, "call_id", None),
        "tool_surface_id": getattr(tool_run, "tool_surface_id", None),
        "function_id": getattr(tool_run, "function_id", None),
        "source_id": getattr(tool_run, "source_id", None),
        "schema_hash": getattr(tool_run, "schema_hash", None),
        "status": enum_or_text(getattr(tool_run, "status", None)),
        "input_payload": dict(getattr(tool_run, "input_payload", {}) or {}),
        "metadata": dict(getattr(tool_run, "metadata", {}) or {}),
        "invocation_context_payload": optional_dict(
            getattr(tool_run, "invocation_context_payload", None),
        ),
        "result_payload": result.to_payload() if result is not None else None,
        "result_summary": _tool_run_result_summary(result, error=error),
        "result_envelope": envelope_payload,
        "read_handles": _tool_result_envelope_list(envelope_payload, "read_handles"),
        "raw_output_blocks": _tool_result_envelope_list(
            envelope_payload,
            "raw_output_blocks",
        ),
        "artifact_refs": _tool_result_envelope_list(envelope_payload, "artifact_refs"),
        "evidence_refs": _tool_result_envelope_list(envelope_payload, "evidence_refs"),
        "created_at": iso_or_none(getattr(tool_run, "created_at", None)),
        "started_at": iso_or_none(getattr(tool_run, "started_at", None)),
        "completed_at": iso_or_none(getattr(tool_run, "completed_at", None)),
        "attempt_count": getattr(tool_run, "attempt_count", None),
        "max_attempts": getattr(tool_run, "max_attempts", None),
        "worker_id": getattr(tool_run, "worker_id", None),
    }
    if error is not None:
        payload["error"] = error.to_payload()
    return {key: value for key, value in payload.items() if value is not None}


def _tool_run_result_summary(result: object | None, *, error: object | None) -> str:
    if error is not None:
        message = getattr(error, "message", None)
        return str(message or "Tool run failed.")
    if result is None:
        return "Tool run has no result yet."
    blocks = getattr(result, "blocks", ())
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text = str(block.get("text") or "").strip()
            if text:
                return text[:240]
    return "Tool completed."


def _tool_result_envelope_list(
    envelope: dict[str, object] | None,
    key: str,
) -> list[object]:
    if envelope is None:
        return []
    value = envelope.get(key)
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []
