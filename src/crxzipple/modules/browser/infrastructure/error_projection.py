from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)(\b(?:api[_-]?key|authorization|credential|password|passwd|secret|token)\b\s*[:=]\s*[\"']?)([^&\s,\"'}]+)",
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")


def display_safe_exception_message(value: Exception | str, *, limit: int = 600) -> str:
    message = " ".join(str(value).split())
    if not message and isinstance(value, Exception):
        message = value.__class__.__name__
    if not message:
        message = "Browser operation failed"
    message = _redact_urls(message)
    message = _BEARER_RE.sub("Bearer [redacted]", message)
    message = _SENSITIVE_ASSIGNMENT_RE.sub(r"\1[redacted]", message)
    if len(message) > limit:
        return f"{message[: max(limit - 3, 0)].rstrip()}..."
    return message


def _redact_urls(message: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        raw_url = match.group(0)
        try:
            parsed = urlsplit(raw_url)
        except ValueError:
            return raw_url
        if parsed.query or parsed.fragment:
            return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "[redacted]", ""))
        return raw_url

    return re.sub(r"https?://[^\s'\"<>]+", _replace, message)


__all__ = ["display_safe_exception_message"]
