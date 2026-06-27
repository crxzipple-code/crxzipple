from __future__ import annotations

from typing import Any

from crxzipple.modules.tool.infrastructure.cli_source_envelopes import (
    process_output_payload,
)
from crxzipple.modules.tool.infrastructure.cli_source_redaction import (
    redact_cli_output,
)


def process_output_payload_for_display(
    output: Any,
    *,
    redactions: tuple[str, ...],
) -> dict[str, Any]:
    details = process_output_payload(output)
    if not redactions:
        return details
    details["stdout"] = redact_cli_output(str(details.get("stdout") or ""), redactions)
    details["stderr"] = redact_cli_output(str(details.get("stderr") or ""), redactions)
    return details


__all__ = ["process_output_payload_for_display"]
