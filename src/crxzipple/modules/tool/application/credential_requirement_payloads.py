from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessCredentialKind,
    AccessCredentialRequirementDeclaration,
    AccessCredentialRequirementSet,
    AccessCredentialSlotRef,
    AccessCredentialTransport,
    AccessSetupFlowHint,
    AccessSetupFlowKind,
)


def credential_requirement_sets_from_payload(
    payload: object | None,
) -> tuple[AccessCredentialRequirementSet, ...]:
    if not isinstance(payload, list | tuple):
        return ()
    requirement_sets: list[AccessCredentialRequirementSet] = []
    for item in payload:
        if isinstance(item, Mapping):
            requirement_sets.append(_credential_requirement_set_from_payload(item))
    return tuple(requirement_sets)


def _credential_requirement_set_from_payload(
    payload: Mapping[str, Any],
) -> AccessCredentialRequirementSet:
    consumer = _consumer_ref_from_payload(payload.get("consumer"))
    requirements = tuple(
        _credential_requirement_from_payload(item, default_consumer=consumer)
        for item in payload.get("requirements", ())
        if isinstance(item, Mapping)
    )
    return AccessCredentialRequirementSet(
        requirement_set_id=str(payload.get("requirement_set_id", "")).strip(),
        consumer=consumer,
        requirements=requirements,
        alternative=bool(payload.get("alternative", False)),
        metadata=_mapping_payload(payload.get("metadata")),
    )


def _credential_requirement_from_payload(
    payload: Mapping[str, Any],
    *,
    default_consumer: AccessConsumerRef,
) -> AccessCredentialRequirementDeclaration:
    slot_payload = _mapping_payload(payload.get("slot"))
    setup_payload = _mapping_payload(payload.get("setup_flow_hint"))
    return AccessCredentialRequirementDeclaration(
        requirement_id=str(payload.get("requirement_id", "")).strip(),
        consumer=(
            _consumer_ref_from_payload(payload.get("consumer"))
            if isinstance(payload.get("consumer"), Mapping)
            else default_consumer
        ),
        slot=AccessCredentialSlotRef(
            slot=str(slot_payload.get("slot", "")).strip(),
            expected_kind=AccessCredentialKind(
                str(slot_payload.get("expected_kind", AccessCredentialKind.API_KEY.value)),
            ),
            binding_id=(
                str(slot_payload["binding_id"]).strip()
                if slot_payload.get("binding_id") is not None
                else None
            ),
            required=bool(slot_payload.get("required", True)),
            display_name=(
                str(slot_payload["display_name"]).strip()
                if slot_payload.get("display_name") is not None
                else None
            ),
            scopes=tuple(
                str(item).strip()
                for item in slot_payload.get("scopes", ())
                if str(item).strip()
            ),
            metadata=_mapping_payload(slot_payload.get("metadata")),
        ),
        provider=(
            str(payload["provider"]).strip()
            if payload.get("provider") is not None
            else None
        ),
        transport=AccessCredentialTransport(
            str(payload.get("transport", AccessCredentialTransport.RUNTIME_CONTEXT.value)),
        ),
        parameter_name=(
            str(payload["parameter_name"]).strip()
            if payload.get("parameter_name") is not None
            else None
        ),
        setup_flow_hint=AccessSetupFlowHint(
            flow_kind=AccessSetupFlowKind(
                str(setup_payload.get("flow_kind", AccessSetupFlowKind.NONE.value)),
            ),
            provider=(
                str(setup_payload["provider"]).strip()
                if setup_payload.get("provider") is not None
                else None
            ),
            authorization_url=(
                str(setup_payload["authorization_url"]).strip()
                if setup_payload.get("authorization_url") is not None
                else None
            ),
            token_url=(
                str(setup_payload["token_url"]).strip()
                if setup_payload.get("token_url") is not None
                else None
            ),
            device_code_url=(
                str(setup_payload["device_code_url"]).strip()
                if setup_payload.get("device_code_url") is not None
                else None
            ),
            callback_url=(
                str(setup_payload["callback_url"]).strip()
                if setup_payload.get("callback_url") is not None
                else None
            ),
            metadata=_mapping_payload(setup_payload.get("metadata")),
        ),
        metadata=_mapping_payload(payload.get("metadata")),
    )


def _consumer_ref_from_payload(payload: object | None) -> AccessConsumerRef:
    values = _mapping_payload(payload)
    return AccessConsumerRef(
        consumer_id=str(values.get("consumer_id", "")).strip(),
        module=str(values.get("module", "")).strip(),
        component=(
            str(values["component"]).strip()
            if values.get("component") is not None
            else None
        ),
        runtime_ref=(
            str(values["runtime_ref"]).strip()
            if values.get("runtime_ref") is not None
            else None
        ),
        metadata=_mapping_payload(values.get("metadata")),
    )


def _mapping_payload(value: object | None) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


__all__ = ["credential_requirement_sets_from_payload"]
