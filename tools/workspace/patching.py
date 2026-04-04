from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tools.workspace.fs_safe import (
    WorkspaceLoadedTextFile,
    delete_text_file_within_workspace,
    load_text_file_from_workspace_root,
    resolve_workspace_root,
    write_text_file_within_workspace,
)


_BEGIN_PATCH = "*** Begin Patch"
_END_PATCH = "*** End Patch"
_ADD_FILE_PREFIX = "*** Add File: "
_DELETE_FILE_PREFIX = "*** Delete File: "
_UPDATE_FILE_PREFIX = "*** Update File: "
_MOVE_TO_PREFIX = "*** Move to: "
_EOF_MARKER = "*** End of File"


@dataclass(frozen=True, slots=True)
class PatchHunk:
    old_lines: tuple[str, ...]
    new_lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AddFilePatch:
    path: str
    content: str


@dataclass(frozen=True, slots=True)
class DeleteFilePatch:
    path: str


@dataclass(frozen=True, slots=True)
class UpdateFilePatch:
    path: str
    hunks: tuple[PatchHunk, ...]


PatchOperation = AddFilePatch | DeleteFilePatch | UpdateFilePatch


@dataclass(frozen=True, slots=True)
class WorkspaceApplyPatchResult:
    workspace_root: str
    added_files: tuple[str, ...]
    modified_files: tuple[str, ...]
    deleted_files: tuple[str, ...]


@dataclass(slots=True)
class _VirtualFileState:
    relative_path: str
    original_exists: bool
    original_content: str | None
    current_exists: bool
    current_content: str | None


def apply_workspace_patch(
    *,
    workspace_dir: str | None,
    patch_text: str,
) -> WorkspaceApplyPatchResult:
    root = resolve_workspace_root(workspace_dir)
    operations = parse_apply_patch(patch_text)
    file_states: dict[str, _VirtualFileState] = {}
    touched_paths: list[str] = []

    for operation in operations:
        path = operation.path
        if path not in touched_paths:
            touched_paths.append(path)
        state = _load_virtual_state(root=root, relative_path=path, cache=file_states)
        if isinstance(operation, AddFilePatch):
            if state.current_exists:
                raise ValueError(
                    f"Workspace file '{state.relative_path}' already exists and cannot be added by apply_patch.",
                )
            state.current_exists = True
            state.current_content = operation.content
            continue
        if isinstance(operation, DeleteFilePatch):
            if not state.current_exists:
                raise ValueError(
                    f"Workspace file '{state.relative_path}' does not exist and cannot be deleted by apply_patch.",
                )
            state.current_exists = False
            state.current_content = None
            continue
        if not state.current_exists or state.current_content is None:
            raise ValueError(
                f"Workspace file '{state.relative_path}' does not exist and cannot be updated by apply_patch.",
            )
        state.current_content = _apply_update_hunks(
            text=state.current_content,
            hunks=operation.hunks,
            relative_path=state.relative_path,
        )

    added_files: list[str] = []
    modified_files: list[str] = []
    deleted_files: list[str] = []
    workspace_root = str(root)

    for relative_path in touched_paths:
        state = file_states[relative_path]
        if state.original_exists == state.current_exists and state.original_content == state.current_content:
            continue
        if state.current_exists and state.current_content is not None:
            write_text_file_within_workspace(
                workspace_dir=workspace_root,
                relative_path=relative_path,
                content=state.current_content,
            )
        elif state.original_exists:
            delete_text_file_within_workspace(
                workspace_dir=workspace_root,
                relative_path=relative_path,
            )
        if not state.original_exists and state.current_exists:
            added_files.append(relative_path)
        elif state.original_exists and not state.current_exists:
            deleted_files.append(relative_path)
        else:
            modified_files.append(relative_path)

    if not added_files and not modified_files and not deleted_files:
        raise ValueError("apply_patch did not produce any file changes.")

    return WorkspaceApplyPatchResult(
        workspace_root=workspace_root,
        added_files=tuple(added_files),
        modified_files=tuple(modified_files),
        deleted_files=tuple(deleted_files),
    )


def parse_apply_patch(patch_text: str) -> tuple[PatchOperation, ...]:
    if not isinstance(patch_text, str) or not patch_text.strip():
        raise ValueError("apply_patch requires a non-empty input string.")
    lines = patch_text.splitlines()
    if not lines or lines[0] != _BEGIN_PATCH:
        raise ValueError("apply_patch input must start with '*** Begin Patch'.")
    if lines[-1] != _END_PATCH:
        raise ValueError("apply_patch input must end with '*** End Patch'.")

    operations: list[PatchOperation] = []
    index = 1
    limit = len(lines) - 1
    while index < limit:
        line = lines[index]
        if line.startswith(_ADD_FILE_PREFIX):
            path = _require_patch_path(line, _ADD_FILE_PREFIX)
            index += 1
            content_lines: list[str] = []
            while index < limit and not lines[index].startswith("*** "):
                entry = lines[index]
                if not entry.startswith("+"):
                    raise ValueError(
                        f"apply_patch add file '{path}' only accepts lines prefixed with '+'.",
                    )
                content_lines.append(entry[1:])
                index += 1
            operations.append(AddFilePatch(path=path, content="\n".join(content_lines)))
            continue
        if line.startswith(_DELETE_FILE_PREFIX):
            operations.append(
                DeleteFilePatch(path=_require_patch_path(line, _DELETE_FILE_PREFIX)),
            )
            index += 1
            continue
        if line.startswith(_UPDATE_FILE_PREFIX):
            path = _require_patch_path(line, _UPDATE_FILE_PREFIX)
            index += 1
            if index < limit and lines[index].startswith(_MOVE_TO_PREFIX):
                raise ValueError("apply_patch rename operations are not supported yet.")
            hunks: list[PatchHunk] = []
            old_lines: list[str] = []
            new_lines: list[str] = []
            saw_change_lines = False
            while index < limit and not lines[index].startswith("*** "):
                entry = lines[index]
                if entry.startswith("@@"):
                    if old_lines or new_lines:
                        hunks.append(
                            PatchHunk(
                                old_lines=tuple(old_lines),
                                new_lines=tuple(new_lines),
                            ),
                        )
                        old_lines = []
                        new_lines = []
                    index += 1
                    continue
                if entry == _EOF_MARKER:
                    index += 1
                    continue
                if not entry:
                    raise ValueError(
                        f"apply_patch update for '{path}' contains an empty patch line without a diff prefix.",
                    )
                prefix = entry[0]
                content = entry[1:]
                if prefix == " ":
                    old_lines.append(content)
                    new_lines.append(content)
                elif prefix == "-":
                    old_lines.append(content)
                elif prefix == "+":
                    new_lines.append(content)
                else:
                    raise ValueError(
                        f"apply_patch update for '{path}' uses unsupported diff prefix '{prefix}'.",
                    )
                saw_change_lines = True
                index += 1
            if old_lines or new_lines:
                hunks.append(
                    PatchHunk(
                        old_lines=tuple(old_lines),
                        new_lines=tuple(new_lines),
                    ),
                )
            if not saw_change_lines or not hunks:
                raise ValueError(
                    f"apply_patch update for '{path}' must include at least one diff hunk.",
                )
            operations.append(UpdateFilePatch(path=path, hunks=tuple(hunks)))
            continue
        raise ValueError(f"apply_patch encountered an unknown section header: {line!r}")

    if not operations:
        raise ValueError("apply_patch requires at least one file operation.")
    return tuple(operations)


def _load_virtual_state(
    *,
    root: Path,
    relative_path: str,
    cache: dict[str, _VirtualFileState],
) -> _VirtualFileState:
    if relative_path in cache:
        return cache[relative_path]
    loaded = _load_optional_file(root=root, relative_path=relative_path)
    state = _VirtualFileState(
        relative_path=loaded.relative_path,
        original_exists=loaded.content is not None,
        original_content=loaded.content,
        current_exists=loaded.content is not None,
        current_content=loaded.content,
    )
    cache[state.relative_path] = state
    return state


def _load_optional_file(*, root: Path, relative_path: str) -> WorkspaceLoadedTextFile:
    try:
        return load_text_file_from_workspace_root(root=root, relative_path=relative_path)
    except FileNotFoundError:
        normalized = _normalize_patch_path(relative_path)
        return WorkspaceLoadedTextFile(
            workspace_root=str(root),
            relative_path=normalized,
            absolute_path=str(root / normalized),
            content=None,
            bytes_read=0,
        )
    except ValueError as exc:
        message = str(exc)
        if "could not be accessed" in message or "does not exist" in message:
            normalized = _normalize_patch_path(relative_path)
            return WorkspaceLoadedTextFile(
                workspace_root=str(root),
                relative_path=normalized,
                absolute_path=str(root / normalized),
                content=None,
                bytes_read=0,
            )
        raise


def _apply_update_hunks(
    *,
    text: str,
    hunks: tuple[PatchHunk, ...],
    relative_path: str,
) -> str:
    updated = text
    for hunk in hunks:
        old_text = "\n".join(hunk.old_lines)
        new_text = "\n".join(hunk.new_lines)
        if not old_text:
            raise ValueError(
                f"apply_patch update for '{relative_path}' requires at least one existing line or context line per hunk.",
            )
        occurrence_count = updated.count(old_text)
        if occurrence_count < 1:
            raise ValueError(
                f"Workspace file '{relative_path}' does not contain the exact text required by apply_patch.",
            )
        if occurrence_count > 1:
            raise ValueError(
                f"Workspace file '{relative_path}' matches an apply_patch hunk {occurrence_count} times; the patch must be more specific.",
            )
        updated = updated.replace(old_text, new_text, 1)
    return updated


def _require_patch_path(line: str, prefix: str) -> str:
    path = line.removeprefix(prefix).strip()
    if not path:
        raise ValueError(f"apply_patch section '{prefix.strip()}' requires a non-empty path.")
    return _normalize_patch_path(path)


def _normalize_patch_path(path: str) -> str:
    candidate = Path(path.strip())
    if not candidate.parts:
        raise ValueError("apply_patch paths must be non-empty.")
    if candidate.is_absolute():
        raise ValueError("apply_patch paths must be relative to the workspace root.")
    if any(part == ".." for part in candidate.parts):
        raise ValueError("apply_patch paths cannot traverse upward with '..'.")
    cleaned = Path(*[part for part in candidate.parts if part not in {"", "."}])
    if not cleaned.parts:
        raise ValueError("apply_patch paths must be non-empty.")
    return cleaned.as_posix()
