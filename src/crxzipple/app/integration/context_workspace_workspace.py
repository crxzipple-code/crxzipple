"""Workspace bootstrap context tree adapter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from crxzipple.modules.context_workspace.application import ContextChildrenRequest
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextEstimate,
    ContextNodeSeed,
    ContextNodeState,
)


class WorkspaceContextNodeProvider:
    owner = "workspace"

    def children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        if request.node.id != "workspace.bootstrap":
            return ()
        workspace_dir = _optional_text(request.workspace.metadata.get("workspace_dir"))
        root = _workspace_root(workspace_dir)
        if root is None:
            return ()
        files = _load_bootstrap_files(root)
        return tuple(
            _workspace_file_node_seed(
                file,
                parent_id=request.node.id,
                display_order=index * 10,
            )
            for index, file in enumerate(files, start=1)
        )


@dataclass(frozen=True, slots=True)
class _WorkspaceBootstrapFile:
    path: str
    content: str
    truncated: bool


_BOOTSTRAP_FILENAMES = (
    "AGENTS.md",
    "AGENT.md",
    "SOUL.md",
    "TOOLS.md",
    "IDENTITY.md",
    "USER.md",
    "BOOTSTRAP.md",
)
_MAX_FILE_BYTES = 2_000_000
_MAX_FILE_CHARS = 20_000
_TOTAL_CHAR_BUDGET = 80_000
_FILE_ACTIONS = (
    ContextAction.PIN,
    ContextAction.UNPIN,
    ContextAction.ESTIMATE,
)


def _load_bootstrap_files(root: Path) -> tuple[_WorkspaceBootstrapFile, ...]:
    files: list[_WorkspaceBootstrapFile] = []
    remaining_chars = _TOTAL_CHAR_BUDGET
    for name in _BOOTSTRAP_FILENAMES:
        if remaining_chars <= 0:
            break
        candidate = (root / name).resolve()
        if not _safe_workspace_file(candidate, root=root):
            continue
        try:
            size = candidate.stat().st_size
        except OSError:
            continue
        if size > _MAX_FILE_BYTES:
            continue
        try:
            content = candidate.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
        except OSError:
            continue
        limit = min(_MAX_FILE_CHARS, remaining_chars)
        truncated = len(content) > limit
        content = content[:limit]
        remaining_chars -= len(content)
        files.append(
            _WorkspaceBootstrapFile(
                path=candidate.relative_to(root).as_posix(),
                content=content,
                truncated=truncated,
            ),
        )
    return tuple(files)


def _workspace_file_node_seed(
    file: _WorkspaceBootstrapFile,
    *,
    parent_id: str,
    display_order: int,
) -> ContextNodeSeed:
    content = file.content.strip()
    summary = _truncate(content, 1600)
    return ContextNodeSeed(
        node_id=f"workspace.file.{_node_token(file.path)}",
        parent_id=parent_id,
        owner="workspace",
        kind="workspace_file",
        title=file.path,
        summary=summary,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=_FILE_ACTIONS,
        owner_ref={"path": file.path},
        estimate=_text_estimate(content),
        display_order=display_order,
        metadata={
            "path": file.path,
            "content_chars": len(content),
            "truncated": file.truncated,
            "source": "workspace.bootstrap",
        },
    )


def _workspace_root(workspace_dir: str | None) -> Path | None:
    if workspace_dir is None:
        return None
    try:
        root = Path(workspace_dir).expanduser().resolve(strict=True)
    except OSError:
        return None
    return root if root.is_dir() else None


def _safe_workspace_file(path: Path, *, root: Path) -> bool:
    try:
        if not path.is_relative_to(root):
            return False
    except ValueError:
        return False
    return path.is_file()


def _text_estimate(text: str) -> ContextEstimate:
    normalized = text or ""
    return ContextEstimate(
        text_chars=len(normalized),
        text_tokens=max((len(normalized) + 3) // 4, 1) if normalized else 0,
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _node_token(value: str) -> str:
    return quote(value.strip(), safe="")


def _truncate(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + "..."


__all__ = ["WorkspaceContextNodeProvider"]
