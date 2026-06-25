from __future__ import annotations

from crxzipple.modules.llm.domain import LlmInvocation
from crxzipple.modules.operations.application.read_models.llm_detail_payloads import (
    columns,
    json_preview,
    text,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_facts import (
    request_metadata,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def policy_trace_table_for_invocation(
    invocation: LlmInvocation,
) -> OperationsTableSectionModel:
    policy = request_metadata(invocation).get("llm_request_policy")
    trace = policy.get("resolution_trace") if isinstance(policy, dict) else None
    rows = tuple(
        OperationsTableRowModel(
            id=f"{invocation.id}:policy_trace:{index}",
            cells={
                "field": text(item.get("field")) or "-",
                "source": text(item.get("source")) or "-",
                "status": text(item.get("status")) or "-",
                "value": json_preview(item.get("value")),
                "reason": text(item.get("reason")) or "-",
            },
            status=text(item.get("status")) or "-",
            tone="warning" if text(item.get("status")) == "downgraded" else "neutral",
        )
        for index, item in enumerate(trace or (), start=1)
        if isinstance(item, dict)
    )
    return OperationsTableSectionModel(
        id=f"{invocation.id}_policy_trace",
        title="Policy Resolution Trace",
        columns=columns(
            ("field", "Field"),
            ("source", "Source"),
            ("status", "Status"),
            ("value", "Value"),
            ("reason", "Reason"),
        ),
        rows=rows,
        total=len(rows),
        empty_state="No policy resolution trace recorded.",
    )
