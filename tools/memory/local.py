from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.memory.application import (
    MemoryActorContext,
    MemoryRecallRequest,
    MemoryRememberRequest,
    MemoryRuntimeService,
    MemorySearchHit,
    memory_citation,
)
from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult

MEMORY_SEARCH_TOOL_ID = "memory_search"
MEMORY_READ_TOOL_ID = "memory_read"
MEMORY_WRITE_DAILY_TOOL_ID = "memory_write_daily"
MEMORY_FLUSH_SKIP_TOOL_ID = "memory_flush_skip"
DEFAULT_MEMORY_SEARCH_LIMIT = 6
MAX_MEMORY_SEARCH_INJECTED_CHARS = 4_000


@dataclass(frozen=True, slots=True)
class MemoryToolDeps:
    memory_runtime_service: MemoryRuntimeService = field(
        metadata={"dependency_id": "memory_runtime_service"},
    )


def _resolve_memory_dependencies(
    deps: MemoryToolDeps | Any,
) -> MemoryRuntimeService | None:
    resolved = _coerce_memory_deps(deps)
    if resolved is None:
        return None
    return resolved.memory_runtime_service


def _coerce_memory_deps(value: MemoryToolDeps | Any) -> MemoryToolDeps | None:
    if isinstance(value, MemoryToolDeps):
        return value
    memory_runtime_service = getattr(value, "memory_runtime_service", None)
    if memory_runtime_service is None:
        return None
    return MemoryToolDeps(
        memory_runtime_service=memory_runtime_service,
    )


def _actor_context(
    execution_context: ToolExecutionContext | None,
) -> MemoryActorContext:
    if execution_context is None:
        raise ValueError("Memory tool context is unavailable for this run.")
    actor = MemoryActorContext.from_attrs(execution_context.attrs)
    if actor.agent_id is None:
        raise ValueError("Memory tool context is unavailable for this run.")
    return actor


def memory_search(deps: MemoryToolDeps | Any):
    memory_runtime_service = _resolve_memory_dependencies(deps)
    if memory_runtime_service is None:
        return None

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        actor = _actor_context(execution_context)
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
        recall = memory_runtime_service.recall(
            MemoryRecallRequest(
                actor=actor,
                query=query,
                max_items=limit,
            ),
        )
        hits = recall.hits
        return ToolRunResult.text(
            render_memory_search_result(query=query, hits=tuple(hits)),
            metadata={
                "tool": MEMORY_SEARCH_TOOL_ID,
                "space_id": recall.scope.context.space_id,
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


def memory_read(deps: MemoryToolDeps | Any):
    memory_runtime_service = _resolve_memory_dependencies(deps)
    if memory_runtime_service is None:
        return None

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        actor = _actor_context(execution_context)
        citation = str(arguments.get("citation", "")).strip()
        if not citation:
            raise ValueError("memory_read requires a citation.")
        recall = memory_runtime_service.recall(
            MemoryRecallRequest(
                actor=actor,
                citation=citation,
                max_items=1,
            ),
        )
        excerpt = recall.excerpt
        return ToolRunResult.text(
            render_memory_read_result(
                excerpt,
                citation=citation,
            ),
            metadata={
                "tool": MEMORY_READ_TOOL_ID,
                "space_id": recall.scope.context.space_id,
                "citation": citation,
                "found": excerpt is not None,
            },
        )

    return handler


def memory_write_daily(deps: MemoryToolDeps | Any):
    memory_runtime_service = _resolve_memory_dependencies(deps)
    if memory_runtime_service is None:
        return None

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        actor = _actor_context(execution_context)
        content = str(arguments.get("content", "")).strip()
        if not content:
            raise ValueError("memory_write_daily requires non-empty content.")
        remember = memory_runtime_service.remember(
            MemoryRememberRequest(
                actor=actor,
                content=content,
                intent="freeform",
                retention="durable",
                metadata={"tool": MEMORY_WRITE_DAILY_TOOL_ID},
            ),
        )
        write_result = remember.write_result
        if write_result is None:
            raise RuntimeError("Memory remember completed without a write result.")
        payload = {
            "status": remember.status,
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
                "space_id": remember.scope.context.space_id,
                **payload,
            },
        )

    return handler


def memory_flush_skip(deps: MemoryToolDeps | Any):
    memory_runtime_service = _resolve_memory_dependencies(deps)
    if memory_runtime_service is None:
        return None

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        plan = memory_runtime_service.resolve_access_plan(
            _actor_context(execution_context),
        )
        del arguments
        payload = {"status": "skipped"}
        return ToolRunResult.text(
            "Memory flush skipped.",
            details=payload,
            metadata={
                "tool": MEMORY_FLUSH_SKIP_TOOL_ID,
                "space_id": plan.scope.context.space_id,
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
