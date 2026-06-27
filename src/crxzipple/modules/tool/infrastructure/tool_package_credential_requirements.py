from __future__ import annotations

from pathlib import Path

from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.tool_package_credential_declarations import (
    parse_credential_requirement_declaration,
)
from crxzipple.modules.tool.infrastructure.tool_package_manifest_parsers import (
    mapping_payload,
)
from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessCredentialRequirementSet,
)


def parse_credential_requirement_sets(
    raw_values: object,
    manifest_path: Path,
    *,
    tool_id: str,
    runtime_key: str | None,
) -> tuple[AccessCredentialRequirementSet, ...]:
    if raw_values in (None, []):
        return ()
    if not isinstance(raw_values, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field 'credential_requirements' must be a list.",
        )
    consumer = AccessConsumerRef(
        consumer_id=tool_id,
        module="tool",
        component="local_package",
        runtime_ref=runtime_key,
        metadata={"manifest_path": str(manifest_path)},
    )
    requirement_sets: list[AccessCredentialRequirementSet] = []
    for index, raw_set in enumerate(raw_values):
        if not isinstance(raw_set, dict):
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' credential_requirements[{index}] must be a mapping.",
            )
        raw_requirements = raw_set.get("requirements")
        if raw_requirements is None:
            raw_requirements = [raw_set]
        if not isinstance(raw_requirements, list):
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' credential_requirements[{index}].requirements must be a list.",
            )
        declarations = tuple(
            parse_credential_requirement_declaration(
                raw_requirement,
                manifest_path,
                consumer=consumer,
                set_index=index,
                requirement_index=requirement_index,
            )
            for requirement_index, raw_requirement in enumerate(raw_requirements)
        )
        requirement_sets.append(
            AccessCredentialRequirementSet(
                requirement_set_id=str(
                    raw_set.get("requirement_set_id")
                    or raw_set.get("id")
                    or f"{tool_id}.credentials.{index}",
                ),
                consumer=consumer,
                requirements=declarations,
                alternative=bool(raw_set.get("alternative", False)),
                metadata=mapping_payload(raw_set.get("metadata")),
            ),
        )
    return tuple(requirement_sets)


__all__ = [
    "parse_credential_requirement_sets",
]
