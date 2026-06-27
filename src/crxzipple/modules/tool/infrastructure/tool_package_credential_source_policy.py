from __future__ import annotations


FORBIDDEN_CREDENTIAL_SOURCE_PREFIXES = (
    "env:",
    "file:",
    "codex_auth_json",
    "codex-cli",
    "auth_ref",
)


def rejects_forbidden_credential_source(value: str) -> bool:
    return value.strip().startswith(FORBIDDEN_CREDENTIAL_SOURCE_PREFIXES)


__all__ = [
    "FORBIDDEN_CREDENTIAL_SOURCE_PREFIXES",
    "rejects_forbidden_credential_source",
]
