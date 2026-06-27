from __future__ import annotations

import json
from typing import Any

from crxzipple.modules.tool.infrastructure.discovery.openapi import OpenApiOperation
from crxzipple.shared.content_blocks import describe_content_for_text_fallback

_OPENAPI_DETAILS_MAX_CHARS = 120_000
_OPENAPI_DETAILS_STRING_LIMIT = 2000
_OPENAPI_DETAILS_LIST_LIMIT = 40
_OPENAPI_DETAILS_DICT_LIMIT = 80


def openapi_result_text(operation: OpenApiOperation, value: Any) -> str:
    fallback = describe_content_for_text_fallback(value)
    weather_summary = _weather_forecast_summary(operation, value)
    if weather_summary is not None:
        return f"{weather_summary}\n\nRaw response:\n{fallback}"
    return fallback


def openapi_result_details(value: Any) -> Any:
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


def decode_response_body(payload: bytes, content_type: str) -> Any:
    text = payload.decode("utf-8")
    if "json" in content_type.lower():
        return json.loads(text)
    return text


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


__all__ = [
    "decode_response_body",
    "openapi_result_details",
    "openapi_result_text",
]
