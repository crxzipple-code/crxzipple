from __future__ import annotations

from pathlib import Path

from crxzipple.modules.skills.application.models import (
    SkillCreateRequest,
    SkillPackage,
    SkillUpdateRequest,
)
from crxzipple.modules.skills.domain import (
    SkillManifest,
    SkillValidationError,
)
from crxzipple.modules.skills.infrastructure.filesystem.manifest_parser import (
    normalize_access_requirement_sequence,
    normalize_string_sequence,
    normalize_tool_function_ids,
    render_skill_markdown,
    strip_markdown_frontmatter,
)
from crxzipple.modules.skills.infrastructure.filesystem.package_files import (
    read_text_file,
)
from crxzipple.modules.skills.infrastructure.filesystem.path_safety import (
    is_within_root,
    resolve_instructions_path,
)


def ensure_writable_package(package: SkillPackage) -> None:
    if package.source == "system":
        raise SkillValidationError(
            f"Skill '{package.name}' is from a readonly system source and cannot be changed.",
        )


def read_existing_instruction_body(package: SkillPackage) -> str:
    content = read_text_file(
        Path(package.instructions_path),
        label=f"Skill '{package.name}' instructions",
    )
    return strip_markdown_frontmatter(content).strip()


def materialize_current_manifest(
    *,
    target_path: Path,
    manifest: SkillManifest,
    legacy_manifest_filename: str,
) -> None:
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
    legacy_manifest_path = target_path / legacy_manifest_filename
    try:
        resolved_legacy_manifest = legacy_manifest_path.resolve(strict=True)
    except OSError:
        return
    if is_within_root(root=target_path, target=resolved_legacy_manifest):
        resolved_legacy_manifest.unlink()


def create_manifest(
    *,
    request: SkillCreateRequest,
    name: str,
) -> SkillManifest:
    return SkillManifest(
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


def updated_manifest(
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
