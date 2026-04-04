from __future__ import annotations

import asyncio
import base64
import json
import os
from typing import Any
from urllib.parse import quote

import requests

from crxzipple.core.config import OpenApiCredentialBinding
from crxzipple.modules.tool.domain import ToolRunResult
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.discovery.openapi import (
    OpenApiOperation,
    OpenApiSecurityRequirement,
    OpenApiSecurityScheme,
)
from crxzipple.modules.tool.infrastructure.runtimes.registry import ToolRuntimeRegistry
from crxzipple.shared.content_blocks import describe_content_for_text_fallback


class OpenApiRemoteInvoker:
    async def execute(
        self,
        operation: OpenApiOperation,
        arguments: dict[str, Any],
    ) -> Any:
        return await asyncio.to_thread(
            self._execute_sync,
            operation,
            dict(arguments),
        )

    def _execute_sync(
        self,
        operation: OpenApiOperation,
        arguments: dict[str, Any],
    ) -> Any:
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
                headers=headers,
                cookies=cookies,
            ),
        )
        if cookies:
            headers["Cookie"] = "; ".join(cookies)

        url = _build_url(operation.base_url, path)
        json_body: dict[str, Any] | list[Any] | None = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            json_body = body

        try:
            response = requests.request(
                method=operation.method,
                url=url,
                params=query_items or None,
                headers=headers,
                json=json_body,
                timeout=operation.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.content
            content_type = response.headers.get("Content-Type", "")
            status_code = response.status_code
            final_url = response.url
        except requests.HTTPError as exc:
            response = exc.response
            status_code = response.status_code if response is not None else "unknown"
            detail = response.text if response is not None else str(exc)
            raise ToolValidationError(
                f"Remote OpenAPI tool '{operation.tool_id}' failed with HTTP {status_code}: {detail}",
            ) from exc
        except requests.RequestException as exc:
            raise ToolValidationError(
                f"Remote OpenAPI tool '{operation.tool_id}' could not reach {url}: {exc}",
            ) from exc

        decoded_body = _decode_response_body(payload, content_type)
        return ToolRunResult.text(
            describe_content_for_text_fallback(decoded_body),
            details=decoded_body,
            metadata={
                "tool": operation.runtime_key,
                "environment": "remote",
                "request": {
                    "method": operation.method,
                    "url": final_url,
                },
                "status_code": status_code,
            },
        )


def register_openapi_remote_handlers(
    registry: ToolRuntimeRegistry,
    operations: list[OpenApiOperation] | tuple[OpenApiOperation, ...],
) -> None:
    invoker = OpenApiRemoteInvoker()
    for operation in operations:

        async def handler(
            arguments: dict[str, Any],
            *,
            _operation: OpenApiOperation = operation,
            _invoker: OpenApiRemoteInvoker = invoker,
        ) -> Any:
            return await _invoker.execute(_operation, arguments)

        registry.register(operation.runtime_key, handler)


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
                schemes_by_name=schemes_by_name,
                bindings_by_name=bindings_by_name,
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
    schemes_by_name: dict[str, OpenApiSecurityScheme],
    bindings_by_name: dict[str, OpenApiCredentialBinding],
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
            secret = _resolve_secret_source(binding.source, scheme_name=scheme_name)
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
                username = _resolve_secret_source(
                    binding.username_source,
                    scheme_name=scheme_name,
                    field_name="username_source",
                )
                password = _resolve_secret_source(
                    binding.password_source,
                    scheme_name=scheme_name,
                    field_name="password_source",
                )
                token = base64.b64encode(
                    f"{username}:{password}".encode("utf-8"),
                ).decode("ascii")
                draft_headers["Authorization"] = f"Basic {token}"
                continue

            token = _resolve_secret_source(binding.source, scheme_name=scheme_name)
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
            token = _resolve_secret_source(binding.source, scheme_name=scheme_name)
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


def _resolve_secret_source(
    source: str | None,
    *,
    scheme_name: str,
    field_name: str = "source",
) -> str:
    if source is None or not source.strip():
        raise ToolValidationError(
            f"OpenAPI credential binding for security scheme '{scheme_name}' is missing {field_name}.",
        )

    if source.startswith("env:"):
        env_name = source.removeprefix("env:").strip()
        if not env_name:
            raise ToolValidationError(
                f"OpenAPI credential binding for security scheme '{scheme_name}' references an empty environment variable.",
            )
        value = os.getenv(env_name)
        if value is None or not value.strip():
            raise ToolValidationError(
                f"OpenAPI credential binding for security scheme '{scheme_name}' could not resolve env var '{env_name}'.",
            )
        return value

    raise ToolValidationError(
        f"OpenAPI credential binding for security scheme '{scheme_name}' uses unsupported source '{source}'.",
    )
