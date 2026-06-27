from __future__ import annotations

from crxzipple.modules.skills.application.authoring_conversions import (
    create_request_from_draft,
    update_request_from_draft,
)
from crxzipple.modules.skills.application.models import (
    SkillDraft,
    SkillDraftIntent,
    SkillMutationResult,
    SkillPackage,
)
from crxzipple.modules.skills.application.package_service import SkillPackageService
from crxzipple.modules.skills.domain import (
    SkillNotFoundError,
    SkillValidationError,
)


def apply_draft_to_owner(
    package_service: SkillPackageService,
    draft: SkillDraft,
) -> SkillMutationResult:
    if draft.intent is SkillDraftIntent.CREATE:
        result = package_service.create(create_request_from_draft(draft))
    else:
        result = package_service.update(update_request_from_draft(draft))
        result = package_service.write_instructions(
            workspace_dir=draft.workspace_dir,
            skill_name=draft.skill_name,
            content=draft.instructions_body,
        )
    for item in draft.support_files:
        result = package_service.write_file(
            workspace_dir=draft.workspace_dir,
            skill_name=draft.skill_name,
            path=item.path,
            content=item.content,
        )
    return result


def current_package(
    package_service: SkillPackageService,
    *,
    workspace_dir: str | None,
    skill_name: str,
) -> SkillPackage | None:
    try:
        return package_service.catalog_service.get(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            surface="",
            include_disabled=True,
        )
    except SkillNotFoundError:
        return None


def current_fingerprint(
    package_service: SkillPackageService,
    *,
    workspace_dir: str | None,
    skill_name: str,
) -> str | None:
    current = current_package(
        package_service,
        workspace_dir=workspace_dir,
        skill_name=skill_name,
    )
    return current.fingerprint if current is not None else None


def current_instructions(
    package_service: SkillPackageService,
    draft: SkillDraft,
) -> str:
    try:
        return package_service.read(
            workspace_dir=draft.workspace_dir,
            skill_name=draft.skill_name,
            path=None,
            surface="",
        ).content
    except SkillNotFoundError:
        return ""


def current_support_file(
    package_service: SkillPackageService,
    draft: SkillDraft,
    path: str,
) -> str:
    try:
        return package_service.read(
            workspace_dir=draft.workspace_dir,
            skill_name=draft.skill_name,
            path=path,
            surface="",
        ).content
    except SkillValidationError:
        return ""
    except SkillNotFoundError:
        return ""
