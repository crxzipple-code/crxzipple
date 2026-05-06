from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Protocol

from crxzipple.modules.memory.application import MemorySearchHit, MemoryUseContext
from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult

if TYPE_CHECKING:
    from crxzipple.modules.memory.application import FileBackedMemoryService


MEMORY_SEARCH_TOOL_ID = "memory_search"
MEMORY_READ_TOOL_ID = "memory_read"
MEMORY_WRITE_DAILY_TOOL_ID = "memory_write_daily"
MEMORY_FLUSH_SKIP_TOOL_ID = "memory_flush_skip"
DEFAULT_MEMORY_SEARCH_LIMIT = 6
MAX_MEMORY_SEARCH_INJECTED_CHARS = 4_000
_AGENT_ID_ATTR = "agent_id"


class MemoryToolContextResolver(Protocol):
    def resolve(self, space_ref: str | None) -> MemoryUseContext | None:
        ...


def _resolve_memory_dependencies(
    container: Any,
) -> tuple[FileBackedMemoryService, MemoryToolContextResolver] | None:
    memory_service = getattr(container, "file_memory_service", None)
    memory_context_resolver = getattr(container, "memory_context_resolver", None)
    if memory_service is None or memory_context_resolver is None:
        return None
    return memory_service, memory_context_resolver


def _resolve_tool_context(
    execution_context: ToolExecutionContext | None,
    *,
    context_resolver: MemoryToolContextResolver,
) -> MemoryUseContext:
    if execution_context is None:
        raise ValueError("Memory tool context is unavailable for this run.")
    agent_id = execution_context.get_str(_AGENT_ID_ATTR)
    context = context_resolver.resolve(agent_id)
    if context is None:
        raise ValueError("Memory tool context is unavailable for this run.")
    return context


def memory_search(container: Any):
    dependencies = _resolve_memory_dependencies(container)
    if dependencies is None:
        return None
    memory_service, context_resolver = dependencies

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        context = _resolve_tool_context(
            execution_context,
            context_resolver=context_resolver,
        )
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ValueError("memory_search requires a non-empty query.")
        raw_limit = arguments.get("limit")
        try:
            limit = (
                int(raw_limit) if raw_limit is not None else DEFAULT_MEMORY_SEARCH_LIMIT
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("memory_search limit must be an integer.") from exc
        limit = min(max(limit, 1), DEFAULT_MEMORY_SEARCH_LIMIT)
        hits = memory_service.search(context=context, query=query, limit=limit)
        return ToolRunResult.text(
            render_memory_search_result(query=query, hits=tuple(hits)),
            metadata={
                "tool": MEMORY_SEARCH_TOOL_ID,
                "space_id": context.space_id,
                "query": query,
                "result_count": len(hits),
                "results": [
                    {
                        "path": hit.path,
                        "start_line": hit.start_line,
                        "end_line": hit.end_line,
                        "kind": hit.kind,
                        "citation": memory_citation(hit.path, hit.start_line, hit.end_line),
                    }
                    for hit in hits
                ],
            },
        )

    return handler


def memory_read(container: Any):
    dependencies = _resolve_memory_dependencies(container)
    if dependencies is None:
        return None
    memory_service, context_resolver = dependencies

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        context = _resolve_tool_context(
            execution_context,
            context_resolver=context_resolver,
        )
        citation = str(arguments.get("citation", "")).strip()
        if not citation:
            raise ValueError("memory_read requires a citation.")
        path, start_line, end_line = _parse_memory_citation(citation)
        excerpt = memory_service.get(
            context=context,
            path=path,
            start_line=start_line,
            line_count=(end_line - start_line + 1) if end_line is not None else None,
        )
        return ToolRunResult.text(
            render_memory_read_result(
                excerpt,
                citation=citation,
            ),
            metadata={
                "tool": MEMORY_READ_TOOL_ID,
                "space_id": context.space_id,
                "citation": citation,
                "found": excerpt is not None,
            },
        )

    return handler


def memory_write_daily(container: Any):
    dependencies = _resolve_memory_dependencies(container)
    if dependencies is None:
        return None
    memory_service, context_resolver = dependencies

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        context = _resolve_tool_context(
            execution_context,
            context_resolver=context_resolver,
        )
        content = str(arguments.get("content", "")).strip()
        if not content:
            raise ValueError("memory_write_daily requires non-empty content.")
        write_result = memory_service.append_daily(
            context=context,
            content=content,
        )
        payload = {
            "status": "written",
            "path": write_result.path,
            "line_start": write_result.line_start,
            "line_end": write_result.line_end,
            "kind": write_result.kind,
        }
        return ToolRunResult.text(
            (
                f"Memory note written to {write_result.path} "
                f"at lines {write_result.line_start}-{write_result.line_end}."
            ),
            details=payload,
            metadata={
                "tool": MEMORY_WRITE_DAILY_TOOL_ID,
                "space_id": context.space_id,
                **payload,
            },
        )

    return handler


def memory_flush_skip(container: Any):
    dependencies = _resolve_memory_dependencies(container)
    if dependencies is None:
        return None
    _, context_resolver = dependencies

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        context = _resolve_tool_context(
            execution_context,
            context_resolver=context_resolver,
        )
        del arguments
        payload = {"status": "skipped"}
        return ToolRunResult.text(
            "Memory flush skipped.",
            details=payload,
            metadata={
                "tool": MEMORY_FLUSH_SKIP_TOOL_ID,
                "space_id": context.space_id,
                **payload,
            },
        )

    return handler


def render_memory_search_result(
    *,
    query: str,
    hits: tuple[MemorySearchHit, ...],
) -> str:
    lines = [
        "# Memory Search Results",
        "",
        f"Query: {query}",
        "",
    ]
    if not hits:
        lines.append("No durable memories matched this query.")
        return "\n".join(lines).strip()
    lines.append("Use memory_read with the citation below if you need more context.")
    lines.append("")
    accepted = 0
    used_chars = 0
    for hit in hits:
        snippet = hit.snippet.strip()
        candidate_chars = used_chars + len(snippet)
        if accepted > 0 and candidate_chars > MAX_MEMORY_SEARCH_INJECTED_CHARS:
            break
        citation = memory_citation(hit.path, hit.start_line, hit.end_line)
        lines.extend(
            [
                f"## Result {accepted + 1}",
                f"- path: {hit.path}",
                f"- citation: {citation}",
                f"- kind: {hit.kind}",
                f"- score: {hit.score:.3f}",
                f"- snippet: {snippet}",
                "",
            ],
        )
        accepted += 1
        used_chars = candidate_chars
    return "\n".join(lines).strip()


def render_memory_read_result(
    excerpt: object | None,
    *,
    citation: str,
) -> str:
    lines = [
        "# Memory Excerpt",
        "",
        f"Requested citation: {citation}",
        "",
    ]
    if excerpt is None:
        lines.append("No memory excerpt was found for the requested citation.")
        return "\n".join(lines).strip()
    lines.extend(
        [
            f"Citation: {memory_citation(excerpt.path, excerpt.start_line, excerpt.end_line)}",
            f"Path: {excerpt.path}",
            f"Kind: {excerpt.kind}",
            "",
            excerpt.text.strip() or "(empty excerpt)",
        ],
    )
    return "\n".join(lines).strip()


def memory_citation(path: str, start_line: int, end_line: int) -> str:
    if end_line <= start_line:
        return f"{path}:{start_line}"
    return f"{path}:{start_line}-{end_line}"


def _parse_memory_citation(citation: str) -> tuple[str, int, int]:
    normalized = citation.strip()
    match = re.fullmatch(r"(.+):(\d+)(?:-(\d+))?", normalized)
    if match is None:
        raise ValueError("memory_read citation must look like path:start or path:start-end.")
    path = match.group(1).strip()
    start_line = int(match.group(2))
    end_group = match.group(3)
    end_line = int(end_group) if end_group is not None else start_line
    if end_line < start_line:
        raise ValueError(
            "memory_read citation end line must be greater than or equal to start line.",
        )
    return path, start_line, end_line
