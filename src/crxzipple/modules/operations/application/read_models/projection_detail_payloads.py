from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.llm_models import (
    defer_llm_invocation_details_payload,
)
from crxzipple.modules.operations.application.read_models.memory_models import (
    defer_memory_file_details_payload,
)
from crxzipple.modules.operations.application.read_models.tool_models import (
    defer_tool_run_details_payload,
)


def strip_deferred_detail_payloads(
    payload: dict[str, Any],
    *,
    module: str,
    kind: str,
) -> None:
    if kind != "page":
        return
    normalized_module = module.strip().lower()
    if normalized_module == "tool":
        defer_tool_run_details_payload(payload)
    elif normalized_module == "llm":
        defer_llm_invocation_details_payload(payload)
    elif normalized_module == "memory":
        defer_memory_file_details_payload(payload)
