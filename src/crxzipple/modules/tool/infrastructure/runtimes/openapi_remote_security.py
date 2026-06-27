from __future__ import annotations

import base64
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from crxzipple.core.config import OpenApiCredentialBinding
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.discovery.openapi import (
    OpenApiOperation,
    OpenApiSecurityRequirement,
    OpenApiSecurityScheme,
)
from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessCredentialKind,
    CredentialBindingRef,
    CredentialProvider,
)


def build_security_query_items(
    operation: OpenApiOperation,
    *,
    credential_provider: CredentialProvider,
    headers: dict[str, str],
    cookies: list[str],
) -> list[tuple[str, str]]:
    if not operation.security_requirements:
        return []

    schemes_by_name = {scheme.name: scheme for scheme in operation.security_schemes}
    bindings_by_name = {
        binding.scheme_name: binding for binding in operation.credential_bindings
    }
    last_error: ToolValidationError | None = None

    for requirement in operation.security_requirements:
        try:
            return _apply_security_requirement(
                requirement,
                operation=operation,
                schemes_by_name=schemes_by_name,
                bindings_by_name=bindings_by_name,
                credential_provider=credential_provider,
                headers=headers,
                cookies=cookies,
            )
        except ToolValidationError as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    return []


def resolve_credential_binding(
    binding_id: str | None,
    *,
    scheme_name: str,
    field_name: str = "credential_binding_id",
    operation: OpenApiOperation,
    expected_kind: AccessCredentialKind | None = None,
    credential_provider: CredentialProvider,
) -> str:
    if binding_id is None or not binding_id.strip():
        raise ToolValidationError(
            f"OpenAPI credential binding for security scheme '{scheme_name}' is missing {field_name}.",
        )
    normalized_binding_id = binding_id.strip()

    try:
        return credential_provider.resolve_credential(
            CredentialBindingRef(
                binding_id=normalized_binding_id,
                source_type="binding",
                source_ref=normalized_binding_id,
                expected_kind=expected_kind,
                metadata={
                    "provider": operation.provider_name,
                    "scheme_name": scheme_name,
                    "field": field_name,
                },
            ),
            consumer=AccessConsumerRef(
                consumer_id=f"tool.openapi:{operation.tool_id}",
                module="tool",
                component="openapi_remote",
                runtime_ref=operation.runtime_key,
                metadata={
                    "provider": operation.provider_name,
                    "scheme_name": scheme_name,
                    "field": field_name,
                },
            ),
        )
    except Exception as exc:
        raise ToolValidationError(
            f"OpenAPI credential binding for security scheme '{scheme_name}' {exc}",
        ) from exc


def sanitize_request_url(url: str, operation: OpenApiOperation) -> str:
    sensitive_query_names = {
        scheme.parameter_name
        for scheme in operation.security_schemes
        if scheme.scheme_type == "apiKey"
        and scheme.location == "query"
        and scheme.parameter_name
    }
    if not sensitive_query_names:
        return url

    parts = urlsplit(url)
    redacted_query = urlencode(
        [
            (name, "[redacted]" if name in sensitive_query_names else value)
            for name, value in parse_qsl(parts.query, keep_blank_values=True)
        ],
        doseq=True,
    )
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            redacted_query,
            parts.fragment,
        ),
    )


def _apply_security_requirement(
    requirement: OpenApiSecurityRequirement,
    *,
    operation: OpenApiOperation,
    schemes_by_name: dict[str, OpenApiSecurityScheme],
    bindings_by_name: dict[str, OpenApiCredentialBinding],
    credential_provider: CredentialProvider,
    headers: dict[str, str],
    cookies: list[str],
) -> list[tuple[str, str]]:
    query_items: list[tuple[str, str]] = []
    if not requirement.scheme_names:
        return query_items

    draft_headers = dict(headers)
    draft_cookies = list(cookies)

    for scheme_name in requirement.scheme_names:
        scheme = schemes_by_name[scheme_name]
        binding = bindings_by_name.get(scheme_name)
        if binding is None:
            raise ToolValidationError(
                f"OpenAPI credential binding for security scheme '{scheme_name}' is not configured.",
            )

        if scheme.scheme_type == "apiKey":
            secret = resolve_credential_binding(
                binding.credential_binding_id,
                scheme_name=scheme_name,
                operation=operation,
                expected_kind=_credential_kind_for_scheme(scheme),
                credential_provider=credential_provider,
            )
            if scheme.location == "header":
                if not scheme.parameter_name:
                    raise ToolValidationError(
                        f"OpenAPI apiKey security scheme '{scheme_name}' is missing header name.",
                    )
                draft_headers[scheme.parameter_name] = secret
            elif scheme.location == "query":
                if not scheme.parameter_name:
                    raise ToolValidationError(
                        f"OpenAPI apiKey security scheme '{scheme_name}' is missing query parameter name.",
                    )
                query_items.append((scheme.parameter_name, secret))
            elif scheme.location == "cookie":
                if not scheme.parameter_name:
                    raise ToolValidationError(
                        f"OpenAPI apiKey security scheme '{scheme_name}' is missing cookie name.",
                    )
                draft_cookies.append(f"{scheme.parameter_name}={secret}")
            else:
                raise ToolValidationError(
                    f"OpenAPI apiKey security scheme '{scheme_name}' uses unsupported location '{scheme.location}'.",
                )
            continue

        if scheme.scheme_type == "http":
            http_scheme = (scheme.http_scheme or "").lower()
            if http_scheme == "basic":
                username = resolve_credential_binding(
                    binding.username_binding_id,
                    scheme_name=scheme_name,
                    field_name="username_binding_id",
                    operation=operation,
                    expected_kind=_credential_kind_for_scheme(scheme),
                    credential_provider=credential_provider,
                )
                password = resolve_credential_binding(
                    binding.password_binding_id,
                    scheme_name=scheme_name,
                    field_name="password_binding_id",
                    operation=operation,
                    expected_kind=_credential_kind_for_scheme(scheme),
                    credential_provider=credential_provider,
                )
                token = base64.b64encode(
                    f"{username}:{password}".encode("utf-8"),
                ).decode("ascii")
                draft_headers["Authorization"] = f"Basic {token}"
                continue

            token = resolve_credential_binding(
                binding.credential_binding_id,
                scheme_name=scheme_name,
                operation=operation,
                expected_kind=_credential_kind_for_scheme(scheme),
                credential_provider=credential_provider,
            )
            if http_scheme == "bearer":
                draft_headers["Authorization"] = f"Bearer {token}"
            elif http_scheme:
                draft_headers["Authorization"] = f"{http_scheme} {token}"
            else:
                raise ToolValidationError(
                    f"OpenAPI http security scheme '{scheme_name}' is missing scheme.",
                )
            continue

        if scheme.scheme_type in {"oauth2", "openIdConnect"}:
            token = resolve_credential_binding(
                binding.credential_binding_id,
                scheme_name=scheme_name,
                operation=operation,
                expected_kind=_credential_kind_for_scheme(scheme),
                credential_provider=credential_provider,
            )
            draft_headers["Authorization"] = f"Bearer {token}"
            continue

        raise ToolValidationError(
            f"OpenAPI security scheme '{scheme_name}' uses unsupported type '{scheme.scheme_type}'.",
        )

    headers.clear()
    headers.update(draft_headers)
    cookies.clear()
    cookies.extend(draft_cookies)
    return query_items


def _credential_kind_for_scheme(
    scheme: OpenApiSecurityScheme,
) -> AccessCredentialKind | None:
    scheme_type = scheme.scheme_type.strip().lower()
    if scheme_type == "apikey":
        return AccessCredentialKind.API_KEY
    if scheme_type == "http":
        http_scheme = (scheme.http_scheme or "").strip().lower()
        if http_scheme == "bearer":
            return AccessCredentialKind.BEARER_TOKEN
        if http_scheme == "basic":
            return AccessCredentialKind.BASIC
    if scheme_type == "oauth2":
        return AccessCredentialKind.OAUTH2_ACCOUNT
    if scheme_type == "openidconnect":
        return AccessCredentialKind.OPENID_CONNECT
    return None


__all__ = [
    "build_security_query_items",
    "resolve_credential_binding",
    "sanitize_request_url",
]
