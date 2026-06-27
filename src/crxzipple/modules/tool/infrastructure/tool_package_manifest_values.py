from __future__ import annotations

from pathlib import Path
from typing import Any

from crxzipple.modules.tool.application.activation import (
    ToolDependencyKind,
    ToolDependencyRequirement,
)
from crxzipple.modules.tool.application.capabilities import (
    DEFAULT_TOOL_CAPABILITY_CATALOG,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.tool_package_manifest_parsers import (
    mapping_payload,
    parse_string_list,
    parse_string_sets,
    required_string,
    stable_payload,
)


def load_runtime_request_metadata(
    raw_runtime_request: object,
    manifest_path: Path,
) -> dict[str, object]:
    if raw_runtime_request in (None, {}):
        return {}
    if not isinstance(raw_runtime_request, dict):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field 'runtime_request' must be a mapping.",
        )
    runtime_request: dict[str, object] = stable_payload(raw_runtime_request)
    for key in ("title", "summary"):
        raw_value = raw_runtime_request.get(key)
        if raw_value is None:
            runtime_request.pop(key, None)
            continue
        value = str(raw_value).strip()
        if value:
            runtime_request[key] = value
        else:
            runtime_request.pop(key, None)
    raw_groups = raw_runtime_request.get("groups")
    if raw_groups is not None:
        runtime_request = _with_runtime_request_groups(
            runtime_request,
            raw_groups,
            manifest_path,
        )
    return runtime_request


def load_dependency_requirements(
    raw_requirements: object,
    manifest_path: Path,
) -> tuple[ToolDependencyRequirement, ...]:
    if raw_requirements in (None, []):
        return ()
    if not isinstance(raw_requirements, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field 'dependencies' must be a list.",
        )
    requirements: list[ToolDependencyRequirement] = []
    for item in raw_requirements:
        if isinstance(item, str):
            dependency_id = item.strip()
            if not dependency_id:
                continue
            requirements.append(
                ToolDependencyRequirement(
                    id=dependency_id,
                    kind="service_dependency",
                ),
            )
            continue
        if not isinstance(item, dict):
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' dependency entries must be strings or mappings.",
            )
        dependency_id = required_string(item, "id", manifest_path)
        dependency_kind = parse_dependency_kind(
            item.get("kind", "service_dependency"),
            manifest_path=manifest_path,
        )
        requirements.append(
            ToolDependencyRequirement(
                id=dependency_id,
                kind=dependency_kind,
                description=str(item.get("description", "")).strip(),
                required=bool(
                    item.get(
                        "required",
                        dependency_kind != "optional_dependency",
                    ),
                ),
                metadata=mapping_payload(item.get("metadata")),
            ),
        )
    return tuple(requirements)


def load_capability_ids(
    payload: dict[str, Any],
    manifest_path: Path,
) -> tuple[str, ...]:
    raw_capabilities = payload.get("capabilities")
    if raw_capabilities is None:
        raw_capabilities = payload.get("capability_ids", [])
    if raw_capabilities in (None, []):
        return ()
    capability_ids = parse_string_list(
        raw_capabilities,
        "capabilities",
        manifest_path,
    )
    return DEFAULT_TOOL_CAPABILITY_CATALOG.validate_capability_ids(capability_ids)


def combined_capability_ids(
    *capability_groups: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            capability_id
            for capability_group in capability_groups
            for capability_id in capability_group
        ),
    )


def runtime_requirement_sets(
    raw_values: object,
    *,
    dependency_requirements: tuple[ToolDependencyRequirement, ...],
    manifest_path: Path,
) -> tuple[tuple[str, ...], ...]:
    requirement_sets = list(
        parse_string_sets(raw_values, "runtime_requirement_sets", manifest_path),
    )
    external_requirements = tuple(
        dependency.id
        for dependency in dependency_requirements
        if dependency.kind == "external_requirement" and dependency.id.strip()
    )
    if external_requirements:
        requirement_sets.append(tuple(dict.fromkeys(external_requirements)))
    return tuple(dict.fromkeys(requirement_sets))


def parse_dependency_kind(
    raw_value: object,
    *,
    manifest_path: Path,
) -> ToolDependencyKind:
    normalized = str(raw_value or "service_dependency").strip()
    if normalized in (
        "service_dependency",
        "external_requirement",
        "optional_dependency",
    ):
        return normalized
    raise ToolValidationError(
        f"Tool namespace manifest '{manifest_path}' dependency kind '{normalized}' is unsupported.",
    )


def _with_runtime_request_groups(
    runtime_request: dict[str, object],
    raw_groups: object,
    manifest_path: Path,
) -> dict[str, object]:
    if not isinstance(raw_groups, dict):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field 'runtime_request.groups' must be a mapping.",
        )
    groups: dict[str, object] = {}
    for raw_group_key, raw_group in raw_groups.items():
        group_key = str(raw_group_key).strip()
        if not group_key:
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' runtime_request group keys cannot be empty.",
            )
        if not isinstance(raw_group, dict):
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' runtime_request group '{group_key}' must be a mapping.",
            )
        group_payload = _runtime_request_group_payload(
            raw_group,
            group_key=group_key,
            manifest_path=manifest_path,
        )
        groups[group_key] = group_payload
    if groups:
        runtime_request["groups"] = groups
    else:
        runtime_request.pop("groups", None)
    return runtime_request


def _runtime_request_group_payload(
    raw_group: dict[str, object],
    *,
    group_key: str,
    manifest_path: Path,
) -> dict[str, object]:
    group_payload: dict[str, object] = stable_payload(raw_group)
    for key in ("title", "summary"):
        raw_value = raw_group.get(key)
        if raw_value is None:
            group_payload.pop(key, None)
            continue
        value = str(raw_value).strip()
        if value:
            group_payload[key] = value
        else:
            group_payload.pop(key, None)
    function_ids = parse_string_list(
        raw_group.get("function_ids", []),
        "runtime_request.groups.function_ids",
        manifest_path,
    )
    raw_order = raw_group.get("order")
    if raw_order is not None:
        try:
            group_payload["order"] = int(raw_order)
        except (TypeError, ValueError) as exc:
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' runtime_request group '{group_key}' order must be an integer.",
            ) from exc
    if function_ids:
        group_payload["function_ids"] = function_ids
    else:
        group_payload.pop("function_ids", None)
    return group_payload
