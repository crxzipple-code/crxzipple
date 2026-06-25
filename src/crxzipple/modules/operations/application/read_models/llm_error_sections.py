from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from crxzipple.modules.llm.application.error_classification import (
    llm_error_family,
    llm_error_retryable,
)
from crxzipple.modules.llm.domain import LlmInvocation
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.shared.time import format_datetime_utc


def error_summary_section(
    failed_invocations: list[LlmInvocation],
) -> OperationsTableSectionModel:
    by_category: dict[tuple[str, str], list[LlmInvocation]] = defaultdict(list)
    for invocation in failed_invocations:
        error_code = invocation.error.code if invocation.error is not None else "unknown"
        by_category[(llm_error_family(error_code), error_code)].append(invocation)
    rows: list[OperationsTableRowModel] = []
    for (category, error_code), items in sorted(
        by_category.items(),
        key=lambda item: (-len(item[1]), item[0]),
    ):
        latest = max(items, key=lambda item: item.completed_at or item.created_at)
        retryable = llm_error_retryable(error_code)
        rows.append(
            OperationsTableRowModel(
                id=f"{category}:{error_code}",
                cells={
                    "category": category,
                    "error_code": error_code,
                    "count": str(len(items)),
                    "retryable": "Yes" if retryable else "No",
                    "last_invocation": latest.id,
                    "last_failed": _datetime_label(latest.completed_at),
                    "reason": latest.error.message if latest.error is not None else "-",
                },
                status=category,
                tone="warning" if retryable else "danger",
            ),
        )
    return OperationsTableSectionModel(
        id="error_summary",
        title="Error Summary",
        columns=_columns(
            ("category", "Category"),
            ("error_code", "Error Code"),
            ("count", "Count"),
            ("retryable", "Retryable"),
            ("last_invocation", "Invocation ID"),
            ("last_failed", "Last Failed"),
            ("reason", "Reason"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No failed LLM invocations.",
    )


def _datetime_label(value: datetime | None) -> str:
    return format_datetime_utc(value) if value is not None else "-"


def _columns(*pairs: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(OperationsTableColumnModel(key=key, label=label) for key, label in pairs)
