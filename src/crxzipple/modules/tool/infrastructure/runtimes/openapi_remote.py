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

_OPENAPI_DETAILS_MAX_CHARS = 120_000
_OPENAPI_DETAILS_STRING_LIMIT = 2000
_OPENAPI_DETAILS_LIST_LIMIT = 40
_OPENAPI_DETAILS_DICT_LIMIT = 80


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


def _openapi_result_text(operation: OpenApiOperation, value: Any) -> str:
    fallback = describe_content_for_text_fallback(value)
    weather_summary = _weather_forecast_summary(operation, value)
    if weather_summary is not None:
        return f"{weather_summary}\n\nRaw response:\n{fallback}"
    return fallback


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
        value = _normalize_openapi_argument(operation, parameter_name, value)
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


def _normalize_openapi_argument(
    operation: OpenApiOperation,
    parameter_name: str,
    value: Any,
) -> Any:
    if isinstance(value, list):
        return [
            _normalize_openapi_argument(operation, parameter_name, item)
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            _normalize_openapi_argument(operation, parameter_name, item)
            for item in value
        )
    if not isinstance(value, str):
        return value

    normalized = _normalize_known_openapi_alias(operation, parameter_name, value)
    schema = _parameter_schema(operation, parameter_name)
    enum_values = _schema_enum(schema)
    if not enum_values:
        return normalized
    if normalized in enum_values:
        return normalized

    lower_matches = {
        str(candidate).lower(): str(candidate)
        for candidate in enum_values
        if isinstance(candidate, str)
    }
    lower_normalized = normalized.lower()
    if lower_normalized in lower_matches:
        return lower_matches[lower_normalized]

    raise ToolValidationError(
        "Remote OpenAPI tool "
        f"'{operation.tool_id}' parameter '{parameter_name}' must be one of: "
        f"{', '.join(str(item) for item in enum_values)}.",
    )


def _normalize_known_openapi_alias(
    operation: OpenApiOperation,
    parameter_name: str,
    value: str,
) -> str:
    normalized = value.strip()
    alias_key = (operation.provider_name, parameter_name)
    aliases = _OPENAPI_PARAMETER_ALIASES.get(alias_key, {})
    return aliases.get(normalized.lower(), normalized)


def _parameter_schema(
    operation: OpenApiOperation,
    parameter_name: str,
) -> dict[str, Any]:
    for parameter in operation.parameters:
        if parameter.name == parameter_name and parameter.json_schema is not None:
            return parameter.json_schema
    return {}


def _schema_enum(schema: dict[str, Any]) -> tuple[Any, ...]:
    raw = schema.get("enum")
    if not isinstance(raw, list):
        return ()
    return tuple(raw)


def _openapi_result_details(value: Any) -> Any:
    if _json_char_count(value) <= _OPENAPI_DETAILS_MAX_CHARS:
        return value
    compacted = _compact_openapi_details(value)
    if _json_char_count(compacted) <= _OPENAPI_DETAILS_MAX_CHARS:
        if isinstance(compacted, dict):
            return {**compacted, "details_compacted": True}
        return {
            "details_compacted": True,
            "result": compacted,
        }
    return {
        "details_compacted": True,
        "details_truncated": True,
        "original_details_chars": _json_char_count(value),
        "result_shape": _shape_summary(value),
        "summary": describe_content_for_text_fallback(value)[:4000],
    }


def _weather_forecast_summary(
    operation: OpenApiOperation,
    value: Any,
) -> str | None:
    if not isinstance(value, dict):
        return None
    tool_id = " ".join(
        part
        for part in (
            operation.tool_id,
            operation.runtime_key,
            operation.provider_name,
        )
        if part
    ).lower()
    hourly = value.get("hourly")
    if "weather" not in tool_id and not (
        isinstance(hourly, dict)
        and isinstance(hourly.get("time"), list)
        and (
            isinstance(hourly.get("temperature_2m"), list)
            or isinstance(hourly.get("precipitation_probability"), list)
        )
    ):
        return None
    if not isinstance(hourly, dict):
        return None
    times = hourly.get("time")
    if not isinstance(times, list) or not times:
        return None
    temperatures = hourly.get("temperature_2m")
    precipitation = hourly.get("precipitation_probability")
    weather_codes = hourly.get("weather_code")
    temp_unit = _nested_unit(value, "hourly_units", "temperature_2m") or "°C"
    precip_unit = _nested_unit(value, "hourly_units", "precipitation_probability") or "%"
    lines = ["Weather forecast summary:"]
    current = value.get("current")
    if isinstance(current, dict):
        current_parts: list[str] = []
        current_time = current.get("time")
        if current_time is not None:
            current_parts.append(f"time={current_time}")
        current_temp = current.get("temperature_2m")
        if current_temp is not None:
            current_parts.append(f"temperature_2m={current_temp}{temp_unit}")
        current_code = current.get("weather_code")
        if current_code is not None:
            current_parts.append(f"weather_code={current_code}")
        if current_parts:
            lines.append("- Current: " + ", ".join(current_parts))
    sample_indexes = _weather_sample_indexes(times)
    if sample_indexes:
        lines.append("- Hourly samples:")
        for index in sample_indexes:
            parts = [str(times[index])]
            temp_value = _list_item(temperatures, index)
            if temp_value is not None:
                parts.append(f"temperature_2m={temp_value}{temp_unit}")
            precip_value = _list_item(precipitation, index)
            if precip_value is not None:
                parts.append(f"precipitation_probability={precip_value}{precip_unit}")
            code_value = _list_item(weather_codes, index)
            if code_value is not None:
                parts.append(f"weather_code={code_value}")
            lines.append("  - " + ", ".join(parts))
    if isinstance(temperatures, list) and temperatures:
        numeric_temperatures = [
            (index, float(item))
            for index, item in enumerate(temperatures)
            if isinstance(item, (int, float))
        ]
        if numeric_temperatures:
            min_index, min_value = min(numeric_temperatures, key=lambda item: item[1])
            max_index, max_value = max(numeric_temperatures, key=lambda item: item[1])
            lines.append(
                "- Temperature range: "
                f"{min_value:g}{temp_unit} at {times[min_index]} to "
                f"{max_value:g}{temp_unit} at {times[max_index]}."
            )
    if isinstance(precipitation, list) and precipitation:
        numeric_precipitation = [
            (index, float(item))
            for index, item in enumerate(precipitation)
            if isinstance(item, (int, float))
        ]
        if numeric_precipitation:
            max_index, max_value = max(numeric_precipitation, key=lambda item: item[1])
            lines.append(
                "- Highest precipitation probability: "
                f"{max_value:g}{precip_unit} at {times[max_index]}."
            )
    return "\n".join(lines)


def _weather_sample_indexes(times: list[Any]) -> list[int]:
    desired_hours = {0, 6, 9, 12, 14, 15, 18, 21, 23}
    indexes: list[int] = []
    for index, value in enumerate(times):
        text = str(value)
        hour_text = text[-5:-3] if len(text) >= 5 else ""
        if hour_text.isdigit() and int(hour_text) in desired_hours:
            indexes.append(index)
    if indexes:
        return indexes[:10]
    if len(times) <= 10:
        return list(range(len(times)))
    return [0, len(times) // 4, len(times) // 2, (len(times) * 3) // 4, len(times) - 1]


def _nested_unit(value: dict[str, Any], section: str, key: str) -> str | None:
    units = value.get(section)
    if not isinstance(units, dict):
        return None
    unit = units.get(key)
    return str(unit) if unit is not None else None


def _list_item(value: Any, index: int) -> Any:
    if not isinstance(value, list) or index >= len(value):
        return None
    return value[index]


def _json_char_count(value: Any) -> int:
    try:
        return len(
            json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
    except TypeError:
        return len(str(value))


def _compact_openapi_details(value: Any) -> Any:
    if isinstance(value, str):
        return _truncate_string(value, _OPENAPI_DETAILS_STRING_LIMIT)
    if isinstance(value, list):
        compacted = [
            _compact_openapi_details(item)
            for item in value[:_OPENAPI_DETAILS_LIST_LIMIT]
        ]
        hidden_count = len(value) - len(compacted)
        if hidden_count > 0:
            compacted.append({"items_omitted_from_details": hidden_count})
        return compacted
    if isinstance(value, dict):
        compacted: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= _OPENAPI_DETAILS_DICT_LIMIT:
                compacted["keys_omitted_from_details"] = len(value) - index
                break
            compacted[str(key)] = _compact_openapi_details(item)
        return compacted
    return value


def _truncate_string(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: max(limit - 3, 0)].rstrip()}..."


def _shape_summary(value: Any) -> Any:
    if isinstance(value, dict):
        shaped: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 24:
                shaped["_truncated_keys"] = len(value) - index
                break
            shaped[str(key)] = _shape_summary(item)
        return shaped
    if isinstance(value, list):
        if not value:
            return {"type": "list", "length": 0}
        return {
            "type": "list",
            "length": len(value),
            "item": _shape_summary(value[0]),
        }
    return type(value).__name__


_OPENAPI_PARAMETER_ALIASES: dict[tuple[str, str], dict[str, str]] = {
    ("brave_search", "search_lang"): {
        "zh": "zh-hans",
        "zh-cn": "zh-hans",
        "zh_cn": "zh-hans",
        "zh-hans-cn": "zh-hans",
        "zh-tw": "zh-hant",
        "zh_tw": "zh-hant",
        "zh-hant-tw": "zh-hant",
    },
    ("brave_search", "ui_lang"): {
        "zh": "zh-CN",
        "zh-cn": "zh-CN",
        "zh_cn": "zh-CN",
        "zh-hans": "zh-CN",
        "zh-hant": "zh-TW",
        "zh-tw": "zh-TW",
        "zh_tw": "zh-TW",
        "en": "en-US",
    },
}


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
