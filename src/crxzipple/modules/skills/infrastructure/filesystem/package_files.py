from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib

import yaml

from crxzipple.modules.skills.application.models import SkillResource
from crxzipple.modules.skills.domain import SkillValidationError
from crxzipple.modules.skills.infrastructure.filesystem.path_safety import is_within_root


DEFAULT_SKILL_RESOURCE_DIRS = ("references", "templates", "assets", "scripts")
MAX_SKILL_FILE_BYTES = 256 * 1024


def read_text_file(path: Path, *, label: str) -> str:
    try:
        if not path.is_file():
            raise SkillValidationError(f"{label} is not backed by a readable file.")
        if path.stat().st_size > MAX_SKILL_FILE_BYTES:
            raise SkillValidationError(f"{label} is too large to load.")
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SkillValidationError(f"{label} could not be read.") from exc


def load_legacy_manifest(
    *,
    root: Path,
    skill_dir: Path,
    manifest_filename: str,
) -> tuple[Path | None, dict[str, Any] | None]:
    manifest_file = skill_dir / manifest_filename
    try:
        manifest_path = manifest_file.resolve(strict=True)
    except OSError:
        return None, None
    if not is_within_root(root=root, target=manifest_path):
        return None, None
    try:
        payload = yaml.safe_load(
            read_text_file(
                manifest_path,
                label=f"Skill manifest '{manifest_file.name}'",
            )
        )
    except SkillValidationError:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    return manifest_path, payload


def discover_resources(*, root: Path) -> tuple[SkillResource, ...]:
    resources: list[SkillResource] = []
    for resource_kind in DEFAULT_SKILL_RESOURCE_DIRS:
        resource_root = root / resource_kind
        if not resource_root.is_dir():
            continue
        try:
            files = sorted(path for path in resource_root.rglob("*") if path.is_file())
        except OSError:
            continue
        for resource_path in files:
            try:
                resolved = resource_path.resolve(strict=True)
            except OSError:
                continue
            if not is_within_root(root=root, target=resolved):
                continue
            try:
                size_bytes = resolved.stat().st_size
            except OSError:
                continue
            if size_bytes > MAX_SKILL_FILE_BYTES:
                continue
            resources.append(
                SkillResource(
                    path=resolved.relative_to(root).as_posix(),
                    kind=resource_kind,
                    size_bytes=size_bytes,
                ),
            )
    return tuple(resources)


def fingerprint_package(
    *,
    root: Path,
    manifest_path: Path,
    instructions_path: Path,
    resources: tuple[SkillResource, ...],
    source: str,
    name: str,
    version: str | None,
) -> str:
    digest = hashlib.sha256()
    digest.update(f"skill:{source}:{name}:{version or ''}\n".encode("utf-8"))
    file_paths: dict[str, Path] = {}
    for path in (manifest_path, instructions_path):
        if is_within_root(root=root, target=path):
            file_paths[path.relative_to(root).as_posix()] = path
    for resource in resources:
        try:
            path = (root / resource.path).resolve(strict=True)
        except OSError:
            continue
        if is_within_root(root=root, target=path):
            file_paths[resource.path] = path
    for relative_path in sorted(file_paths):
        digest.update(f"path:{relative_path}\n".encode("utf-8"))
        path = file_paths[relative_path]
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<unreadable>")
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"
