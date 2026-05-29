from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from os import stat_result


DEFAULT_WORKSPACE_BOOTSTRAP_FILE_GROUPS = (
    ("AGENT.md", "AGENTS.md"),
    ("SOUL.md",),
    ("TOOLS.md",),
    ("IDENTITY.md",),
    ("USER.md",),
    ("BOOTSTRAP.md",),
)
MAX_WORKSPACE_BOOTSTRAP_BYTES = 2 * 1024 * 1024
MAX_WORKSPACE_BOOTSTRAP_CHARS = 20_000
MAX_WORKSPACE_BOOTSTRAP_TOTAL_CHARS = 80_000


@dataclass(frozen=True, slots=True)
class PromptContextFile:
    path: str
    content: str


@dataclass(frozen=True, slots=True)
class _LoadedBootstrapFile:
    context_file: PromptContextFile
    resolved_path: Path


@dataclass(frozen=True, slots=True)
class _CachedWorkspaceFile:
    identity: str
    content: str


_WORKSPACE_FILE_CACHE: dict[str, _CachedWorkspaceFile] = {}


def load_workspace_context_files(
    workspace_dir: str | None,
) -> tuple[PromptContextFile, ...]:
    root = _resolve_workspace_root(workspace_dir)
    if root is None:
        return ()
    context_files: list[PromptContextFile] = []
    seen_paths: set[Path] = set()
    remaining_budget = MAX_WORKSPACE_BOOTSTRAP_TOTAL_CHARS
    for candidate_names in DEFAULT_WORKSPACE_BOOTSTRAP_FILE_GROUPS:
        if remaining_budget <= 0:
            break
        bootstrap_file = None
        for relative_name in candidate_names:
            loaded_file = _load_bootstrap_file(
                root=root,
                relative_name=relative_name,
            )
            if loaded_file is not None:
                break
        if loaded_file is None:
            continue
        bootstrap_file = loaded_file.context_file
        if loaded_file.resolved_path in seen_paths:
            continue
        seen_paths.add(loaded_file.resolved_path)
        if len(bootstrap_file.content) > remaining_budget:
            bootstrap_file = PromptContextFile(
                path=bootstrap_file.path,
                content=_truncate_content(
                    bootstrap_file.content,
                    path=bootstrap_file.path,
                    max_chars=remaining_budget,
                ),
            )
        if not bootstrap_file.content.strip():
            continue
        context_files.append(bootstrap_file)
        remaining_budget = max(0, remaining_budget - len(bootstrap_file.content))
    return tuple(context_files)


def _resolve_workspace_root(workspace_dir: str | None) -> Path | None:
    if workspace_dir is None or not workspace_dir.strip():
        return None
    try:
        root = Path(workspace_dir).expanduser().resolve(strict=True)
    except OSError:
        return None
    if not root.is_dir():
        return None
    return root


def _load_bootstrap_file(*, root: Path, relative_name: str) -> _LoadedBootstrapFile | None:
    candidate = root / relative_name
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None
    if not _is_within_root(root=root, target=resolved):
        return None
    try:
        if not resolved.is_file():
            return None
        stat = resolved.stat()
        if stat.st_size > MAX_WORKSPACE_BOOTSTRAP_BYTES:
            return None
        content = _read_cached_workspace_content(
            resolved=resolved,
            stat=stat,
        )
    except (OSError, UnicodeDecodeError):
        return None
    if not content:
        return None
    return _LoadedBootstrapFile(
        context_file=PromptContextFile(
            path=relative_name,
            content=_truncate_content(
                content,
                path=relative_name,
                max_chars=MAX_WORKSPACE_BOOTSTRAP_CHARS,
            ),
        ),
        resolved_path=resolved,
    )


def _is_within_root(*, root: Path, target: Path) -> bool:
    try:
        target.relative_to(root)
    except ValueError:
        return False
    return True


def _truncate_content(content: str, *, path: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(content) <= max_chars:
        return content
    marker = f"\n\n[...truncated, read {path} for full content...]\n"
    if len(marker) >= max_chars:
        return marker[:max_chars]
    head_budget = max(1, max_chars - len(marker))
    return f"{content[:head_budget].rstrip()}{marker}"


def _read_cached_workspace_content(*, resolved: Path, stat: stat_result) -> str:
    cache_key = str(resolved)
    identity = _workspace_file_identity(resolved=resolved, stat=stat)
    cached = _WORKSPACE_FILE_CACHE.get(cache_key)
    if cached is not None and cached.identity == identity:
        return cached.content
    content = resolved.read_text(encoding="utf-8").strip()
    _WORKSPACE_FILE_CACHE[cache_key] = _CachedWorkspaceFile(
        identity=identity,
        content=content,
    )
    return content


def _workspace_file_identity(*, resolved: Path, stat: stat_result) -> str:
    return (
        f"{resolved}:{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}"
    )
