from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.shared.access import AccessCredentialRequirementSet


class ToolSourceCatalogKind(StrEnum):
    LOCAL_PACKAGE = "local_package"
    MCP = "mcp"
    OPENAPI = "openapi"
    CLI = "cli"
    PROVIDER_BACKEND = "provider_backend"


class ToolSourceStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"
    DELETED = "deleted"


class ToolSourceDiscoveryStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class ToolFunctionRuntimeKind(StrEnum):
    LOCAL = "local"
    REMOTE = "remote"
    SANDBOX = "sandbox"
    MCP = "mcp"
    OPENAPI = "openapi"
    CLI = "cli"
    PROVIDER_BACKEND = "provider_backend"


class ToolFunctionStatus(StrEnum):
    ACTIVE = "active"
    STALE = "stale"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class ToolFunctionRequirements:
    credential_requirements: tuple[AccessCredentialRequirementSet, ...] = ()
    access_requirement_sets: tuple[tuple[str, ...], ...] = ()
    runtime_requirement_sets: tuple[tuple[str, ...], ...] = ()
    required_effect_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "credential_requirements",
            tuple(self.credential_requirements),
        )
        object.__setattr__(
            self,
            "access_requirement_sets",
            _normalize_text_sets(self.access_requirement_sets),
        )
        object.__setattr__(
            self,
            "runtime_requirement_sets",
            _normalize_text_sets(self.runtime_requirement_sets),
        )
        object.__setattr__(
            self,
            "required_effect_ids",
            _normalize_text_tuple(self.required_effect_ids),
        )


def _normalize_text_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip()
        ),
    )


def _normalize_text_sets(
    values: tuple[tuple[str, ...], ...],
) -> tuple[tuple[str, ...], ...]:
    resolved: list[tuple[str, ...]] = []
    for value in values:
        normalized = _normalize_text_tuple(tuple(value))
        if normalized not in resolved:
            resolved.append(normalized)
    return tuple(resolved)


def ensure_tool_function_requirements(
    value: ToolFunctionRequirements,
    *,
    label: str,
) -> ToolFunctionRequirements:
    if not isinstance(value, ToolFunctionRequirements):
        raise ToolValidationError(f"{label} requirements are invalid.")
    return value
