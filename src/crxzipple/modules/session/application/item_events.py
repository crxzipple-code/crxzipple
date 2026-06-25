from __future__ import annotations

from crxzipple.modules.session.domain.value_objects import SessionItem


def session_item_fact_payload(item: SessionItem) -> dict[str, object]:
    return {
        "item_id": item.id,
        "session_key": item.session_key,
        "session_id": item.session_id,
        "sequence_no": item.sequence_no,
        "kind": item.kind.value,
        "phase": item.phase.value,
        "role": item.role,
        "source_module": item.source_module,
        "source_kind": item.source_kind,
        "source_id": item.source_id,
        "provider_item_id": item.provider_item_id,
        "provider_item_type": item.provider_item_type,
        "call_id": item.call_id,
        "tool_name": item.tool_name,
        "model_visible": item.model_visible,
        "user_visible": item.user_visible,
        "chat_visible": item.chat_visible,
        "trace_visible": item.trace_visible,
        "item": item.to_payload(),
    }
