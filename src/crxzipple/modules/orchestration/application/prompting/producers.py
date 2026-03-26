from __future__ import annotations

from crxzipple.modules.orchestration.application.prompting.blocks import (
    PromptBlock,
    PromptBlockPolicy,
)
from crxzipple.modules.orchestration.application.prompting.runtime_context import (
    build_runtime_context_message,
)
from crxzipple.modules.orchestration.application.memory_context import RecalledMemory
from crxzipple.modules.orchestration.application.skills_context import AvailableSkill
from crxzipple.modules.orchestration.application.workspace_context import PromptContextFile
from crxzipple.modules.orchestration.domain import OrchestrationRun


_AGENT_INSTRUCTION_POLICY = PromptBlockPolicy(priority=1000, max_tokens=6_000)
_RUNTIME_CONTEXT_POLICY = PromptBlockPolicy(priority=950, max_tokens=800)
_PROJECT_CONTEXT_POLICY = PromptBlockPolicy(
    priority=500,
    max_tokens=12_000,
    truncate_strategy="middle",
)
_SKILLS_CATALOG_POLICY = PromptBlockPolicy(priority=350, max_tokens=2_500)
_RECALLED_MEMORY_POLICY = PromptBlockPolicy(
    priority=450,
    max_tokens=3_500,
    truncate_strategy="middle",
)
_MEMORY_LOOKUP_POLICY = PromptBlockPolicy(priority=720, max_tokens=900)


def build_agent_instruction_block(system_prompt: str) -> PromptBlock | None:
    normalized = system_prompt.strip()
    if not normalized:
        return None
    return PromptBlock(
        kind="agent_instruction",
        content=normalized,
        policy=_AGENT_INSTRUCTION_POLICY,
    )


def build_workspace_context_block(
    context_files: tuple[PromptContextFile, ...],
    *,
    home_dir: str | None,
) -> PromptBlock | None:
    if not context_files:
        return None
    lines = [
        "# Agent Home Context",
        "",
        "The following agent-home files were loaded for this agent run.",
        "",
    ]
    for file in context_files:
        lines.extend(
            [
                f"## {file.path}",
                "",
                file.content,
                "",
            ],
        )
    metadata: dict[str, object] = {
        "files": [
            {
                "path": file.path,
                "chars": len(file.content),
            }
            for file in context_files
        ],
    }
    if home_dir is not None and home_dir.strip():
        metadata["agent_home_dir"] = home_dir.strip()
        metadata["workspace_dir"] = home_dir.strip()
    return PromptBlock(
        kind="project_context",
        content="\n".join(lines).strip(),
        metadata=metadata,
        policy=_PROJECT_CONTEXT_POLICY,
    )


def build_skills_catalog_block(
    available_skills: tuple[AvailableSkill, ...],
) -> PromptBlock | None:
    if not available_skills:
        return None
    lines = [
        "# Available Skills",
        "",
        "The following optional skills are available for this run.",
        "Use a skill only when it clearly matches the current task.",
        "If you choose one, call open_skill to load its SKILL.md before following the skill-specific workflow.",
        "Do not read every skill by default. Prefer the single most relevant skill.",
        "",
        "<available_skills>",
    ]
    for skill in available_skills:
        lines.append(
            f"- {skill.name}: {skill.description} (file: {skill.path})",
        )
    lines.extend(
        [
            "</available_skills>",
        ],
    )
    return PromptBlock(
        kind="skills_catalog",
        content="\n".join(lines).strip(),
        metadata={
            "count": len(available_skills),
            "skills": [
                {
                    "name": skill.name,
                    "path": skill.path,
                    "source": skill.source,
                }
                for skill in available_skills
            ],
        },
        policy=_SKILLS_CATALOG_POLICY,
    )


def build_recalled_memory_block(
    recalled_memories: tuple[RecalledMemory, ...],
) -> PromptBlock | None:
    if not recalled_memories:
        return None
    lines = [
        "# Recalled Memory",
        "",
        "The following durable memories may be relevant to the current turn.",
        "Use them only when they actually help with the current request.",
        "",
    ]
    for memory in recalled_memories:
        lines.extend(
            [
                f"## {memory.title}",
                "",
                f"Memory ID: {memory.id}",
            ],
        )
        if memory.tags:
            lines.append(f"Tags: {', '.join(memory.tags)}")
        if memory.summary:
            lines.extend(["", f"Summary: {memory.summary}"])
        lines.extend(["", memory.content, ""])
    return PromptBlock(
        kind="recalled_memory",
        content="\n".join(lines).strip(),
        metadata={
            "count": len(recalled_memories),
            "memories": [
                {
                    "id": memory.id,
                    "title": memory.title,
                    "tags": list(memory.tags),
                    "source_candidate_id": memory.source_candidate_id,
                }
                for memory in recalled_memories
            ],
        },
        policy=_RECALLED_MEMORY_POLICY,
    )


def build_runtime_context_block(
    run: OrchestrationRun,
    *,
    llm_id: str,
    home_dir: str | None,
    workdir: str | None,
) -> PromptBlock | None:
    if run.agent_id is None or not run.agent_id.strip():
        return None
    return PromptBlock(
        kind="runtime_context",
        content=build_runtime_context_message(
            agent_id=run.agent_id,
            llm_id=llm_id,
            home_dir=home_dir,
            workdir=workdir,
        ),
        metadata={
            "agent_id": run.agent_id,
            "llm_id": llm_id,
            "agent_home_dir": home_dir.strip()
            if home_dir is not None and home_dir.strip()
            else None,
            "workdir": workdir.strip()
            if workdir is not None and workdir.strip()
            else None,
            "workspace_dir": (
                workdir.strip()
                if workdir is not None and workdir.strip()
                else (home_dir.strip() if home_dir is not None and home_dir.strip() else None)
            ),
        },
        policy=_RUNTIME_CONTEXT_POLICY,
    )

def build_memory_lookup_block(instruction: str | None) -> PromptBlock | None:
    if instruction is None or not instruction.strip():
        return None
    return PromptBlock(
        kind="memory_lookup_guidance",
        content=instruction.strip(),
        policy=_MEMORY_LOOKUP_POLICY,
    )
