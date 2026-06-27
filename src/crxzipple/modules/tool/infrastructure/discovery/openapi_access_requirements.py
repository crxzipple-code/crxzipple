from __future__ import annotations

from typing import Any, Protocol

from crxzipple.core.config import OpenApiCredentialBinding
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


class _OpenApiSecuritySchemeLike(Protocol):
    name: str
    scheme_type: str
    parameter_name: str | None
    location: str | None
    http_scheme: str | None
    metadata: dict[str, Any]


class _OpenApiSecurityRequirementLike(Protocol):
    scheme_names: tuple[str, ...]
    scopes_by_scheme: dict[str, tuple[str, ...]]


class _OpenApiOperationLike(Protocol):
    provider_name: str
    tool_id: str
    runtime_key: str
    security_schemes: tuple[_OpenApiSecuritySchemeLike, ...]
    security_requirements: tuple[_OpenApiSecurityRequirementLike, ...]
    credential_bindings: tuple[OpenApiCredentialBinding, ...]


def operation_access_requirement_sets(
    operation: _OpenApiOperationLike,
) -> tuple[tuple[str, ...], ...]:
    if not operation.security_requirements:
        return ()
    bindings_by_name = {
        binding.scheme_name: binding for binding in operation.credential_bindings
    }
    requirement_sets: list[tuple[str, ...]] = []
    for requirement in operation.security_requirements:
        if not requirement.scheme_names:
            requirement_sets.append(())
            continue
        requirements: list[str] = []
        for scheme_name in requirement.scheme_names:
            binding = bindings_by_name.get(scheme_name)
            if binding is None:
                requirements.append("credential")
                continue
            requirements.extend(_credential_binding_requirements(binding))
        requirement_sets.append(
            tuple(dict.fromkeys(item for item in requirements if item)),
        )
    if any(not requirement_set for requirement_set in requirement_sets):
        return ((),)
    return tuple(dict.fromkeys(requirement_sets))


def operation_credential_requirement_sets(
    operation: _OpenApiOperationLike,
) -> tuple[AccessCredentialRequirementSet, ...]:
    if not operation.security_requirements:
        return ()

    schemes_by_name = {scheme.name: scheme for scheme in operation.security_schemes}
    bindings_by_name = {
        binding.scheme_name: binding for binding in operation.credential_bindings
    }
    consumer = AccessConsumerRef(
        consumer_id=operation.tool_id,
        module="tool",
        component="openapi",
        runtime_ref=operation.runtime_key,
        metadata={"provider_name": operation.provider_name},
    )
    requirement_sets: list[AccessCredentialRequirementSet] = []
    for index, requirement in enumerate(operation.security_requirements):
        declarations: list[AccessCredentialRequirementDeclaration] = []
        for scheme_name in requirement.scheme_names:
            scheme = schemes_by_name.get(scheme_name)
            if scheme is None:
                continue
            declarations.extend(
                _credential_requirement_declarations(
                    operation=operation,
                    consumer=consumer,
                    scheme=scheme,
                    binding=bindings_by_name.get(scheme_name),
                    scopes=requirement.scopes_by_scheme.get(scheme_name, ()),
                ),
            )
        requirement_sets.append(
            AccessCredentialRequirementSet(
                requirement_set_id=f"{operation.tool_id}.security.{index}",
                consumer=consumer,
                requirements=tuple(declarations),
                alternative=len(operation.security_requirements) > 1,
                metadata={"security_requirement_index": index},
            ),
        )
    if any(not requirement_set.requirements for requirement_set in requirement_sets):
        return (
            AccessCredentialRequirementSet(
                requirement_set_id=f"{operation.tool_id}.security.none",
                consumer=consumer,
                requirements=(),
                alternative=True,
                metadata={"openapi_security": "optional"},
            ),
        )
    return tuple(requirement_sets)


def _credential_binding_requirements(
    binding: OpenApiCredentialBinding,
) -> tuple[str, ...]:
    values = (
        binding.credential_binding_id,
        binding.username_binding_id,
        binding.password_binding_id,
    )
    return tuple(
        dict.fromkeys(
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip()
        ),
    )


def _credential_requirement_declarations(
    *,
    operation: _OpenApiOperationLike,
    consumer: AccessConsumerRef,
    scheme: _OpenApiSecuritySchemeLike,
    binding: OpenApiCredentialBinding | None,
    scopes: tuple[str, ...],
) -> tuple[AccessCredentialRequirementDeclaration, ...]:
    kind = _credential_kind_for_scheme(scheme)
    if kind is None:
        return ()
    transport = _credential_transport_for_scheme(scheme)
    if kind is AccessCredentialKind.BASIC:
        return (
            _credential_requirement_declaration(
                operation=operation,
                consumer=consumer,
                scheme=scheme,
                slot=f"{scheme.name}.username",
                kind=kind,
                transport=transport,
                scopes=scopes,
                binding_id=binding.username_binding_id if binding else None,
                metadata={"basic_part": "username"},
            ),
            _credential_requirement_declaration(
                operation=operation,
                consumer=consumer,
                scheme=scheme,
                slot=f"{scheme.name}.password",
                kind=kind,
                transport=transport,
                scopes=scopes,
                binding_id=binding.password_binding_id if binding else None,
                metadata={"basic_part": "password"},
            ),
        )
    return (
        _credential_requirement_declaration(
            operation=operation,
            consumer=consumer,
            scheme=scheme,
            slot=scheme.name,
            kind=kind,
            transport=transport,
            scopes=scopes,
            binding_id=binding.credential_binding_id if binding else None,
            metadata={},
        ),
    )


def _credential_requirement_declaration(
    *,
    operation: _OpenApiOperationLike,
    consumer: AccessConsumerRef,
    scheme: _OpenApiSecuritySchemeLike,
    slot: str,
    kind: AccessCredentialKind,
    transport: AccessCredentialTransport,
    scopes: tuple[str, ...],
    binding_id: str | None,
    metadata: dict[str, Any],
) -> AccessCredentialRequirementDeclaration:
    return AccessCredentialRequirementDeclaration(
        requirement_id=f"{operation.tool_id}.{slot}",
        consumer=consumer,
        slot=AccessCredentialSlotRef(
            slot=slot,
            expected_kind=kind,
            binding_id=binding_id,
            display_name=slot,
            scopes=scopes,
            metadata={"openapi_security_scheme": scheme.name},
        ),
        provider=operation.provider_name,
        transport=transport,
        parameter_name=scheme.parameter_name,
        setup_flow_hint=_setup_flow_hint_for_scheme(scheme),
        metadata={
            "openapi_security_scheme": scheme.name,
            "openapi_security_type": scheme.scheme_type,
            **scheme.metadata,
            **metadata,
        },
    )


def _credential_kind_for_scheme(
    scheme: _OpenApiSecuritySchemeLike,
) -> AccessCredentialKind | None:
    scheme_type = scheme.scheme_type.strip().lower()
    if scheme_type == "apikey":
        return AccessCredentialKind.API_KEY
    if scheme_type == "http":
        if scheme.http_scheme == "bearer":
            return AccessCredentialKind.BEARER_TOKEN
        if scheme.http_scheme == "basic":
            return AccessCredentialKind.BASIC
    if scheme_type == "oauth2":
        return AccessCredentialKind.OAUTH2_ACCOUNT
    if scheme_type == "openidconnect":
        return AccessCredentialKind.OPENID_CONNECT
    return None


def _credential_transport_for_scheme(
    scheme: _OpenApiSecuritySchemeLike,
) -> AccessCredentialTransport:
    scheme_type = scheme.scheme_type.strip().lower()
    if scheme_type == "apikey":
        location = (scheme.location or "").strip().lower()
        if location == "header":
            return AccessCredentialTransport.HEADER
        if location == "query":
            return AccessCredentialTransport.QUERY
        if location == "cookie":
            return AccessCredentialTransport.COOKIE
    if scheme_type in {"oauth2", "openidconnect"}:
        return AccessCredentialTransport.OAUTH_AUTHORIZATION_HEADER
    if scheme_type == "http" and scheme.http_scheme == "bearer":
        return AccessCredentialTransport.OAUTH_AUTHORIZATION_HEADER
    if scheme_type == "http" and scheme.http_scheme == "basic":
        return AccessCredentialTransport.HEADER
    return AccessCredentialTransport.RUNTIME_CONTEXT


def _setup_flow_hint_for_scheme(
    scheme: _OpenApiSecuritySchemeLike,
) -> AccessSetupFlowHint:
    if scheme.scheme_type.strip().lower() == "oauth2":
        return AccessSetupFlowHint(
            flow_kind=AccessSetupFlowKind.BROWSER_OAUTH,
            provider=scheme.name,
            authorization_url=_optional_metadata_text(scheme.metadata, "authorization_url"),
            token_url=_optional_metadata_text(scheme.metadata, "token_url"),
        )
    if scheme.scheme_type.strip().lower() == "openidconnect":
        return AccessSetupFlowHint(
            flow_kind=AccessSetupFlowKind.BROWSER_OAUTH,
            provider=scheme.name,
            authorization_url=_optional_metadata_text(
                scheme.metadata,
                "open_id_connect_url",
            ),
        )
    return AccessSetupFlowHint(flow_kind=AccessSetupFlowKind.MANUAL)


def _optional_metadata_text(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    if not isinstance(value, str):
        return None
    return value.strip() or None


__all__ = [
    "operation_access_requirement_sets",
    "operation_credential_requirement_sets",
]
