from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


MAX_WORKSPACE_READ_FILE_BYTES = 256 * 1024
MAX_WORKSPACE_WRITE_FILE_BYTES = 256 * 1024
DEFAULT_WORKSPACE_READ_LINE_LIMIT = 120
MAX_WORKSPACE_READ_LINE_LIMIT = 400
DEFAULT_WORKSPACE_LIST_LIMIT = 50
MAX_WORKSPACE_LIST_LIMIT = 200
DEFAULT_WORKSPACE_SEARCH_LIMIT = 20
MAX_WORKSPACE_SEARCH_LIMIT = 100


@dataclass(frozen=True, slots=True)
class WorkspaceTextRead:
    workspace_root: str
    relative_path: str
    absolute_path: str
    start_line: int
    end_line: int
    total_lines: int
    lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkspaceTextWrite:
    workspace_root: str
    relative_path: str
    absolute_path: str
    bytes_written: int
    existed_before: bool


@dataclass(frozen=True, slots=True)
class WorkspaceTextEdit:
    workspace_root: str
    relative_path: str
    absolute_path: str
    bytes_written: int
    start_line: int
    end_line: int
    replacement_count: int


@dataclass(frozen=True, slots=True)
class WorkspaceTextDelete:
    workspace_root: str
    relative_path: str
    absolute_path: str


@dataclass(frozen=True, slots=True)
class WorkspaceLoadedTextFile:
    workspace_root: str
    relative_path: str
    absolute_path: str
    content: str | None
    bytes_read: int


@dataclass(frozen=True, slots=True)
class WorkspaceSearchMatch:
    path: str
    absolute_path: str
    line_number: int
    column_number: int
    line_text: str


@dataclass(frozen=True, slots=True)
class WorkspaceTextSearch:
    workspace_root: str
    search_root: str | None
    query: str
    matches: tuple[WorkspaceSearchMatch, ...]
    scanned_file_count: int


@dataclass(frozen=True, slots=True)
class WorkspaceListEntry:
    path: str
    absolute_path: str
    entry_type: str
    size_bytes: int | None


@dataclass(frozen=True, slots=True)
class WorkspacePathListing:
    workspace_root: str
    listed_path: str | None
    listed_type: str
    entries: tuple[WorkspaceListEntry, ...]


def resolve_workspace_root(workspace_dir: str | None) -> Path:
    if workspace_dir is None or not workspace_dir.strip():
        raise ValueError("A bound workspace is required for workspace file tools.")
    try:
        root = Path(workspace_dir).expanduser().resolve(strict=True)
    except OSError as exc:
        raise ValueError(
            f"Workspace '{workspace_dir}' could not be resolved.",
        ) from exc
    if not root.is_dir():
        raise ValueError(f"Workspace '{workspace_dir}' is not a readable directory.")
    return root


def write_text_file_within_workspace(
    *,
    workspace_dir: str | None,
    relative_path: str,
    content: str,
) -> WorkspaceTextWrite:
    root = resolve_workspace_root(workspace_dir)
    target, normalized_relative, existed_before = resolve_workspace_write_target(
        root=root,
        relative_path=relative_path,
    )
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_WORKSPACE_WRITE_FILE_BYTES:
        raise ValueError(
            f"Workspace file '{normalized_relative}' is too large to write in one call.",
        )
    try:
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            f"Workspace file '{normalized_relative}' could not be written.",
        ) from exc
    return WorkspaceTextWrite(
        workspace_root=str(root),
        relative_path=normalized_relative,
        absolute_path=str(target),
        bytes_written=len(encoded),
        existed_before=existed_before,
    )


def replace_text_within_workspace(
    *,
    workspace_dir: str | None,
    relative_path: str,
    old_text: str,
    new_text: str,
) -> WorkspaceTextEdit:
    if not old_text:
        raise ValueError("workspace edit requires a non-empty oldText.")
    root = resolve_workspace_root(workspace_dir)
    target, normalized_relative = resolve_workspace_file(
        root=root,
        relative_path=relative_path,
    )
    try:
        stat = target.stat()
    except OSError as exc:
        raise ValueError(
            f"Workspace file '{normalized_relative}' could not be accessed.",
        ) from exc
    if not target.is_file():
        raise ValueError(f"Workspace path '{normalized_relative}' is not a readable file.")
    if stat.st_nlink > 1:
        raise ValueError(
            f"Workspace file '{normalized_relative}' is hard-linked and cannot be edited safely.",
        )
    if stat.st_size > MAX_WORKSPACE_WRITE_FILE_BYTES:
        raise ValueError(
            f"Workspace file '{normalized_relative}' is too large to edit in one call.",
        )
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"Workspace file '{normalized_relative}' is not valid UTF-8 text.",
        ) from exc
    except OSError as exc:
        raise ValueError(
            f"Workspace file '{normalized_relative}' could not be read.",
        ) from exc

    occurrence_count = text.count(old_text)
    if occurrence_count < 1:
        raise ValueError(
            f"Workspace file '{normalized_relative}' does not contain the exact text to replace.",
        )
    if occurrence_count > 1:
        raise ValueError(
            f"Workspace file '{normalized_relative}' contains the target text {occurrence_count} times; edit requires exactly one match.",
        )

    match_index = text.index(old_text)
    start_line = text[:match_index].count("\n") + 1
    end_line = start_line + old_text.count("\n")
    updated = text.replace(old_text, new_text, 1)
    encoded = updated.encode("utf-8")
    if len(encoded) > MAX_WORKSPACE_WRITE_FILE_BYTES:
        raise ValueError(
            f"Workspace file '{normalized_relative}' is too large after applying the edit.",
        )
    try:
        target.write_text(updated, encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            f"Workspace file '{normalized_relative}' could not be written.",
        ) from exc

    return WorkspaceTextEdit(
        workspace_root=str(root),
        relative_path=normalized_relative,
        absolute_path=str(target),
        bytes_written=len(encoded),
        start_line=start_line,
        end_line=end_line,
        replacement_count=1,
    )


def delete_text_file_within_workspace(
    *,
    workspace_dir: str | None,
    relative_path: str,
) -> WorkspaceTextDelete:
    root = resolve_workspace_root(workspace_dir)
    target, normalized_relative = resolve_workspace_file(
        root=root,
        relative_path=relative_path,
    )
    try:
        stat = target.stat()
    except OSError as exc:
        raise ValueError(
            f"Workspace file '{normalized_relative}' could not be accessed.",
        ) from exc
    if not target.is_file():
        raise ValueError(f"Workspace path '{normalized_relative}' is not a writable file.")
    if stat.st_nlink > 1:
        raise ValueError(
            f"Workspace file '{normalized_relative}' is hard-linked and cannot be deleted safely.",
        )
    try:
        target.unlink()
    except OSError as exc:
        raise ValueError(
            f"Workspace file '{normalized_relative}' could not be deleted.",
        ) from exc
    return WorkspaceTextDelete(
        workspace_root=str(root),
        relative_path=normalized_relative,
        absolute_path=str(target),
    )


def read_text_file_within_workspace(
    *,
    workspace_dir: str | None,
    relative_path: str,
    offset: int = 1,
    limit: int = DEFAULT_WORKSPACE_READ_LINE_LIMIT,
) -> WorkspaceTextRead:
    root = resolve_workspace_root(workspace_dir)
    target, normalized_relative = resolve_workspace_file(root=root, relative_path=relative_path)
    try:
        stat = target.stat()
    except OSError as exc:
        raise ValueError(f"Workspace file '{normalized_relative}' could not be accessed.") from exc
    if not target.is_file():
        raise ValueError(f"Workspace path '{normalized_relative}' is not a readable file.")
    if stat.st_nlink > 1:
        raise ValueError(
            f"Workspace file '{normalized_relative}' is hard-linked and cannot be read safely.",
        )
    if stat.st_size > MAX_WORKSPACE_READ_FILE_BYTES:
        raise ValueError(
            f"Workspace file '{normalized_relative}' is too large to read in one call.",
        )

    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"Workspace file '{normalized_relative}' is not valid UTF-8 text.",
        ) from exc
    except OSError as exc:
        raise ValueError(f"Workspace file '{normalized_relative}' could not be read.") from exc

    start_line = max(offset, 1)
    line_limit = min(max(limit, 1), MAX_WORKSPACE_READ_LINE_LIMIT)
    all_lines = tuple(text.splitlines())
    total_lines = len(all_lines)

    if total_lines and start_line > total_lines:
        raise ValueError(
            f"Workspace file '{normalized_relative}' has only {total_lines} lines.",
        )

    selected = (
        all_lines[start_line - 1 : start_line - 1 + line_limit]
        if total_lines
        else ()
    )
    end_line = start_line + len(selected) - 1 if selected else 0

    return WorkspaceTextRead(
        workspace_root=str(root),
        relative_path=normalized_relative,
        absolute_path=str(target),
        start_line=start_line,
        end_line=end_line,
        total_lines=total_lines,
        lines=selected,
    )


def load_text_file_from_workspace_root(
    *,
    root: Path,
    relative_path: str,
    max_bytes: int = MAX_WORKSPACE_WRITE_FILE_BYTES,
) -> WorkspaceLoadedTextFile:
    target, normalized_relative = resolve_workspace_file(root=root, relative_path=relative_path)
    try:
        stat = target.stat()
    except OSError as exc:
        raise ValueError(
            f"Workspace file '{normalized_relative}' could not be accessed.",
        ) from exc
    if not target.is_file():
        raise ValueError(f"Workspace path '{normalized_relative}' is not a readable file.")
    if stat.st_nlink > 1:
        raise ValueError(
            f"Workspace file '{normalized_relative}' is hard-linked and cannot be read safely.",
        )
    if stat.st_size > max_bytes:
        raise ValueError(
            f"Workspace file '{normalized_relative}' is too large to read in one call.",
        )
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"Workspace file '{normalized_relative}' is not valid UTF-8 text.",
        ) from exc
    except OSError as exc:
        raise ValueError(
            f"Workspace file '{normalized_relative}' could not be read.",
        ) from exc
    return WorkspaceLoadedTextFile(
        workspace_root=str(root),
        relative_path=normalized_relative,
        absolute_path=str(target),
        content=text,
        bytes_read=len(text.encode("utf-8")),
    )


def search_text_within_workspace(
    *,
    workspace_dir: str | None,
    query: str,
    limit: int = DEFAULT_WORKSPACE_SEARCH_LIMIT,
    relative_path: str | None = None,
    case_sensitive: bool = False,
) -> WorkspaceTextSearch:
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("workspace_search requires a non-empty query.")
    normalized_limit = min(max(limit, 1), MAX_WORKSPACE_SEARCH_LIMIT)
    root = resolve_workspace_root(workspace_dir)
    search_root, search_root_relative = resolve_workspace_search_root(
        root=root,
        relative_path=relative_path,
    )
    matches: list[WorkspaceSearchMatch] = []
    scanned_file_count = 0
    needle = normalized_query if case_sensitive else normalized_query.casefold()

    for candidate in _iter_search_files(root=root, search_root=search_root):
        if len(matches) >= normalized_limit:
            break
        try:
            loaded = load_text_file_from_workspace_root(
                root=root,
                relative_path=candidate.relative_to(root).as_posix(),
                max_bytes=MAX_WORKSPACE_READ_FILE_BYTES,
            )
        except ValueError:
            continue
        if loaded.content is None:
            continue
        scanned_file_count += 1
        for line_number, line_text in enumerate(loaded.content.splitlines(), start=1):
            haystack = line_text if case_sensitive else line_text.casefold()
            if needle not in haystack:
                continue
            column_number = haystack.index(needle) + 1
            matches.append(
                WorkspaceSearchMatch(
                    path=loaded.relative_path,
                    absolute_path=loaded.absolute_path,
                    line_number=line_number,
                    column_number=column_number,
                    line_text=line_text,
                ),
            )
            if len(matches) >= normalized_limit:
                break

    return WorkspaceTextSearch(
        workspace_root=str(root),
        search_root=search_root_relative,
        query=normalized_query,
        matches=tuple(matches),
        scanned_file_count=scanned_file_count,
    )


def list_workspace_path(
    *,
    workspace_dir: str | None,
    relative_path: str | None = None,
    limit: int = DEFAULT_WORKSPACE_LIST_LIMIT,
) -> WorkspacePathListing:
    normalized_limit = min(max(limit, 1), MAX_WORKSPACE_LIST_LIMIT)
    root = resolve_workspace_root(workspace_dir)
    target, listed_path = resolve_workspace_search_root(
        root=root,
        relative_path=relative_path,
    )

    if target.is_file():
        return WorkspacePathListing(
            workspace_root=str(root),
            listed_path=listed_path,
            listed_type="file",
            entries=(_build_workspace_list_entry(root=root, candidate=target),),
        )

    entries: list[WorkspaceListEntry] = []
    try:
        children = sorted(
            target.iterdir(),
            key=lambda item: (
                0 if item.is_dir() and not item.is_symlink() else 1,
                item.name.lower(),
                item.name,
            ),
        )
    except OSError as exc:
        raise ValueError(
            f"Workspace path '{listed_path or '.'}' could not be listed.",
        ) from exc

    for child in children:
        if len(entries) >= normalized_limit:
            break
        try:
            if child.is_symlink():
                continue
            resolved = child.resolve(strict=True)
        except OSError:
            continue
        if not _is_within_root(root=root, target=resolved):
            continue
        if not resolved.exists():
            continue
        if resolved.is_dir():
            entries.append(
                WorkspaceListEntry(
                    path=resolved.relative_to(root).as_posix(),
                    absolute_path=str(resolved),
                    entry_type="directory",
                    size_bytes=None,
                ),
            )
            continue
        if not resolved.is_file():
            continue
        try:
            stat = resolved.stat()
        except OSError:
            continue
        if stat.st_nlink > 1:
            continue
        entries.append(
            WorkspaceListEntry(
                path=resolved.relative_to(root).as_posix(),
                absolute_path=str(resolved),
                entry_type="file",
                size_bytes=stat.st_size,
            ),
        )

    return WorkspacePathListing(
        workspace_root=str(root),
        listed_path=listed_path,
        listed_type="directory",
        entries=tuple(entries),
    )


def resolve_workspace_write_target(
    *,
    root: Path,
    relative_path: str,
) -> tuple[Path, str, bool]:
    normalized_relative = _normalize_relative_path(relative_path)
    normalized_path = Path(normalized_relative)
    _assert_no_symlink_components(root=root, relative_path=normalized_path)
    parent = _ensure_workspace_parent_dir(
        root=root,
        relative_path=normalized_path.parent,
        normalized_relative=normalized_relative,
    )
    if not _is_within_root(root=root, target=parent):
        raise ValueError(
            f"Workspace path '{normalized_relative}' escapes the bound workspace root.",
        )
    if not parent.is_dir():
        raise ValueError(
            f"Workspace parent path for '{normalized_relative}' is not a writable directory.",
        )
    target = parent / normalized_path.name
    existed_before = target.exists()
    if existed_before:
        try:
            stat = target.stat()
        except OSError as exc:
            raise ValueError(
                f"Workspace file '{normalized_relative}' could not be accessed.",
            ) from exc
        if not target.is_file():
            raise ValueError(
                f"Workspace path '{normalized_relative}' is not a writable file.",
            )
        if stat.st_nlink > 1:
            raise ValueError(
                f"Workspace file '{normalized_relative}' is hard-linked and cannot be written safely.",
            )
    return target, normalized_relative, existed_before


def resolve_workspace_file(*, root: Path, relative_path: str) -> tuple[Path, str]:
    normalized_relative = _normalize_relative_path(relative_path)
    _assert_no_symlink_components(root=root, relative_path=Path(normalized_relative))
    try:
        candidate = (root / normalized_relative).resolve(strict=True)
    except OSError as exc:
        raise ValueError(
            f"Workspace file '{normalized_relative}' could not be accessed.",
        ) from exc
    if not _is_within_root(root=root, target=candidate):
        raise ValueError(
            f"Workspace path '{normalized_relative}' escapes the bound workspace root.",
        )
    return candidate, candidate.relative_to(root).as_posix()


def resolve_workspace_search_root(
    *,
    root: Path,
    relative_path: str | None,
) -> tuple[Path, str | None]:
    if relative_path is None:
        return root, None
    normalized_input = relative_path.strip()
    if not normalized_input or normalized_input == ".":
        return root, None
    normalized_relative = _normalize_relative_path(relative_path)
    normalized_path = Path(normalized_relative)
    _assert_no_symlink_components(root=root, relative_path=normalized_path)
    try:
        candidate = (root / normalized_relative).resolve(strict=True)
    except OSError as exc:
        raise ValueError(
            f"Workspace path '{normalized_relative}' could not be accessed.",
        ) from exc
    if not _is_within_root(root=root, target=candidate):
        raise ValueError(
            f"Workspace path '{normalized_relative}' escapes the bound workspace root.",
        )
    return candidate, candidate.relative_to(root).as_posix()


def _build_workspace_list_entry(*, root: Path, candidate: Path) -> WorkspaceListEntry:
    try:
        stat = candidate.stat()
    except OSError as exc:
        raise ValueError(
            f"Workspace path '{candidate.relative_to(root).as_posix()}' could not be accessed.",
        ) from exc
    return WorkspaceListEntry(
        path=candidate.relative_to(root).as_posix(),
        absolute_path=str(candidate),
        entry_type="file" if candidate.is_file() else "directory",
        size_bytes=stat.st_size if candidate.is_file() else None,
    )


def _normalize_relative_path(relative_path: str) -> str:
    normalized = relative_path.strip()
    if not normalized:
        raise ValueError("A non-empty workspace-relative path is required.")
    candidate = Path(normalized)
    if candidate.is_absolute():
        raise ValueError("Workspace file tools require a path relative to the workspace root.")
    if any(part == ".." for part in candidate.parts):
        raise ValueError("Workspace file paths cannot traverse upward with '..'.")
    cleaned = Path(*[part for part in candidate.parts if part not in {"", "."}])
    if not cleaned.parts:
        raise ValueError("A non-empty workspace-relative path is required.")
    return cleaned.as_posix()


def _assert_no_symlink_components(*, root: Path, relative_path: Path) -> None:
    current = root
    for part in relative_path.parts:
        current = current / part
        try:
            if current.is_symlink():
                raise ValueError(
                    f"Workspace path '{relative_path.as_posix()}' uses symbolic links, which are not supported.",
                )
        except OSError as exc:
            raise ValueError(
                f"Workspace path '{relative_path.as_posix()}' could not be resolved safely.",
            ) from exc


def _is_within_root(*, root: Path, target: Path) -> bool:
    try:
        target.relative_to(root)
    except ValueError:
        return False
    return True


def _ensure_workspace_parent_dir(
    *,
    root: Path,
    relative_path: Path,
    normalized_relative: str,
) -> Path:
    current = root
    for part in relative_path.parts:
        current = current / part
        try:
            exists = current.exists()
        except OSError as exc:
            raise ValueError(
                f"Workspace parent path for '{normalized_relative}' could not be resolved.",
            ) from exc
        if exists:
            try:
                resolved = current.resolve(strict=True)
            except OSError as exc:
                raise ValueError(
                    f"Workspace parent path for '{normalized_relative}' could not be resolved.",
                ) from exc
            if not _is_within_root(root=root, target=resolved):
                raise ValueError(
                    f"Workspace path '{normalized_relative}' escapes the bound workspace root.",
                )
            if not resolved.is_dir():
                raise ValueError(
                    f"Workspace parent path for '{normalized_relative}' is not a writable directory.",
                )
            current = resolved
            continue
        try:
            current.mkdir()
        except OSError as exc:
            raise ValueError(
                f"Workspace parent path for '{normalized_relative}' could not be created.",
            ) from exc
        try:
            resolved = current.resolve(strict=True)
        except OSError as exc:
            raise ValueError(
                f"Workspace parent path for '{normalized_relative}' could not be resolved.",
            ) from exc
        if not _is_within_root(root=root, target=resolved):
            raise ValueError(
                f"Workspace path '{normalized_relative}' escapes the bound workspace root.",
            )
        if not resolved.is_dir():
            raise ValueError(
                f"Workspace parent path for '{normalized_relative}' is not a writable directory.",
            )
        current = resolved
    return current


def _iter_search_files(*, root: Path, search_root: Path):
    if search_root.is_file():
        yield search_root
        return
    for current_dir, dirnames, filenames in os.walk(search_root, followlinks=False):
        current_path = Path(current_dir)
        kept_dirnames: list[str] = []
        for dirname in sorted(dirnames):
            candidate = current_path / dirname
            try:
                if candidate.is_symlink():
                    continue
                resolved = candidate.resolve(strict=True)
            except OSError:
                continue
            if not _is_within_root(root=root, target=resolved):
                continue
            if not resolved.is_dir():
                continue
            kept_dirnames.append(dirname)
        dirnames[:] = kept_dirnames
        for filename in sorted(filenames):
            candidate = current_path / filename
            try:
                if candidate.is_symlink():
                    continue
                resolved = candidate.resolve(strict=True)
            except OSError:
                continue
            if not _is_within_root(root=root, target=resolved):
                continue
            if not resolved.is_file():
                continue
            yield resolved
