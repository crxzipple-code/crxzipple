from __future__ import annotations

import shutil
from pathlib import Path


_FILE_MAPPINGS: tuple[tuple[tuple[str, ...], tuple[str, ...], str], ...] = (
    (("AGENT.md", "AGENTS.md"), ("AGENT.md", "AGENTS.md"), "AGENT.md"),
    (("SOUL.md",), ("SOUL.md",), "SOUL.md"),
    (("USER.md",), ("USER.md",), "USER.md"),
    (("IDENTITY.md",), ("IDENTITY.md",), "IDENTITY.md"),
    (("MEMORY.md", "memory.md"), ("MEMORY.md", "memory.md"), "MEMORY.md"),
)
_DIRECTORY_MAPPINGS: tuple[str, ...] = ("memory", "skills", ".state")


def migrate_agent_home_contents(
    source_dir: str | None,
    target_home_dir: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if source_dir is None or not source_dir.strip():
        return (), ()

    source_root = Path(source_dir).expanduser()
    target_root = Path(target_home_dir).expanduser()
    if not source_root.exists():
        return (), ()
    if _same_path(source_root, target_root):
        return (), ()

    target_root.mkdir(parents=True, exist_ok=True)
    copied_paths: list[str] = []
    skipped_paths: list[str] = []

    for source_names, target_names, canonical_name in _FILE_MAPPINGS:
        source_path = _first_existing(source_root, source_names)
        if source_path is None:
            continue
        if _any_existing(target_root, target_names):
            skipped_paths.append(canonical_name)
            continue
        target_path = target_root / canonical_name
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        copied_paths.append(f"{source_path.name} -> {canonical_name}")

    for relative_dir in _DIRECTORY_MAPPINGS:
        source_path = source_root / relative_dir
        if not source_path.exists() or not source_path.is_dir():
            continue
        target_path = target_root / relative_dir
        target_path.mkdir(parents=True, exist_ok=True)
        _copy_tree_missing(
            source_root=source_path,
            target_root=target_path,
            copied_paths=copied_paths,
            skipped_paths=skipped_paths,
            label_prefix=f"{relative_dir}/",
        )

    return tuple(copied_paths), tuple(skipped_paths)


def _same_path(first: Path, second: Path) -> bool:
    try:
        return first.resolve() == second.resolve()
    except OSError:
        return first.absolute() == second.absolute()


def _first_existing(root: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        candidate = root / name
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _any_existing(root: Path, names: tuple[str, ...]) -> bool:
    return any((root / name).exists() for name in names)


def _copy_tree_missing(
    *,
    source_root: Path,
    target_root: Path,
    copied_paths: list[str],
    skipped_paths: list[str],
    label_prefix: str,
) -> None:
    for source_path in sorted(source_root.rglob("*")):
        relative_path = source_path.relative_to(source_root)
        target_path = target_root / relative_path
        label = f"{label_prefix}{relative_path.as_posix()}"
        if source_path.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
            continue
        if target_path.exists():
            skipped_paths.append(label)
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        copied_paths.append(label)
