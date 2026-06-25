"""Provider input item projection from context slices."""

from __future__ import annotations

from .context_slice_input_payloads import context_slice_item_input_payloads
from .context_slice_refs import metadata_text_value


def context_slice_projected_input_items(
    context_slice: object | None,
) -> tuple[dict[str, object], ...]:
    if context_slice is None:
        return ()
    projected: list[dict[str, object]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for item in getattr(context_slice, "items", ()) or ():
        if getattr(item, "owner", None) != "session":
            continue
        owner_ref = getattr(item, "owner_ref", None)
        if not isinstance(owner_ref, dict):
            continue
        node_id = metadata_text_value(
            getattr(item, "node_id", None),
            getattr(item, "item_id", None),
        )
        session_item_id = metadata_text_value(
            owner_ref.get("session_item_id"),
            owner_ref.get("item_id"),
            owner_ref.get("owner_id"),
            owner_ref.get("call_session_item_id"),
            owner_ref.get("result_session_item_id"),
            owner_ref.get("tool_call_id"),
        )
        if session_item_id is None:
            continue
        payloads = context_slice_item_input_payloads(item, owner_ref)
        if not payloads:
            continue
        metadata = {
            "owner": "session",
            "kind": getattr(item, "kind", "session_item"),
            "session_item_id": session_item_id,
            "node_id": node_id,
        }
        for key in (
            "sequence_no",
            "tool_call_id",
            "tool_name",
            "tool_run_id",
            "llm_response_item_id",
            "source_id",
        ):
            value = owner_ref.get(key)
            if value not in (None, "", {}, []):
                metadata[key] = value
        for payload in payloads:
            payload_body = payload["payload"]
            protocol_id = ""
            if isinstance(payload_body, dict):
                protocol_id = metadata_text_value(
                    payload_body.get("call_id"),
                    payload_body.get("name"),
                ) or ""
            payload_kind = str(payload["kind"])
            dedupe_key = _projected_slice_item_identity(
                session_item_id=session_item_id,
                payload_kind=payload_kind,
                protocol_id=protocol_id,
            )
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            projected.append(
                {
                    "kind": payload_kind,
                    "payload": payload["payload"],
                    "source": "context_slice",
                    "metadata": {
                        key: value
                        for key, value in metadata.items()
                        if value not in (None, "", {}, [])
                    },
                },
            )
    return _drop_unpaired_projected_function_items(tuple(projected))


def _projected_slice_item_identity(
    *,
    session_item_id: str,
    payload_kind: str,
    protocol_id: str,
) -> tuple[str, str, str]:
    if protocol_id and payload_kind in {"function_call", "function_call_output"}:
        return ("tool_protocol", payload_kind, protocol_id)
    return ("session_item", payload_kind, session_item_id)


def _drop_unpaired_projected_function_items(
    items: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    call_ids = {
        call_id
        for item in items
        for payload in (item.get("payload"),)
        if item.get("kind") == "function_call"
        and isinstance(payload, dict)
        for call_id in (metadata_text_value(payload.get("call_id")),)
        if call_id is not None
    }
    output_ids = {
        call_id
        for item in items
        for payload in (item.get("payload"),)
        if item.get("kind") == "function_call_output"
        and isinstance(payload, dict)
        for call_id in (metadata_text_value(payload.get("call_id")),)
        if call_id is not None
    }
    if not call_ids and not output_ids:
        return items
    paired_ids = call_ids & output_ids
    filtered: list[dict[str, object]] = []
    for item in items:
        kind = item.get("kind")
        if kind not in {"function_call", "function_call_output"}:
            filtered.append(item)
            continue
        payload = item.get("payload")
        call_id = (
            metadata_text_value(payload.get("call_id"))
            if isinstance(payload, dict)
            else None
        )
        if call_id is not None and call_id in paired_ids:
            filtered.append(item)
    return tuple(filtered)

