from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.access.application.read_models import (
    AccessConsumerBindingReadModel,
    AccessCredentialRequirementReadModel,
    AccessOAuthProviderReadModel,
    AccessReadinessReadModel,
    CredentialBindingReadModel,
)
from crxzipple.shared.access import AccessSetupFlowHint, AccessSetupFlowKind


JsonObject = dict[str, Any]


def credential_requirements_from_records(
    consumers: tuple[AccessConsumerBindingReadModel, ...],
    *,
    credentials: tuple[CredentialBindingReadModel, ...],
    readiness: tuple[AccessReadinessReadModel, ...],
    oauth_providers: tuple[AccessOAuthProviderReadModel, ...],
) -> tuple[AccessCredentialRequirementReadModel, ...]:
    credentials_by_id = {item.binding_id: item for item in credentials}
    active_oauth_provider_ids = {
        item.provider_id for item in oauth_providers if item.status == "active"
    }
    rows: list[AccessCredentialRequirementReadModel] = []
    for consumer in consumers:
        if not consumer.requirement_sets:
            continue
        for set_index, requirement_set in enumerate(consumer.requirement_sets):
            for requirement_index, requirement in enumerate(requirement_set):
                parsed = _parse_requirement_ref(requirement)
                credential_binding_id = _binding_id_for_slot(
                    consumer,
                    str(parsed["slot"]),
                )
                binding = (
                    credentials_by_id.get(credential_binding_id)
                    if credential_binding_id
                    else None
                )
                ready, status, reason = _requirement_status(
                    expected_kind=parsed["expected_kind"],
                    binding=binding,
                    consumer_enabled=consumer.enabled,
                    consumer_status=consumer.status,
                )
                rows.append(
                    AccessCredentialRequirementReadModel(
                        requirement_id=_requirement_row_id(
                            consumer,
                            set_index=set_index,
                            requirement_index=requirement_index,
                        ),
                        consumer_module=consumer.consumer_module,
                        consumer_kind=consumer.consumer_kind,
                        consumer_id=consumer.consumer_id,
                        slot=str(parsed["slot"]),
                        expected_kind=str(parsed["expected_kind"]),
                        binding_id=credential_binding_id,
                        consumer_binding_id=consumer.binding_id,
                        display_name=consumer.display_name,
                        provider=parsed.get("provider"),
                        required=True,
                        ready=ready,
                        missing=binding is None,
                        status=status,
                        reason=reason,
                        setup_flow_hint=_setup_flow_hint_for_kind(
                            str(parsed["expected_kind"]),
                            provider=parsed.get("provider"),
                            provider_configured=(
                                parsed.get("provider") in active_oauth_provider_ids
                                if parsed.get("provider") is not None
                                else False
                            ),
                        ),
                        metadata={
                            "requirement_set_index": set_index,
                            "requirement_index": requirement_index,
                        },
                        last_checked_at=_readiness_observed_at(
                            readiness,
                            target_kind="credential_binding",
                            target_id=credential_binding_id,
                        ),
                    ),
                )
    return tuple(rows)


def requirements_by_consumer_payload(
    requirements: tuple[AccessCredentialRequirementReadModel, ...],
) -> JsonObject:
    grouped: dict[str, list[JsonObject]] = {}
    for requirement in requirements:
        key = ":".join(
            (
                requirement.consumer_module,
                requirement.consumer_kind,
                requirement.consumer_id,
            ),
        )
        grouped.setdefault(key, []).append(requirement.to_payload())
    return grouped


def _binding_id_for_slot(
    consumer: AccessConsumerBindingReadModel,
    slot: str,
) -> str | None:
    binding_id = consumer.credential_bindings.get(slot)
    if binding_id:
        return binding_id
    if consumer.credential_bindings:
        return None
    return consumer.credential_binding_id


def _parse_requirement_ref(
    value: str,
    *,
    fallback_kind: str | None = None,
) -> JsonObject:
    normalized = str(value).strip()
    provider: str | None = None
    kind_source = normalized
    if ":" in normalized and not normalized.startswith(("env:", "file:", "literal:")):
        possible_provider, rest = normalized.split(":", 1)
        if possible_provider.strip() and "(" in rest:
            provider = possible_provider.strip()
            kind_source = rest
    expected_kind = _expected_kind_from_text(kind_source, fallback_kind=fallback_kind)
    slot = _slot_from_text(kind_source, expected_kind=expected_kind)
    return {
        "provider": provider,
        "expected_kind": expected_kind,
        "slot": slot,
    }


def _expected_kind_from_text(
    value: str,
    *,
    fallback_kind: str | None,
) -> str:
    normalized = value.strip().lower()
    candidates = {
        "api_key": ("api_key", "apikey", "x-api-key"),
        "bearer_token": ("bearer", "bearer_token", "access_token"),
        "basic": ("basic", "username", "password"),
        "oauth2_account": ("oauth2", "oauth"),
        "openid_connect": ("openid", "oidc"),
        "app_secret": ("app_secret", "client_secret"),
        "webhook_secret": ("webhook_secret", "webhook"),
        "certificate": ("certificate", "cert", "pem"),
    }
    for kind, markers in candidates.items():
        if any(marker in normalized for marker in markers):
            return kind
    if fallback_kind:
        return fallback_kind.strip().lower() or "api_key"
    return "api_key"


def _slot_from_text(value: str, *, expected_kind: str) -> str:
    normalized = value.strip()
    if "(" in normalized:
        prefix = normalized.split("(", 1)[0].strip().lower()
        inside = normalized.rsplit("(", 1)[1].rsplit(")", 1)[0].strip()
        if inside and not inside.startswith(("env:", "file:", "literal:", "inline:")):
            return _safe_slot(inside)
        if prefix:
            return _safe_slot(prefix)
    return _safe_slot(expected_kind)


def _safe_slot(value: str) -> str:
    normalized = "".join(
        char if char.isalnum() or char in {"_", "-"} else "_"
        for char in value.strip().lower()
    ).strip("_")
    return normalized or "credential"


def _requirement_status(
    *,
    expected_kind: str,
    binding: CredentialBindingReadModel | None,
    consumer_enabled: bool,
    consumer_status: str,
) -> tuple[bool, str, str | None]:
    if not consumer_enabled or consumer_status != "active":
        return False, "disabled", "consumer binding is disabled"
    if binding is None:
        return False, "missing", "credential binding is missing"
    if binding.status != "active":
        return False, binding.status, "credential binding is not active"
    binding_kind = binding.binding_kind.strip().lower()
    if binding_kind != expected_kind:
        return (
            False,
            "credential_kind_mismatch",
            "credential binding kind does not match requirement",
        )
    source_kind = binding.source_kind.strip().lower()
    if source_kind == "oauth_account" and binding_kind not in {
        "oauth2_account",
        "openid_connect",
    }:
        return (
            False,
            "credential_source_kind_mismatch",
            "oauth_account source can only satisfy OAuth or OpenID Connect credentials",
        )
    if binding_kind in {"oauth2_account", "openid_connect"} and source_kind != "oauth_account":
        return (
            False,
            "credential_source_kind_mismatch",
            "OAuth credential bindings must use an oauth_account source",
        )
    return True, "ready", None


def _setup_flow_hint_for_kind(
    expected_kind: str,
    *,
    provider: object,
    provider_configured: bool = False,
) -> AccessSetupFlowHint:
    if expected_kind in {"oauth2_account", "openid_connect"}:
        if provider_configured:
            return AccessSetupFlowHint(
                flow_kind=AccessSetupFlowKind.BROWSER_OAUTH,
                provider=str(provider).strip() if provider else None,
                metadata={
                    "setup_provider_missing": False,
                    "requires_setup_session": True,
                    "reason": "access_oauth_provider_configured",
                },
            )
        return AccessSetupFlowHint(
            flow_kind=AccessSetupFlowKind.MANUAL,
            provider=str(provider).strip() if provider else None,
            metadata={
                "setup_provider_missing": True,
                "expected_flow_kind": str(AccessSetupFlowKind.BROWSER_OAUTH),
                "reason": "access_oauth_provider_not_configured",
            },
        )
    return AccessSetupFlowHint(flow_kind=AccessSetupFlowKind.MANUAL)


def _requirement_row_id(
    consumer: AccessConsumerBindingReadModel,
    *,
    set_index: int,
    requirement_index: int,
) -> str:
    return ":".join(
        (
            "credential_requirement",
            consumer.consumer_module,
            consumer.consumer_kind,
            consumer.consumer_id,
            str(set_index),
            str(requirement_index),
        ),
    )


def _readiness_observed_at(
    readiness: tuple[AccessReadinessReadModel, ...],
    *,
    target_kind: str,
    target_id: str | None,
) -> datetime | None:
    if target_id is None:
        return None
    match = next(
        (
            item
            for item in readiness
            if item.target_kind == target_kind and item.target_id == target_id
        ),
        None,
    )
    return match.observed_at if match is not None else None
