from __future__ import annotations

from crxzipple.modules.orchestration.application.prompting.blocks import (
    PromptBlock,
    PromptBlockPolicy,
)
from crxzipple.modules.orchestration.application.prompting.runtime_context import (
    build_runtime_context_message,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun


_AGENT_INSTRUCTION_POLICY = PromptBlockPolicy(priority=1000, max_tokens=6_000)
_RUNTIME_CONTEXT_POLICY = PromptBlockPolicy(priority=950, max_tokens=800)


def build_agent_instruction_block(system_prompt: str) -> PromptBlock | None:
    normalized = system_prompt.strip()
    if not normalized:
        return None
    return PromptBlock(
        kind="agent_instruction",
        content=normalized,
        policy=_AGENT_INSTRUCTION_POLICY,
    )


def build_runtime_context_block(
    run: OrchestrationRun,
    *,
    llm_id: str,
    home_dir: str | None,
    workspace_dir: str | None,
) -> PromptBlock | None:
    if run.agent_id is None or not run.agent_id.strip():
        return None
    return PromptBlock(
        kind="runtime_context",
        content=build_runtime_context_message(
            agent_id=run.agent_id,
            llm_id=llm_id,
            home_dir=home_dir,
            workspace_dir=workspace_dir,
        ),
        metadata={
            "agent_id": run.agent_id,
            "llm_id": llm_id,
            "agent_home_dir": home_dir.strip()
            if home_dir is not None and home_dir.strip()
            else None,
            "workspace_dir": (
                workspace_dir.strip()
                if workspace_dir is not None and workspace_dir.strip()
                else (home_dir.strip() if home_dir is not None and home_dir.strip() else None)
            ),
        },
        policy=_RUNTIME_CONTEXT_POLICY,
    )
