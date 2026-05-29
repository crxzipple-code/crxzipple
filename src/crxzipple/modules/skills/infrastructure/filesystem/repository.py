from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
from pathlib import Path
import shutil
from typing import Any

import yaml

from crxzipple.modules.skills.application.models import (
    InstalledSkill,
    SkillCreateRequest,
    SkillMutationResult,
    SkillPackage,
    SkillReadResult,
    SkillResource,
    SkillUpdateRequest,
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


@dataclass(frozen=True, slots=True)
class FilesystemSkillSourceRoot:
    source_id: str
    root_path: str


FilesystemSkillSourceProvider = Callable[[], tuple[FilesystemSkillSourceRoot, ...]]


class FilesystemSkillRepository:
    def __init__(
        self,
        *,
        global_root: Path | None = None,
        system_root: Path | None = None,
        source_provider: FilesystemSkillSourceProvider | None = None,
    ) -> None:
        self._global_root = global_root or DEFAULT_GLOBAL_SKILLS_DIR
        self._system_root = system_root or DEFAULT_SYSTEM_SKILLS_DIR
        self._source_provider = source_provider

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
        package = self._load_explicit_skill_dir(
            skill_dir=skill_dir,
            source="validation",
            strict=True,
            allow_legacy_manifest=True,
        )
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
        self._materialize_current_manifest(target_path=target_path, manifest=package.manifest)
        installed_package = self._load_explicit_skill_dir(
            skill_dir=target_path,
            source=scope.value,
            strict=True,
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

    def create(self, request: SkillCreateRequest) -> SkillMutationResult:
        name = self._normalize_skill_name(request.name)
        target_root = self._resolve_install_root(
            scope=request.scope,
            workspace_dir=request.workspace_dir,
        )
        target_root.mkdir(parents=True, exist_ok=True)
        target_path = target_root / name
        if target_path.exists():
            raise SkillValidationError(
                f"Target skill '{target_path}' already exists.",
            )
        manifest = SkillManifest(
            api_version="skills.crxzipple/v1alpha1",
            kind="Skill",
            name=name,
            description=request.description,
            version=request.version,
            tags=request.tags,
            required_tools=self._normalize_tool_function_ids(request.required_tools),
            optional_tools=self._normalize_tool_function_ids(request.optional_tools),
            suggested_tools=self._normalize_tool_function_ids(request.suggested_tools),
            allowed_tools=self._normalize_tool_function_ids(request.suggested_tools),
            required_effects=request.required_effects,
            required_access=self._normalize_access_requirement_sequence(
                request.required_access,
            ),
            surfaces=request.surfaces,
            supported_platforms=self._normalize_string_sequence(
                request.supported_platforms,
            ),
            setup_hints=request.setup_hints,
        )
        target_path.mkdir(parents=True)
        (target_path / DEFAULT_SKILL_INSTRUCTIONS_FILENAME).write_text(
            self._render_skill_markdown(
                manifest=manifest,
                body=request.instructions,
            ),
            encoding="utf-8",
        )
        package = self._load_explicit_skill_dir(
            skill_dir=target_path,
            source=request.scope.value,
        )
        if package is None:
            raise SkillValidationError(
                f"Created skill at '{target_path}' could not be loaded.",
            )
        return SkillMutationResult(
            skill=package,
            action="create",
            changed=True,
            message=f"Skill '{package.name}' created.",
        )

    def update(self, request: SkillUpdateRequest) -> SkillMutationResult:
        package = self._package_by_name(
            workspace_dir=request.workspace_dir,
            skill_name=request.skill_name,
        )
        self._ensure_writable_package(package)
        manifest = self._updated_manifest(package.manifest, request)
        body = self._read_existing_instruction_body(package)
        Path(package.instructions_path).write_text(
            self._render_skill_markdown(manifest=manifest, body=body),
            encoding="utf-8",
        )
        updated_package = self._package_by_name(
            workspace_dir=request.workspace_dir,
            skill_name=package.name,
        )
        return SkillMutationResult(
            skill=updated_package,
            action="update",
            changed=True,
            message=f"Skill '{updated_package.name}' updated.",
        )

    def write_instructions(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        content: str,
    ) -> SkillMutationResult:
        package = self._package_by_name(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
        )
        self._ensure_writable_package(package)
        Path(package.instructions_path).write_text(
            self._render_skill_markdown(
                manifest=package.manifest,
                body=content,
            ),
            encoding="utf-8",
        )
        updated_package = self._package_by_name(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
        )
        return SkillMutationResult(
            skill=updated_package,
            action="write_instructions",
            changed=True,
            message=f"Skill '{updated_package.name}' instructions updated.",
        )

    def write_file(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        path: str,
        content: str,
    ) -> SkillMutationResult:
        package = self._package_by_name(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
        )
        self._ensure_writable_package(package)
        relative_path = self._normalize_support_file_path(package=package, path=path)
        target_path = (Path(package.root_path) / relative_path).resolve(strict=False)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        updated_package = self._package_by_name(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
        )
        return SkillMutationResult(
            skill=updated_package,
            action="write_file",
            changed=True,
            message=f"Skill file '{relative_path}' updated.",
        )

    def delete_file(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        path: str,
    ) -> SkillMutationResult:
        package = self._package_by_name(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
        )
        self._ensure_writable_package(package)
        relative_path = self._normalize_support_file_path(package=package, path=path)
        target_path = (Path(package.root_path) / relative_path).resolve(strict=True)
        if not target_path.is_file():
            raise SkillValidationError(f"Skill file '{relative_path}' is not a file.")
        target_path.unlink()
        updated_package = self._package_by_name(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
        )
        return SkillMutationResult(
            skill=updated_package,
            action="delete_file",
            changed=True,
            message=f"Skill file '{relative_path}' deleted.",
        )

    def delete(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
    ) -> SkillMutationResult:
        package = self._package_by_name(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
        )
        if package.source == "system":
            raise SkillValidationError(
                f"Skill '{package.name}' is from a readonly system source and cannot be deleted.",
            )
        root_path = Path(package.root_path)
        if not root_path.is_dir():
            raise SkillValidationError(
                f"Skill '{package.name}' root '{root_path}' is not a directory.",
            )
        try:
            shutil.rmtree(root_path)
        except OSError as exc:
            raise SkillValidationError(
                f"Skill '{package.name}' could not be deleted from '{root_path}'.",
            ) from exc
        return SkillMutationResult(
            skill=package,
            action="delete",
            changed=True,
            message=f"Skill '{package.name}' deleted.",
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
        roots.extend(self._provided_skill_roots())
        roots.append((self._normalize_skill_root(self._system_root), "system"))
        return tuple(roots)

    def _provided_skill_roots(self) -> tuple[tuple[Path, str], ...]:
        if self._source_provider is None:
            return ()
        roots: list[tuple[Path, str]] = []
        for source in self._source_provider():
            source_id = source.source_id.strip()
            if source_id in {"workspace", "global", "system"}:
                continue
            if not source_id:
                continue
            root_path = source.root_path.strip()
            if not root_path:
                continue
            roots.append((self._normalize_skill_root(Path(root_path)), source_id))
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
        direct_package = self._load_explicit_skill_dir(skill_dir=root, source=source)
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
        strict: bool = False,
        allow_legacy_manifest: bool = False,
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
        legacy_manifest_path, legacy_payload = (
            self._load_legacy_manifest(root=root, skill_dir=skill_dir)
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
            manifest = self._parse_normalized_manifest(
                frontmatter_payload=frontmatter_payload,
                legacy_payload=legacy_payload,
            )
        except SkillValidationError:
            if strict:
                raise
            return None
        resolved_instructions_path = self._resolve_instructions_path(
            root=root_path,
            relative_path=manifest.instructions_path,
        )
        if resolved_instructions_path is None:
            return None
        resources = self._discover_resources(root=root_path)
        return SkillPackage(
            manifest=manifest,
            root_path=str(root_path),
            manifest_path=str(manifest_path),
            instructions_path=str(resolved_instructions_path),
            source=source,
            resources=resources,
            fingerprint=self._fingerprint_package(
                root=root_path,
                manifest_path=manifest_path,
                instructions_path=resolved_instructions_path,
                resources=resources,
                source=source,
                name=manifest.name,
                version=manifest.version,
            ),
        )

    def _load_explicit_skill_dir(
        self,
        *,
        skill_dir: Path,
        source: str,
        strict: bool = False,
        allow_legacy_manifest: bool = False,
    ) -> SkillPackage | None:
        return self._load_skill_package(
            root=skill_dir.parent,
            skill_dir=skill_dir,
            source=source,
            strict=strict,
            allow_legacy_manifest=allow_legacy_manifest,
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
        if frontmatter_payload is None:
            legacy = self._parse_manifest(legacy_payload) if legacy_payload is not None else None
            if legacy is None:
                raise SkillValidationError("Skill package must define SKILL.md frontmatter.")
            return legacy
        name = self._optional_string(frontmatter_payload.get("name"))
        if name is None:
            raise SkillValidationError("Skill frontmatter field 'name' is required.")
        description = self._optional_string(frontmatter_payload.get("description"))
        if description is None:
            raise SkillValidationError("Skill frontmatter field 'description' is required.")
        self._reject_legacy_access_fields(frontmatter_payload)
        setup = frontmatter_payload.get("setup")
        setup = setup if isinstance(setup, dict) else {}
        suggested_tools = (
            self._normalize_tool_function_ids(frontmatter_payload.get("suggested_tools"))
            or self._normalize_tool_function_ids(frontmatter_payload.get("preferred_tools"))
            or self._normalize_tool_function_ids(frontmatter_payload.get("allowed_tools"))
        )
        return SkillManifest(
            api_version=self._optional_string(frontmatter_payload.get("apiVersion"))
            or "skills.crxzipple/v1alpha1",
            kind=self._optional_string(frontmatter_payload.get("kind"))
            or "Skill",
            name=name,
            description=self._normalize_description(description),
            version=self._optional_string(frontmatter_payload.get("version")),
            tags=self._normalize_string_sequence(frontmatter_payload.get("tags")),
            when_to_use=self._optional_string(frontmatter_payload.get("when_to_use"))
            or self._optional_string(frontmatter_payload.get("whenToUse")),
            anti_patterns=self._normalize_string_sequence(
                frontmatter_payload.get("anti_patterns"),
            ),
            instructions_path=self._optional_string(
                frontmatter_payload.get("instructions_path"),
            )
            or self._optional_string(frontmatter_payload.get("instructions"))
            or DEFAULT_SKILL_INSTRUCTIONS_FILENAME,
            required_tools=self._normalize_tool_function_ids(
                frontmatter_payload.get("required_tools"),
            ),
            optional_tools=self._normalize_tool_function_ids(
                frontmatter_payload.get("optional_tools"),
            ),
            suggested_tools=suggested_tools,
            allowed_tools=suggested_tools,
            required_effects=self._normalize_string_sequence(
                frontmatter_payload.get("required_effects"),
            ),
            required_access=self._normalize_access_requirement_sequence(
                frontmatter_payload.get("required_access"),
            ),
            surfaces=self._normalize_string_sequence(frontmatter_payload.get("surfaces")),
            supported_platforms=self._normalize_string_sequence(
                frontmatter_payload.get("supported_platforms"),
            )
            or self._normalize_string_sequence(frontmatter_payload.get("platforms")),
            setup_hints=self._normalize_string_sequence(frontmatter_payload.get("setup_hints"))
            or self._normalize_string_sequence(setup.get("help")),
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
            required_tools=self._normalize_tool_function_ids(tools.get("required")),
            optional_tools=self._normalize_tool_function_ids(tools.get("optional")),
            suggested_tools=self._normalize_tool_function_ids(allowed_tools),
            allowed_tools=self._normalize_tool_function_ids(allowed_tools),
            supported_platforms=self._normalize_string_sequence(
                runtime.get("supported_platforms"),
            )
            or self._normalize_string_sequence(runtime.get("platforms")),
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

    def _normalize_support_file_path(
        self,
        *,
        package: SkillPackage,
        path: str,
    ) -> str:
        normalized = path.strip().replace("\\", "/")
        if not normalized:
            raise SkillValidationError("Skill file path is required.")
        if normalized.startswith("/") or normalized in {".", ".."}:
            raise SkillValidationError("Skill file path must be package-relative.")
        root = Path(package.root_path)
        candidate = (root / normalized).resolve(strict=False)
        try:
            candidate.relative_to(root.resolve(strict=True))
        except (OSError, ValueError) as exc:
            raise SkillValidationError(
                f"Skill file '{normalized}' escapes the skill package root.",
            ) from exc
        if normalized == package.manifest.instructions_path:
            raise SkillValidationError(
                "Use the instructions endpoint to update the skill instructions file.",
            )
        if not any(
            normalized == resource_dir or normalized.startswith(f"{resource_dir}/")
            for resource_dir in DEFAULT_SKILL_RESOURCE_DIRS
        ):
            allowed = ", ".join(DEFAULT_SKILL_RESOURCE_DIRS)
            raise SkillValidationError(
                f"Skill support files must live under one of: {allowed}.",
            )
        return normalized

    @staticmethod
    def _normalize_skill_name(name: str) -> str:
        normalized = name.strip()
        if not normalized:
            raise SkillValidationError("Skill name is required.")
        if normalized in {".", ".."} or "/" in normalized or "\\" in normalized:
            raise SkillValidationError("Skill name must be a package-safe identifier.")
        return normalized

    @staticmethod
    def _ensure_writable_package(package: SkillPackage) -> None:
        if package.source == "system":
            raise SkillValidationError(
                f"Skill '{package.name}' is from a readonly system source and cannot be changed.",
            )

    def _read_existing_instruction_body(self, package: SkillPackage) -> str:
        content = self._read_text_file(
            Path(package.instructions_path),
            label=f"Skill '{package.name}' instructions",
        )
        return self._strip_markdown_frontmatter(content).strip()

    def _materialize_current_manifest(self, *, target_path: Path, manifest: SkillManifest) -> None:
        instructions_path = self._resolve_instructions_path(
            root=target_path,
            relative_path=manifest.instructions_path,
        )
        if instructions_path is None:
            raise SkillValidationError(
                f"Installed skill '{target_path}' is missing '{manifest.instructions_path}'.",
            )
        body = self._strip_markdown_frontmatter(
            self._read_text_file(
                instructions_path,
                label=f"Skill '{manifest.name}' instructions",
            ),
        ).strip()
        instructions_path.write_text(
            self._render_skill_markdown(manifest=manifest, body=body),
            encoding="utf-8",
        )
        legacy_manifest_path = target_path / DEFAULT_SKILL_MANIFEST_FILENAME
        try:
            resolved_legacy_manifest = legacy_manifest_path.resolve(strict=True)
        except OSError:
            return
        if self._is_within_root(root=target_path, target=resolved_legacy_manifest):
            resolved_legacy_manifest.unlink()

    def _updated_manifest(
        self,
        manifest: SkillManifest,
        request: SkillUpdateRequest,
    ) -> SkillManifest:
        return SkillManifest(
            api_version=manifest.api_version,
            kind=manifest.kind,
            name=manifest.name,
            description=request.description if request.description is not None else manifest.description,
            version=request.version if request.version is not None else manifest.version,
            tags=request.tags if request.tags is not None else manifest.tags,
            when_to_use=manifest.when_to_use,
            anti_patterns=manifest.anti_patterns,
            instructions_path=manifest.instructions_path,
            required_tools=(
                self._normalize_tool_function_ids(request.required_tools)
                if request.required_tools is not None
                else manifest.required_tools
            ),
            optional_tools=(
                self._normalize_tool_function_ids(request.optional_tools)
                if request.optional_tools is not None
                else manifest.optional_tools
            ),
            suggested_tools=(
                self._normalize_tool_function_ids(request.suggested_tools)
                if request.suggested_tools is not None
                else manifest.suggested_tools
            ),
            allowed_tools=(
                self._normalize_tool_function_ids(request.suggested_tools)
                if request.suggested_tools is not None
                else manifest.allowed_tools
            ),
            required_effects=(
                request.required_effects
                if request.required_effects is not None
                else manifest.required_effects
            ),
            required_access=(
                self._normalize_access_requirement_sequence(request.required_access)
                if request.required_access is not None
                else manifest.required_access
            ),
            surfaces=request.surfaces if request.surfaces is not None else manifest.surfaces,
            supported_platforms=(
                self._normalize_string_sequence(request.supported_platforms)
                if request.supported_platforms is not None
                else manifest.supported_platforms
            ),
            setup_hints=(
                request.setup_hints
                if request.setup_hints is not None
                else manifest.setup_hints
            ),
        )

    def _render_skill_markdown(self, *, manifest: SkillManifest, body: str) -> str:
        payload = self._manifest_frontmatter_payload(manifest)
        frontmatter = yaml.safe_dump(
            payload,
            sort_keys=False,
            allow_unicode=True,
        ).strip()
        normalized_body = body.strip()
        return f"---\n{frontmatter}\n---\n\n{normalized_body}\n"

    @staticmethod
    def _manifest_frontmatter_payload(manifest: SkillManifest) -> dict[str, object]:
        payload: dict[str, object] = {
            "apiVersion": manifest.api_version,
            "kind": manifest.kind,
            "name": manifest.name,
            "description": manifest.description,
            "instructions_path": manifest.instructions_path,
        }
        optional_values: tuple[tuple[str, object | None], ...] = (
            ("version", manifest.version),
            ("tags", list(manifest.tags) or None),
            ("when_to_use", manifest.when_to_use),
            ("anti_patterns", list(manifest.anti_patterns) or None),
            ("required_tools", list(manifest.required_tools) or None),
            ("optional_tools", list(manifest.optional_tools) or None),
            ("suggested_tools", list(manifest.suggested_tools) or None),
            ("required_effects", list(manifest.required_effects) or None),
            ("required_access", list(manifest.required_access) or None),
            ("surfaces", list(manifest.surfaces) or None),
            ("supported_platforms", list(manifest.supported_platforms) or None),
            ("setup_hints", list(manifest.setup_hints) or None),
        )
        for key, value in optional_values:
            if value is not None:
                payload[key] = value
        return payload

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

    def _fingerprint_package(
        self,
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
            if self._is_within_root(root=root, target=path):
                file_paths[path.relative_to(root).as_posix()] = path
        for resource in resources:
            try:
                path = (root / resource.path).resolve(strict=True)
            except OSError:
                continue
            if self._is_within_root(root=root, target=path):
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
        if not isinstance(value, list | tuple):
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
    def _normalize_tool_function_ids(cls, value: Any) -> tuple[str, ...]:
        items = cls._normalize_string_sequence(value)
        for item in items:
            if item.startswith(("env:", "file:")) or item in {
                "codex_auth_json",
                "auth_ref",
            }:
                raise SkillValidationError(
                    "Skill required_tools must reference ToolFunction ids, not credential sources.",
                )
            if "/" in item or "\\" in item or any(character.isspace() for character in item):
                raise SkillValidationError(
                    f"Skill tool requirement '{item}' is not a valid ToolFunction id.",
                )
        return items

    @classmethod
    def _normalize_access_requirement_sequence(cls, value: Any) -> tuple[str, ...]:
        items = cls._normalize_requirement_sequence(value)
        for item in items:
            if item.startswith(("env:", "file:", "codex_auth_json", "auth_ref")):
                raise SkillValidationError(
                    "Skill required_access must reference Access bindings or requirements, not direct credential sources.",
                )
            if item.startswith(("~", "/")) or "\\" in item:
                raise SkillValidationError(
                    f"Skill access requirement '{item}' must not reference a local path.",
                )
        return items

    @staticmethod
    def _reject_legacy_access_fields(payload: dict[str, Any]) -> None:
        legacy_fields = (
            "required_auth",
            "required_secrets",
            "required_environment_variables",
            "required_credential_files",
        )
        present = [field for field in legacy_fields if field in payload]
        if present:
            joined = ", ".join(present)
            raise SkillValidationError(
                f"Skill frontmatter uses retired access fields: {joined}. Use required_access instead.",
            )

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
        name = str(value.get("name") or "").strip()
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
