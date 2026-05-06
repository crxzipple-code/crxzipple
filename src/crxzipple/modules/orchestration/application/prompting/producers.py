from __future__ import annotations

from crxzipple.modules.orchestration.application.prompting.blocks import (
    PromptBlock,
    PromptBlockPolicy,
)
from crxzipple.modules.orchestration.application.prompting.runtime_context import (
    build_runtime_context_message,
)
from crxzipple.modules.orchestration.application.memory_context import RecalledMemory
from crxzipple.modules.orchestration.application.workspace_context import PromptContextFile
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.tool.domain import Tool
from crxzipple.modules.skills.application import SkillCatalogPrompt


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
_SESSION_TOOLS_POLICY = PromptBlockPolicy(priority=925, max_tokens=1_200)
_AVAILABLE_TOOLS_POLICY = PromptBlockPolicy(priority=930, max_tokens=1_800)

_SESSION_TOOL_ORDER = (
    "session_status",
    "sessions_list",
    "sessions_history",
    "sessions_send",
    "sessions_spawn",
    "subagents",
    "sessions_stop",
    "sessions_yield",
)


def _tool_family(tool: Tool) -> str:
    tool_id = tool.id
    if tool_id in {"read", "write", "edit", "apply_patch", "exec", "process", "workspace_list", "workspace_search"}:
        return "workspace"
    if tool_id.startswith("memory_"):
        return "memory"
    if tool_id.startswith("session") or tool_id.startswith("sessions_") or tool_id == "subagents":
        return "session"
    if tool_id.startswith("browser_"):
        return "browser"
    if tool_id.startswith("mobile_"):
        return "mobile"
    if tool_id.startswith("brave_search.") or tool_id.startswith("open_meteo_") or tool_id.startswith("itick_market."):
        return "external_data"
    if tool_id.startswith("skill_"):
        return "skills"
    return "general"


_TOOL_FAMILY_LABELS: dict[str, str] = {
    "workspace": "Workspace tools",
    "memory": "Memory tools",
    "session": "Session tools",
    "browser": "Browser tools",
    "mobile": "Mobile tools",
    "external_data": "External data tools",
    "skills": "Skill tools",
    "general": "General tools",
}


_TOOL_FAMILY_ORDER = (
    "workspace",
    "memory",
    "browser",
    "mobile",
    "external_data",
    "session",
    "skills",
    "general",
)


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
    workspace_dir: str | None,
) -> PromptBlock | None:
    if not context_files:
        return None
    lines = [
        "# Workspace Context",
        "",
        "The following workspace bootstrap files were loaded for this run.",
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
    if workspace_dir is not None and workspace_dir.strip():
        metadata["workspace_dir"] = workspace_dir.strip()
    return PromptBlock(
        kind="project_context",
        content="\n".join(lines).strip(),
        metadata=metadata,
        policy=_PROJECT_CONTEXT_POLICY,
    )


def build_skills_catalog_block(
    catalog: SkillCatalogPrompt | None,
) -> PromptBlock | None:
    if catalog is None:
        return None
    return PromptBlock(
        kind="skills_catalog",
        content=catalog.content,
        metadata=dict(catalog.metadata),
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


def build_session_tools_block(
    available_tool_names: tuple[str, ...],
) -> PromptBlock | None:
    available_tool_name_set = set(available_tool_names)
    visible = tuple(
        tool_name
        for tool_name in _SESSION_TOOL_ORDER
        if tool_name in available_tool_name_set
    )
    if not visible:
        return None
    lines = [
        "# Session Tools",
        "",
        "These are a specialized subset of the full available-tools inventory above, not the complete tool list for the run.",
        "These tools operate on exact session buckets and active instances.",
        "They are not memory recall, semantic search, or implicit context carry-over.",
        "",
    ]
    if "session_status" in visible:
        lines.append(
            "- `session_status`: inspect the current session bucket and active instance state first; for requester sessions it also shows subagent-tree totals and follow-up scheduling state.",
        )
    if "sessions_list" in visible:
        lines.append(
            "- `sessions_list`: list visible session buckets for the current agent.",
        )
    if "sessions_history" in visible:
        lines.append(
            "- `sessions_history`: read trimmed exact transcript history from a chosen session bucket or specific instance.",
        )
    if "sessions_send" in visible:
        lines.append(
            "- `sessions_send`: append exact text into a target session bucket's current active instance and optionally enqueue follow-up work there.",
        )
    if "sessions_spawn" in visible:
        lines.append(
            "- `sessions_spawn`: create a fresh child session bucket under the current agent and enqueue child work there; it returns accepted immediately instead of waiting for the child result inline.",
        )
    if "subagents" in visible:
        lines.append(
            "- `subagents`: expand the current requester session's spawned child-session tree when you need per-child bucket relationships or current/latest run details.",
        )
    if "sessions_stop" in visible:
        lines.append(
            "- `sessions_stop`: cancel non-terminal work in the current requester session bucket and recursively stop its spawned child session buckets.",
        )
    if "sessions_yield" in visible:
        lines.append(
            "- `sessions_yield`: stop auto-continuing after the current tool turn and return control cleanly to the session boundary.",
        )
    lines.extend(
        [
            "",
            "Use session tools only when you intend to inspect or route work to an exact session bucket.",
            "Use memory tools for semantic recall or durable facts instead of session tools.",
            "Prefer `session_status` first for requester-wide state; use `subagents` only when you need to drill into specific child buckets.",
            "After a fresh reset, do not assume previous transcript or compaction summary carries into the new active instance unless it appears in transcript or memory.",
        ],
    )
    return PromptBlock(
        kind="session_tools",
        content="\n".join(lines).strip(),
        metadata={
            "tool_ids": list(visible),
        },
        policy=_SESSION_TOOLS_POLICY,
    )


def build_available_tools_block(
    available_tools: tuple[Tool, ...],
) -> PromptBlock | None:
    if not available_tools:
        return None
    families: dict[str, list[str]] = {key: [] for key in _TOOL_FAMILY_ORDER}
    for tool in available_tools:
        families.setdefault(_tool_family(tool), []).append(tool.id)

    lines = [
        "# Available Tools",
        "",
        "All of the following tool families are callable in this run when they fit the task.",
        "Do not assume only session tools are available.",
        "If the user asks what tools are available, answer from this full inventory and mention the available families that are actually present in the run.",
        "",
    ]
    visible_tool_ids: list[str] = []
    for family in _TOOL_FAMILY_ORDER:
        tool_ids = sorted(set(families.get(family, [])))
        if not tool_ids:
            continue
        visible_tool_ids.extend(tool_ids)
        lines.append(f"- {_TOOL_FAMILY_LABELS[family]}: {', '.join(f'`{tool_id}`' for tool_id in tool_ids)}")

    lines.extend(
        [
            "",
            "Choose the narrowest tool that matches the user's request.",
            "Use session tools for exact session routing/state; use workspace, memory, browser, data, or skill tools when those match the task better.",
            "When summarizing your capabilities, do not collapse the inventory down to only session tools or memory unless those are truly the only families present.",
        ],
    )
    return PromptBlock(
        kind="available_tools",
        content="\n".join(lines).strip(),
        metadata={"tool_ids": visible_tool_ids},
        policy=_AVAILABLE_TOOLS_POLICY,
    )
