from __future__ import annotations

from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.workbench.application.projection_helpers import metadata_str


def turn_id(run: OrchestrationRun) -> str:
    return metadata_str(run, "turn_id") or run.id


def turn_ordinal(run: OrchestrationRun) -> int:
    value = run.metadata.get("turn_ordinal")
    return value if isinstance(value, int) and value > 0 else 1
