from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.core.config import OpenApiCredentialBinding, OpenApiProviderSettings
from crxzipple.modules.tool.domain import ToolSourceKind
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


@dataclass(frozen=True, slots=True)
class OpenApiSecurityRequirement:
    scheme_names: tuple[str, ...]


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
            source_kind=ToolSourceKind.REMOTE_REGISTRY,
            runtime_key=self.runtime_key,
            enabled=True,
        )


class OpenApiDiscoveryProvider:
    source_kind = ToolSourceKind.REMOTE_REGISTRY

    def __init__(self, config: OpenApiProviderSettings) -> None:
        self.config = config
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
            self._operations_cache = tuple(_parse_operations(self.config))
        return self._operations_cache


def _parse_operations(config: OpenApiProviderSettings) -> list[OpenApiOperation]:
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
                    parameters.append(
                        ToolParameter(
                            name="body",
                            data_type=_request_body_data_type(request_body),
                            description="JSON request body payload.",
                            required=body_required,
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
    return ToolParameter(
        name=str(parameter["name"]),
        data_type=_schema_type(schema),
        description=str(parameter.get("description", "")).strip(),
        required=bool(parameter.get("required", False)),
    )


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
    content = request_body.get("content")
    if not isinstance(content, dict):
        return "object"
    media = content.get("application/json")
    if not isinstance(media, dict):
        return "object"
    schema = media.get("schema") if isinstance(media.get("schema"), dict) else {}
    return _schema_type(schema)


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
        )
    return schemes


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
        for scheme_name in item:
            normalized_scheme_name = str(scheme_name)
            if normalized_scheme_name not in security_schemes:
                raise ToolValidationError(
                    f"OpenAPI provider '{provider_name}' security requirement references unknown scheme '{normalized_scheme_name}'.",
                )
            scheme_names.append(normalized_scheme_name)
        requirements.append(
            OpenApiSecurityRequirement(
                scheme_names=tuple(scheme_names),
            ),
        )
    return tuple(requirements)
