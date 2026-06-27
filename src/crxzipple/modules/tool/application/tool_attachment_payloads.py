from __future__ import annotations

import base64
import binascii


def decode_tool_attachment_bytes(data: str) -> bytes | None:
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        return None


__all__ = ["decode_tool_attachment_bytes"]
