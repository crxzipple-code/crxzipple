from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import yaml

from crxzipple.modules.skills.application.models import (
    InstalledSkill,
    SkillPackage,
    SkillReadResult,
)
from crxzipple.modules.skills.domain import (
    SkillInstallScope,
    SkillManifest,
    SkillNotFoundError,
    SkillValidationError,
)


DEFAULT_SKILL_MANIFEST_FILENAME = "skill.yaml"
DEFAULT_SKILL_INSTRUCTIONS_FILENAME = "SKILL.md"
DEFAULT_WORKSPACE_SKILL_ROOTS = (
    ".crxzipple/skills",
    "skills",
)
DEFAULT_MANAGED_WORKSPACE_SKILL_ROOT = DEFAULT_WORKSPACE_SKILL_ROOTS[0]
DEFAULT_GLOBAL_SKILLS_DIR = Path.home() / ".crxzipple" / "skills"
DEFAULT_SYSTEM_SKILLS_DIR = Path(__file__).resolve().parents[6] / "skills"
MAX_SKILL_FILE_BYTES = 256 * 1024
MAX_SKILL_CONTENT_CHARS = 20_000
MAX_SKILL_DESCRIPTION_CHARS = 240


class FilesystemSkillRepository:
    def __init__(
        self,
        *,
        global_root: Path | None = None,
        system_root: Path | None = None,
    ) -> None:
        self._global_root = global_root or DEFAULT_GLOBAL_SKILLS_DIR
        self._system_root = system_root or DEFAULT_SYSTEM_SKILLS_DIR

    def list_available(
        self,
        *,
        workspace_dir: str | None,
    ) -> tuple[SkillPackage, ...]:
        available: dict[str, SkillPackage] = {}
        for root, source in self._skill_roots(workspace_dir):
            if not root.is_dir():
                continue
            for package in self._discover_root_skills(root=root, source=source):
                if package.name in available:
                    continue
                available[package.name] = package
        return tuple(sorted(available.values(), key=lambda item: item.name))

    def get(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
    ) -> SkillPackage:
        return self._package_by_name(workspace_dir=workspace_dir, skill_name=skill_name)

    def read(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        path: str | None,
    ) -> SkillReadResult:
        package = self._package_by_name(workspace_dir=workspace_dir, skill_name=skill_name)
        requested_path = (
            path.strip()
            if isinstance(path, str) and path.strip()
            else package.manifest.instructions_path
        )
        resolved_path = self._resolve_package_file_path(
            package=package,
            relative_path=requested_path,
        )
        content = self._read_text_file(
            resolved_path,
            label=f"Skill '{package.name}' file '{requested_path}'",
        ).strip()
        if len(content) > MAX_SKILL_CONTENT_CHARS:
            marker = "\n\n[...truncated skill content...]\n"
            budget = max(0, MAX_SKILL_CONTENT_CHARS - len(marker))
            content = f"{content[:budget].rstrip()}{marker}"
        return SkillReadResult(
            package=package,
            requested_path=requested_path,
            resolved_path=str(resolved_path),
            content=content,
        )

    def validate(self, *, path: str) -> SkillPackage:
        skill_dir = self._resolve_skill_directory(path=path, label="Skill package")
        package = self._load_explicit_skill_dir(skill_dir=skill_dir, source="validation")
        if package is None:
            raise SkillValidationError(
                f"Skill package '{skill_dir}' is not a valid skill bundle.",
            )
        return package

    def install(
        self,
        *,
        source_dir: str,
        scope: SkillInstallScope,
        workspace_dir: str | None,
    ) -> InstalledSkill:
        package = self.validate(path=source_dir)
        target_root = self._resolve_install_root(scope=scope, workspace_dir=workspace_dir)
        target_root.mkdir(parents=True, exist_ok=True)
        target_path = target_root / package.name
        if target_path.exists():
            raise SkillValidationError(
                f"Target skill '{target_path}' already exists.",
            )
        shutil.copytree(Path(package.root_path), target_path)
        installed_package = self._load_explicit_skill_dir(
            skill_dir=target_path,
            source=scope.value,
        )
        if installed_package is None:
            raise SkillValidationError(
                f"Installed skill at '{target_path}' could not be reloaded.",
            )
        return InstalledSkill(
            package=installed_package,
            scope=scope,
            target_root=str(target_root),
            target_path=str(target_path),
        )

    def _package_by_name(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
    ) -> SkillPackage:
        normalized_name = skill_name.strip()
        for package in self.list_available(workspace_dir=workspace_dir):
            if package.name == normalized_name:
                return package
        raise SkillNotFoundError(f"Skill '{normalized_name}' is not available.")

    def _skill_roots(
        self,
        workspace_dir: str | None,
    ) -> tuple[tuple[Path, str], ...]:
        roots: list[tuple[Path, str]] = []
        workspace_root = self._resolve_workspace_root(workspace_dir)
        if workspace_root is not None:
            for relative_root in DEFAULT_WORKSPACE_SKILL_ROOTS:
                roots.append((workspace_root / relative_root, "workspace"))
        roots.append((self._normalize_skill_root(self._global_root), "global"))
        roots.append((self._normalize_skill_root(self._system_root), "system"))
        return tuple(roots)

    def _resolve_install_root(
        self,
        *,
        scope: SkillInstallScope,
        workspace_dir: str | None,
    ) -> Path:
        if scope is SkillInstallScope.WORKSPACE:
            workspace_root = self._resolve_workspace_root(workspace_dir)
            if workspace_root is None:
                raise SkillValidationError(
                    "A readable workspace_dir is required for workspace skill installs.",
                )
            return workspace_root / DEFAULT_MANAGED_WORKSPACE_SKILL_ROOT
        return self._normalize_skill_root(self._global_root)

    @staticmethod
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

    @staticmethod
    def _normalize_skill_root(root: Path) -> Path:
        try:
            return root.expanduser().resolve(strict=False)
        except OSError:
            return root.expanduser()

    def _resolve_skill_directory(self, *, path: str, label: str) -> Path:
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

    def _discover_root_skills(
        self,
        *,
        root: Path,
        source: str,
    ) -> tuple[SkillPackage, ...]:
        discovered: list[SkillPackage] = []
        try:
            children = sorted(
                (path for path in root.iterdir() if path.is_dir()),
                key=lambda item: item.name,
            )
        except OSError:
            return ()
        for skill_dir in children:
            package = self._load_skill_package(root=root, skill_dir=skill_dir, source=source)
            if package is not None:
                discovered.append(package)
        return tuple(discovered)

    def _load_skill_package(
        self,
        *,
        root: Path,
        skill_dir: Path,
        source: str,
    ) -> SkillPackage | None:
        manifest_file = skill_dir / DEFAULT_SKILL_MANIFEST_FILENAME
        try:
            manifest_path = manifest_file.resolve(strict=True)
        except OSError:
            return None
        if not self._is_within_root(root=root, target=manifest_path):
            return None
        try:
            manifest_payload = yaml.safe_load(
                self._read_text_file(
                    manifest_path,
                    label=f"Skill manifest '{manifest_file.name}'",
                )
            )
        except SkillValidationError:
            return None
        if not isinstance(manifest_payload, dict):
            return None
        try:
            manifest = self._parse_manifest(manifest_payload)
        except SkillValidationError:
            return None
        try:
            root_path = skill_dir.resolve(strict=True)
        except OSError:
            return None
        instructions_path = self._resolve_instructions_path(
            root=root_path,
            relative_path=manifest.instructions_path,
        )
        if instructions_path is None:
            return None
        return SkillPackage(
            manifest=manifest,
            root_path=str(root_path),
            manifest_path=str(manifest_path),
            instructions_path=str(instructions_path),
            source=source,
        )

    def _load_explicit_skill_dir(
        self,
        *,
        skill_dir: Path,
        source: str,
    ) -> SkillPackage | None:
        return self._load_skill_package(
            root=skill_dir.parent,
            skill_dir=skill_dir,
            source=source,
        )

    def _parse_manifest(self, payload: dict[str, Any]) -> SkillManifest:
        api_version = self._required_string(payload.get("apiVersion"), "apiVersion")
        kind = self._required_string(payload.get("kind"), "kind")
        metadata = payload.get("metadata")
        spec = payload.get("spec")
        if not isinstance(metadata, dict):
            raise SkillValidationError("Skill manifest metadata must be a mapping.")
        if not isinstance(spec, dict):
            raise SkillValidationError("Skill manifest spec must be a mapping.")
        name = self._required_string(metadata.get("name"), "metadata.name")
        description = self._normalize_description(
            self._required_string(metadata.get("description"), "metadata.description")
        )
        version = self._optional_string(metadata.get("version"))
        tags = self._normalize_string_sequence(metadata.get("tags"))
        instructions_path = self._required_string(spec.get("instructions"), "spec.instructions")
        dependencies = spec.get("dependencies")
        runtime = spec.get("runtime")
        dependencies = dependencies if isinstance(dependencies, dict) else {}
        runtime = runtime if isinstance(runtime, dict) else {}
        tools = dependencies.get("tools")
        tools = tools if isinstance(tools, dict) else {}
        return SkillManifest(
            api_version=api_version,
            kind=kind,
            name=name,
            description=description,
            version=version,
            tags=tags,
            instructions_path=instructions_path,
            required_tools=self._normalize_string_sequence(tools.get("required")),
            optional_tools=self._normalize_string_sequence(tools.get("optional")),
            allowed_tools=self._normalize_string_sequence(runtime.get("allowed_tools")),
        )

    @staticmethod
    def _is_within_root(*, root: Path, target: Path) -> bool:
        try:
            target.relative_to(root)
        except ValueError:
            return False
        return True

    def _resolve_instructions_path(self, *, root: Path, relative_path: str) -> Path | None:
        try:
            candidate = (root / relative_path).resolve(strict=True)
        except OSError:
            return None
        if not self._is_within_root(root=root, target=candidate):
            return None
        if not candidate.is_file():
            return None
        return candidate

    def _resolve_package_file_path(
        self,
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
        if not self._is_within_root(root=root, target=candidate):
            raise SkillValidationError(
                f"Skill file '{relative_path}' escapes the skill package root.",
            )
        if not candidate.is_file():
            raise SkillValidationError(
                f"Skill file '{relative_path}' is not a readable file.",
            )
        return candidate

    @staticmethod
    def _required_string(value: Any, field_name: str) -> str:
        if not isinstance(value, str):
            raise SkillValidationError(f"Skill manifest field '{field_name}' must be a string.")
        normalized = value.strip()
        if not normalized:
            raise SkillValidationError(f"Skill manifest field '{field_name}' is required.")
        return normalized

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None or isinstance(value, bool):
            return None
        normalized = str(value).strip()
        return normalized or None

    @staticmethod
    def _normalize_string_sequence(value: Any) -> tuple[str, ...]:
        if isinstance(value, str):
            normalized = value.strip()
            return (normalized,) if normalized else ()
        if not isinstance(value, list):
            return ()
        items: list[str] = []
        for raw_item in value:
            if not isinstance(raw_item, str):
                continue
            normalized = raw_item.strip()
            if not normalized or normalized in items:
                continue
            items.append(normalized)
        return tuple(items)

    @staticmethod
    def _normalize_description(content: str) -> str:
        normalized = " ".join(content.strip().split())
        if len(normalized) <= MAX_SKILL_DESCRIPTION_CHARS:
            return normalized
        return f"{normalized[: MAX_SKILL_DESCRIPTION_CHARS - 1].rstrip()}..."

    @staticmethod
    def _read_text_file(path: Path, *, label: str) -> str:
        try:
            if not path.is_file():
                raise SkillValidationError(f"{label} is not backed by a readable file.")
            if path.stat().st_size > MAX_SKILL_FILE_BYTES:
                raise SkillValidationError(f"{label} is too large to load.")
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise SkillValidationError(f"{label} could not be read.") from exc
