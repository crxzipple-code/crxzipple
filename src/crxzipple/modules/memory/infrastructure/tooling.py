from __future__ import annotations

import re
from typing import TYPE_CHECKING
from typing import Any

from crxzipple.modules.memory.domain import MemoryEntry, MemoryEntryNotFoundError
from crxzipple.modules.tool.domain import (
    Tool,
    ToolEnvironment,
    ToolExecutionSupport,
    ToolExecutionStrategy,
    ToolKind,
    ToolMode,
    ToolParameter,
    ToolRunResult,
    ToolSourceKind,
)
from crxzipple.modules.tool.infrastructure.discovery import LocalToolCatalog

if TYPE_CHECKING:
    from crxzipple.modules.memory.application.services import MemoryApplicationService


MEMORY_SEARCH_TOOL_ID = "memory_search"
MEMORY_GET_TOOL_ID = "memory_get"
DEFAULT_MEMORY_SEARCH_LIMIT = 6
MAX_MEMORY_SEARCH_INJECTED_CHARS = 4_000
SYSTEM_MANAGED_TOOL_TAG = "system-managed"
_MEMORY_AGENT_ID_ARGUMENT = "__agent_id"
_MEMORY_LOOKUP_INSTRUCTION = (
    "Durable memory is available for this agent. "
    "When earlier decisions, user preferences, project context, or prior commitments may matter, "
    "call memory_search first instead of guessing. "
    "If you need the full content of a specific memory, call memory_get with the returned entry_id."
)


def is_memory_tool_name(name: str) -> bool:
    return name in {MEMORY_SEARCH_TOOL_ID, MEMORY_GET_TOOL_ID}


def memory_tool_ids() -> tuple[str, str]:
    return (MEMORY_SEARCH_TOOL_ID, MEMORY_GET_TOOL_ID)


def memory_lookup_instruction() -> str:
    return _MEMORY_LOOKUP_INSTRUCTION


def inject_memory_tool_context(
    arguments: dict[str, Any],
    *,
    agent_id: str,
) -> dict[str, Any]:
    payload = dict(arguments)
    payload[_MEMORY_AGENT_ID_ARGUMENT] = agent_id
    return payload


def register_builtin_memory_tools(
    catalog: LocalToolCatalog,
    memory_service: MemoryApplicationService,
) -> None:
    async def _memory_search_tool(arguments: dict[str, Any]) -> ToolRunResult:
        from crxzipple.modules.memory.application.services import RecallMemoryEntriesInput

        agent_id = _require_agent_id(arguments)
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ValueError("memory_search requires a non-empty query.")
        raw_limit = arguments.get("limit")
        try:
            limit = int(raw_limit) if raw_limit is not None else DEFAULT_MEMORY_SEARCH_LIMIT
        except (TypeError, ValueError) as exc:
            raise ValueError("memory_search limit must be an integer.") from exc
        limit = min(max(limit, 1), DEFAULT_MEMORY_SEARCH_LIMIT)
        entries = memory_service.recall_entries(
            RecallMemoryEntriesInput(
                agent_id=agent_id,
                query_text=query,
                limit=limit,
                search_limit=max(limit * 4, limit),
            ),
        )
        return ToolRunResult(
            content=render_memory_search_result(
                query=query,
                entries=tuple(entries),
            ),
            metadata={
                "tool": MEMORY_SEARCH_TOOL_ID,
                "agent_id": agent_id,
                "query": query,
                "result_count": len(entries),
                "results": [
                    {
                        "entry_id": entry.id,
                        "title": entry.title,
                        "summary": entry.summary,
                        "tags": list(entry.tags),
                        "citation": memory_citation(entry),
                    }
                    for entry in entries
                ],
            },
        )

    async def _memory_get_tool(arguments: dict[str, Any]) -> ToolRunResult:
        agent_id = _require_agent_id(arguments)
        entry_id = str(arguments.get("entry_id", "")).strip()
        if not entry_id:
            raise ValueError("memory_get requires an entry_id.")
        try:
            entry = memory_service.get_entry(entry_id)
        except MemoryEntryNotFoundError:
            entry = None
        if entry is not None and entry.agent_id != agent_id:
            entry = None
        return ToolRunResult(
            content=render_memory_get_result(entry, entry_id=entry_id),
            metadata={
                "tool": MEMORY_GET_TOOL_ID,
                "agent_id": agent_id,
                "entry_id": entry_id,
                "found": entry is not None,
                "citation": memory_citation(entry) if entry is not None else None,
            },
        )

    shared_tags = ("memory", "builtin", SYSTEM_MANAGED_TOOL_TAG)
    support = ToolExecutionSupport(
        supported_modes=(ToolMode.INLINE,),
        supported_strategies=(ToolExecutionStrategy.ASYNC,),
        supported_environments=(ToolEnvironment.LOCAL,),
    )
    catalog.register(
        Tool(
            id=MEMORY_SEARCH_TOOL_ID,
            name="Memory Search",
            description="Search durable memory entries relevant to the current task.",
            kind=ToolKind.FUNCTION,
            parameters=(
                ToolParameter(
                    name="query",
                    data_type="string",
                    description="Search query describing the memory you want to recall.",
                    required=True,
                ),
                ToolParameter(
                    name="limit",
                    data_type="integer",
                    description="Maximum number of durable memory hits to return.",
                    required=False,
                ),
            ),
            tags=shared_tags,
            execution_support=support,
            source_kind=ToolSourceKind.LOCAL_DISCOVERY,
            runtime_key=MEMORY_SEARCH_TOOL_ID,
            enabled=True,
        ),
        _memory_search_tool,
        provider_name="local_system",
    )
    catalog.register(
        Tool(
            id=MEMORY_GET_TOOL_ID,
            name="Memory Get",
            description="Load the full content for one durable memory entry.",
            kind=ToolKind.FUNCTION,
            parameters=(
                ToolParameter(
                    name="entry_id",
                    data_type="string",
                    description="Exact durable memory entry id to load.",
                    required=True,
                ),
            ),
            tags=shared_tags,
            execution_support=support,
            source_kind=ToolSourceKind.LOCAL_DISCOVERY,
            runtime_key=MEMORY_GET_TOOL_ID,
            enabled=True,
        ),
        _memory_get_tool,
        provider_name="local_system",
    )


def render_memory_search_result(
    *,
    query: str,
    entries: tuple[MemoryEntry, ...],
) -> str:
    lines = [
        "# Memory Search Results",
        "",
        f"Query: {query}",
        "",
    ]
    if not entries:
        lines.append("No durable memories matched this query.")
        return "\n".join(lines).strip()
    lines.append(
        "Use memory_get with an entry_id below if you need the full memory content.",
    )
    lines.append("")
    accepted = 0
    for entry in entries:
        entry_lines = [
            f"## {entry.title}",
            "",
            f"- entry_id: {entry.id}",
        ]
        citation = memory_citation(entry)
        if citation is not None:
            entry_lines.append(f"- citation: {citation}")
        if entry.tags:
            entry_lines.append(f"- tags: {', '.join(entry.tags)}")
        if entry.summary:
            entry_lines.append(f"- summary: {entry.summary}")
        snippet = _snippet_for_query(entry, query)
        if snippet:
            entry_lines.append(f"- snippet: {snippet}")
        entry_lines.append("")
        projected = "\n".join([*lines, *entry_lines]).strip()
        if len(projected) > MAX_MEMORY_SEARCH_INJECTED_CHARS:
            continue
        lines.extend(entry_lines)
        accepted += 1
    omitted = max(0, len(entries) - accepted)
    if omitted > 0:
        lines.extend(
            [
                f"[...omitted {omitted} additional memory hit(s) for prompt budget...]",
                "",
            ],
        )
    return "\n".join(lines).strip()


def render_memory_get_result(
    entry: MemoryEntry | None,
    *,
    entry_id: str,
) -> str:
    lines = [
        "# Memory Entry",
        "",
        f"Requested entry_id: {entry_id}",
        "",
    ]
    if entry is None:
        lines.append("No durable memory entry was found for this id.")
        return "\n".join(lines).strip()
    lines.extend([f"Title: {entry.title}"])
    citation = memory_citation(entry)
    if citation is not None:
        lines.append(f"Citation: {citation}")
    if entry.summary:
        lines.extend(["", f"Summary: {entry.summary}"])
    lines.extend(["", entry.content])
    return "\n".join(lines).strip()


def memory_citation(entry: MemoryEntry) -> str | None:
    path = entry.metadata.get("memory_file_path")
    if not isinstance(path, str) or not path.strip():
        return None
    line_start = _metadata_int(entry, "memory_file_line_start")
    line_end = _metadata_int(entry, "memory_file_line_end")
    normalized_path = path.strip()
    if line_start is None:
        return normalized_path
    if line_end is None or line_end <= line_start:
        return f"{normalized_path}:L{line_start}"
    return f"{normalized_path}:L{line_start}-L{line_end}"


def _require_agent_id(arguments: dict[str, Any]) -> str:
    agent_id = str(arguments.get(_MEMORY_AGENT_ID_ARGUMENT, "")).strip()
    if not agent_id:
        raise ValueError("memory lookup tools require an agent context.")
    return agent_id


def _metadata_int(entry: MemoryEntry, key: str) -> int | None:
    value = entry.metadata.get(key)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _snippet_for_query(entry: MemoryEntry, query: str) -> str | None:
    candidates = [entry.summary, entry.content]
    query_tokens = [
        token
        for token in re.findall(r"[A-Za-z0-9_:-]+", query.casefold())
        if len(token) >= 3
    ]
    for source in candidates:
        snippet = _extract_snippet(source, query_tokens)
        if snippet:
            return snippet
    return None


def _extract_snippet(text: str, query_tokens: list[str]) -> str | None:
    normalized = text.strip()
    if not normalized:
        return None
    compact = " ".join(normalized.split())
    if not compact:
        return None
    lower = compact.casefold()
    match_index = next((lower.find(token) for token in query_tokens if token in lower), -1)
    if match_index < 0:
        if len(compact) <= 160:
            return compact
        return f"{compact[:157].rstrip()}..."
    start = max(match_index - 60, 0)
    end = min(match_index + 120, len(compact))
    snippet = compact[start:end].strip()
    if start > 0:
        snippet = f"...{snippet}"
    if end < len(compact):
        snippet = f"{snippet}..."
    return snippet
