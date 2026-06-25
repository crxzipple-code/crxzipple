from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.tool_run_artifact_ref_projection import (
    artifact_from_mapping,
    artifact_refs_from_metadata,
    result_blocks,
)
from crxzipple.modules.operations.application.read_models.tool_run_result_payloads import (
    tool_run_result_payload,
)
from crxzipple.modules.tool.domain import ToolRun


def tool_run_artifact_refs(
    run: ToolRun,
    *,
    artifact_service: Any | None,
) -> list[dict[str, str]]:
    payload = tool_run_result_payload(run)
    refs: list[dict[str, str]] = []
    seen: set[str] = set()

    for block in result_blocks(payload):
        artifact = artifact_from_mapping(block, artifact_service=artifact_service)
        if artifact is None or artifact["artifact_id"] in seen:
            continue
        refs.append(artifact)
        seen.add(artifact["artifact_id"])

    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        for artifact in artifact_refs_from_metadata(
            metadata,
            artifact_service=artifact_service,
        ):
            if artifact["artifact_id"] in seen:
                continue
            refs.append(artifact)
            seen.add(artifact["artifact_id"])

    return refs
