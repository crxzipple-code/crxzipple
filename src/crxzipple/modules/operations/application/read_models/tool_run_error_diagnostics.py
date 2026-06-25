from __future__ import annotations

import re

from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    truncate_text,
)
from crxzipple.modules.tool.domain import ToolRun, ToolRunStatus


def tool_run_error_facts(
    run: ToolRun,
    *,
    provider_label: str,
) -> OperationsKeyValueSectionModel:
    if not run.error_message and run.status is not ToolRunStatus.TIMED_OUT:
        return OperationsKeyValueSectionModel(
            id="error_facts",
            title="Error Facts",
            items=(),
        )
    family, code, tone = tool_error_classification(run)
    http_status = error_http_status(run.error_message)
    retryable = run.can_retry() and run.status in {
        ToolRunStatus.FAILED,
        ToolRunStatus.TIMED_OUT,
    }
    return OperationsKeyValueSectionModel(
        id="error_facts",
        title="Error Facts",
        items=(
            OperationsKeyValueItemModel(
                label="Error Family",
                value=family,
                tone=tone,
            ),
            OperationsKeyValueItemModel(
                label="Error Code",
                value=code,
                tone=tone,
            ),
            OperationsKeyValueItemModel(
                label="Provider",
                value=provider_label,
            ),
            OperationsKeyValueItemModel(
                label="HTTP Status",
                value=http_status or "-",
                tone=(
                    "danger"
                    if http_status and http_status.startswith(("4", "5"))
                    else "neutral"
                ),
            ),
            OperationsKeyValueItemModel(
                label="Retryable",
                value="Yes" if retryable else "No",
                tone="warning" if retryable else "neutral",
            ),
            OperationsKeyValueItemModel(
                label="Root Cause",
                value=tool_error_root_cause(run),
                tone=tone,
            ),
        ),
    )


def tool_error_classification(run: ToolRun) -> tuple[str, str, str]:
    message = (run.error_message or "").lower()
    if (
        run.status is ToolRunStatus.TIMED_OUT
        or "timeout" in message
        or "timed out" in message
    ):
        return ("timeout", "tool_timeout", "warning")
    if looks_like_access_failure(run):
        return ("access", "access_denied", "danger")
    if "rate limit" in message or "429" in message or "too many requests" in message:
        return ("provider_limit", "rate_limited", "warning")
    if "lease expired" in message or "retry budget exhausted" in message:
        return ("worker_lease", "lease_expired", "danger")
    if any(marker in message for marker in ("connection", "network", "dns", "socket")):
        return ("network", "network_error", "warning")
    if any(marker in message for marker in ("schema", "validation", "invalid")):
        return ("validation", "invalid_payload", "danger")
    return ("execution", "tool_execution_failed", "danger")


def error_http_status(message: str | None) -> str | None:
    if not message:
        return None
    match = re.search(r"\b([45][0-9]{2})\b", message)
    return match.group(1) if match else None


def tool_error_root_cause(run: ToolRun) -> str:
    if run.status is ToolRunStatus.TIMED_OUT:
        return "tool run timed out"
    if not run.error_message:
        return "-"
    return truncate_text(run.error_message, 160)


def looks_like_access_failure(run: ToolRun) -> bool:
    message = (run.error_message or "").lower()
    return any(
        marker in message
        for marker in (
            "access",
            "auth",
            "credential",
            "permission",
            "forbidden",
            "api key",
            "login",
            "401",
            "403",
        )
    )
