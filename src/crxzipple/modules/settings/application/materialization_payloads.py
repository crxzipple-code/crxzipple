from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.shared.settings import (
    AccessConfig,
    ToolProviderConfig,
    ToolRootConfig,
)


JsonObject = dict[str, Any]


def with_default_id(
    payload: Mapping[str, Any],
    field_name: str,
    resource_id: str,
) -> JsonObject:
    normalized = dict(payload)
    normalized.setdefault(field_name, resource_id)
    normalized.setdefault("id", resource_id)
    return normalized


def legacy_llm_profile_payload(
    resource_id: str,
    payload: Mapping[str, Any],
) -> JsonObject:
    normalized = with_default_id(payload, "profile_id", resource_id)
    if normalized.get("model_name") is None and normalized.get("model") is not None:
        normalized["model_name"] = normalized["model"]
    for field_name in ("provider", "api_family", "model_name"):
        required_legacy_text(normalized.get(field_name), field_name=field_name)
    return normalized


def legacy_agent_profile_payload(
    resource_id: str,
    payload: Mapping[str, Any],
) -> JsonObject:
    return with_default_id(payload, "profile_id", resource_id)


def legacy_channel_profile_payload(
    resource_id: str,
    payload: Mapping[str, Any],
) -> JsonObject:
    normalized = normalize_channel_payload(resource_id, payload)
    normalized.setdefault("id", resource_id)
    return normalized


def required_legacy_text(value: object, *, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} is required.")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


def tool_provider_from_payload(
    resource_id: str,
    payload: Mapping[str, Any],
) -> ToolProviderConfig | None:
    provider_kind = str(
        payload.get("provider_kind") or payload.get("kind") or "",
    ).strip()
    if provider_kind in {"", "local_root"}:
        return None
    default_provider_id = str(payload.get("name") or resource_id)
    normalized = with_default_id(payload, "provider_id", default_provider_id)
    if normalized.get("spec_path") is None and normalized.get("spec_location") is not None:
        normalized["spec_path"] = normalized["spec_location"]
    return ToolProviderConfig.from_payload(normalized)


def tool_root_from_payload(
    resource_id: str,
    payload: Mapping[str, Any],
) -> ToolRootConfig | None:
    provider_kind = str(
        payload.get("provider_kind") or payload.get("kind") or "",
    ).strip()
    if provider_kind not in {"", "local_root"}:
        return None
    if payload.get("path") is None:
        return None
    normalized = with_default_id(payload, "root_id", resource_id)
    normalized.setdefault("source_kind", "local")
    return ToolRootConfig.from_payload(normalized)


def access_config_from_payload(
    resource_id: str,
    payload: Mapping[str, Any],
) -> AccessConfig:
    normalized = normalize_access_payload(resource_id, payload)
    return AccessConfig.from_payload(normalized)


def normalize_channel_payload(
    resource_id: str,
    payload: Mapping[str, Any],
) -> JsonObject:
    normalized = with_default_id(payload, "profile_id", resource_id)
    if (
        normalized.get("channel_kind") is None
        and normalized.get("channel_type") is not None
    ):
        normalized["channel_kind"] = normalized["channel_type"]
    return normalized


def normalize_access_payload(
    resource_id: str,
    payload: Mapping[str, Any],
) -> JsonObject:
    normalized = with_default_id(payload, "config_id", resource_id)
    declaration_kind = str(
        normalized.get("access_declaration_kind")
        or normalized.get("declaration_kind")
        or normalized.get("resource_type")
        or "",
    ).strip()
    if declaration_kind in {"asset", "access_asset"}:
        normalized.setdefault("assets", (without_declaration_kind(normalized),))
    elif declaration_kind in {"credential_binding", "credential"}:
        normalized.setdefault(
            "credential_bindings",
            (without_declaration_kind(normalized),),
        )
    elif declaration_kind in {"consumer_binding", "consumer"}:
        normalized.setdefault(
            "consumer_bindings",
            (without_declaration_kind(normalized),),
        )
    elif declaration_kind in {"provider_scope_enablement", "provider_scope"}:
        normalized.setdefault(
            "provider_scope_enablements",
            (without_declaration_kind(normalized),),
        )
    elif declaration_kind in {"permission_enablement", "permission"}:
        normalized.setdefault(
            "permission_enablements",
            (without_declaration_kind(normalized),),
        )
    return normalized


def without_declaration_kind(payload: Mapping[str, Any]) -> JsonObject:
    return {
        str(key): value
        for key, value in payload.items()
        if key
        not in {
            "access_declaration_kind",
            "declaration_kind",
            "resource_type",
            "config_id",
            "id",
        }
    }
