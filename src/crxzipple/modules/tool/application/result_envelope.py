from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

TOOL_RESULT_ENVELOPE_METADATA_KEY = "tool_result_envelope"
TOOL_RESULT_RAW_OUTPUT_BLOCKS_METADATA_KEY = "tool_result_raw_output_blocks"


@dataclass(frozen=True, slots=True)
class ToolResultEnvelope:
    status: str
    summary: str
    tool_run_id: str | None = None
    call_id: str | None = None
    tool_name: str | None = None
    output_payload: dict[str, Any] = field(default_factory=dict)
    error_payload: dict[str, Any] = field(default_factory=dict)
    artifact_refs: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    key_facts: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    read_handles: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    model_visible_payload: dict[str, Any] = field(default_factory=dict)
    user_visible_payload: dict[str, Any] = field(default_factory=dict)
    trace_payload: dict[str, Any] = field(default_factory=dict)
    omitted_count: int = 0
    omitted_chars: int = 0
    truncated: bool = False

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "summary": self.summary,
            "tool_run_id": self.tool_run_id,
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "output_payload": dict(self.output_payload),
            "error_payload": dict(self.error_payload),
            "artifact_refs": [dict(ref) for ref in self.artifact_refs],
            "key_facts": dict(self.key_facts),
            "warnings": list(self.warnings),
            "evidence_refs": list(self.evidence_refs),
            "read_handles": [dict(handle) for handle in self.read_handles],
            "model_visible_payload": dict(self.model_visible_payload),
            "user_visible_payload": dict(self.user_visible_payload),
            "trace_payload": dict(self.trace_payload),
            "omitted_count": self.omitted_count,
            "omitted_chars": self.omitted_chars,
            "truncated": self.truncated,
        }
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, {}, [], ())
        }
