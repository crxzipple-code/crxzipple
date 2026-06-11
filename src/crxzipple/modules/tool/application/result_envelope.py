from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

TOOL_RESULT_ENVELOPE_METADATA_KEY = "tool_result_envelope"
TOOL_RESULT_RAW_OUTPUT_BLOCKS_METADATA_KEY = "tool_result_raw_output_blocks"


@dataclass(frozen=True, slots=True)
class ToolResultEnvelope:
    status: str
    summary: str
    key_facts: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    read_handles: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    omitted_count: int = 0
    omitted_chars: int = 0
    truncated: bool = False

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "summary": self.summary,
            "key_facts": dict(self.key_facts),
            "warnings": list(self.warnings),
            "evidence_refs": list(self.evidence_refs),
            "read_handles": [dict(handle) for handle in self.read_handles],
            "omitted_count": self.omitted_count,
            "omitted_chars": self.omitted_chars,
            "truncated": self.truncated,
        }
        return payload
