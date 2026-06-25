from __future__ import annotations

import hashlib

from crxzipple.app.integration.context_workspace_session_content_values import (
    truncate,
)


def tool_interaction_summary(
    *,
    tool_name: str,
    status: str,
    frontier: bool,
    current_turn: bool,
    arguments_json: str,
    result_content: str,
    error_json: str | None,
) -> str:
    base = f"{tool_name} tool call {status}."
    if frontier:
        if error_json:
            return f"{base} error={truncate(error_json, 180)}"
        if result_content:
            result_summary = truncate(result_content.replace("\n", " "), 200)
            return f"{base} {result_summary}"
        return base
    if current_turn:
        if error_json:
            return f"{base} current-turn error available."
        if result_content:
            result_digest = _short_digest(result_content)
            if result_digest is not None:
                return f"{base} current-turn result_sha256={result_digest}."
        return f"{base} current-turn result available."
    digest_parts = []
    args_digest = _short_digest(arguments_json)
    if args_digest is not None:
        digest_parts.append(f"args_sha256={args_digest}")
    result_digest = _short_digest(result_content or error_json or "")
    if result_digest is not None:
        digest_parts.append(f"result_sha256={result_digest}")
    if error_json:
        digest_parts.append(f"error={truncate(error_json, 120)}")
    digest = "; ".join(digest_parts)
    if digest:
        return f"{status} consumed; {digest}; expand for refs."
    return f"{status} consumed; expand for refs."


def _short_digest(value: str) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
