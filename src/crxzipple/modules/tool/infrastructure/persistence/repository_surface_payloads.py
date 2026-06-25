from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from crxzipple.modules.tool.application.surface import (
    ToolSurface,
    ToolSurfaceFunction,
    ToolSurfaceGroup,
    ToolSurfaceSource,
)
from crxzipple.modules.tool.infrastructure.persistence.repository_payloads import (
    dict_payload,
    string_tuple_payload,
)
from crxzipple.shared.time import coerce_utc_datetime


def tool_surface_from_payload(
    payload: dict[str, object],
    *,
    fallback_surface_id: str,
    fallback_created_at: datetime,
) -> ToolSurface:
    return ToolSurface(
        surface_id=str(payload.get("surface_id") or fallback_surface_id),
        session_id=_optional_payload_text(payload.get("session_id")),
        run_id=_optional_payload_text(payload.get("run_id")),
        agent_id=_optional_payload_text(payload.get("agent_id")),
        policy_version=str(payload.get("policy_version") or "tool_surface.v1"),
        sources=tuple(
            _tool_surface_source_from_payload(item)
            for item in _mapping_list(payload.get("sources"))
        ),
        functions=tuple(
            _tool_surface_function_from_payload(item)
            for item in _mapping_list(payload.get("functions"))
        ),
        default_tool_choice=str(payload.get("default_tool_choice") or "auto"),
        parallel_tool_calls=bool(payload.get("parallel_tool_calls", True)),
        estimate=dict_payload(payload.get("estimate")),
        diagnostics=dict_payload(payload.get("diagnostics")),
        created_at=_datetime_payload(payload.get("created_at"), fallback_created_at),
    )


def _tool_surface_source_from_payload(payload: Mapping[str, object]) -> ToolSurfaceSource:
    return ToolSurfaceSource(
        source_id=str(payload.get("source_id") or ""),
        source_key=str(payload.get("source_key") or payload.get("source_id") or ""),
        source_kind=str(payload.get("source_kind") or ""),
        title=str(payload.get("title") or ""),
        summary=str(payload.get("summary") or ""),
        groups=tuple(
            _tool_surface_group_from_payload(item)
            for item in _mapping_list(payload.get("groups"))
        ),
        readiness=dict_payload(payload.get("readiness")),
        authorization=dict_payload(payload.get("authorization")),
        runtime_requirements=tuple(_mapping_list(payload.get("runtime_requirements"))),
        runtime_request_metadata=dict_payload(
            payload.get("runtime_request_metadata"),
        ),
        metadata=dict_payload(payload.get("metadata")),
    )


def _tool_surface_group_from_payload(payload: Mapping[str, object]) -> ToolSurfaceGroup:
    return ToolSurfaceGroup(
        group_key=str(payload.get("group_key") or ""),
        title=str(payload.get("title") or ""),
        summary=str(payload.get("summary") or ""),
        function_refs=string_tuple_payload(payload.get("function_refs")),
        default_expanded=bool(payload.get("default_expanded", False)),
        schema_enabled=bool(payload.get("schema_enabled", True)),
        estimate=dict_payload(payload.get("estimate")),
        metadata=dict_payload(payload.get("metadata")),
    )


def _tool_surface_function_from_payload(
    payload: Mapping[str, object],
) -> ToolSurfaceFunction:
    return ToolSurfaceFunction(
        function_id=str(payload.get("function_id") or ""),
        name=str(payload.get("name") or ""),
        title=str(payload.get("title") or ""),
        description=str(payload.get("description") or ""),
        input_schema=dict_payload(payload.get("input_schema")),
        source_id=str(payload.get("source_id") or ""),
        group_key=str(payload.get("group_key") or ""),
        runtime_kind=str(payload.get("runtime_kind") or ""),
        execution_modes=string_tuple_payload(payload.get("execution_modes")),
        execution_strategies=string_tuple_payload(payload.get("execution_strategies")),
        execution_environments=string_tuple_payload(
            payload.get("execution_environments"),
        ),
        requires_confirmation=bool(payload.get("requires_confirmation", False)),
        mutates_state=bool(payload.get("mutates_state", False)),
        supports_parallel=bool(payload.get("supports_parallel", True)),
        readiness=dict_payload(payload.get("readiness")),
        authorization=dict_payload(payload.get("authorization")),
        concurrency_key=_optional_payload_text(payload.get("concurrency_key")),
        provider_schema_hints=dict_payload(payload.get("provider_schema_hints")),
        metadata=dict_payload(payload.get("metadata")),
    )


def _mapping_list(value: object | None) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, Mapping))


def _datetime_payload(value: object | None, fallback: datetime) -> datetime:
    if isinstance(value, str) and value.strip():
        try:
            return coerce_utc_datetime(datetime.fromisoformat(value))
        except ValueError:
            return fallback
    return fallback


def _optional_payload_text(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
