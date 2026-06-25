"""Small normalization helpers for request snapshot metadata."""

from __future__ import annotations

from ._metadata import metadata_text


def metadata_int_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def metadata_dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def top_rendered_nodes(value: object) -> list[dict[str, object]]:
    if not isinstance(value, dict):
        return []
    return metadata_dict_list(value.get("top_rendered_nodes"))


def metadata_text_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    values = [metadata_text(item) for item in value]
    return list(dict.fromkeys(item for item in values if item is not None))


def llm_message_content_chars(content: object) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(_llm_content_block_chars(item) for item in content)
    if content is None:
        return 0
    return len(str(content))


def _llm_content_block_chars(value: object) -> int:
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return len(text)
        data = value.get("data")
        if isinstance(data, str):
            return len(data)
        return len(str(value))
    if value is None:
        return 0
    return len(str(value))
