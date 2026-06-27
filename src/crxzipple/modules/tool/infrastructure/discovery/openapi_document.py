from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

from crxzipple.core.config import OpenApiProviderSettings
from crxzipple.modules.tool.domain.exceptions import ToolValidationError

from .openapi_models import OpenApiOperation
from .openapi_schema import (
    json_body_tool_parameter,
    parameter_to_tool_parameter,
    request_body_schema,
    supports_json_request_body,
)
from .openapi_security import parse_security_requirements, parse_security_schemes


SUPPORTED_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def parse_openapi_operations(
    config: OpenApiProviderSettings,
    *,
    capability_ids: tuple[str, ...] = (),
) -> list[OpenApiOperation]:
    document = load_openapi_document(config.spec_location)
    if not isinstance(document, dict):
        raise ToolValidationError(
            f"OpenAPI document for provider '{config.name}' must decode to an object.",
        )

    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise ToolValidationError(
            f"OpenAPI document for provider '{config.name}' does not contain a valid paths object.",
        )

    base_url = resolve_base_url(config, document)
    security_schemes = parse_security_schemes(
        document.get("components"),
        provider_name=config.name,
    )
    top_level_security = parse_security_requirements(
        document.get("security"),
        security_schemes=security_schemes,
        provider_name=config.name,
    )
    operations: list[OpenApiOperation] = []
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        path_parameters = collect_parameters(path_item.get("parameters"))
        for method, operation in sorted(path_item.items()):
            if method.lower() not in SUPPORTED_HTTP_METHODS or not isinstance(
                operation,
                dict,
            ):
                continue

            operations.append(
                build_openapi_operation(
                    config,
                    method=method,
                    path=path,
                    operation=operation,
                    path_parameters=path_parameters,
                    base_url=base_url,
                    security_schemes=security_schemes,
                    top_level_security=top_level_security,
                    capability_ids=capability_ids,
                ),
            )

    return operations


def load_openapi_document(spec_location: str) -> Any:
    parsed = urlparse(spec_location)
    if parsed.scheme in {"http", "https"}:
        with urlopen(spec_location, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    if parsed.scheme == "file":
        return json.loads(Path(parsed.path).read_text(encoding="utf-8"))
    return json.loads(Path(spec_location).read_text(encoding="utf-8"))


def resolve_base_url(
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


def collect_parameters(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    parameters: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict) and "name" in item and "in" in item:
            parameters.append(item)
    return parameters


def merge_parameters(
    inherited: list[dict[str, Any]],
    local: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {
        (str(item["name"]), str(item["in"])): item for item in inherited
    }
    for item in local:
        merged[(str(item["name"]), str(item["in"]))] = item
    return list(merged.values())


def normalize_operation_id(raw: Any, *, method: str, path: str) -> str:
    candidate = str(raw).strip() if raw is not None else ""
    if not candidate:
        candidate = f"{method}_{path}"
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", candidate).strip("_").lower()
    if not normalized:
        raise ToolValidationError(
            f"Could not derive a valid operation id from '{method.upper()} {path}'.",
        )
    return normalized


def build_openapi_operation(
    config: OpenApiProviderSettings,
    *,
    method: str,
    path: str,
    operation: dict[str, Any],
    path_parameters: list[dict[str, Any]],
    base_url: str,
    security_schemes: dict[str, Any],
    top_level_security: tuple[Any, ...],
    capability_ids: tuple[str, ...],
) -> OpenApiOperation:
    merged_parameters = merge_parameters(
        path_parameters,
        collect_parameters(operation.get("parameters")),
    )
    operation_id = normalize_operation_id(
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
        parameter_to_tool_parameter(parameter)
        for parameter in merged_parameters
        if parameter["in"] in {"path", "query"}
    ]

    body_required = False
    request_body = operation.get("requestBody")
    if isinstance(request_body, dict):
        body_required = bool(request_body.get("required", False))
        if supports_json_request_body(request_body):
            parameters.append(
                json_body_tool_parameter(
                    request_body_schema(request_body),
                    required=body_required,
                ),
            )

    effective_security = (
        parse_security_requirements(
            operation.get("security"),
            security_schemes=security_schemes,
            provider_name=config.name,
        )
        if "security" in operation
        else top_level_security
    )

    return OpenApiOperation(
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
    )


__all__ = [
    "SUPPORTED_HTTP_METHODS",
    "build_openapi_operation",
    "collect_parameters",
    "load_openapi_document",
    "merge_parameters",
    "normalize_operation_id",
    "parse_openapi_operations",
    "resolve_base_url",
]
