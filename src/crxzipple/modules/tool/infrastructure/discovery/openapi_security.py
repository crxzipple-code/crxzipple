from __future__ import annotations

from typing import Any

from crxzipple.modules.tool.domain.exceptions import ToolValidationError

from .openapi_models import OpenApiSecurityRequirement, OpenApiSecurityScheme


def parse_security_schemes(
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
            metadata=security_scheme_metadata(payload),
        )
    return schemes


def security_scheme_metadata(payload: dict[str, Any]) -> dict[str, Any]:
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


def parse_security_requirements(
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
            scopes_by_scheme[normalized_scheme_name] = parse_security_scopes(
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


def parse_security_scopes(
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


__all__ = [
    "parse_security_requirements",
    "parse_security_schemes",
    "parse_security_scopes",
    "security_scheme_metadata",
]
