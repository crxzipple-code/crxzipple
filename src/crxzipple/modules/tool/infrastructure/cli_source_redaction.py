from __future__ import annotations


def redact_cli_output(text: str, redactions: tuple[str, ...]) -> str:
    redacted = text
    for secret in sorted(set(redactions), key=len, reverse=True):
        if not secret:
            continue
        redacted = redacted.replace(secret, "[credential:redacted]")
    return redacted


__all__ = ["redact_cli_output"]
