from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from crxzipple.modules.channels.domain import ChannelAccountProfile, ChannelProfile


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def resolve_channel_account_profile(
    profile: ChannelProfile | None,
    *,
    channel_account_id: str,
) -> ChannelAccountProfile | None:
    if profile is None:
        return None
    normalized_account = channel_account_id.strip()
    if not normalized_account:
        return None
    for item in profile.accounts:
        if item.account_id.strip() == normalized_account:
            return item
    return None


def session_item_fact_as_message_payload(payload: dict[str, Any]) -> dict[str, Any]:
    item = payload.get("item")
    if not isinstance(item, dict):
        return payload
    normalized = dict(payload)
    item_id = str(payload.get("item_id") or item.get("id") or "").strip()
    normalized["message_id"] = item_id
    normalized["role"] = payload.get("role") or item.get("role")
    normalized["kind"] = payload.get("kind") or item.get("kind")
    normalized["source_kind"] = payload.get("source_kind") or item.get("source_kind")
    normalized["source_id"] = payload.get("source_id") or item.get("source_id")
    normalized["message"] = dict(item)
    return normalized


def extract_text_message(message: dict[str, Any]) -> str:
    raw_text = message.get("text")
    if isinstance(raw_text, str) and raw_text.strip():
        return raw_text
    raw_content = message.get("content")
    if isinstance(raw_content, str) and raw_content.strip():
        return raw_content.strip()
    content_payload = message.get("content_payload")
    if isinstance(content_payload, dict):
        raw_payload_text = content_payload.get("text")
        if isinstance(raw_payload_text, str) and raw_payload_text.strip():
            return raw_payload_text
        raw_blocks = content_payload.get("blocks")
        if isinstance(raw_blocks, list):
            parts: list[str] = []
            for item in raw_blocks:
                if not isinstance(item, dict):
                    continue
                if str(item.get("type") or "").strip().lower() != "text":
                    continue
                raw_block_text = item.get("text")
                if isinstance(raw_block_text, str) and raw_block_text.strip():
                    parts.append(raw_block_text)
            if parts:
                return "".join(parts)
    serialized = json.dumps(message, ensure_ascii=False)
    return serialized if serialized != "{}" else ""
