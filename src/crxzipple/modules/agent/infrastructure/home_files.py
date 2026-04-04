from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


_EDITABLE_FILE_SPECS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("agent.json", ("agent.json",), "json"),
    ("AGENT.md", ("AGENT.md", "AGENTS.md"), "markdown"),
    ("SOUL.md", ("SOUL.md",), "markdown"),
    ("USER.md", ("USER.md",), "markdown"),
    ("IDENTITY.md", ("IDENTITY.md",), "markdown"),
    ("MEMORY.md", ("MEMORY.md", "memory.md"), "markdown"),
    (".state/memory-binding.json", (".state/memory-binding.json",), "json"),
)


@dataclass(frozen=True, slots=True)
class AgentHomeEditableFile:
    name: str
    path: str
    exists: bool
    language: str
    content: str


def read_agent_home_files(home_dir: str) -> tuple[AgentHomeEditableFile, ...]:
    root = Path(home_dir).expanduser()
    files: list[AgentHomeEditableFile] = []
    for canonical_name, aliases, language in _EDITABLE_FILE_SPECS:
        resolved_path = _resolve_file_path(root, aliases)
        exists = resolved_path.exists()
        content = resolved_path.read_text(encoding="utf-8") if exists else ""
        files.append(
            AgentHomeEditableFile(
                name=canonical_name,
                path=str(resolved_path),
                exists=exists,
                language=language,
                content=content,
            ),
        )
    return tuple(files)


def write_agent_home_files(
    home_dir: str,
    files: dict[str, str],
) -> tuple[AgentHomeEditableFile, ...]:
    root = Path(home_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    editable_names = {name for name, _, _ in _EDITABLE_FILE_SPECS}
    unknown_names = sorted(set(files) - editable_names)
    if unknown_names:
        raise ValueError(
            f"Unsupported agent home files: {', '.join(unknown_names)}.",
        )

    for canonical_name, aliases, _language in _EDITABLE_FILE_SPECS:
        if canonical_name not in files:
            continue
        resolved_path = _resolve_file_path(root, aliases)
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_path.write_text(files[canonical_name], encoding="utf-8")

    return read_agent_home_files(home_dir)


def _resolve_file_path(root: Path, aliases: tuple[str, ...]) -> Path:
    for alias in aliases:
        candidate = root / alias
        if candidate.exists():
            return candidate
    return root / aliases[0]
