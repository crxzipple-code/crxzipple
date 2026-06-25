from __future__ import annotations

from crxzipple.modules.llm.domain import LlmInvocation
from crxzipple.modules.operations.application.read_models.llm_detail_payloads import (
    columns,
    enum_value,
    json_preview,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.session.application import (
    runtime_semantic_kind_from_llm_response_item,
)


def response_items_table_for_invocation(
    invocation: LlmInvocation,
) -> OperationsTableSectionModel:
    response_items = tuple(getattr(invocation, "response_items", ()) or ())
    rows = tuple(
        OperationsTableRowModel(
            id=str(getattr(item, "id", f"{invocation.id}:response_item:{index}")),
            cells={
                "sequence": str(getattr(item, "sequence_no", index)),
                "kind": enum_value(getattr(item, "kind", None)),
                "phase": enum_value(getattr(item, "phase", None)),
                "provider_type": str(getattr(item, "provider_item_type", None) or "-"),
                "tool": str(getattr(item, "tool_name", None) or "-"),
                "call_id": str(getattr(item, "call_id", None) or "-"),
                "provider_replay_candidate": (
                    "Yes"
                    if bool(getattr(item, "provider_replay_candidate", False))
                    else "No"
                ),
                "user_timeline_candidate": (
                    "Yes"
                    if bool(getattr(item, "user_timeline_candidate", False))
                    else "No"
                ),
                "content": json_preview(getattr(item, "content_payload", {}) or {}),
                "provider_payload": json_preview(
                    getattr(item, "provider_payload", {}) or {},
                ),
            },
            status=enum_value(getattr(item, "kind", None)),
            tone=_response_item_tone(enum_value(getattr(item, "kind", None))),
        )
        for index, item in enumerate(response_items[:40], start=1)
    )
    return OperationsTableSectionModel(
        id=f"{invocation.id}_response_items",
        title="Response Items",
        columns=columns(
            ("sequence", "Seq"),
            ("kind", "Kind"),
            ("phase", "Phase"),
            ("provider_type", "Provider Type"),
            ("tool", "Tool"),
            ("call_id", "Call ID"),
            ("provider_replay_candidate", "Provider Replay Candidate"),
            ("user_timeline_candidate", "User Timeline Candidate"),
            ("content", "Content"),
            ("provider_payload", "Provider Payload"),
        ),
        rows=rows,
        total=len(response_items),
        empty_state="No response items recorded.",
    )


def response_runtime_mapping_table_for_invocation(
    invocation: LlmInvocation,
) -> OperationsTableSectionModel:
    response_items = tuple(getattr(invocation, "response_items", ()) or ())
    rows = tuple(
        OperationsTableRowModel(
            id=f"{invocation.id}:response_runtime_mapping:{index}",
            cells={
                "provider_item": str(getattr(item, "provider_item_id", None) or "-"),
                "provider_type": str(getattr(item, "provider_item_type", None) or "-"),
                "response_item": str(getattr(item, "id", "") or "-"),
                "sequence": str(getattr(item, "sequence_no", index)),
                "response_kind": enum_value(getattr(item, "kind", None)),
                "phase": enum_value(getattr(item, "phase", None)),
                "runtime_semantic": runtime_semantic_kind_from_llm_response_item(item),
                "role": enum_value(getattr(item, "role", None)),
                "tool": str(getattr(item, "tool_name", None) or "-"),
                "call_id": str(getattr(item, "call_id", None) or "-"),
                "provider_replay_candidate": (
                    "Yes"
                    if bool(getattr(item, "provider_replay_candidate", False))
                    else "No"
                ),
                "user_timeline_candidate": (
                    "Yes"
                    if bool(getattr(item, "user_timeline_candidate", False))
                    else "No"
                ),
            },
            status=runtime_semantic_kind_from_llm_response_item(item),
            tone=_response_item_tone(enum_value(getattr(item, "kind", None))),
        )
        for index, item in enumerate(response_items[:40], start=1)
    )
    return OperationsTableSectionModel(
        id=f"{invocation.id}_response_runtime_mapping",
        title="Response Runtime Mapping",
        columns=columns(
            ("provider_item", "Provider Item"),
            ("provider_type", "Provider Type"),
            ("response_item", "Response Item"),
            ("sequence", "Seq"),
            ("response_kind", "Response Kind"),
            ("phase", "Phase"),
            ("runtime_semantic", "Runtime Semantic"),
            ("role", "Role"),
            ("tool", "Tool"),
            ("call_id", "Call ID"),
            ("provider_replay_candidate", "Provider Replay Candidate"),
            ("user_timeline_candidate", "User Timeline Candidate"),
        ),
        rows=rows,
        total=len(response_items),
        empty_state="No response runtime mapping recorded.",
    )


def _response_item_tone(kind: str) -> str:
    if kind == "tool_call":
        return "info"
    if kind == "provider_external_item":
        return "warning"
    if kind == "assistant_message":
        return "success"
    return "neutral"
