from __future__ import annotations

from pathlib import Path
from typing import Iterable

from crxzipple.modules.skills.application.models import SkillPackage
from crxzipple.modules.skills.domain import SkillValidationError


def is_within_root(*, root: Path, target: Path) -> bool:
    try:
        target.relative_to(root)
    except ValueError:
        return False
    return True


def resolve_workspace_root(workspace_dir: str | None) -> Path | None:
    if workspace_dir is None or not workspace_dir.strip():
        return None
    try:
        resolved = Path(workspace_dir).expanduser().resolve(strict=True)
    except OSError:
        return None
    if not resolved.is_dir():
        return None
    return resolved


def normalize_skill_root(root: Path) -> Path:
    try:
        return root.expanduser().resolve(strict=False)
    except OSError:
        return root.expanduser()


def resolve_skill_directory(*, path: str, label: str) -> Path:
    candidate = path.strip()
    if not candidate:
        raise SkillValidationError(f"{label} path is required.")
    try:
        resolved = Path(candidate).expanduser().resolve(strict=True)
    except OSError as exc:
        raise SkillValidationError(f"{label} '{candidate}' could not be resolved.") from exc
    if not resolved.is_dir():
        raise SkillValidationError(f"{label} '{candidate}' is not a directory.")
    return resolved


def resolve_instructions_path(*, root: Path, relative_path: str) -> Path | None:
    try:
        candidate = (root / relative_path).resolve(strict=True)
    except OSError:
        return None
    if not is_within_root(root=root, target=candidate):
        return None
    if not candidate.is_file():
        return None
    return candidate


def resolve_package_file_path(
    *,
    package: SkillPackage,
    relative_path: str,
) -> Path:
    root = Path(package.root_path)
    try:
        candidate = (root / relative_path).resolve(strict=True)
    except OSError as exc:
        raise SkillValidationError(
            f"Skill file '{relative_path}' could not be resolved for skill '{package.name}'.",
        ) from exc
    if not is_within_root(root=root, target=candidate):
        raise SkillValidationError(
            f"Skill file '{relative_path}' escapes the skill package root.",
        )
    if not candidate.is_file():
        raise SkillValidationError(
            f"Skill file '{relative_path}' is not a readable file.",
        )
    return candidate


def normalize_support_file_path(
    *,
    package: SkillPackage,
    path: str,
    allowed_resource_dirs: Iterable[str],
) -> str:
    normalized = path.strip().replace("\\", "/")
    if not normalized:
        raise SkillValidationError("Skill file path is required.")
    if normalized.startswith("/") or normalized in {".", ".."}:
        raise SkillValidationError("Skill file path must be package-relative.")
    if any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise SkillValidationError("Skill file path must not contain traversal segments.")
    root = Path(package.root_path)
    root_resolved = root.resolve(strict=True)
    candidate = (root / normalized).resolve(strict=False)
    try:
        relative_path = candidate.relative_to(root_resolved).as_posix()
    except (OSError, ValueError) as exc:
        raise SkillValidationError(
            f"Skill file '{normalized}' escapes the skill package root.",
        ) from exc
    if relative_path == package.manifest.instructions_path:
        raise SkillValidationError(
            "Use the instructions endpoint to update the skill instructions file.",
        )
    allowed = tuple(allowed_resource_dirs)
    if not any(
        relative_path == resource_dir or relative_path.startswith(f"{resource_dir}/")
        for resource_dir in allowed
    ):
        allowed_label = ", ".join(allowed)
        raise SkillValidationError(
            f"Skill support files must live under one of: {allowed_label}.",
        )
    return relative_path


def normalize_skill_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise SkillValidationError("Skill name is required.")
    if normalized in {".", ".."} or "/" in normalized or "\\" in normalized:
        raise SkillValidationError("Skill name must be a package-safe identifier.")
    return normalized
