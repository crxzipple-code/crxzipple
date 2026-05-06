from __future__ import annotations

import json
import re
from typing import Any

from crxzipple.modules.channels.application.bindings import (
    resolve_channel_metadata_binding,
)


def normalize_lark_chat_type(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"p2p", "direct"}:
        return "direct"
    if normalized in {"group", "chat_group"}:
        return "group"
    return normalized or "direct"


def parse_lark_message_content(message: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    message_type = str(message.get("message_type") or "text").strip().lower()
    raw_content = message.get("content")
    if isinstance(raw_content, str) and raw_content.strip():
        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError:
            parsed = {"text": raw_content}
    elif isinstance(raw_content, dict):
        parsed = dict(raw_content)
    else:
        parsed = {}
    return message_type, parsed


def extract_lark_mentions(
    *,
    message: dict[str, Any],
    parsed_content: dict[str, Any],
) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    raw_mentions = message.get("mentions")
    if isinstance(raw_mentions, list):
        for item in raw_mentions:
            if not isinstance(item, dict):
                continue
            user_id_payload = item.get("id")
            user_ids = user_id_payload if isinstance(user_id_payload, dict) else {}
            mentions.append(
                {
                    "key": str(item.get("key") or "").strip() or None,
                    "name": str(item.get("name") or "").strip() or None,
                    "open_id": str(user_ids.get("open_id") or "").strip() or None,
                    "user_id": str(user_ids.get("user_id") or "").strip() or None,
                    "union_id": str(user_ids.get("union_id") or "").strip() or None,
                },
            )
    raw_text = str(parsed_content.get("text") or "")
    if raw_text:
        for open_id in re.findall(r'<at\\s+user_id="([^"]+)">.*?</at>', raw_text):
            normalized = open_id.strip()
            if not normalized:
                continue
            if any(item.get("open_id") == normalized for item in mentions):
                continue
            mentions.append(
                {
                    "key": None,
                    "name": None,
                    "open_id": normalized,
                    "user_id": None,
                    "union_id": None,
                },
            )
    return mentions


def is_truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def should_accept_lark_message(
    *,
    account_metadata: dict[str, Any],
    chat_type: str,
    mentions: list[dict[str, Any]],
) -> bool:
    if chat_type != "group":
        return True
    if not is_truthy(account_metadata.get("lark_group_require_bot_mention")):
        return True
    bot_open_id = resolve_channel_metadata_binding(
        account_metadata,
        key="lark_bot_open_id",
        description="Lark bot open id",
        required=False,
    ) or ""
    if not bot_open_id:
        return False
    return any(
        str(item.get("open_id") or "").strip() == bot_open_id
        for item in mentions
        if isinstance(item, dict)
    )


def extract_lark_post_lines(parsed_content: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()

    def _append_line(value: str) -> None:
        normalized = value.strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        lines.append(normalized)

    locale_payloads: list[dict[str, Any]] = []
    if "content" in parsed_content or "title" in parsed_content:
        locale_payloads.append(parsed_content)
    for value in parsed_content.values():
        if isinstance(value, dict):
            locale_payloads.append(value)

    for locale_payload in locale_payloads:
        raw_title = locale_payload.get("title")
        if isinstance(raw_title, str) and raw_title.strip():
            _append_line(raw_title)
        raw_content = locale_payload.get("content")
        if not isinstance(raw_content, list):
            continue
        for row in raw_content:
            if not isinstance(row, list):
                continue
            parts: list[str] = []
            for item in row:
                if not isinstance(item, dict):
                    continue
                item_text = str(item.get("text") or "").strip()
                item_tag = str(item.get("tag") or "").strip().lower()
                if item_text:
                    parts.append(item_text)
                elif item_tag == "img":
                    image_key = str(item.get("image_key") or "").strip()
                    parts.append(f"[image:{image_key}]" if image_key else "[image]")
                elif item_tag == "a":
                    href = str(item.get("href") or "").strip()
                    if href:
                        parts.append(href)
            if parts:
                _append_line("".join(parts))
    return lines


def describe_lark_non_text_message(
    message_type: str,
    parsed_content: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    metadata: dict[str, Any] = {
        "message_type": message_type,
        "raw_content": dict(parsed_content),
    }
    if message_type == "image":
        image_key = str(parsed_content.get("image_key") or "").strip() or None
        if image_key is not None:
            metadata["image_key"] = image_key
        return "[Lark image message]", metadata
    if message_type == "file":
        file_key = str(parsed_content.get("file_key") or "").strip() or None
        file_name = str(parsed_content.get("file_name") or "").strip() or None
        if file_key is not None:
            metadata["file_key"] = file_key
        if file_name is not None:
            metadata["file_name"] = file_name
        if file_name:
            return f"[Lark file: {file_name}]", metadata
        return "[Lark file message]", metadata
    if message_type == "post":
        post_lines = extract_lark_post_lines(parsed_content)
        if post_lines:
            metadata["post_lines"] = list(post_lines)
            return "\n".join(post_lines), metadata
        return "[Lark post message]", metadata
    if message_type == "audio":
        return "[Lark audio message]", metadata
    if message_type == "media":
        return "[Lark media message]", metadata
    if message_type == "sticker":
        return "[Lark sticker message]", metadata
    return f"[Lark {message_type or 'unknown'} message]", metadata


def normalize_lark_message_content(
    message: dict[str, Any],
    *,
    mentions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    message_type, parsed_content = parse_lark_message_content(message)
    resolved_mentions = list(mentions or [])
    if message_type == "text":
        text = str(parsed_content.get("text") or "")
        return {
            "blocks": [
                {
                    "type": "text",
                    "text": text,
                },
            ],
            "text": text,
            "metadata": {
                "mentions": resolved_mentions,
            },
        }
    placeholder_text, metadata = describe_lark_non_text_message(
        message_type,
        parsed_content,
    )
    metadata["mentions"] = resolved_mentions
    return {
        "blocks": [
            {
                "type": "text",
                "text": placeholder_text,
            },
        ],
        "text": placeholder_text,
        "metadata": metadata,
    }
