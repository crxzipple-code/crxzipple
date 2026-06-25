from __future__ import annotations

from crxzipple.modules.workbench.application import view_models as models
from typing import Any

from crxzipple.modules.orchestration.application.ports import OrchestrationRunQueryPort
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.workbench.application.execution_projection import (
    execution_llm_invocation_ids_for_run,
    llm_invocation_llm_id,
    run_may_have_execution_items,
    safe_llm_invocation,
)
from crxzipple.modules.workbench.application.projection_helpers import optional_text
from crxzipple.modules.workbench.application.run_llm_projection import (
    llm_id,
)


def agent_ref(run: OrchestrationRun, agent_query: Any | None):
    agent_id = run.agent_id or "unknown"
    if agent_query is not None and run.agent_id is not None:
        try:
            profile = agent_query.get_profile(run.agent_id)
        except Exception:
            profile = None
        if profile is not None:
            identity = getattr(profile, "identity", None)
            display_name = optional_text(getattr(identity, "display_name", None))
            name = display_name or optional_text(getattr(profile, "name", None))
            if name is not None:
                return models.RuntimeRef(id=agent_id, name=name)
    return models.RuntimeRef(id=agent_id, name=run.agent_id or "Unknown Agent")


def model_ref(
    run: OrchestrationRun,
    llm_query: Any | None,
    *,
    run_query: OrchestrationRunQueryPort | None = None,
):
    resolved_llm_id = llm_id(run) or llm_invocation_llm_id(
        llm_invocation_for_run(run_query, llm_query, run),
    )
    if resolved_llm_id is None:
        return models.RuntimeRef(id="auto", name="Auto")
    if llm_query is not None:
        try:
            profile = llm_query.get_profile(resolved_llm_id)
        except Exception:
            profile = None
        if profile is not None:
            provider = getattr(getattr(profile, "provider", None), "value", None)
            model_name = optional_text(getattr(profile, "model_name", None))
            if model_name is not None:
                label = f"{provider}/{model_name}" if provider else model_name
                return models.RuntimeRef(id=resolved_llm_id, name=label)
    return models.RuntimeRef(id=resolved_llm_id, name=resolved_llm_id)


def llm_invocation_for_run(
    run_query: OrchestrationRunQueryPort | None,
    llm_query: Any | None,
    run: OrchestrationRun,
) -> Any | None:
    if llm_query is None or not run_may_have_execution_items(run):
        return None
    invocation_ids: list[str] = []
    if run_query is not None:
        invocation_ids.extend(execution_llm_invocation_ids_for_run(run_query, run.id))
    if not invocation_ids:
        return None
    for invocation_id in dict.fromkeys(invocation_ids):
        invocation = safe_llm_invocation(llm_query, invocation_id)
        if invocation is not None:
            return invocation
    return None


__all__ = ["agent_ref", "llm_invocation_for_run", "model_ref"]
