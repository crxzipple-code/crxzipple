from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any, Mapping

from crxzipple.modules.tool.domain.value_objects import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionSupport,
    ToolMode,
)
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


def dict_payload(value: object | None) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def dict_tuple_payload(value: object | None) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, dict))


def string_tuple_payload(value: object | None) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(
        dict.fromkeys(
            str(item).strip()
            for item in value
            if str(item).strip()
        ),
    )


def enum_filter_value(value: object | None) -> str | None:
    if value is None:
        return None
    raw_value = getattr(value, "value", value)
    return str(raw_value)


def credential_requirement_set_payload(
    requirement_set: AccessCredentialRequirementSet,
) -> dict[str, object]:
    payload = _stable_json_value(requirement_set)
    assert isinstance(payload, dict)
    return payload


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


def execution_support_to_payload(
    execution_support: ToolExecutionSupport,
) -> dict[str, object]:
    return {
        "supported_modes": [
            mode.value for mode in execution_support.supported_modes
        ],
        "supported_strategies": [
            strategy.value
            for strategy in execution_support.supported_strategies
        ],
        "supported_environments": [
            environment.value
            for environment in execution_support.supported_environments
        ],
    }


def execution_support_from_payload(payload: object | None) -> ToolExecutionSupport:
    if not isinstance(payload, dict):
        return ToolExecutionSupport()
    return ToolExecutionSupport(
        supported_modes=tuple(
            ToolMode(value)
            for value in payload.get("supported_modes", (ToolMode.INLINE.value,))
        ),
        supported_strategies=tuple(
            ToolExecutionStrategy(value)
            for value in payload.get(
                "supported_strategies",
                (ToolExecutionStrategy.ASYNC.value,),
            )
        ),
        supported_environments=tuple(
            ToolEnvironment(value)
            for value in payload.get(
                "supported_environments",
                (ToolEnvironment.LOCAL.value,),
            )
        ),
    )


def _stable_json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            field.name: _stable_json_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _stable_json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple | list):
        return [_stable_json_value(item) for item in value]
    return value


def _credential_requirement_set_from_payload(
    payload: Mapping[str, Any],
) -> AccessCredentialRequirementSet:
    consumer = _consumer_ref_from_payload(payload.get("consumer"))
    raw_requirements = payload.get("requirements")
    requirements: list[AccessCredentialRequirementDeclaration] = []
    if isinstance(raw_requirements, list | tuple):
        for item in raw_requirements:
            if isinstance(item, Mapping):
                requirements.append(
                    _credential_requirement_from_payload(item, default_consumer=consumer),
                )
    return AccessCredentialRequirementSet(
        requirement_set_id=str(payload.get("requirement_set_id", "")).strip(),
        consumer=consumer,
        requirements=tuple(requirements),
        alternative=bool(payload.get("alternative", False)),
        metadata=dict_payload(payload.get("metadata")),
    )


def _credential_requirement_from_payload(
    payload: Mapping[str, Any],
    *,
    default_consumer: AccessConsumerRef,
) -> AccessCredentialRequirementDeclaration:
    slot_payload = payload.get("slot") if isinstance(payload.get("slot"), Mapping) else {}
    setup_payload = (
        payload.get("setup_flow_hint")
        if isinstance(payload.get("setup_flow_hint"), Mapping)
        else {}
    )
    assert isinstance(slot_payload, Mapping)
    assert isinstance(setup_payload, Mapping)
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
            metadata=dict_payload(slot_payload.get("metadata")),
        ),
        provider=(
            str(payload["provider"]).strip()
            if payload.get("provider") is not None
            else None
        ),
        transport=AccessCredentialTransport(
            str(
                payload.get(
                    "transport",
                    AccessCredentialTransport.RUNTIME_CONTEXT.value,
                ),
            ),
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
            metadata=dict_payload(setup_payload.get("metadata")),
        ),
        metadata=dict_payload(payload.get("metadata")),
    )


def _consumer_ref_from_payload(payload: object | None) -> AccessConsumerRef:
    if not isinstance(payload, Mapping):
        payload = {}
    return AccessConsumerRef(
        consumer_id=str(payload.get("consumer_id", "")).strip(),
        module=str(payload.get("module", "")).strip(),
        component=(
            str(payload["component"]).strip()
            if payload.get("component") is not None
            else None
        ),
        runtime_ref=(
            str(payload["runtime_ref"]).strip()
            if payload.get("runtime_ref") is not None
            else None
        ),
        metadata=dict_payload(payload.get("metadata")),
    )
