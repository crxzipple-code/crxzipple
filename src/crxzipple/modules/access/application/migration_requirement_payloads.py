from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any, Mapping

from crxzipple.modules.access.application.credential_requirement_rules import (
    canonical_credential_binding,
    is_credential_binding,
)
from crxzipple.modules.access.application.inventory_requirement_rules import (
    credential_binding_for_requirement,
)
from crxzipple.modules.access.application.migration_value_helpers import get_value


JsonObject = dict[str, Any]
_SENSITIVE_CHANNEL_KEYS = (
    "api_key",
    "auth",
    "credential",
    "password",
    "secret",
    "signing",
    "token",
    "webhook",
)


@dataclass(frozen=True, slots=True)
class MigrationCredentialSource:
    identity: str
    binding_kind: str
    source_kind: str
    source_ref: str
    canonical_ref: str
    masked_preview: str
    display_name: str


def credential_source(binding: str) -> MigrationCredentialSource:
    normalized = binding.strip()
    if is_credential_binding(normalized):
        canonical = canonical_credential_binding(normalized)
        if canonical.startswith("env:"):
            env_name = canonical.removeprefix("env:").strip()
            identity = f"env:{digest(env_name)}"
            return MigrationCredentialSource(
                identity=identity,
                binding_kind="credential_binding",
                source_kind="env",
                source_ref=env_name,
                canonical_ref=canonical,
                masked_preview=f"env:{env_name}",
                display_name=f"Environment credential {env_name}",
            )
        if canonical.startswith("file:"):
            path_ref = canonical.removeprefix("file:").strip()
            identity = f"file:{digest(path_ref)}"
            return MigrationCredentialSource(
                identity=identity,
                binding_kind="credential_binding",
                source_kind="file",
                source_ref=path_ref,
                canonical_ref=canonical,
                masked_preview="file:***",
                display_name="File credential",
            )
    literal_hash = digest(normalized, length=16)
    return MigrationCredentialSource(
        identity=f"literal:{literal_hash}",
        binding_kind="literal_ref",
        source_kind="literal",
        source_ref=f"sha256:{literal_hash}",
        canonical_ref=f"literal:sha256:{literal_hash}",
        masked_preview="literal:***",
        display_name="Inline literal credential",
    )


def channel_metadata_requirements(metadata: Mapping[str, object]) -> tuple[str, ...]:
    requirements: list[str] = []
    raw_requirements = metadata.get("access_requirements")
    if isinstance(raw_requirements, (list, tuple)):
        for item in raw_requirements:
            _append_requirement(requirements, item)
    for key, value in metadata.items():
        if not isinstance(key, str):
            continue
        normalized_key = key.strip()
        if normalized_key == "access_requirements":
            continue
        if normalized_key.endswith("_binding"):
            _append_requirement(requirements, value)
            continue
        if not _is_sensitive_channel_key(normalized_key):
            continue
        if isinstance(value, str) and value.strip():
            if is_credential_binding(value):
                _append_requirement(requirements, value)
            else:
                _append_requirement(requirements, _literal_ref(value))
    return tuple(requirements)


def requirement_sets_from_tool(tool: object) -> tuple[tuple[str, ...], ...]:
    raw_sets = get_value(tool, "access_requirement_sets", ()) or ()
    sets = normalize_requirement_sets(
        tuple(
            tuple(item) if isinstance(item, (list, tuple)) else (str(item),)
            for item in raw_sets
        ),
    )
    if sets:
        return sets
    raw_requirements = get_value(tool, "access_requirements", ()) or ()
    return normalize_requirement_sets((tuple(raw_requirements),))


def normalize_requirement_sets(
    requirement_sets: tuple[tuple[str, ...], ...],
) -> tuple[tuple[str, ...], ...]:
    resolved: list[tuple[str, ...]] = []
    for requirement_set in requirement_sets:
        normalized = tuple(
            dict.fromkeys(
                item.strip()
                for item in requirement_set
                if isinstance(item, str) and item.strip()
            ),
        )
        if normalized and normalized not in resolved:
            resolved.append(normalized)
    return tuple(resolved)


def masked_requirement_sets(
    requirement_sets: tuple[tuple[str, ...], ...],
) -> tuple[tuple[str, ...], ...]:
    return tuple(
        tuple(_masked_requirement(item) for item in requirement_set)
        for requirement_set in requirement_sets
    )


def requirement_display(requirement_sets: tuple[tuple[str, ...], ...]) -> str:
    labels = [
        " + ".join(_masked_requirement(item) for item in requirement_set)
        for requirement_set in requirement_sets
    ]
    return " / ".join(label for label in labels if label) or "Access requirement"


def credential_binding_for_migration_requirement(requirement: str) -> str | None:
    normalized = requirement.strip()
    if normalized.startswith("literal:sha256:"):
        return normalized
    return credential_binding_for_requirement(normalized)


def slugify(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "-", value.strip())
    return normalized.strip("-") or "default"


def digest(value: str, *, length: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def redaction_policy() -> JsonObject:
    return {
        "secret_material_allowed": False,
        "sensitive_metadata_keys": ("api_key", "password", "secret", "token", "value"),
    }


def _masked_requirement(requirement: str) -> str:
    binding = credential_binding_for_migration_requirement(requirement)
    if binding is None:
        return requirement.strip()
    if is_credential_binding(binding):
        normalized = requirement.strip()
        if normalized == binding.strip():
            return canonical_credential_binding(binding)
        return normalized
    return "literal:***"

def _literal_ref(value: str) -> str:
    return f"literal:sha256:{digest(value.strip(), length=16)}"


def _append_requirement(resolved: list[str], value: object) -> None:
    if not isinstance(value, str):
        return
    normalized = value.strip()
    if normalized and normalized not in resolved:
        resolved.append(normalized)


def _is_sensitive_channel_key(key: str) -> bool:
    normalized = key.lower()
    return any(part in normalized for part in _SENSITIVE_CHANNEL_KEYS)
