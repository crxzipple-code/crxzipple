from __future__ import annotations

from dataclasses import replace

from crxzipple.modules.llm.application.session_runtime_items import (
    extract_item_content,
    item_role,
)
from crxzipple.modules.session.domain import SessionItem
from crxzipple.shared.content_blocks import (
    content_blocks_from_payload,
    describe_content_for_text_fallback,
    extract_text_content,
    text_content_block,
)
from crxzipple.shared.token_estimates import estimate_text_tokens


def message_content_chars(content: object) -> int:
    text_content = extract_text_content(content)
    if text_content is not None:
        return len(text_content)
    return len(describe_content_for_text_fallback(content))


def message_content_tokens(content: object) -> int:
    text_content = extract_text_content(content)
    if text_content is not None:
        return estimate_text_tokens(text_content)
    return estimate_text_tokens(describe_content_for_text_fallback(content))


def session_item_content_chars(item: SessionItem) -> int:
    return message_content_chars(extract_item_content(item, role=item_role(item)))


def truncate_item_to_recent_chars(
    item: SessionItem,
    max_chars: int,
) -> SessionItem:
    if max_chars <= 0:
        return item
    blocks = content_blocks_from_payload(item.content_payload)
    text_content = extract_text_content(blocks if blocks else item.content_payload)
    if text_content is None:
        fallback_text = describe_content_for_text_fallback(item.content_payload)
        truncated_text = fallback_text[-max_chars:]
        return replace(
            item,
            content_payload={
                "blocks": [text_content_block(truncated_text)],
                "text": truncated_text,
            },
        )
    truncated_text = text_content[-max_chars:]
    payload = dict(item.content_payload)
    payload["blocks"] = [text_content_block(truncated_text)]
    payload["text"] = truncated_text
    return replace(
        item,
        content_payload=payload,
    )
