from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.tool.application.catalog_models import (
    ToolFunctionCatalogRecord,
    ToolSourceCatalogKind,
    ToolSourceCatalogRecord,
)


@dataclass(frozen=True, slots=True)
class ToolRuntimeRequestBundleGroup:
    group_key: str
    title: str
    summary: str
    function_ids: tuple[str, ...]
    function_count: int
    capability_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolRuntimeRequestBundle:
    source_id: str
    title: str
    summary: str
    source_kind: str
    function_ids: tuple[str, ...]
    function_count: int
    groups: tuple[ToolRuntimeRequestBundleGroup, ...] = ()
    credential_requirement_count: int = 0
    runtime_requirement_count: int = 0
    capability_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


def build_runtime_request_bundle(
    source: ToolSourceCatalogRecord,
    functions: tuple[ToolFunctionCatalogRecord, ...],
) -> ToolRuntimeRequestBundle:
    runtime_request = _runtime_request_config(source)
    title = _runtime_request_text(runtime_request, "title") or source.display_name
    summary = (
        _runtime_request_text(runtime_request, "summary")
        or source.description
        or f"Tool bundle '{title}' exposed by source '{source.source_id}'."
    )
    return ToolRuntimeRequestBundle(
        source_id=source.source_id,
        title=title,
        summary=summary,
        source_kind=source.kind.value,
        function_ids=tuple(function.function_id for function in functions),
        function_count=len(functions),
        groups=_runtime_request_bundle_groups(source, runtime_request, functions),
        credential_requirement_count=_credential_requirement_count(
            source,
            functions,
        ),
        runtime_requirement_count=_runtime_requirement_count(source, functions),
        capability_ids=_bundle_capability_ids(source, functions),
        metadata={
            "source_id": source.source_id,
            "source_kind": source.kind.value,
            "runtime_request": dict(runtime_request),
            "config_hash": source.config_hash,
            "function_ids": [function.function_id for function in functions],
        },
    )


def _runtime_request_config(source: ToolSourceCatalogRecord) -> Mapping[str, Any]:
    raw_runtime_request = source.config.get("runtime_request")
    if isinstance(raw_runtime_request, Mapping):
        return dict(raw_runtime_request)
    provider = source.config.get("provider")
    if isinstance(provider, Mapping):
        provider_runtime_request = provider.get("runtime_request")
        if isinstance(provider_runtime_request, Mapping):
            return dict(provider_runtime_request)
    return {}


def _runtime_request_bundle_groups(
    source: ToolSourceCatalogRecord,
    runtime_request: Mapping[str, Any],
    functions: tuple[ToolFunctionCatalogRecord, ...],
) -> tuple[ToolRuntimeRequestBundleGroup, ...]:
    raw_groups = runtime_request.get("groups")
    function_by_id = {function.function_id: function for function in functions}
    groups: list[tuple[int, int, ToolRuntimeRequestBundleGroup]] = []
    grouped_function_ids: set[str] = set()
    if isinstance(raw_groups, Mapping):
        for index, (raw_group_key, raw_group) in enumerate(raw_groups.items()):
            group_key = str(raw_group_key).strip()
            if not group_key or not isinstance(raw_group, Mapping):
                continue
            declared_function_ids = _runtime_request_group_function_ids(raw_group)
            group_functions = tuple(
                function_by_id[function_id]
                for function_id in declared_function_ids
                if function_id in function_by_id
            )
            if not group_functions:
                continue
            grouped_function_ids.update(function.function_id for function in group_functions)
            title = _runtime_request_text(raw_group, "title") or group_key.replace("_", " ").title()
            summary = (
                _runtime_request_text(raw_group, "summary")
                or f"Tool functions in the '{title}' group."
            )
            order = _runtime_request_group_order(raw_group, fallback=1000 + index)
            groups.append(
                (
                    order,
                    index,
                    ToolRuntimeRequestBundleGroup(
                        group_key=group_key,
                        title=title,
                        summary=summary,
                        function_ids=tuple(
                            function.function_id for function in group_functions
                        ),
                        function_count=len(group_functions),
                        capability_ids=_function_capability_ids(group_functions),
                        metadata={
                            "group_key": group_key,
                            "order": order,
                            "function_ids": [
                                function.function_id for function in group_functions
                            ],
                            **_runtime_request_group_metadata(raw_group),
                        },
                    ),
                ),
            )
    ungrouped_functions = tuple(
        function
        for function in functions
        if function.function_id not in grouped_function_ids
    )
    if ungrouped_functions:
        group_key = "source" if not groups else "other"
        order = 10000 + len(groups)
        groups.append(
            (
                order,
                len(groups),
                ToolRuntimeRequestBundleGroup(
                    group_key=group_key,
                    title=_default_source_group_title(source, runtime_request, group_key),
                    summary=_default_source_group_summary(source, runtime_request, group_key),
                    function_ids=tuple(function.function_id for function in ungrouped_functions),
                    function_count=len(ungrouped_functions),
                    capability_ids=_function_capability_ids(ungrouped_functions),
                    metadata={
                        "group_key": group_key,
                        "order": order,
                        "auto_source_group": True,
                        "source_kind": source.kind.value,
                        "function_ids": [
                            function.function_id for function in ungrouped_functions
                        ],
                    },
                ),
            ),
        )
    return tuple(group for _, _, group in sorted(groups, key=lambda item: item[:2]))


def _default_source_group_title(
    source: ToolSourceCatalogRecord,
    runtime_request: Mapping[str, Any],
    group_key: str,
) -> str:
    if group_key == "other":
        return "Other Functions"
    return _runtime_request_text(runtime_request, "title") or source.display_name


def _default_source_group_summary(
    source: ToolSourceCatalogRecord,
    runtime_request: Mapping[str, Any],
    group_key: str,
) -> str:
    if group_key == "other":
        return (
            "Additional functions from this source that were not assigned to a "
            "more specific runtime request group. Expand to inspect exact callable functions."
        )
    source_summary = _runtime_request_text(runtime_request, "summary") or source.description
    kind_summary = _default_source_kind_summary(source.kind)
    if source_summary:
        return (
            f"{source_summary} {kind_summary} Expand this group to inspect exact "
            "callable functions and their input schemas."
        )
    return f"{kind_summary} Expand this group to inspect exact callable functions and their input schemas."


def _default_source_kind_summary(source_kind: ToolSourceCatalogKind) -> str:
    if source_kind is ToolSourceCatalogKind.OPENAPI:
        return "OpenAPI source operations are API-backed calls from one configured service."
    if source_kind is ToolSourceCatalogKind.MCP:
        return "MCP source tools are remote protocol capabilities from one configured server."
    if source_kind is ToolSourceCatalogKind.CLI:
        return "CLI source entries are command-line guidance; use command execution tools to inspect help and run commands."
    if source_kind is ToolSourceCatalogKind.LOCAL_PACKAGE:
        return "Local package functions are CRXZipple-owned runtime capabilities from one package."
    if source_kind is ToolSourceCatalogKind.PROVIDER_BACKEND:
        return "Provider backend functions are routed through one configured backend capability."
    return "Tool source functions come from one configured capability source."


def _runtime_request_group_order(group: Mapping[str, Any], *, fallback: int) -> int:
    raw_order = group.get("order")
    if raw_order is None:
        return fallback
    try:
        return int(raw_order)
    except (TypeError, ValueError):
        return fallback


def _runtime_request_group_function_ids(group: Mapping[str, Any]) -> tuple[str, ...]:
    raw_function_ids = group.get("function_ids")
    if not isinstance(raw_function_ids, Iterable) or isinstance(
        raw_function_ids,
        (str, bytes),
    ):
        return ()
    return tuple(
        dict.fromkeys(
            str(function_id).strip()
            for function_id in raw_function_ids
            if str(function_id).strip()
        ),
    )


def _runtime_request_group_metadata(group: Mapping[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    default_schema_ids = _runtime_request_group_string_values(
        group.get("default_tool_schema_ids"),
    )
    if default_schema_ids:
        metadata["default_tool_schema_ids"] = list(default_schema_ids)
    default_schema_source = _runtime_request_text(group, "default_tool_schema_source")
    if default_schema_source:
        metadata["default_tool_schema_source"] = default_schema_source
    default_schema_max_count = _runtime_request_group_positive_int(
        group.get("default_tool_schema_max_count"),
    )
    if default_schema_max_count is not None:
        metadata["default_tool_schema_max_count"] = default_schema_max_count
    return metadata


def _runtime_request_group_string_values(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        return ()
    return tuple(
        dict.fromkeys(
            str(item).strip()
            for item in value
            if str(item).strip()
        ),
    )


def _runtime_request_group_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip():
        try:
            parsed = int(value.strip())
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def _runtime_request_text(runtime_request: Mapping[str, Any], key: str) -> str | None:
    value = runtime_request.get(key)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _credential_requirement_count(
    source: ToolSourceCatalogRecord,
    functions: tuple[ToolFunctionCatalogRecord, ...],
) -> int:
    return len(source.credential_requirements) + sum(
        len(function.requirements.credential_requirements)
        for function in functions
    )


def _runtime_requirement_count(
    source: ToolSourceCatalogRecord,
    functions: tuple[ToolFunctionCatalogRecord, ...],
) -> int:
    function_requirement_count = sum(
        len(requirement_set)
        for function in functions
        for requirement_set in function.requirements.runtime_requirement_sets
    )
    return len(source.runtime_requirements) + function_requirement_count


def _bundle_capability_ids(
    source: ToolSourceCatalogRecord,
    functions: tuple[ToolFunctionCatalogRecord, ...],
) -> tuple[str, ...]:
    raw_source_capabilities = source.config.get("capability_ids")
    source_capabilities = (
        tuple(
            str(capability_id).strip()
            for capability_id in raw_source_capabilities
            if str(capability_id).strip()
        )
        if isinstance(raw_source_capabilities, (list, tuple))
        else ()
    )
    return tuple(
        dict.fromkeys(
            capability_id
            for capability_id in (
                *source_capabilities,
                *_function_capability_ids(functions),
            )
            if capability_id
        ),
    )


def _function_capability_ids(
    functions: tuple[ToolFunctionCatalogRecord, ...],
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            capability_id
            for function in functions
            for capability_id in function.capabilities
            if capability_id
        ),
    )
