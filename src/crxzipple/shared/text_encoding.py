from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


_MOJIBAKE_HINT_CHARS = frozenset(
    "ÃÂÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞ"
    "ãâäåæçèéêëìíîïðñòóôõöøùúûüýþÿ"
    "œŒšŠžŽ"
)


def repair_possible_utf8_latin1_mojibake_text(text: str) -> str:
    if not text or text.isascii():
        return text
    if _count_east_asian_chars(text) > 0:
        return text
    if _count_mojibake_hints(text) < 3:
        return text
    try:
        candidate = text.encode("latin1").decode("utf-8")
    except UnicodeError:
        return text
    if candidate == text:
        return text
    if _count_east_asian_chars(candidate) == 0:
        return text
    try:
        roundtrip = candidate.encode("utf-8").decode("latin1")
    except UnicodeError:
        return text
    if roundtrip != text:
        return text
    return candidate


def repair_possible_utf8_latin1_mojibake_content(value: Any) -> Any:
    if isinstance(value, str):
        return repair_possible_utf8_latin1_mojibake_text(value)
    if isinstance(value, Mapping):
        repaired = dict(value)
        block_type = repaired.get("type")
        if block_type == "text" and isinstance(repaired.get("text"), str):
            repaired["text"] = repair_possible_utf8_latin1_mojibake_text(
                repaired["text"],
            )
            return repaired
        if "blocks" in repaired:
            repaired["blocks"] = repair_possible_utf8_latin1_mojibake_content(
                repaired["blocks"],
            )
        elif "content" in repaired:
            repaired["content"] = repair_possible_utf8_latin1_mojibake_content(
                repaired["content"],
            )
        elif isinstance(repaired.get("text"), str):
            repaired["text"] = repair_possible_utf8_latin1_mojibake_text(
                repaired["text"],
            )
        return repaired
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [repair_possible_utf8_latin1_mojibake_content(item) for item in value]
    return value


def _count_mojibake_hints(text: str) -> int:
    return sum(1 for char in text if char in _MOJIBAKE_HINT_CHARS)


def _count_east_asian_chars(text: str) -> int:
    count = 0
    for char in text:
        codepoint = ord(char)
        if (
            0x3400 <= codepoint <= 0x4DBF
            or 0x4E00 <= codepoint <= 0x9FFF
            or 0xF900 <= codepoint <= 0xFAFF
            or 0x3040 <= codepoint <= 0x309F
            or 0x30A0 <= codepoint <= 0x30FF
            or 0xAC00 <= codepoint <= 0xD7AF
        ):
            count += 1
    return count
