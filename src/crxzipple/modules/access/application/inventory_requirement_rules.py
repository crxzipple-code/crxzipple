from __future__ import annotations

from crxzipple.modules.access.application.credential_requirement_rules import (
    canonical_credential_binding,
    is_credential_binding,
    parse_access_requirement,
)


AccessReadinessCheckSpec = tuple[str, str, bool]
_CREDENTIAL_REQUIREMENT_KINDS = {"api_key", "bearer", "basic", "credential"}


def credential_binding_for_requirement(requirement: str) -> str | None:
    normalized = requirement.strip()
    if is_credential_binding(normalized):
        return normalized
    parsed = parse_access_requirement(normalized)
    if parsed.kind not in _CREDENTIAL_REQUIREMENT_KINDS or len(parsed.scopes) != 1:
        return None
    candidate = parsed.scopes[0].strip()
    if is_credential_binding(candidate):
        return candidate
    return None


def credential_asset_kind(binding: str) -> str:
    normalized = binding.strip()
    if normalized.startswith("env:"):
        return "env"
    if normalized.startswith("file:"):
        return "file"
    return "inline_credential"


def credential_binding_check_spec(
    binding: str,
    *,
    allow_literal: bool,
) -> AccessReadinessCheckSpec:
    canonical = canonical_credential_binding(binding)
    return (
        "credential_binding",
        masked_inventory_requirement(canonical, allow_literal=allow_literal),
        allow_literal and not is_credential_binding(canonical),
    )


def access_check_label(target_type: str, raw: str) -> str:
    normalized = raw.strip()
    if normalized.startswith("env:"):
        env_name = normalized.removeprefix("env:").strip()
        return env_name or "env"
    if normalized.startswith("file:"):
        path = normalized.removeprefix("file:").strip()
        return f"file:{path}" if path else "file credential"
    if target_type == "credential_binding":
        return _credential_binding_label(normalized)
    return normalized


def masked_inventory_requirement(value: str, *, allow_literal: bool) -> str:
    normalized = value.strip()
    if is_credential_binding(normalized):
        return canonical_credential_binding(normalized)
    if allow_literal:
        return "literal:***"
    return normalized


def _credential_binding_label(binding: str) -> str:
    normalized = binding.strip()
    if normalized.startswith("env:"):
        env_name = normalized.removeprefix("env:").strip()
        return f"env:{env_name}" if env_name else "env"
    if normalized.startswith("file:"):
        return "file credential"
    return "inline credential"
