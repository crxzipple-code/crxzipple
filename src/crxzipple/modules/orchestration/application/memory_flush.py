from __future__ import annotations

MEMORY_FLUSH_SKIP_TOKEN = "NO_MEMORY_FLUSH"


def is_memory_flush_skip_reply(text: str | None) -> bool:
    if text is None:
        return False
    return text.strip().upper() == MEMORY_FLUSH_SKIP_TOKEN
