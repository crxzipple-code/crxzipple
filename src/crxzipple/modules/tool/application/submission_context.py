from __future__ import annotations

from crxzipple.modules.tool.application.provider_backend_service import (
    provider_backend_execution_context_payload,
)
from crxzipple.modules.tool.application.service_support import ExecuteToolInput
from crxzipple.modules.tool.domain.value_objects import ToolExecutionContext


def tool_call_id(data: ExecuteToolInput) -> str | None:
    explicit = optional_text(data.call_id)
    if explicit is not None:
        return explicit
    return metadata_text(data.metadata, "tool_call_id")


def tool_surface_id(data: ExecuteToolInput) -> str | None:
    explicit = optional_text(data.tool_surface_id)
    if explicit is not None:
        return explicit
    direct = metadata_text(data.metadata, "tool_surface_id")
    if direct is not None:
        return direct
    plan = data.metadata.get("tool_execution_plan")
    if isinstance(plan, dict):
        return metadata_text(plan, "tool_surface_id")
    return None


def metadata_text(metadata: dict[str, object], key: str) -> str | None:
    return optional_text(metadata.get(key))


def optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def execution_context_with_provider_backend(
    execution_context: ToolExecutionContext | None,
    provider_backend_payload: dict[str, object] | None,
) -> ToolExecutionContext | None:
    payload = provider_backend_execution_context_payload(
        (
            execution_context.to_payload()
            if execution_context is not None
            else None
        ),
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
