from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

from crxzipple.modules.tool.application.capabilities import (
    DEFAULT_TOOL_CAPABILITY_CATALOG,
)
from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.core.config import OpenApiCredentialBinding, OpenApiProviderSettings
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
from crxzipple.modules.tool.domain import ToolDefinitionOrigin
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.value_objects import (
    ToolEnvironment,
    ToolExecutionPolicy,
    ToolExecutionSupport,
    ToolExecutionStrategy,
    ToolKind,
    ToolMode,
    ToolParameter,
)


SUPPORTED_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


@dataclass(frozen=True, slots=True)
class OpenApiSecurityScheme:
    name: str
    scheme_type: str
    parameter_name: str | None = None
    location: str | None = None
    http_scheme: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OpenApiSecurityRequirement:
    scheme_names: tuple[str, ...]
    scopes_by_scheme: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OpenApiOperation:
    provider_name: str
    tool_id: str
    runtime_key: str
    name: str
    description: str
    method: str
    path_template: str
    base_url: str
    timeout_seconds: int
    path_parameters: tuple[str, ...]
    query_parameters: tuple[str, ...]
    body_required: bool
    tags: tuple[str, ...]
    parameters: tuple[ToolParameter, ...]
    security_schemes: tuple[OpenApiSecurityScheme, ...] = ()
    security_requirements: tuple[OpenApiSecurityRequirement, ...] = ()
    credential_bindings: tuple[OpenApiCredentialBinding, ...] = ()
    required_effect_ids: tuple[str, ...] = ()
    capability_ids: tuple[str, ...] = ()

    def to_tool_spec(self) -> ToolSpec:
        return ToolSpec(
            id=self.tool_id,
            name=self.name,
            description=self.description,
            provider_name=self.provider_name,
            kind=ToolKind.HTTP,
            parameters=self.parameters,
            tags=self.tags,
            required_effect_ids=self.required_effect_ids,
            access_requirement_sets=_operation_access_requirement_sets(self),
            credential_requirements=_operation_credential_requirement_sets(self),
            capability_ids=self.capability_ids,
            execution_policy=ToolExecutionPolicy(
                timeout_seconds=self.timeout_seconds,
                requires_confirmation=False,
                mutates_state=self.method.lower() not in {"get", "head", "options"},
            ),
            execution_support=ToolExecutionSupport(
                supported_modes=(ToolMode.INLINE, ToolMode.BACKGROUND),
                supported_strategies=(ToolExecutionStrategy.ASYNC,),
                supported_environments=(ToolEnvironment.REMOTE,),
            ),
            definition_origin=ToolDefinitionOrigin.REMOTE_DISCOVERY,
            runtime_key=self.runtime_key,
            enabled=True,
        )


class OpenApiDiscoveryProvider:
    definition_origin = ToolDefinitionOrigin.REMOTE_DISCOVERY

    def __init__(
        self,
        config: OpenApiProviderSettings,
        *,
        capability_ids: tuple[str, ...] = (),
    ) -> None:
        self.config = config
        self.capability_ids = DEFAULT_TOOL_CAPABILITY_CATALOG.validate_capability_ids(
            capability_ids,
        )
        self.name = config.name
        self.description = (
            config.description
            or f"Discovers remote HTTP tools from OpenAPI document '{config.name}'."
        )
        self._operations_cache: tuple[OpenApiOperation, ...] | None = None

    def discover_specs(self) -> list[ToolSpec]:
        return [operation.to_tool_spec() for operation in self.operations()]

    def operations(self) -> tuple[OpenApiOperation, ...]:
        if self._operations_cache is None:
            self._operations_cache = tuple(
                _parse_operations(
                    self.config,
                    capability_ids=self.capability_ids,
                ),
            )
        return self._operations_cache


def _operation_access_requirement_sets(
    operation: OpenApiOperation,
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


def _operation_credential_requirement_sets(
    operation: OpenApiOperation,
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


def _credential_requirement_declarations(
    *,
    operation: OpenApiOperation,
    consumer: AccessConsumerRef,
    scheme: OpenApiSecurityScheme,
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
    operation: OpenApiOperation,
    consumer: AccessConsumerRef,
    scheme: OpenApiSecurityScheme,
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
    scheme: OpenApiSecurityScheme,
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
    scheme: OpenApiSecurityScheme,
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


def _setup_flow_hint_for_scheme(scheme: OpenApiSecurityScheme) -> AccessSetupFlowHint:
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


def _parse_operations(
    config: OpenApiProviderSettings,
    *,
    capability_ids: tuple[str, ...] = (),
) -> list[OpenApiOperation]:
    document = _load_document(config.spec_location)
    if not isinstance(document, dict):
        raise ToolValidationError(
            f"OpenAPI document for provider '{config.name}' must decode to an object.",
        )

    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise ToolValidationError(
            f"OpenAPI document for provider '{config.name}' does not contain a valid paths object.",
        )

    base_url = _resolve_base_url(config, document)
    security_schemes = _parse_security_schemes(
        document.get("components"),
        provider_name=config.name,
    )
    top_level_security = _parse_security_requirements(
        document.get("security"),
        security_schemes=security_schemes,
        provider_name=config.name,
    )
    operations: list[OpenApiOperation] = []
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        path_parameters = _collect_parameters(path_item.get("parameters"))
        for method, operation in sorted(path_item.items()):
            if method.lower() not in SUPPORTED_HTTP_METHODS or not isinstance(
                operation,
                dict,
            ):
                continue

            merged_parameters = _merge_parameters(
                path_parameters,
                _collect_parameters(operation.get("parameters")),
            )
            operation_id = _normalize_operation_id(
                operation.get("operationId"),
                method=method,
                path=path,
            )
            tool_id = f"{config.name}.{operation_id}"
            runtime_key = f"openapi.{config.name}.{operation_id}"
            name = str(operation.get("summary") or operation_id).strip()
            description = str(
                operation.get("description") or operation.get("summary") or f"{method.upper()} {path}",
            ).strip()
            tags = tuple(
                dict.fromkeys(
                    tag
                    for tag in (
                        *(
                            str(tag).strip().lower()
                            for tag in operation.get("tags", [])
                            if str(tag).strip()
                        ),
                        "openapi",
                        config.name.lower(),
                    )
                    if tag
                ),
            )

            parameters = [
                _parameter_to_tool_parameter(parameter)
                for parameter in merged_parameters
                if parameter["in"] in {"path", "query"}
            ]

            body_required = False
            request_body = operation.get("requestBody")
            if isinstance(request_body, dict):
                body_required = bool(request_body.get("required", False))
                if _supports_json_request_body(request_body):
                    request_body_schema = _request_body_schema(request_body)
                    parameters.append(
                        ToolParameter(
                            name="body",
                            data_type=_schema_type(request_body_schema),
                            description="JSON request body payload.",
                            required=body_required,
                            json_schema=_tool_parameter_json_schema(
                                request_body_schema,
                                description="JSON request body payload.",
                            ),
                        ),
                    )

            effective_security = (
                _parse_security_requirements(
                    operation.get("security"),
                    security_schemes=security_schemes,
                    provider_name=config.name,
                )
                if "security" in operation
                else top_level_security
            )

            operations.append(
                OpenApiOperation(
                    provider_name=config.name,
                    tool_id=tool_id,
                    runtime_key=runtime_key,
                    name=name,
                    description=description,
                    method=method.upper(),
                    path_template=path,
                    base_url=base_url,
                    timeout_seconds=config.timeout_seconds,
                    path_parameters=tuple(
                        parameter["name"]
                        for parameter in merged_parameters
                        if parameter["in"] == "path"
                    ),
                    query_parameters=tuple(
                        parameter["name"]
                        for parameter in merged_parameters
                        if parameter["in"] == "query"
                    ),
                    body_required=body_required,
                    tags=tags,
                    parameters=tuple(parameters),
                    security_schemes=tuple(security_schemes.values()),
                    security_requirements=effective_security,
                    credential_bindings=config.credential_bindings,
                    required_effect_ids=config.default_effect_ids,
                    capability_ids=capability_ids,
                ),
            )

    return operations


def _load_document(spec_location: str) -> Any:
    parsed = urlparse(spec_location)
    if parsed.scheme in {"http", "https"}:
        with urlopen(spec_location, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    if parsed.scheme == "file":
        return json.loads(Path(parsed.path).read_text(encoding="utf-8"))
    return json.loads(Path(spec_location).read_text(encoding="utf-8"))


def _resolve_base_url(
    config: OpenApiProviderSettings,
    document: dict[str, Any],
) -> str:
    if config.base_url:
        return config.base_url.rstrip("/")

    servers = document.get("servers")
    if isinstance(servers, list):
        for item in servers:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", "")).strip()
            if not url:
                continue
            parsed = urlparse(url)
            if parsed.scheme in {"http", "https"}:
                return url.rstrip("/")
            if parsed.scheme == "" and url.startswith("/"):
                raise ToolValidationError(
                    f"OpenAPI provider '{config.name}' defines a relative server url; configure base_url explicitly.",
                )

    raise ToolValidationError(
        f"OpenAPI provider '{config.name}' requires an absolute base_url or servers entry.",
    )


def _collect_parameters(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    parameters: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict) and "name" in item and "in" in item:
            parameters.append(item)
    return parameters


def _merge_parameters(
    inherited: list[dict[str, Any]],
    local: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {
        (str(item["name"]), str(item["in"])): item for item in inherited
    }
    for item in local:
        merged[(str(item["name"]), str(item["in"]))] = item
    return list(merged.values())


def _normalize_operation_id(raw: Any, *, method: str, path: str) -> str:
    candidate = str(raw).strip() if raw is not None else ""
    if not candidate:
        candidate = f"{method}_{path}"
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", candidate).strip("_").lower()
    if not normalized:
        raise ToolValidationError(
            f"Could not derive a valid operation id from '{method.upper()} {path}'.",
        )
    return normalized


def _parameter_to_tool_parameter(parameter: dict[str, Any]) -> ToolParameter:
    schema = parameter.get("schema") if isinstance(parameter.get("schema"), dict) else {}
    description = str(parameter.get("description", "")).strip()
    return ToolParameter(
        name=str(parameter["name"]),
        data_type=_schema_type(schema),
        description=description,
        required=bool(parameter.get("required", False)),
        json_schema=_tool_parameter_json_schema(schema, description=description),
    )


def _tool_parameter_json_schema(
    schema: dict[str, Any],
    *,
    description: str,
) -> dict[str, Any]:
    payload = dict(schema)
    if not payload:
        payload["type"] = _schema_type(schema)
    if description and not payload.get("description"):
        payload["description"] = description
    return payload


def _schema_type(schema: dict[str, Any]) -> str:
    schema_type = str(schema.get("type", "")).strip().lower()
    if schema_type == "array":
        items = schema.get("items") if isinstance(schema.get("items"), dict) else {}
        item_type = _schema_type(items)
        return f"array[{item_type}]"
    if schema_type:
        return schema_type
    if "properties" in schema:
        return "object"
    return "string"


def _supports_json_request_body(request_body: dict[str, Any]) -> bool:
    content = request_body.get("content")
    if not isinstance(content, dict):
        return False
    return "application/json" in content


def _request_body_data_type(request_body: dict[str, Any]) -> str:
    return _schema_type(_request_body_schema(request_body))


def _request_body_schema(request_body: dict[str, Any]) -> dict[str, Any]:
    content = request_body.get("content")
    if not isinstance(content, dict):
        return {"type": "object"}
    media = content.get("application/json")
    if not isinstance(media, dict):
        return {"type": "object"}
    schema = media.get("schema") if isinstance(media.get("schema"), dict) else {}
    return schema or {"type": "object"}


def _parse_security_schemes(
    components: Any,
    *,
    provider_name: str,
) -> dict[str, OpenApiSecurityScheme]:
    if not isinstance(components, dict):
        return {}
    raw_schemes = components.get("securitySchemes")
    if not isinstance(raw_schemes, dict):
        return {}

    schemes: dict[str, OpenApiSecurityScheme] = {}
    for name, payload in raw_schemes.items():
        if not isinstance(payload, dict):
            continue
        scheme_type = str(payload.get("type", "")).strip()
        if not scheme_type:
            raise ToolValidationError(
                f"OpenAPI provider '{provider_name}' security scheme '{name}' is missing type.",
            )
        schemes[str(name)] = OpenApiSecurityScheme(
            name=str(name),
            scheme_type=scheme_type,
            parameter_name=(
                str(payload.get("name")).strip()
                if payload.get("name") is not None
                else None
            ),
            location=(
                str(payload.get("in")).strip()
                if payload.get("in") is not None
                else None
            ),
            http_scheme=(
                str(payload.get("scheme")).strip().lower()
                if payload.get("scheme") is not None
                else None
            ),
            metadata=_security_scheme_metadata(payload),
        )
    return schemes


def _security_scheme_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    description = payload.get("description")
    if isinstance(description, str) and description.strip():
        metadata["description"] = description.strip()
    open_id_connect_url = payload.get("openIdConnectUrl")
    if isinstance(open_id_connect_url, str) and open_id_connect_url.strip():
        metadata["open_id_connect_url"] = open_id_connect_url.strip()
    flows = payload.get("flows")
    if not isinstance(flows, dict):
        return metadata
    flow_metadata: dict[str, dict[str, Any]] = {}
    for flow_name, flow_payload in flows.items():
        if not isinstance(flow_payload, dict):
            continue
        normalized_flow_name = str(flow_name).strip()
        if not normalized_flow_name:
            continue
        resolved_flow: dict[str, Any] = {}
        for source_key, target_key in (
            ("authorizationUrl", "authorization_url"),
            ("tokenUrl", "token_url"),
            ("refreshUrl", "refresh_url"),
        ):
            value = flow_payload.get(source_key)
            if isinstance(value, str) and value.strip():
                resolved_flow[target_key] = value.strip()
                metadata.setdefault(target_key, value.strip())
        scopes = flow_payload.get("scopes")
        if isinstance(scopes, dict):
            resolved_flow["scopes"] = tuple(
                str(scope).strip() for scope in scopes if str(scope).strip()
            )
        flow_metadata[normalized_flow_name] = resolved_flow
    if flow_metadata:
        metadata["flows"] = flow_metadata
    return metadata


def _parse_security_requirements(
    raw_security: Any,
    *,
    security_schemes: dict[str, OpenApiSecurityScheme],
    provider_name: str,
) -> tuple[OpenApiSecurityRequirement, ...]:
    if raw_security is None:
        return ()
    if not isinstance(raw_security, list):
        raise ToolValidationError(
            f"OpenAPI provider '{provider_name}' security section must be a list.",
        )
    if not raw_security:
        return ()

    requirements: list[OpenApiSecurityRequirement] = []
    for item in raw_security:
        if not isinstance(item, dict):
            raise ToolValidationError(
                f"OpenAPI provider '{provider_name}' security requirements must be objects.",
            )
        scheme_names: list[str] = []
        scopes_by_scheme: dict[str, tuple[str, ...]] = {}
        for scheme_name, raw_scopes in item.items():
            normalized_scheme_name = str(scheme_name)
            if normalized_scheme_name not in security_schemes:
                raise ToolValidationError(
                    f"OpenAPI provider '{provider_name}' security requirement references unknown scheme '{normalized_scheme_name}'.",
                )
            scheme_names.append(normalized_scheme_name)
            scopes_by_scheme[normalized_scheme_name] = _parse_security_scopes(
                raw_scopes,
                provider_name=provider_name,
                scheme_name=normalized_scheme_name,
            )
        requirements.append(
            OpenApiSecurityRequirement(
                scheme_names=tuple(scheme_names),
                scopes_by_scheme=scopes_by_scheme,
            ),
        )
    return tuple(requirements)


def _parse_security_scopes(
    raw_scopes: Any,
    *,
    provider_name: str,
    scheme_name: str,
) -> tuple[str, ...]:
    if raw_scopes is None:
        return ()
    if not isinstance(raw_scopes, list):
        raise ToolValidationError(
            f"OpenAPI provider '{provider_name}' security requirement for scheme '{scheme_name}' scopes must be a list.",
        )
    return tuple(
        dict.fromkeys(
            str(scope).strip()
            for scope in raw_scopes
            if str(scope).strip()
        ),
    )
