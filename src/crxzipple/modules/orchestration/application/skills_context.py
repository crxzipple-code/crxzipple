from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_SKILL_ENTRY_FILENAME = "SKILL.md"
DEFAULT_WORKSPACE_SKILL_ROOTS = (
    ".crxzipple/skills",
    "skills",
)
DEFAULT_GLOBAL_SKILLS_DIR = Path.home() / ".crxzipple" / "skills"
DEFAULT_SYSTEM_SKILLS_DIR = Path(__file__).resolve().parents[5] / "skills"
MAX_SKILL_FILE_BYTES = 256 * 1024
MAX_SKILL_DESCRIPTION_CHARS = 240
MAX_SKILL_CONTENT_CHARS = 20_000


@dataclass(frozen=True, slots=True)
class AvailableSkill:
    name: str
    description: str
    path: str
    source: str


def load_available_skills(
    workspace_dir: str | None,
    *,
    global_root: Path | None = None,
    system_root: Path | None = None,
) -> tuple[AvailableSkill, ...]:
    roots = _skill_roots(
        workspace_dir,
        global_root=global_root,
        system_root=system_root,
    )
    available: dict[str, AvailableSkill] = {}
    for root, source in roots:
        if not root.is_dir():
            continue
        for skill in _discover_root_skills(root=root, source=source):
            if skill.name in available:
                continue
            available[skill.name] = skill
    return tuple(sorted(available.values(), key=lambda item: item.name))


def _skill_roots(
    workspace_dir: str | None,
    *,
    global_root: Path | None,
    system_root: Path | None,
) -> tuple[tuple[Path, str], ...]:
    roots: list[tuple[Path, str]] = []
    workspace_root = _resolve_workspace_root(workspace_dir)
    if workspace_root is not None:
        for relative_root in DEFAULT_WORKSPACE_SKILL_ROOTS:
            roots.append((workspace_root / relative_root, "workspace"))
    roots.append((_normalize_skill_root(global_root or DEFAULT_GLOBAL_SKILLS_DIR), "global"))
    roots.append((_normalize_skill_root(system_root or DEFAULT_SYSTEM_SKILLS_DIR), "system"))
    return tuple(roots)


def _resolve_workspace_root(workspace_dir: str | None) -> Path | None:
    if workspace_dir is None or not workspace_dir.strip():
        return None
    try:
        resolved = Path(workspace_dir).expanduser().resolve(strict=True)
    except OSError:
        return None
    if not resolved.is_dir():
        return None
    return resolved


def _normalize_skill_root(root: Path) -> Path:
    try:
        return root.expanduser().resolve(strict=False)
    except OSError:
        return root.expanduser()


def _discover_root_skills(*, root: Path, source: str) -> tuple[AvailableSkill, ...]:
    discovered: list[AvailableSkill] = []
    try:
        children = sorted(
            (path for path in root.iterdir() if path.is_dir()),
            key=lambda item: item.name,
        )
    except OSError:
        return ()
    for skill_dir in children:
        skill_file = skill_dir / DEFAULT_SKILL_ENTRY_FILENAME
        try:
            resolved = skill_file.resolve(strict=True)
        except OSError:
            continue
        if not _is_within_root(root=root, target=resolved):
            continue
        try:
            if not resolved.is_file():
                continue
            if resolved.stat().st_size > MAX_SKILL_FILE_BYTES:
                continue
            raw_content = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        description = _extract_skill_description(raw_content)
        discovered.append(
            AvailableSkill(
                name=skill_dir.name,
                description=description,
                path=str(resolved),
                source=source,
            ),
        )
    return tuple(discovered)


def _is_within_root(*, root: Path, target: Path) -> bool:
    try:
        target.relative_to(root)
    except ValueError:
        return False
    return True


def _extract_skill_description(content: str) -> str:
    normalized = content.strip()
    if not normalized:
        return "No description provided."
    paragraph_lines: list[str] = []
    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
            if paragraph_lines:
                break
            continue
        if line.startswith("#") and not paragraph_lines:
            continue
        paragraph_lines.append(line)
    if not paragraph_lines:
        return "No description provided."
    description = " ".join(paragraph_lines)
    if len(description) <= MAX_SKILL_DESCRIPTION_CHARS:
        return description
    return f"{description[: MAX_SKILL_DESCRIPTION_CHARS - 1].rstrip()}..."


def load_skill_content(skill: AvailableSkill) -> str:
    try:
        resolved = Path(skill.path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"Skill '{skill.name}' could not be resolved.") from exc
    try:
        if not resolved.is_file():
            raise ValueError(f"Skill '{skill.name}' is not backed by a readable file.")
        if resolved.stat().st_size > MAX_SKILL_FILE_BYTES:
            raise ValueError(f"Skill '{skill.name}' is too large to inject.")
        content = resolved.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"Skill '{skill.name}' could not be read.") from exc
    if len(content) <= MAX_SKILL_CONTENT_CHARS:
        return content
    marker = "\n\n[...truncated skill content...]\n"
    budget = max(0, MAX_SKILL_CONTENT_CHARS - len(marker))
    return f"{content[:budget].rstrip()}{marker}"
