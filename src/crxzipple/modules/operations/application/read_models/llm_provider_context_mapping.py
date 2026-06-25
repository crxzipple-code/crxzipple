from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.domain import LlmInvocation
from crxzipple.modules.operations.application.read_models.llm_invocation_labels import (
    provider_render_report,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def provider_context_mapping_table(
    invocation: LlmInvocation,
) -> OperationsTableSectionModel:
    render_report = provider_render_report(invocation)
    raw_mapping = render_report.get("input_item_mapping")
    rows: list[OperationsTableRowModel] = []
    if isinstance(raw_mapping, list):
        for index, item in enumerate(raw_mapping[:80], start=1):
            if not isinstance(item, dict):
                continue
            rows.append(
                OperationsTableRowModel(
                    id=f"{invocation.id}:provider_context_mapping:{index}",
                    cells={
                        "provider_index": _text(
                            item.get("provider_payload_index"),
                        )
                        or str(index - 1),
                        "input_index": _text(item.get("input_item_index"))
                        or str(index - 1),
                        "input_kind": _text(item.get("input_item_kind")) or "-",
                        "source": _text(item.get("input_item_source")) or "-",
                        "owner": _text(item.get("owner")) or "-",
                        "kind": _text(item.get("kind")) or "-",
                        "session_item": _text(item.get("session_item_id")) or "-",
                        "tool_call": _text(item.get("tool_call_id")) or "-",
                        "tool_run": _text(item.get("tool_run_id")) or "-",
                        "trace_status": _text(item.get("trace_status")) or "-",
                        "trace_reason": _text(item.get("trace_reason")) or "-",
                    },
                    status=_text(item.get("trace_status"))
                    or _text(item.get("input_item_source"))
                    or "mapped",
                    tone="info",
                ),
            )
    return OperationsTableSectionModel(
        id=f"{invocation.id}_provider_context_mapping",
        title="Provider Context Mapping",
        columns=_columns(
            ("provider_index", "Provider Index"),
            ("input_index", "Input Index"),
            ("input_kind", "Input Kind"),
            ("source", "Source"),
            ("owner", "Owner"),
            ("kind", "Kind"),
            ("session_item", "Session Item"),
            ("tool_call", "Tool Call"),
            ("tool_run", "Tool Run"),
            ("trace_status", "Trace Status"),
            ("trace_reason", "Trace Reason"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No provider context mapping recorded.",
    )


def _columns(*pairs: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(OperationsTableColumnModel(key=key, label=label) for key, label in pairs)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
