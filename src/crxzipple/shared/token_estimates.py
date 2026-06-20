from __future__ import annotations

import math

ESTIMATED_CHARS_PER_TOKEN = 4


def estimate_text_tokens(content: str) -> int:
    normalized = content.strip()
    if not normalized:
        return 0
    return max(1, math.ceil(len(normalized) / ESTIMATED_CHARS_PER_TOKEN))
