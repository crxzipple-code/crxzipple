from __future__ import annotations

from typing import Any

import httpx

from crxzipple.modules.tool.domain import ToolRunResult
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.discovery.openapi import OpenApiOperation
from crxzipple.modules.tool.infrastructure.runtimes.registry import ToolRuntimeRegistry
from crxzipple.shared.access import CredentialProvider
from .openapi_remote_requests import (
    build_request as _build_request,
)
from .openapi_remote_results import (
    decode_response_body as _decode_response_body,
    openapi_result_details as _openapi_result_details,
    openapi_result_text as _openapi_result_text,
)
from .openapi_remote_security import sanitize_request_url as _sanitize_request_url
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
            _openapi_result_text(operation, decoded_body),
            details=_openapi_result_details(decoded_body),
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
