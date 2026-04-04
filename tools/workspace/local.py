from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult
from tools.workspace.fs_safe import (
    DEFAULT_WORKSPACE_LIST_LIMIT,
    DEFAULT_WORKSPACE_SEARCH_LIMIT,
    DEFAULT_WORKSPACE_READ_LINE_LIMIT,
    WorkspaceListEntry,
    WorkspacePathListing,
    WorkspaceSearchMatch,
    WorkspaceTextSearch,
    WorkspaceTextEdit,
    WorkspaceTextRead,
    WorkspaceTextWrite,
    list_workspace_path,
    read_text_file_within_workspace,
    search_text_within_workspace,
    replace_text_within_workspace,
    write_text_file_within_workspace,
)
from tools.workspace.patching import (
    WorkspaceApplyPatchResult,
    apply_workspace_patch,
)


WORKSPACE_LIST_TOOL_ID = "workspace_list"
WORKSPACE_SEARCH_TOOL_ID = "workspace_search"
WORKSPACE_READ_TOOL_ID = "read"
WORKSPACE_WRITE_TOOL_ID = "write"
WORKSPACE_EDIT_TOOL_ID = "edit"
WORKSPACE_APPLY_PATCH_TOOL_ID = "apply_patch"
MAX_RENDERED_LINE_CHARS = 240
_SESSION_KEY_ATTR = "session_key"
_WORKSPACE_DIR_ATTR = "workspace_dir"


class WorkspaceToolWorkspaceResolver(Protocol):
    def resolve(self, execution_context: ToolExecutionContext | None) -> str | None:
        ...


@dataclass(frozen=True, slots=True)
class SessionBoundWorkspaceResolver:
    session_workspace_lookup: Callable[[str], str | None]
    allow_execution_context_fallback: bool = True

    def resolve(self, execution_context: ToolExecutionContext | None) -> str | None:
        if execution_context is None:
            return None
        session_key = execution_context.get_str(_SESSION_KEY_ATTR)
        if session_key is not None:
            return self.session_workspace_lookup(session_key)
        if not self.allow_execution_context_fallback:
            return None
        return execution_context.get_str(_WORKSPACE_DIR_ATTR)


@dataclass(frozen=True, slots=True)
class RenderedWorkspaceRead:
    content: str
    rendered_end_line: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class RenderedWorkspaceList:
    content: str


@dataclass(frozen=True, slots=True)
class RenderedWorkspaceSearch:
    content: str


@dataclass(frozen=True, slots=True)
class RenderedWorkspaceWrite:
    content: str


@dataclass(frozen=True, slots=True)
class RenderedWorkspaceEdit:
    content: str


@dataclass(frozen=True, slots=True)
class RenderedWorkspaceApplyPatch:
    content: str


def workspace_list(container: Any):
    session_workspace_lookup = getattr(container, "session_workspace_lookup", None)
    if session_workspace_lookup is None:
        return None
    workspace_resolver = SessionBoundWorkspaceResolver(
        session_workspace_lookup=session_workspace_lookup,
    )

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        path = _coerce_optional_path(arguments, keys=("path", "directory", "dir"))
        limit = _coerce_positive_int(
            arguments,
            keys=("limit", "max_entries", "maxEntries"),
            default=DEFAULT_WORKSPACE_LIST_LIMIT,
            label="workspace_list limit",
        )
        workspace_dir = workspace_resolver.resolve(execution_context)
        listing = list_workspace_path(
            workspace_dir=workspace_dir,
            relative_path=path,
            limit=limit if limit is not None else DEFAULT_WORKSPACE_LIST_LIMIT,
        )
        rendered = render_workspace_list_result(listing)
        return ToolRunResult.text(
            rendered.content,
            metadata={
                "tool": WORKSPACE_LIST_TOOL_ID,
                "workspace_dir": listing.workspace_root,
                "listed_path": listing.listed_path,
                "listed_type": listing.listed_type,
                "entry_count": len(listing.entries),
                "entries": [
                    {
                        "path": entry.path,
                        "absolute_path": entry.absolute_path,
                        "entry_type": entry.entry_type,
                        "size_bytes": entry.size_bytes,
                    }
                    for entry in listing.entries
                ],
            },
        )

    return handler


def workspace_search(container: Any):
    session_workspace_lookup = getattr(container, "session_workspace_lookup", None)
    if session_workspace_lookup is None:
        return None
    workspace_resolver = SessionBoundWorkspaceResolver(
        session_workspace_lookup=session_workspace_lookup,
    )

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        query = _coerce_text_argument(
            arguments,
            keys=("query", "pattern", "text"),
            label="query",
            allow_empty=False,
        )
        limit = _coerce_positive_int(
            arguments,
            keys=("limit", "max_results", "maxResults"),
            default=DEFAULT_WORKSPACE_SEARCH_LIMIT,
            label="workspace_search limit",
        )
        path = _coerce_optional_path(arguments, keys=("path", "directory", "dir"))
        workspace_dir = workspace_resolver.resolve(execution_context)
        search_result = search_text_within_workspace(
            workspace_dir=workspace_dir,
            query=query,
            limit=limit if limit is not None else DEFAULT_WORKSPACE_SEARCH_LIMIT,
            relative_path=path,
        )
        rendered = render_workspace_search_result(search_result)
        return ToolRunResult.text(
            rendered.content,
            metadata={
                "tool": WORKSPACE_SEARCH_TOOL_ID,
                "workspace_dir": search_result.workspace_root,
                "search_root": search_result.search_root,
                "query": search_result.query,
                "result_count": len(search_result.matches),
                "scanned_file_count": search_result.scanned_file_count,
                "results": [
                    {
                        "path": match.path,
                        "absolute_path": match.absolute_path,
                        "line_number": match.line_number,
                        "column_number": match.column_number,
                        "line_text": match.line_text,
                    }
                    for match in search_result.matches
                ],
            },
        )

    return handler


def read(container: Any):
    session_workspace_lookup = getattr(container, "session_workspace_lookup", None)
    if session_workspace_lookup is None:
        return None
    workspace_resolver = SessionBoundWorkspaceResolver(
        session_workspace_lookup=session_workspace_lookup,
    )

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        path = _coerce_path(arguments)
        offset = _coerce_positive_int(
            arguments,
            keys=("offset", "start_line", "from_line", "from"),
            default=1,
            label="read offset",
        )
        limit = _coerce_positive_int(
            arguments,
            keys=("limit", "line_count", "lines"),
            default=None,
            label="read limit",
        )
        workspace_dir = workspace_resolver.resolve(execution_context)
        read_result = read_text_file_within_workspace(
            workspace_dir=workspace_dir,
            relative_path=path,
            offset=offset,
            limit=limit if limit is not None else DEFAULT_WORKSPACE_READ_LINE_LIMIT,
        )
        rendered = render_workspace_read_result(read_result)
        return ToolRunResult.text(
            rendered.content,
            metadata={
                "tool": WORKSPACE_READ_TOOL_ID,
                "workspace_dir": read_result.workspace_root,
                "path": read_result.relative_path,
                "absolute_path": read_result.absolute_path,
                "start_line": read_result.start_line,
                "end_line": rendered.rendered_end_line,
                "total_lines": read_result.total_lines,
                "truncated": rendered.truncated,
            },
        )

    return handler


def write(container: Any):
    session_workspace_lookup = getattr(container, "session_workspace_lookup", None)
    if session_workspace_lookup is None:
        return None
    workspace_resolver = SessionBoundWorkspaceResolver(
        session_workspace_lookup=session_workspace_lookup,
    )

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        path = _coerce_path(arguments)
        content = _coerce_content(arguments)
        workspace_dir = workspace_resolver.resolve(execution_context)
        write_result = write_text_file_within_workspace(
            workspace_dir=workspace_dir,
            relative_path=path,
            content=content,
        )
        rendered = render_workspace_write_result(write_result)
        return ToolRunResult.text(
            rendered.content,
            metadata={
                "tool": WORKSPACE_WRITE_TOOL_ID,
                "workspace_dir": write_result.workspace_root,
                "path": write_result.relative_path,
                "absolute_path": write_result.absolute_path,
                "bytes_written": write_result.bytes_written,
                "existed_before": write_result.existed_before,
            },
        )

    return handler


def edit(container: Any):
    session_workspace_lookup = getattr(container, "session_workspace_lookup", None)
    if session_workspace_lookup is None:
        return None
    workspace_resolver = SessionBoundWorkspaceResolver(
        session_workspace_lookup=session_workspace_lookup,
    )

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        path = _coerce_path(arguments)
        old_text = _coerce_text_argument(
            arguments,
            keys=("oldText", "old_text", "oldString", "old_string"),
            label="oldText",
            allow_empty=False,
        )
        new_text = _coerce_text_argument(
            arguments,
            keys=("newText", "new_text", "newString", "new_string"),
            label="newText",
            allow_empty=True,
        )
        workspace_dir = workspace_resolver.resolve(execution_context)
        edit_result = replace_text_within_workspace(
            workspace_dir=workspace_dir,
            relative_path=path,
            old_text=old_text,
            new_text=new_text,
        )
        rendered = render_workspace_edit_result(edit_result)
        return ToolRunResult.text(
            rendered.content,
            metadata={
                "tool": WORKSPACE_EDIT_TOOL_ID,
                "workspace_dir": edit_result.workspace_root,
                "path": edit_result.relative_path,
                "absolute_path": edit_result.absolute_path,
                "bytes_written": edit_result.bytes_written,
                "start_line": edit_result.start_line,
                "end_line": edit_result.end_line,
                "replacement_count": edit_result.replacement_count,
            },
        )

    return handler


def apply_patch(container: Any):
    session_workspace_lookup = getattr(container, "session_workspace_lookup", None)
    if session_workspace_lookup is None:
        return None
    workspace_resolver = SessionBoundWorkspaceResolver(
        session_workspace_lookup=session_workspace_lookup,
    )

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        patch_input = _coerce_text_argument(
            arguments,
            keys=("input", "patch"),
            label="input",
            allow_empty=False,
        )
        workspace_dir = workspace_resolver.resolve(execution_context)
        patch_result = apply_workspace_patch(
            workspace_dir=workspace_dir,
            patch_text=patch_input,
        )
        rendered = render_workspace_apply_patch_result(patch_result)
        return ToolRunResult.text(
            rendered.content,
            metadata={
                "tool": WORKSPACE_APPLY_PATCH_TOOL_ID,
                "workspace_dir": patch_result.workspace_root,
                "added_files": list(patch_result.added_files),
                "modified_files": list(patch_result.modified_files),
                "deleted_files": list(patch_result.deleted_files),
            },
        )

    return handler


def render_workspace_read_result(read: WorkspaceTextRead) -> RenderedWorkspaceRead:
    header = [
        "# Workspace File Read",
        "",
        f"- path: {read.relative_path}",
        (
            f"- lines: {read.start_line}-{read.end_line} of {read.total_lines}"
            if read.total_lines
            else "- lines: 0 of 0"
        ),
    ]
    if not read.lines:
        header.extend(
            [
                "",
                "The file is empty.",
            ],
        )
        return RenderedWorkspaceRead(
            content="\n".join(header).strip(),
            rendered_end_line=read.end_line,
            truncated=False,
        )

    body: list[str] = ["", "```text"]
    rendered_end_line = read.start_line - 1
    truncated = False
    for line_number, raw_line in enumerate(read.lines, start=read.start_line):
        line = raw_line
        if len(line) > MAX_RENDERED_LINE_CHARS:
            line = f"{line[: MAX_RENDERED_LINE_CHARS - 20].rstrip()} ... [line truncated]"
            truncated = True
        body.append(f"{line_number:>6} | {line}")
        rendered_end_line = line_number
    body.append("```")
    if read.end_line < read.total_lines:
        truncated = True
    if truncated and rendered_end_line < read.total_lines:
        body.extend(
            [
                "",
                (
                    f"[...truncated; call read again with offset {rendered_end_line + 1} "
                    f"to continue from {read.relative_path}...]"
                ),
            ],
        )
    return RenderedWorkspaceRead(
        content="\n".join(header + body).strip(),
        rendered_end_line=rendered_end_line,
        truncated=truncated,
    )


def render_workspace_list_result(
    listing: WorkspacePathListing,
) -> RenderedWorkspaceList:
    lines = [
        "# Workspace Path Listing",
        "",
        f"Listed path: {listing.listed_path or '.'}",
        f"Type: {listing.listed_type}",
        f"Entries: {len(listing.entries)}",
        "",
    ]
    if not listing.entries:
        lines.append("No entries were found.")
        return RenderedWorkspaceList(content="\n".join(lines).strip())
    for index, entry in enumerate(listing.entries, start=1):
        lines.extend(_render_workspace_list_entry(index=index, entry=entry))
    return RenderedWorkspaceList(content="\n".join(lines).strip())


def render_workspace_search_result(
    result: WorkspaceTextSearch,
) -> RenderedWorkspaceSearch:
    lines = [
        "# Workspace Search Results",
        "",
        f"Query: {result.query}",
    ]
    if result.search_root is not None:
        lines.append(f"Search root: {result.search_root}")
    lines.extend(
        [
            f"Scanned files: {result.scanned_file_count}",
            f"Matches: {len(result.matches)}",
            "",
        ],
    )
    if not result.matches:
        lines.append("No workspace files matched this query.")
        return RenderedWorkspaceSearch(content="\n".join(lines).strip())
    lines.append("Use read with the matching path and nearby line numbers for more context.")
    lines.append("")
    for index, match in enumerate(result.matches, start=1):
        lines.extend(_render_workspace_search_match(index=index, match=match))
    return RenderedWorkspaceSearch(content="\n".join(lines).strip())


def render_workspace_write_result(write: WorkspaceTextWrite) -> RenderedWorkspaceWrite:
    action = "updated" if write.existed_before else "created"
    return RenderedWorkspaceWrite(
        content="\n".join(
            [
                "# Workspace File Write",
                "",
                f"- path: {write.relative_path}",
                f"- status: {action}",
                f"- bytes_written: {write.bytes_written}",
            ],
        ).strip(),
    )


def render_workspace_edit_result(edit: WorkspaceTextEdit) -> RenderedWorkspaceEdit:
    return RenderedWorkspaceEdit(
        content="\n".join(
            [
                "# Workspace File Edit",
                "",
                f"- path: {edit.relative_path}",
                f"- lines: {edit.start_line}-{edit.end_line}",
                f"- replacements: {edit.replacement_count}",
                f"- bytes_written: {edit.bytes_written}",
            ],
        ).strip(),
    )


def render_workspace_apply_patch_result(
    result: WorkspaceApplyPatchResult,
) -> RenderedWorkspaceApplyPatch:
    lines = [
        "# Workspace Apply Patch",
        "",
    ]
    if result.added_files:
        lines.append(f"- added: {', '.join(result.added_files)}")
    if result.modified_files:
        lines.append(f"- modified: {', '.join(result.modified_files)}")
    if result.deleted_files:
        lines.append(f"- deleted: {', '.join(result.deleted_files)}")
    return RenderedWorkspaceApplyPatch(content="\n".join(lines).strip())


def _render_workspace_search_match(
    *,
    index: int,
    match: WorkspaceSearchMatch,
) -> list[str]:
    line_text = match.line_text
    if len(line_text) > MAX_RENDERED_LINE_CHARS:
        line_text = f"{line_text[: MAX_RENDERED_LINE_CHARS - 20].rstrip()} ... [line truncated]"
    return [
        f"## Result {index}",
        f"- path: {match.path}",
        f"- line: {match.line_number}",
        f"- column: {match.column_number}",
        f"- snippet: {line_text}",
        "",
    ]


def _render_workspace_list_entry(
    *,
    index: int,
    entry: WorkspaceListEntry,
) -> list[str]:
    lines = [
        f"## Entry {index}",
        f"- path: {entry.path}",
        f"- type: {entry.entry_type}",
    ]
    if entry.size_bytes is not None:
        lines.append(f"- size_bytes: {entry.size_bytes}")
    lines.append("")
    return lines


def _coerce_path(arguments: dict[str, Any]) -> str:
    for key in ("path", "file_path", "filePath", "file"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError("workspace file tools require a non-empty path.")


def _coerce_optional_path(
    arguments: dict[str, Any],
    *,
    keys: tuple[str, ...],
) -> str | None:
    for key in keys:
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _coerce_content(arguments: dict[str, Any]) -> str:
    return _coerce_text_argument(
        arguments,
        keys=("content", "text"),
        label="content",
        allow_empty=True,
    )


def _coerce_text_argument(
    arguments: dict[str, Any],
    *,
    keys: tuple[str, ...],
    label: str,
    allow_empty: bool,
) -> str:
    for key in keys:
        if key not in arguments:
            continue
        value = arguments[key]
        if isinstance(value, str):
            if value or allow_empty:
                return value
            raise ValueError(f"{label} must be a non-empty string.")
        if isinstance(value, dict):
            text = value.get("text")
            if not isinstance(text, str):
                raise ValueError(f"{label} text content blocks require a text field.")
            if text or allow_empty:
                return text
            raise ValueError(f"{label} must be a non-empty string.")
        if isinstance(value, list):
            fragments: list[str] = []
            for item in value:
                if not isinstance(item, dict):
                    raise ValueError(f"{label} content blocks must be mappings.")
                block_type = str(item.get("type", "text")).strip() or "text"
                if block_type != "text":
                    raise ValueError(f"{label} only supports text content blocks.")
                text = item.get("text")
                if not isinstance(text, str):
                    raise ValueError(f"{label} text content blocks require a text field.")
                fragments.append(text)
            joined = "".join(fragments)
            if joined or allow_empty:
                return joined
            raise ValueError(f"{label} must be a non-empty string.")
        raise ValueError(f"{label} must be a string or text content block list.")
    raise ValueError(f"{label} is required.")


def _coerce_positive_int(
    arguments: dict[str, Any],
    *,
    keys: tuple[str, ...],
    default: int | None,
    label: str,
) -> int | None:
    raw_value = None
    for key in keys:
        if key in arguments and arguments[key] is not None:
            raw_value = arguments[key]
            break
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer.") from exc
    if value < 1:
        raise ValueError(f"{label} must be at least 1.")
    return value
