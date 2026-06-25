from __future__ import annotations

from crxzipple.modules.skills.application.models import (
    SkillCreateRequest,
    SkillDraft,
    SkillPackage,
    SkillUpdateRequest,
)
from crxzipple.modules.skills.domain import (
    SkillManifest,
    SkillRequirements,
    SkillValidationError,
)


def resolve_draft_skill_name(skill_name: str, manifest: dict[str, object]) -> str:
    value = str(manifest.get("name") or skill_name).strip()
    if not value:
        raise SkillValidationError("skill_name is required")
    return value


def create_request_from_draft(draft: SkillDraft) -> SkillCreateRequest:
    manifest = dict(draft.manifest or {})
    return SkillCreateRequest(
        name=draft.skill_name,
        description=str(manifest.get("description") or ""),
        instructions=draft.instructions_body,
        scope=draft.target_scope,
        workspace_dir=draft.workspace_dir,
        version=_optional_text(manifest.get("version")),
        tags=_text_tuple(manifest.get("tags")),
        required_tools=draft.requirements.required_tools,
        optional_tools=draft.requirements.optional_tools,
        suggested_tools=draft.requirements.suggested_tools,
        required_effects=draft.requirements.required_effects,
        required_access=draft.requirements.required_access,
        surfaces=draft.requirements.surfaces,
        supported_platforms=draft.requirements.supported_platforms,
        setup_hints=draft.requirements.setup_hints,
    )


def update_request_from_draft(draft: SkillDraft) -> SkillUpdateRequest:
    manifest = dict(draft.manifest or {})
    return SkillUpdateRequest(
        skill_name=draft.skill_name,
        workspace_dir=draft.workspace_dir,
        description=str(manifest.get("description") or ""),
        version=_optional_text(manifest.get("version")),
        tags=_text_tuple(manifest.get("tags")),
        required_tools=draft.requirements.required_tools,
        optional_tools=draft.requirements.optional_tools,
        suggested_tools=draft.requirements.suggested_tools,
        required_effects=draft.requirements.required_effects,
        required_access=draft.requirements.required_access,
        surfaces=draft.requirements.surfaces,
        supported_platforms=draft.requirements.supported_platforms,
        setup_hints=draft.requirements.setup_hints,
    )


def draft_package(draft: SkillDraft) -> SkillPackage:
    manifest = dict(draft.manifest or {})
    skill_manifest = SkillManifest(
        api_version=str(
            manifest.get("apiVersion")
            or manifest.get("api_version")
            or "skills.crxzipple/v1alpha1",
        ),
        kind=str(manifest.get("kind") or "Skill"),
        name=draft.skill_name,
        description=str(manifest.get("description") or ""),
        version=_optional_text(manifest.get("version")),
        tags=_text_tuple(manifest.get("tags")),
        when_to_use=_optional_text(manifest.get("when_to_use")),
        anti_patterns=_text_tuple(manifest.get("anti_patterns")),
        instructions_path=str(manifest.get("instructions_path") or "SKILL.md"),
        required_tools=draft.requirements.required_tools,
        optional_tools=draft.requirements.optional_tools,
        suggested_tools=draft.requirements.suggested_tools,
        required_effects=draft.requirements.required_effects,
        required_access=draft.requirements.required_access,
        surfaces=draft.requirements.surfaces,
        supported_platforms=draft.requirements.supported_platforms,
        setup_hints=draft.requirements.setup_hints,
    )
    return SkillPackage(
        manifest=skill_manifest,
        root_path=f"draft://{draft.draft_id}",
        manifest_path=f"draft://{draft.draft_id}/manifest",
        instructions_path=f"draft://{draft.draft_id}/SKILL.md",
        source=draft.target_source_id or draft.target_scope.value,
        resources=(),
        fingerprint=draft.base_fingerprint or "",
    )


def draft_manifest_payload(draft: SkillDraft) -> dict[str, object]:
    manifest = dict(draft.manifest or {})
    manifest["name"] = draft.skill_name
    requirements = draft.requirements.to_payload()
    for key, value in requirements.items():
        if value:
            manifest[key] = value
    return manifest


def package_manifest_payload(package: SkillPackage) -> dict[str, object]:
    manifest = package.manifest
    payload: dict[str, object] = {
        "apiVersion": manifest.api_version,
        "kind": manifest.kind,
        "name": manifest.name,
        "description": manifest.description,
        "instructions_path": manifest.instructions_path,
    }
    for key, value in (
        ("version", manifest.version),
        ("tags", list(manifest.tags)),
        ("when_to_use", manifest.when_to_use),
        ("anti_patterns", list(manifest.anti_patterns)),
        ("required_tools", list(manifest.required_tools)),
        ("optional_tools", list(manifest.optional_tools)),
        ("suggested_tools", list(manifest.suggested_tools)),
        ("required_effects", list(manifest.required_effects)),
        ("required_access", list(manifest.required_access)),
        ("surfaces", list(manifest.surfaces)),
        ("supported_platforms", list(manifest.supported_platforms)),
        ("setup_hints", list(manifest.setup_hints)),
    ):
        if value:
            payload[key] = value
    return payload


def merged_requirements(
    manifest: dict[str, object],
    requirements: SkillRequirements,
) -> SkillRequirements:
    manifest_requirements = SkillRequirements(
        required_tools=_text_tuple(manifest.get("required_tools")),
        optional_tools=_text_tuple(manifest.get("optional_tools")),
        suggested_tools=(
            _text_tuple(manifest.get("suggested_tools"))
            or _text_tuple(manifest.get("allowed_tools"))
        ),
        required_effects=_text_tuple(manifest.get("required_effects")),
        surfaces=_text_tuple(manifest.get("surfaces")),
        supported_platforms=_text_tuple(manifest.get("supported_platforms")),
        required_access=_text_tuple(manifest.get("required_access")),
        setup_hints=_text_tuple(manifest.get("setup_hints")),
    )
    return SkillRequirements(
        required_tools=requirements.required_tools or manifest_requirements.required_tools,
        optional_tools=requirements.optional_tools or manifest_requirements.optional_tools,
        suggested_tools=requirements.suggested_tools or manifest_requirements.suggested_tools,
        required_effects=requirements.required_effects or manifest_requirements.required_effects,
        surfaces=requirements.surfaces or manifest_requirements.surfaces,
        supported_platforms=(
            requirements.supported_platforms
            or manifest_requirements.supported_platforms
        ),
        required_access=requirements.required_access or manifest_requirements.required_access,
        setup_hints=requirements.setup_hints or manifest_requirements.setup_hints,
    )


def _text_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        normalized = value.strip()
        return (normalized,) if normalized else ()
    if not isinstance(value, list | tuple):
        return ()
    items: list[str] = []
    for raw in value:
        if not isinstance(raw, str):
            continue
        normalized = raw.strip()
        if normalized and normalized not in items:
            items.append(normalized)
    return tuple(items)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
