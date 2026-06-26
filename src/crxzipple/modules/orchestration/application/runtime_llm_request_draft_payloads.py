from __future__ import annotations

from crxzipple.modules.llm.domain import LlmMessage
from crxzipple.modules.orchestration.application.runtime_request_mode import (
    RuntimeRequestMode,
)
from crxzipple.modules.session.domain import SessionItem
from crxzipple.shared.content_blocks import (
    content_blocks_from_payload,
    normalize_content_blocks,
)


def routing_input_content(
    *,
    transcript_messages: tuple[LlmMessage, ...],
    session_items: tuple[SessionItem, ...],
) -> dict[str, object] | None:
    transcript_payload = _routing_input_content_from_transcript(transcript_messages)
    if isinstance(transcript_payload, dict):
        raw_blocks = transcript_payload.get("blocks")
        if isinstance(raw_blocks, list):
            transcript_blocks = [
                dict(block) for block in raw_blocks if isinstance(block, dict)
            ]
            if transcript_blocks:
                return {"blocks": transcript_blocks}
    blocks: list[dict[str, object]] = []
    for item in session_items:
        blocks.extend(content_blocks_from_payload(item.content_payload))
    if not blocks:
        return None
    return {"blocks": blocks}


def routing_input_block_count(value: dict[str, object] | None) -> int | None:
    if not isinstance(value, dict):
        return None
    blocks = value.get("blocks")
    if not isinstance(blocks, list):
        return None
    return len(tuple(block for block in blocks if isinstance(block, dict)))


def session_replay_window_event_payload(value: object) -> dict[str, object]:
    if value is None:
        return {}
    payload: dict[str, object] = {}
    for attr in (
        "active_session_only",
        "from_sequence_no",
        "to_sequence_no",
        "item_count",
    ):
        item = getattr(value, attr, None)
        if item is not None:
            payload[attr] = item
    protocol_call_ids = getattr(value, "protocol_call_ids", None)
    if protocol_call_ids:
        payload["protocol_call_ids"] = list(protocol_call_ids)
    return payload


def transcript_policy_payload(
    *,
    session_key: str,
    session_replay_window: object | None,
    mode: RuntimeRequestMode,
) -> dict[str, object]:
    if session_replay_window is not None:
        return {
            "session_replay_window": _session_replay_window_policy_payload(
                session_replay_window,
                session_key=session_key,
            ),
        }
    return {
        "session_binding_lookup": {
            "session_key": session_key,
            "active_session_only": True,
            "item_limit": 0,
            "mode": mode.value,
        },
    }


def _routing_input_content_from_transcript(
    messages: tuple[LlmMessage, ...],
) -> dict[str, object] | None:
    blocks: list[dict[str, object]] = []
    for message in messages:
        try:
            normalized_blocks = normalize_content_blocks(message.content)
        except ValueError:
            continue
        blocks.extend(normalized_blocks)
    if not blocks:
        return None
    return {"blocks": blocks}


def _session_replay_window_policy_payload(
    value: object,
    *,
    session_key: str,
) -> dict[str, object]:
    payload = session_replay_window_event_payload(value)
    payload["session_key"] = session_key
    return payload
