from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from crxzipple.shared.access import AccessSetupFlowHint


JsonObject = dict[str, Any]


def add_timestamp_payload(
    payload: JsonObject,
    key: str,
    value: datetime | None,
) -> None:
    if value is not None:
        payload[key] = value.isoformat()


def normalize_requirement_sets(
    requirement_sets: tuple[tuple[str, ...], ...],
) -> tuple[tuple[str, ...], ...]:
    resolved: list[tuple[str, ...]] = []
    for requirement_set in requirement_sets:
        normalized = tuple(
            dict.fromkeys(
                str(item).strip()
                for item in requirement_set
                if item is not None and str(item).strip()
            ),
        )
        if normalized and normalized not in resolved:
            resolved.append(normalized)
    return tuple(resolved)


def normalize_slot_bindings(value: Mapping[str, str]) -> JsonObject:
    normalized: dict[str, str] = {}
    for slot, binding_id in value.items():
        slot_text = str(slot).strip()
        binding_text = str(binding_id).strip()
        if slot_text and binding_text:
            normalized[slot_text] = binding_text
    return normalized


def redacted_mapping(value: Mapping[str, object]) -> JsonObject:
    return {str(key): redacted_value(str(key), item) for key, item in value.items()}


def redacted_check_mapping(value: Mapping[str, object]) -> JsonObject:
    payload = redacted_mapping(value)
    target_type = str(payload.get("target_type") or "")
    requirement = payload.get("requirement")
    if (
        target_type == "credential_binding"
        and isinstance(requirement, str)
    ):
        payload["requirement"] = (
            masked_binding_reference(requirement)
            if is_safe_binding_reference(requirement)
            else "literal:***"
        )
    return payload


def setup_flow_hint_payload(
    value: AccessSetupFlowHint | None,
) -> JsonObject | None:
    if value is None:
        return None
    return {
        "flow_kind": str(value.flow_kind),
        "provider": value.provider,
        "authorization_url": value.authorization_url,
        "token_url": value.token_url,
        "device_code_url": value.device_code_url,
        "callback_url": value.callback_url,
        "metadata": redacted_mapping(value.metadata),
    }


def requirements_by_consumer(
    requirements: tuple[Any, ...],
) -> JsonObject:
    grouped: dict[str, list[JsonObject]] = {}
    for requirement in requirements:
        key = ":".join(
            (
                str(requirement.consumer_module),
                str(requirement.consumer_kind),
                str(requirement.consumer_id),
            ),
        )
        grouped.setdefault(key, []).append(requirement.to_payload())
    return grouped


def safe_requirement_sets(
    requirement_sets: tuple[tuple[str, ...], ...],
) -> list[list[str]]:
    return [
        [safe_requirement_ref(item) for item in requirement_set]
        for requirement_set in requirement_sets
    ]


def safe_requirement_ref(value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        return ""
    if normalized.startswith(("env:", "file:", "literal:", "inline:")):
        return f"{normalized.split(':', 1)[0]}:***"
    if "(" in normalized and normalized.endswith(")"):
        prefix = normalized.split("(", 1)[0].strip()
        return f"{prefix}(***)"
    return normalized


def safe_source_ref(source_kind: str, source_ref: str) -> str:
    normalized_kind = source_kind.strip().lower()
    if normalized_kind in {"env", "file"}:
        return f"{normalized_kind}:***"
    if normalized_kind in {"literal", "inline", "inline_credential", "secret"}:
        return "***"
    return str(redacted_value("source_ref", source_ref))


def source_metadata(source_kind: str, source_ref: str) -> JsonObject:
    normalized_kind = source_kind.strip().lower()
    normalized_ref = source_ref.strip()
    metadata: JsonObject = {
        "source_kind": normalized_kind,
        "configured": bool(normalized_ref),
        "source_ref_redacted": bool(normalized_ref),
    }
    if normalized_kind == "env" and normalized_ref:
        metadata["reference_kind"] = "environment_variable"
    elif normalized_kind == "file" and normalized_ref:
        metadata["reference_kind"] = "file_path"
    elif normalized_kind == "oauth_account" and normalized_ref:
        metadata["source_ref_redacted"] = False
    return metadata


def safe_masked_preview(source_kind: str, masked_preview: str | None) -> str | None:
    if masked_preview is None:
        return None
    normalized_kind = source_kind.strip().lower()
    if normalized_kind in {"env", "file"}:
        return f"{normalized_kind}:***"
    if normalized_kind in {"literal", "inline", "inline_credential", "secret"}:
        return "***"
    return str(redacted_value("masked_preview", masked_preview))


def redacted_value(key: str, value: object) -> object:
    if is_sensitive_key(key):
        if isinstance(value, str) and is_safe_binding_reference(value):
            return masked_binding_reference(value)
        return "***" if value is not None else None
    if isinstance(value, Mapping):
        return redacted_mapping(value)
    if isinstance(value, (list, tuple)):
        return [redacted_value("", item) for item in value]
    if isinstance(value, str) and is_safe_binding_reference(value):
        return masked_binding_reference(value)
    return value


def is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in {
        "access_token",
        "api_key",
        "authorization",
        "canonical_ref",
        "client_secret",
        "code",
        "code_verifier",
        "device_code",
        "id_token",
        "password",
        "refresh_token",
        "secret",
        "secret_value",
        "source_ref",
        "state",
        "token",
        "value",
    }


def is_safe_binding_reference(value: str) -> bool:
    normalized = value.strip()
    return normalized.startswith(("env:", "file:"))


def masked_binding_reference(value: str) -> str:
    normalized = value.strip()
    if normalized.startswith("env:"):
        return "env:***"
    if normalized.startswith("file:"):
        return "file:***"
    return "***"
