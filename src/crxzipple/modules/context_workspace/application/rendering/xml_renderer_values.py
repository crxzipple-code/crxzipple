from __future__ import annotations

import json
from html import escape

from crxzipple.modules.context_workspace.domain import ContextNode


def append_xml_text_block(
    lines: list[str],
    tag_name: str,
    value: str | None,
    *,
    block_indent: str,
    value_indent: str,
) -> None:
    if value is None:
        return
    lines.append(f"{block_indent}<{tag_name}>")
    for content_line in value.splitlines() or [""]:
        lines.append(f"{value_indent}{escape(content_line)}")
    lines.append(f"{block_indent}</{tag_name}>")


def json_fragment(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        return str(value)


def bounded_optional_text(value: object, limit: int) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return bounded_text(normalized, limit)


def bounded_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(limit - 3, 0)].rstrip() + "..."


def optional_dict_text(mapping: dict[str, object], key: str) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.isdigit():
            return int(normalized)
    return None


def text_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set)):
        return ()
    parts: list[str] = []
    for item in value:
        normalized = str(item or "").strip()
        if normalized:
            parts.append(normalized)
    return tuple(dict.fromkeys(parts))


def truncate_xml_attr(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(limit - 3, 0)].rstrip() + "..."


def optional_metadata_text(node: ContextNode, key: str) -> str | None:
    value = node.metadata.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def optional_ref_text(node: ContextNode, key: str) -> str | None:
    value = node.owner_ref.get(key)
    if value is None:
        value = node.metadata.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def metadata_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    return False


def node_bool_value(node: ContextNode, key: str) -> bool:
    if key in node.owner_ref:
        return metadata_bool(node.owner_ref[key])
    return metadata_bool(node.metadata.get(key))


def metadata_sequence_label(node: ContextNode, key: str) -> str:
    value = node.metadata.get(key)
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, (list, tuple, set)):
        return str(value).strip()
    parts: list[str] = []
    for item in value:
        normalized = str(item or "").strip()
        if normalized:
            parts.append(normalized)
    return ", ".join(parts)


def xml_bool(value: bool) -> str:
    return "true" if value else "false"


__all__ = [
    "append_xml_text_block",
    "bounded_optional_text",
    "bounded_text",
    "json_fragment",
    "metadata_bool",
    "metadata_sequence_label",
    "node_bool_value",
    "optional_dict_text",
    "optional_int",
    "optional_metadata_text",
    "optional_ref_text",
    "text_list",
    "truncate_xml_attr",
    "xml_bool",
]
