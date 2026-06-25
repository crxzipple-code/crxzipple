from __future__ import annotations

from crxzipple.modules.skills.application.models import (
    SkillDraft,
    SkillDraftIntent,
    SkillDraftSupportFile,
    SkillDraftValidation,
    SkillPackage,
)
from crxzipple.modules.skills.application.runtime_request_resolver import (
    ResolvedSkillReadiness,
)
from crxzipple.modules.skills.domain import SkillRequirements


SUPPORT_FILE_DIRS = ("references", "templates", "assets", "scripts")


def support_file_errors(file: SkillDraftSupportFile) -> list[str]:
    normalized = file.path.strip().replace("\\", "/")
    if not normalized:
        return ["support file path is required"]
    if normalized.startswith("/") or normalized in {".", ".."} or ".." in normalized.split("/"):
        return [f"support file '{file.path}' must be package-relative"]
    if normalized == "SKILL.md":
        return ["support files cannot replace SKILL.md"]
    if not any(
        normalized == directory or normalized.startswith(f"{directory}/")
        for directory in SUPPORT_FILE_DIRS
    ):
        allowed = ", ".join(SUPPORT_FILE_DIRS)
        return [f"support file '{file.path}' must live under one of: {allowed}"]
    return []


def requirement_errors(requirements: SkillRequirements) -> list[str]:
    errors: list[str] = []
    for tool_id in requirements.required_tools + requirements.optional_tools + requirements.suggested_tools:
        if tool_id.startswith(("env:", "file:")) or "/" in tool_id or "\\" in tool_id:
            errors.append(
                f"tool requirement '{tool_id}' must reference a ToolFunction id",
            )
    for access_id in requirements.required_access:
        if access_id.startswith(("env:", "file:", "codex_auth_json", "auth_ref")):
            errors.append(
                f"access requirement '{access_id}' must reference Access owner requirements",
            )
    return errors


def draft_validation(
    draft: SkillDraft,
    *,
    existing_package: SkillPackage | None,
    requirement_readiness: ResolvedSkillReadiness,
) -> SkillDraftValidation:
    manifest = dict(draft.manifest or {})
    errors: list[str] = []
    warnings: list[str] = []
    skill_name = str(manifest.get("name") or draft.skill_name).strip()
    description = str(manifest.get("description") or "").strip()
    if not skill_name:
        errors.append("skill_name is required")
    if skill_name and skill_name != draft.skill_name:
        errors.append("manifest.name must match skill_name")
    if not description:
        errors.append("manifest.description is required")
    if not draft.instructions_body.strip():
        errors.append("instructions_body is required")
    if draft.target_source_id and draft.target_source_id not in {
        "workspace",
        "global",
        "system",
    }:
        warnings.append(
            "target_source_id is not directly writable by the current package service; target_scope will be used",
        )
    for item in draft.support_files:
        errors.extend(support_file_errors(item))
    errors.extend(requirement_errors(draft.requirements))
    if draft.intent is SkillDraftIntent.CREATE:
        if existing_package is not None:
            errors.append(f"skill '{draft.skill_name}' already exists")
    elif existing_package is None:
        errors.append(f"skill '{draft.skill_name}' does not exist")
    elif (
        draft.base_fingerprint
        and existing_package.fingerprint
        and existing_package.fingerprint != draft.base_fingerprint
    ):
        warnings.append("target skill changed after this draft was created")

    readiness_status = "invalid" if errors else requirement_readiness.status
    return SkillDraftValidation(
        errors=tuple(errors),
        warnings=tuple(warnings),
        missing_tools=requirement_readiness.missing_tools,
        missing_access=requirement_readiness.missing_access,
        missing_effects=requirement_readiness.missing_effects,
        unsupported_surfaces=requirement_readiness.unsupported_surfaces,
        unsupported_platforms=requirement_readiness.unsupported_platforms,
        readiness_status=readiness_status,
    )
