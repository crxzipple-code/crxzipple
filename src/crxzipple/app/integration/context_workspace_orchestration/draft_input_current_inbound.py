"""Current inbound input projection helpers."""

from __future__ import annotations

from crxzipple.modules.llm.domain import LlmInputItemKind, LlmMessageRole
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)


def mode_allows_session_current_inbound_anchor(
    draft: RuntimeLlmRequestDraft,
) -> bool:
    mode = str(getattr(getattr(draft, "mode", None), "value", "") or "").strip()
    return mode in {
        "normal_turn",
        "session_start",
        "approval_resume",
        "approval_denied",
        "recovery_resume",
    }


def is_current_inbound_input_item(
    item: object,
    *,
    allow_session_anchor: bool,
) -> bool:
    source = str(getattr(item, "source", "") or "").strip()
    metadata = getattr(item, "metadata", None)
    if source == "current_inbound":
        return True
    if not isinstance(metadata, dict):
        return False
    if metadata.get("runtime_request_block_kind") == "current_inbound":
        return True
    if not allow_session_anchor:
        return False
    payload = getattr(item, "payload", None)
    role = payload.get("role") if isinstance(payload, dict) else None
    return _is_current_inbound_session_user_metadata(metadata, role=role)


def is_current_inbound_projected(item: dict[str, object]) -> bool:
    if item.get("source") == "current_inbound":
        return True
    metadata = item.get("metadata")
    payload = item.get("payload")
    role = payload.get("role") if isinstance(payload, dict) else None
    return isinstance(metadata, dict) and (
        metadata.get("runtime_request_block_kind") == "current_inbound"
        or _is_current_inbound_session_user_metadata(metadata, role=role)
    )


def project_input_item(item: object) -> dict[str, object] | None:
    kind = getattr(item, "kind", None)
    kind_value = getattr(kind, "value", None) or str(kind or "").strip()
    if not kind_value:
        return None
    payload = getattr(item, "payload", None)
    if not isinstance(payload, dict):
        return None
    metadata = getattr(item, "metadata", None)
    metadata_payload = dict(metadata) if isinstance(metadata, dict) else {}
    metadata_payload.setdefault("runtime_request_block_kind", "current_inbound")
    return {
        "kind": kind_value,
        "payload": dict(payload),
        "source": "current_inbound",
        "metadata": metadata_payload,
    }


def project_message(
    message: object,
    *,
    allow_session_anchor: bool,
) -> dict[str, object] | None:
    role = getattr(message, "role", None)
    if role is LlmMessageRole.SYSTEM:
        return None
    role_value = getattr(role, "value", None) or str(role or "").strip()
    if role_value not in {"user", "assistant", "tool"}:
        return None
    metadata = getattr(message, "metadata", None)
    if not isinstance(metadata, dict):
        return None
    if (
        metadata.get("runtime_request_block_kind") != "current_inbound"
        and (
            not allow_session_anchor
            or not _is_current_inbound_session_user_metadata(
                metadata,
                role=role_value,
            )
        )
    ):
        return None
    metadata_payload = dict(metadata)
    metadata_payload.setdefault("runtime_request_block_kind", "current_inbound")
    return {
        "kind": LlmInputItemKind.MESSAGE.value,
        "payload": {
            "role": role_value,
            "content": getattr(message, "content", None),
        },
        "source": "current_inbound",
        "metadata": metadata_payload,
    }


def projected_identity(item: dict[str, object]) -> tuple[str, str, str]:
    payload = item.get("payload")
    metadata = item.get("metadata")
    payload_map = payload if isinstance(payload, dict) else {}
    metadata_map = metadata if isinstance(metadata, dict) else {}
    kind = str(item.get("kind") or "")
    session_item_id = _first_metadata_text(
        metadata_map.get("session_item_id"),
        metadata_map.get("source_id"),
    )
    if session_item_id:
        return ("session_item", kind, session_item_id)
    call_id = _first_metadata_text(
        payload_map.get("call_id"),
        metadata_map.get("tool_call_id"),
        metadata_map.get("call_id"),
    )
    if call_id and kind in {"function_call", "function_call_output"}:
        return ("tool_protocol", kind, call_id)
    return (
        "payload",
        kind,
        str(payload_map.get("call_id") or payload_map.get("role") or ""),
    )


def _is_current_inbound_session_user_metadata(
    metadata: dict[str, object],
    *,
    role: object,
) -> bool:
    role_value = str(role or "").strip().lower()
    if role_value != "user":
        return False
    if metadata.get("source_module") != "orchestration":
        return False
    if metadata.get("source_kind") != "orchestration_run":
        return False
    kind = str(metadata.get("kind") or "").strip()
    return kind in {"user_message", "session_item", ""}


def _first_metadata_text(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
