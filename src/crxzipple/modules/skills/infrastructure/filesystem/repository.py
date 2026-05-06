from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import yaml

from crxzipple.modules.skills.application.models import (
    InstalledSkill,
    SkillPackage,
    SkillReadResult,
    SkillResource,
)
from crxzipple.modules.skills.domain import (
    SkillInstallScope,
    SkillManifest,
    SkillNotFoundError,
    SkillValidationError,
)


DEFAULT_SKILL_MANIFEST_FILENAME = "skill.yaml"
DEFAULT_SKILL_INSTRUCTIONS_FILENAME = "SKILL.md"
DEFAULT_SKILL_RESOURCE_DIRS = ("references", "templates", "assets", "scripts")
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
        if requested_path == package.manifest.instructions_path:
            content = self._strip_markdown_frontmatter(content).strip()
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
        try:
            root_path = skill_dir.resolve(strict=True)
        except OSError:
            return None
        if not self._is_within_root(root=root, target=root_path):
            return None
        instructions_path = self._resolve_instructions_path(
            root=root_path,
            relative_path=DEFAULT_SKILL_INSTRUCTIONS_FILENAME,
        )
        if instructions_path is None:
            return None
        legacy_manifest_path, legacy_payload = self._load_legacy_manifest(
            root=root,
            skill_dir=skill_dir,
        )
        frontmatter_payload = self._load_skill_frontmatter(instructions_path)
        if frontmatter_payload is None and legacy_payload is None:
            return None
        manifest_path = instructions_path if frontmatter_payload is not None else legacy_manifest_path
        if manifest_path is None:
            return None
        try:
            manifest = self._parse_normalized_manifest(
                frontmatter_payload=frontmatter_payload,
                legacy_payload=legacy_payload,
            )
        except SkillValidationError:
            return None
        resolved_instructions_path = self._resolve_instructions_path(
            root=root_path,
            relative_path=manifest.instructions_path,
        )
        if resolved_instructions_path is None:
            return None
        return SkillPackage(
            manifest=manifest,
            root_path=str(root_path),
            manifest_path=str(manifest_path),
            instructions_path=str(resolved_instructions_path),
            source=source,
            resources=self._discover_resources(root=root_path),
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

    def _load_legacy_manifest(
        self,
        *,
        root: Path,
        skill_dir: Path,
    ) -> tuple[Path | None, dict[str, Any] | None]:
        manifest_file = skill_dir / DEFAULT_SKILL_MANIFEST_FILENAME
        try:
            manifest_path = manifest_file.resolve(strict=True)
        except OSError:
            return None, None
        if not self._is_within_root(root=root, target=manifest_path):
            return None, None
        try:
            payload = yaml.safe_load(
                self._read_text_file(
                    manifest_path,
                    label=f"Skill manifest '{manifest_file.name}'",
                )
            )
        except SkillValidationError:
            return None, None
        if not isinstance(payload, dict):
            return None, None
        return manifest_path, payload

    def _load_skill_frontmatter(self, instructions_path: Path) -> dict[str, Any] | None:
        try:
            content = self._read_text_file(
                instructions_path,
                label=f"Skill instructions '{instructions_path.name}'",
            )
        except SkillValidationError:
            return None
        lines = content.splitlines()
        if not lines or lines[0].strip() != "---":
            return None
        closing_index = next(
            (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
            None,
        )
        if closing_index is None:
            return None
        payload = yaml.safe_load("\n".join(lines[1:closing_index])) or {}
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _strip_markdown_frontmatter(content: str) -> str:
        lines = content.splitlines()
        if not lines or lines[0].strip() != "---":
            return content
        closing_index = next(
            (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
            None,
        )
        if closing_index is None:
            return content
        return "\n".join(lines[closing_index + 1 :])

    def _parse_normalized_manifest(
        self,
        *,
        frontmatter_payload: dict[str, Any] | None,
        legacy_payload: dict[str, Any] | None,
    ) -> SkillManifest:
        legacy = self._parse_manifest(legacy_payload) if legacy_payload is not None else None
        if frontmatter_payload is None:
            if legacy is None:
                raise SkillValidationError("Skill package must define SKILL.md frontmatter.")
            return legacy
        name = self._optional_string(frontmatter_payload.get("name")) or (
            legacy.name if legacy is not None else None
        )
        if name is None:
            raise SkillValidationError("Skill frontmatter field 'name' is required.")
        description = self._optional_string(frontmatter_payload.get("description")) or (
            legacy.description if legacy is not None else None
        )
        if description is None:
            raise SkillValidationError("Skill frontmatter field 'description' is required.")
        setup = frontmatter_payload.get("setup")
        setup = setup if isinstance(setup, dict) else {}
        legacy_suggested_tools = (
            legacy.suggested_tools or legacy.allowed_tools
        ) if legacy is not None else ()
        suggested_tools = (
            self._normalize_string_sequence(frontmatter_payload.get("suggested_tools"))
            or self._normalize_string_sequence(frontmatter_payload.get("preferred_tools"))
            or self._normalize_string_sequence(frontmatter_payload.get("allowed_tools"))
            or legacy_suggested_tools
        )
        required_secrets = self._normalize_requirement_sequence(
            frontmatter_payload.get("required_secrets"),
        ) + self._normalize_requirement_sequence(
            frontmatter_payload.get("required_environment_variables"),
        )
        return SkillManifest(
            api_version=self._optional_string(frontmatter_payload.get("apiVersion"))
            or (legacy.api_version if legacy is not None else "skills.crxzipple/v1alpha1"),
            kind=self._optional_string(frontmatter_payload.get("kind"))
            or (legacy.kind if legacy is not None else "Skill"),
            name=name,
            description=self._normalize_description(description),
            version=self._optional_string(frontmatter_payload.get("version"))
            or (legacy.version if legacy is not None else None),
            tags=self._normalize_string_sequence(frontmatter_payload.get("tags"))
            or (legacy.tags if legacy is not None else ()),
            when_to_use=self._optional_string(frontmatter_payload.get("when_to_use"))
            or self._optional_string(frontmatter_payload.get("whenToUse"))
            or (legacy.when_to_use if legacy is not None else None),
            anti_patterns=self._normalize_string_sequence(
                frontmatter_payload.get("anti_patterns"),
            )
            or (legacy.anti_patterns if legacy is not None else ()),
            instructions_path=self._optional_string(
                frontmatter_payload.get("instructions_path"),
            )
            or self._optional_string(frontmatter_payload.get("instructions"))
            or (
                legacy.instructions_path
                if legacy is not None
                else DEFAULT_SKILL_INSTRUCTIONS_FILENAME
            ),
            required_tools=self._normalize_string_sequence(
                frontmatter_payload.get("required_tools"),
            )
            or (legacy.required_tools if legacy is not None else ()),
            optional_tools=self._normalize_string_sequence(
                frontmatter_payload.get("optional_tools"),
            )
            or (legacy.optional_tools if legacy is not None else ()),
            suggested_tools=suggested_tools,
            allowed_tools=suggested_tools,
            required_effects=self._normalize_string_sequence(
                frontmatter_payload.get("required_effects"),
            )
            or (legacy.required_effects if legacy is not None else ()),
            required_auth=self._normalize_requirement_sequence(
                frontmatter_payload.get("required_auth"),
            )
            or (legacy.required_auth if legacy is not None else ()),
            required_secrets=tuple(dict.fromkeys(required_secrets))
            or (legacy.required_secrets if legacy is not None else ()),
            required_credential_files=self._normalize_requirement_sequence(
                frontmatter_payload.get("required_credential_files"),
            )
            or (legacy.required_credential_files if legacy is not None else ()),
            surfaces=self._normalize_string_sequence(frontmatter_payload.get("surfaces"))
            or (legacy.surfaces if legacy is not None else ()),
            setup_hints=self._normalize_string_sequence(frontmatter_payload.get("setup_hints"))
            or self._normalize_string_sequence(setup.get("help"))
            or (legacy.setup_hints if legacy is not None else ()),
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
        allowed_tools = self._normalize_string_sequence(runtime.get("allowed_tools"))
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
            suggested_tools=allowed_tools,
            allowed_tools=allowed_tools,
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

    def _discover_resources(self, *, root: Path) -> tuple[SkillResource, ...]:
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
                if not self._is_within_root(root=root, target=resolved):
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

    @classmethod
    def _normalize_requirement_sequence(cls, value: Any) -> tuple[str, ...]:
        if isinstance(value, str):
            normalized = value.strip()
            return (normalized,) if normalized else ()
        if isinstance(value, dict):
            item = cls._normalize_requirement_mapping(value)
            return (item,) if item else ()
        if not isinstance(value, list):
            return ()
        items: list[str] = []
        for raw_item in value:
            normalized = ""
            if isinstance(raw_item, str):
                normalized = raw_item.strip()
            elif isinstance(raw_item, dict):
                normalized = cls._normalize_requirement_mapping(raw_item)
            if not normalized or normalized in items:
                continue
            items.append(normalized)
        return tuple(items)

    @staticmethod
    def _normalize_requirement_mapping(value: dict[str, Any]) -> str:
        provider = str(value.get("provider") or "").strip()
        kind = str(value.get("kind") or "").strip()
        name = str(
            value.get("name")
            or value.get("env")
            or value.get("env_var")
            or value.get("path")
            or "",
        ).strip()
        if provider:
            label = f"{provider}:{kind}" if kind else provider
        else:
            label = name or kind
        scopes = FilesystemSkillRepository._normalize_string_sequence(value.get("scopes"))
        if label and scopes:
            return f"{label}({','.join(scopes)})"
        return label

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
