from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crxzipple.modules.skills.application.models import SkillPackage
from crxzipple.modules.skills.domain import SkillValidationError
from crxzipple.modules.skills.infrastructure.filesystem.manifest_parser import (
    parse_markdown_frontmatter,
    parse_normalized_manifest,
)
from crxzipple.modules.skills.infrastructure.filesystem.package_files import (
    discover_resources,
    fingerprint_package,
    load_legacy_manifest,
    read_text_file,
)
from crxzipple.modules.skills.infrastructure.filesystem.path_safety import (
    is_within_root,
    resolve_instructions_path,
)


@dataclass(frozen=True, slots=True)
class SkillPackageLoader:
    manifest_filename: str
    instructions_filename: str

    def discover_root_skills(
        self,
        *,
        root: Path,
        source: str,
    ) -> tuple[SkillPackage, ...]:
        direct_package = self.load_explicit_skill_dir(skill_dir=root, source=source)
        if direct_package is not None:
            return (direct_package,)
        discovered: list[SkillPackage] = []
        try:
            children = sorted(
                (path for path in root.iterdir() if path.is_dir()),
                key=lambda item: item.name,
            )
        except OSError:
            return ()
        for skill_dir in children:
            package = self.load_skill_package(root=root, skill_dir=skill_dir, source=source)
            if package is not None:
                discovered.append(package)
        return tuple(discovered)

    def load_explicit_skill_dir(
        self,
        *,
        skill_dir: Path,
        source: str,
        strict: bool = False,
        allow_legacy_manifest: bool = False,
    ) -> SkillPackage | None:
        return self.load_skill_package(
            root=skill_dir.parent,
            skill_dir=skill_dir,
            source=source,
            strict=strict,
            allow_legacy_manifest=allow_legacy_manifest,
        )

    def load_skill_package(
        self,
        *,
        root: Path,
        skill_dir: Path,
        source: str,
        strict: bool = False,
        allow_legacy_manifest: bool = False,
    ) -> SkillPackage | None:
        try:
            root_path = skill_dir.resolve(strict=True)
        except OSError:
            return None
        if not is_within_root(root=root, target=root_path):
            return None
        instructions_path = resolve_instructions_path(
            root=root_path,
            relative_path=self.instructions_filename,
        )
        if instructions_path is None:
            return None
        legacy_manifest_path, legacy_payload = (
            load_legacy_manifest(
                root=root,
                skill_dir=skill_dir,
                manifest_filename=self.manifest_filename,
            )
            if allow_legacy_manifest
            else (None, None)
        )
        frontmatter_payload = self._load_skill_frontmatter(instructions_path)
        if frontmatter_payload is None and legacy_payload is None:
            return None
        manifest_path = instructions_path if frontmatter_payload is not None else legacy_manifest_path
        if manifest_path is None:
            return None
        try:
            manifest = parse_normalized_manifest(
                frontmatter_payload=frontmatter_payload,
                legacy_payload=legacy_payload,
            )
        except SkillValidationError:
            if strict:
                raise
            return None
        resolved_instructions_path = resolve_instructions_path(
            root=root_path,
            relative_path=manifest.instructions_path,
        )
        if resolved_instructions_path is None:
            return None
        resources = discover_resources(root=root_path)
        return SkillPackage(
            manifest=manifest,
            root_path=str(root_path),
            manifest_path=str(manifest_path),
            instructions_path=str(resolved_instructions_path),
            source=source,
            resources=resources,
            fingerprint=fingerprint_package(
                root=root_path,
                manifest_path=manifest_path,
                instructions_path=resolved_instructions_path,
                resources=resources,
                source=source,
                name=manifest.name,
                version=manifest.version,
            ),
        )

    @staticmethod
    def _load_skill_frontmatter(instructions_path: Path) -> dict[str, Any] | None:
        try:
            content = read_text_file(
                instructions_path,
                label=f"Skill instructions '{instructions_path.name}'",
            )
        except SkillValidationError:
            return None
        return parse_markdown_frontmatter(content)
