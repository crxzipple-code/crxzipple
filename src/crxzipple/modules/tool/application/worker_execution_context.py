from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.tool.application.provider_backend_service import (
    provider_backend_execution_context_payload,
)
from crxzipple.modules.tool.domain.value_objects import ToolExecutionContext


def execution_context_with_provider_backend(
    execution_context: ToolExecutionContext | None,
    provider_backend_payload: Mapping[str, Any] | None,
) -> ToolExecutionContext | None:
    payload = provider_backend_execution_context_payload(
        execution_context.to_payload() if execution_context is not None else None,
        provider_backend_payload,
    )
    if payload is None:
        return execution_context
    return ToolExecutionContext(attrs=payload)


def execution_context_with_tool_run_id(
    execution_context: ToolExecutionContext | None,
    run_id: str,
) -> ToolExecutionContext:
    payload = execution_context.to_payload() if execution_context is not None else {}
    payload["tool_run_id"] = run_id
    return ToolExecutionContext(attrs=payload)


__all__ = [
    "execution_context_with_provider_backend",
    "execution_context_with_tool_run_id",
]
