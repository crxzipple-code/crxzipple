from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import httpx

from crxzipple.core.config import OpenApiCredentialBinding
from crxzipple.modules.tool.domain import ToolRunResult
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.discovery.openapi import (
    OpenApiOperation,
    OpenApiSecurityRequirement,
    OpenApiSecurityScheme,
)
from crxzipple.modules.tool.infrastructure.runtimes.registry import ToolRuntimeRegistry
from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessCredentialKind,
    CredentialBindingRef,
    CredentialProvider,
)
from crxzipple.shared.content_blocks import describe_content_for_text_fallback
from crxzipple.shared.infrastructure.http import get_async_http_client


class OpenApiRemoteInvoker:
    def __init__(self, credential_provider: CredentialProvider) -> None:
        self.credential_provider = credential_provider

    async def execute(
        self,
        operation: OpenApiOperation,
        arguments: dict[str, Any],
    ) -> Any:
        url, query_items, headers, json_body = _build_request(
            operation,
            dict(arguments),
            credential_provider=self.credential_provider,
        )

        try:
            client = get_async_http_client(
                url,
                timeout=operation.timeout_seconds,
                client_factory=httpx.AsyncClient,
            )
            response = await client.request(
                method=operation.method,
                url=url,
                params=query_items or None,
                headers=headers,
                json=json_body,
            )
        except httpx.RequestError as exc:
            raise ToolValidationError(
                f"Remote OpenAPI tool '{operation.tool_id}' could not reach {url}: {exc}",
            ) from exc

        if response.status_code >= 400:
            raise ToolValidationError(
                f"Remote OpenAPI tool '{operation.tool_id}' failed with HTTP {response.status_code}: {response.text}",
            )

        payload = response.content
        content_type = response.headers.get("Content-Type", "")
        status_code = response.status_code
        final_url = str(response.url)
        sanitized_url = _sanitize_request_url(final_url, operation)

        decoded_body = _decode_response_body(payload, content_type)
        return ToolRunResult.text(
            describe_content_for_text_fallback(decoded_body),
            details=decoded_body,
            metadata={
                "tool": operation.runtime_key,
                "environment": "remote",
                "request": {
                    "method": operation.method,
                    "url": sanitized_url,
                },
                "status_code": status_code,
            },
        )


def register_openapi_remote_handlers(
    registry: ToolRuntimeRegistry,
    operations: list[OpenApiOperation] | tuple[OpenApiOperation, ...],
    *,
    credential_provider: CredentialProvider,
    max_concurrency: int | None = None,
    replace: bool = False,
) -> None:
    invoker = OpenApiRemoteInvoker(credential_provider)
    for operation in operations:

        async def handler(
            arguments: dict[str, Any],
            *,
            _operation: OpenApiOperation = operation,
            _invoker: OpenApiRemoteInvoker = invoker,
        ) -> Any:
            return await _invoker.execute(_operation, arguments)

        registry.register(
            operation.runtime_key,
            handler,
            concurrency_key=f"openapi:{operation.provider_name}",
            max_concurrency=max_concurrency,
            replace=replace,
        )


def _build_request(
    operation: OpenApiOperation,
    arguments: dict[str, Any],
    *,
    credential_provider: CredentialProvider,
) -> tuple[
    str,
    list[tuple[str, str]],
    dict[str, str],
    dict[str, Any] | list[Any] | None,
]:
    path = operation.path_template
    for parameter_name in operation.path_parameters:
        if parameter_name not in arguments:
            raise ToolValidationError(
                f"Remote OpenAPI tool '{operation.tool_id}' requires path parameter '{parameter_name}'.",
            )
        path = path.replace(
            "{" + parameter_name + "}",
            quote(str(arguments.pop(parameter_name)), safe=""),
        )

    query_items: list[tuple[str, str]] = []
    for parameter_name in operation.query_parameters:
        value = arguments.pop(parameter_name, None)
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            query_items.extend(
                (parameter_name, _serialize_scalar(item)) for item in value
            )
        else:
            query_items.append((parameter_name, _serialize_scalar(value)))

    body = arguments.pop("body", None)
    if operation.body_required and body is None:
        raise ToolValidationError(
            f"Remote OpenAPI tool '{operation.tool_id}' requires a JSON body payload.",
        )

    headers = {"Accept": "application/json"}
    cookies: list[str] = []
    query_items.extend(
        _build_security_query_items(
            operation,
            credential_provider=credential_provider,
            headers=headers,
            cookies=cookies,
        ),
    )
    if cookies:
        headers["Cookie"] = "; ".join(cookies)

    json_body: dict[str, Any] | list[Any] | None = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        json_body = body

    return _build_url(operation.base_url, path), query_items, headers, json_body


def _build_url(
    base_url: str,
    path: str,
) -> str:
    base = base_url.rstrip("/")
    path_value = path if path.startswith("/") else f"/{path}"
    return f"{base}{path_value}"


def _serialize_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _decode_response_body(payload: bytes, content_type: str) -> Any:
    text = payload.decode("utf-8")
    if "json" in content_type.lower():
        return json.loads(text)
    return text


def _build_security_query_items(
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
            secret = _resolve_credential_binding(
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
                username = _resolve_credential_binding(
                    binding.username_binding_id,
                    scheme_name=scheme_name,
                    field_name="username_binding_id",
                    operation=operation,
                    expected_kind=_credential_kind_for_scheme(scheme),
                    credential_provider=credential_provider,
                )
                password = _resolve_credential_binding(
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

            token = _resolve_credential_binding(
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
            token = _resolve_credential_binding(
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


def _resolve_credential_binding(
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


def _sanitize_request_url(url: str, operation: OpenApiOperation) -> str:
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
