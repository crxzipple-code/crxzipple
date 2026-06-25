from __future__ import annotations

import json
from typing import Any


def format_sse_event(event_name: str, payload: dict[str, Any]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


__all__ = ["format_sse_event"]
