from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import shutil

from crxzipple.modules.skills.application.models import (
    InstalledSkill,
    SkillCreateRequest,
    SkillMutationResult,
    SkillPackage,
    SkillReadResult,
    SkillUpdateRequest,
)
from crxzipple.modules.skills.domain import (
    SkillInstallScope,
    SkillManifest,
    SkillNotFoundError,
    SkillValidationError,
)
from crxzipple.modules.skills.infrastructure.filesystem.manifest_parser import (
    normalize_access_requirement_sequence,
    normalize_string_sequence,
    normalize_tool_function_ids,
    render_skill_markdown,
    strip_markdown_frontmatter,
)
from crxzipple.modules.skills.infrastructure.filesystem.package_loader import (
    SkillPackageLoader,
)
from crxzipple.modules.skills.infrastructure.filesystem.package_files import (
    DEFAULT_SKILL_RESOURCE_DIRS,
    read_text_file,
)
from crxzipple.modules.skills.infrastructure.filesystem.path_safety import (
    is_within_root,
    normalize_skill_name,
    normalize_skill_root,
    normalize_support_file_path,
    resolve_instructions_path,
    resolve_package_file_path,
    resolve_skill_directory,
    resolve_workspace_root,
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
MAX_SKILL_CONTENT_CHARS = 20_000


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
        self._loader = SkillPackageLoader(
            manifest_filename=DEFAULT_SKILL_MANIFEST_FILENAME,
            instructions_filename=DEFAULT_SKILL_INSTRUCTIONS_FILENAME,
        )

    def list_available(
        self,
        *,
        workspace_dir: str | None,
    ) -> tuple[SkillPackage, ...]:
        available: dict[str, SkillPackage] = {}
        for root, source in self._skill_roots(workspace_dir):
            if not root.is_dir():
                continue
            for package in self._loader.discover_root_skills(root=root, source=source):
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
        resolved_path = resolve_package_file_path(
            package=package,
            relative_path=requested_path,
        )
        content = read_text_file(
            resolved_path,
            label=f"Skill '{package.name}' file '{requested_path}'",
        ).strip()
        if requested_path == package.manifest.instructions_path:
            content = strip_markdown_frontmatter(content).strip()
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
        skill_dir = resolve_skill_directory(path=path, label="Skill package")
        package = self._loader.load_explicit_skill_dir(
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
        try:
            shutil.copytree(Path(package.root_path), target_path)
        except FileExistsError as exc:
            raise SkillValidationError(
                f"Target skill '{target_path}' already exists.",
            ) from exc
        self._materialize_current_manifest(target_path=target_path, manifest=package.manifest)
        installed_package = self._loader.load_explicit_skill_dir(
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
        name = normalize_skill_name(request.name)
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
            required_tools=normalize_tool_function_ids(request.required_tools),
            optional_tools=normalize_tool_function_ids(request.optional_tools),
            suggested_tools=normalize_tool_function_ids(request.suggested_tools),
            allowed_tools=normalize_tool_function_ids(request.suggested_tools),
            required_effects=request.required_effects,
            required_access=normalize_access_requirement_sequence(
                request.required_access,
            ),
            surfaces=request.surfaces,
            supported_platforms=normalize_string_sequence(
                request.supported_platforms,
            ),
            setup_hints=request.setup_hints,
        )
        try:
            target_path.mkdir(parents=True)
        except FileExistsError as exc:
            raise SkillValidationError(
                f"Target skill '{target_path}' already exists.",
            ) from exc
        (target_path / DEFAULT_SKILL_INSTRUCTIONS_FILENAME).write_text(
            render_skill_markdown(
                manifest=manifest,
                body=request.instructions,
            ),
            encoding="utf-8",
        )
        package = self._loader.load_explicit_skill_dir(
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
            render_skill_markdown(manifest=manifest, body=body),
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
            render_skill_markdown(
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
        relative_path = normalize_support_file_path(
            package=package,
            path=path,
            allowed_resource_dirs=DEFAULT_SKILL_RESOURCE_DIRS,
        )
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
        relative_path = normalize_support_file_path(
            package=package,
            path=path,
            allowed_resource_dirs=DEFAULT_SKILL_RESOURCE_DIRS,
        )
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
        workspace_root = resolve_workspace_root(workspace_dir)
        if workspace_root is not None:
            for relative_root in DEFAULT_WORKSPACE_SKILL_ROOTS:
                roots.append((workspace_root / relative_root, "workspace"))
        roots.append((normalize_skill_root(self._global_root), "global"))
        roots.extend(self._provided_skill_roots())
        roots.append((normalize_skill_root(self._system_root), "system"))
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
            roots.append((normalize_skill_root(Path(root_path)), source_id))
        return tuple(roots)

    def _resolve_install_root(
        self,
        *,
        scope: SkillInstallScope,
        workspace_dir: str | None,
    ) -> Path:
        if scope is SkillInstallScope.WORKSPACE:
            workspace_root = resolve_workspace_root(workspace_dir)
            if workspace_root is None:
                raise SkillValidationError(
                    "A readable workspace_dir is required for workspace skill installs.",
                )
            return workspace_root / DEFAULT_MANAGED_WORKSPACE_SKILL_ROOT
        return normalize_skill_root(self._global_root)

    @staticmethod
    def _ensure_writable_package(package: SkillPackage) -> None:
        if package.source == "system":
            raise SkillValidationError(
                f"Skill '{package.name}' is from a readonly system source and cannot be changed.",
            )

    def _read_existing_instruction_body(self, package: SkillPackage) -> str:
        content = read_text_file(
            Path(package.instructions_path),
            label=f"Skill '{package.name}' instructions",
        )
        return strip_markdown_frontmatter(content).strip()

    def _materialize_current_manifest(self, *, target_path: Path, manifest: SkillManifest) -> None:
        instructions_path = resolve_instructions_path(
            root=target_path,
            relative_path=manifest.instructions_path,
        )
        if instructions_path is None:
            raise SkillValidationError(
                f"Installed skill '{target_path}' is missing '{manifest.instructions_path}'.",
            )
        body = strip_markdown_frontmatter(
            read_text_file(
                instructions_path,
                label=f"Skill '{manifest.name}' instructions",
            ),
        ).strip()
        instructions_path.write_text(
            render_skill_markdown(manifest=manifest, body=body),
            encoding="utf-8",
        )
        legacy_manifest_path = target_path / DEFAULT_SKILL_MANIFEST_FILENAME
        try:
            resolved_legacy_manifest = legacy_manifest_path.resolve(strict=True)
        except OSError:
            return
        if is_within_root(root=target_path, target=resolved_legacy_manifest):
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
                normalize_tool_function_ids(request.required_tools)
                if request.required_tools is not None
                else manifest.required_tools
            ),
            optional_tools=(
                normalize_tool_function_ids(request.optional_tools)
                if request.optional_tools is not None
                else manifest.optional_tools
            ),
            suggested_tools=(
                normalize_tool_function_ids(request.suggested_tools)
                if request.suggested_tools is not None
                else manifest.suggested_tools
            ),
            allowed_tools=(
                normalize_tool_function_ids(request.suggested_tools)
                if request.suggested_tools is not None
                else manifest.allowed_tools
            ),
            required_effects=(
                request.required_effects
                if request.required_effects is not None
                else manifest.required_effects
            ),
            required_access=(
                normalize_access_requirement_sequence(request.required_access)
                if request.required_access is not None
                else manifest.required_access
            ),
            surfaces=request.surfaces if request.surfaces is not None else manifest.surfaces,
            supported_platforms=(
                normalize_string_sequence(request.supported_platforms)
                if request.supported_platforms is not None
                else manifest.supported_platforms
            ),
            setup_hints=(
                request.setup_hints
                if request.setup_hints is not None
                else manifest.setup_hints
            ),
        )
