from __future__ import annotations

from crxzipple.modules.access.domain import (
    AccessReadinessStatus,
    AccessRequirement,
)
from crxzipple.shared.access import CredentialBindingRef


_OAUTH_BINDING_KINDS = frozenset({"oauth2_account", "openid_connect"})
_KNOWN_BINDING_KINDS = frozenset(
    {
        "api_key",
        "bearer_token",
        "basic",
        "oauth2_account",
        "openid_connect",
        "app_secret",
        "webhook_secret",
        "certificate",
    },
)


def parse_access_requirement(requirement: str) -> AccessRequirement:
    normalized = requirement.strip()
    if not normalized:
        return AccessRequirement(raw="")

    provider_kind, scopes = _split_scopes(normalized)
    provider: str | None = None
    kind: str | None = None
    if ":" in provider_kind:
        provider_value, kind_value = provider_kind.split(":", 1)
        provider = provider_value.strip() or None
        kind = kind_value.strip() or None
    else:
        kind = provider_kind.strip() or None
    return AccessRequirement(
        raw=normalized,
        provider=provider,
        kind=kind,
        scopes=scopes,
    )


def is_credential_binding(value: str) -> bool:
    normalized = value.strip()
    return normalized.startswith(("env:", "file:"))


def credential_binding_env_name(binding: str) -> str | None:
    normalized = binding.strip()
    if not normalized.startswith("env:"):
        return None
    env_name = normalized.removeprefix("env:").strip()
    return env_name or None


def canonical_credential_binding(binding: str) -> str:
    normalized = binding.strip()
    if normalized.startswith("env:"):
        return f"env:{normalized.removeprefix('env:').strip()}"
    if normalized.startswith("file:"):
        return f"file:{normalized.removeprefix('file:').strip()}"
    return normalized


def single_scope_binding(requirement: AccessRequirement) -> str | None:
    if len(requirement.scopes) != 1:
        return None
    candidate = requirement.scopes[0].strip()
    if is_credential_binding(candidate):
        return candidate
    return None


def expected_kind_for_requirement(
    requirement: AccessRequirement,
    *,
    explicit: str | None,
) -> str | None:
    normalized_explicit = normalize_binding_kind(explicit)
    if normalized_explicit is not None:
        return normalized_explicit
    kind = normalize_binding_kind(requirement.kind)
    if kind is not None:
        return kind
    return None


def expected_kind_from_binding_ref(
    binding: str | CredentialBindingRef,
    *,
    explicit: str | None,
) -> str | None:
    normalized_explicit = normalize_binding_kind(explicit)
    if normalized_explicit is not None:
        return normalized_explicit
    if not isinstance(binding, CredentialBindingRef):
        return None
    normalized_ref_kind = normalize_binding_kind(getattr(binding, "expected_kind", None))
    if normalized_ref_kind is not None:
        return normalized_ref_kind
    for key in ("expected_kind", "credential_kind", "binding_kind", "kind"):
        value = binding.metadata.get(key)
        normalized = normalize_binding_kind(value if isinstance(value, str) else None)
        if normalized is not None:
            return normalized
    return normalize_binding_kind(binding.source_type)


def credential_compatibility_error(
    record: object,
    *,
    expected_kind: str | None,
    binding_id: str,
) -> str | None:
    binding_kind = normalize_binding_kind(getattr(record, "binding_kind", None))
    source_kind = str(getattr(record, "source_kind", "") or "").strip().lower()
    normalized_id = binding_id.strip()
    if expected_kind is not None and binding_kind != expected_kind:
        return (
            "credential_kind_mismatch: credential binding "
            f"'{normalized_id}' is '{binding_kind or 'unknown'}' but requirement "
            f"expects '{expected_kind}'."
        )
    if source_kind == "oauth_account" and binding_kind not in _OAUTH_BINDING_KINDS:
        return (
            "credential_source_kind_mismatch: credential binding "
            f"'{normalized_id}' uses oauth_account source with "
            f"'{binding_kind or 'unknown'}' binding kind."
        )
    if binding_kind in _OAUTH_BINDING_KINDS and source_kind != "oauth_account":
        return (
            "credential_source_kind_mismatch: credential binding "
            f"'{normalized_id}' is '{binding_kind}' but source kind is "
            f"'{source_kind or 'unknown'}'."
        )
    return None


def normalize_binding_kind(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    aliases = {
        "bearer": "bearer_token",
        "oauth": "oauth2_account",
        "oauth2": "oauth2_account",
        "openid": "openid_connect",
        "oidc": "openid_connect",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in _KNOWN_BINDING_KINDS else None


def mismatch_readiness_status(message: str) -> AccessReadinessStatus:
    if message.startswith("credential_kind_mismatch:"):
        return AccessReadinessStatus.CREDENTIAL_KIND_MISMATCH
    return AccessReadinessStatus.CREDENTIAL_SOURCE_KIND_MISMATCH


def _split_scopes(value: str) -> tuple[str, tuple[str, ...]]:
    if not value.endswith(")") or "(" not in value:
        return value, ()
    head, raw_scopes = value[:-1].split("(", 1)
    scopes = tuple(
        scope.strip()
        for scope in raw_scopes.split(",")
        if scope is not None and scope.strip()
    )
    return head.strip(), scopes
