from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.tool.application.catalog_model_helpers import hash_payload
from crxzipple.modules.tool.application.catalog_model_types import (
    ToolFunctionRequirements,
    ToolFunctionRuntimeKind,
)


def compute_tool_function_schema_hash(
    *,
    input_schema: Mapping[str, Any],
    runtime_kind: ToolFunctionRuntimeKind | str,
    handler_ref: str,
    requirements: ToolFunctionRequirements,
    capabilities: tuple[str, ...],
) -> str:
    return hash_payload(
        {
            "schema_version": 1,
            "input_schema": input_schema,
            "runtime_kind": str(runtime_kind),
            "handler_ref": handler_ref,
            "requirements": requirements,
            "capabilities": capabilities,
        },
    )
