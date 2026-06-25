from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from crxzipple.modules.skills.application.models import (
    SkillDraft,
    SkillDraftIntent,
    SkillDraftStatus,
    SkillDraftValidation,
    SkillMutationResult,
    SkillPackage,
)
from crxzipple.modules.skills.domain import SkillValidationError


TERMINAL_DRAFT_STATUSES = frozenset(
    {
        SkillDraftStatus.APPLIED,
        SkillDraftStatus.REJECTED,
        SkillDraftStatus.EXPIRED,
    },
)


def ensure_mutable(draft: SkillDraft) -> None:
    if draft.status in TERMINAL_DRAFT_STATUSES:
        raise SkillValidationError(
            f"Skill draft '{draft.draft_id}' is {draft.status.value} and cannot be changed.",
        )


def invalid_draft_for_apply(
    draft: SkillDraft,
    *,
    validation: SkillDraftValidation,
    updated_at: datetime,
) -> SkillDraft:
    return replace(
        draft,
        status=SkillDraftStatus.INVALID,
        validation=validation,
        updated_at=updated_at,
    )


def apply_validation_error_message(validation: SkillDraftValidation) -> str:
    return "Skill draft is invalid: " + "; ".join(validation.errors)


def assert_apply_target(
    draft: SkillDraft,
    *,
    current_package: SkillPackage | None,
) -> None:
    if draft.intent is SkillDraftIntent.UPDATE:
        if current_package is None:
            raise SkillValidationError(
                f"Skill '{draft.skill_name}' does not exist.",
            )
        if (
            draft.base_fingerprint
            and current_package.fingerprint
            and current_package.fingerprint != draft.base_fingerprint
        ):
            raise SkillValidationError(
                "Skill draft target changed after the draft was created. "
                "Refresh the draft before applying it.",
            )
    if draft.target_source_id in {"system"}:
        raise SkillValidationError(
            "System skill source is readonly and cannot receive authored drafts.",
        )


def applied_draft(
    draft: SkillDraft,
    *,
    validation: SkillDraftValidation,
    result: SkillMutationResult,
    reason: str | None,
    updated_at: datetime,
) -> SkillDraft:
    return replace(
        draft,
        status=SkillDraftStatus.APPLIED,
        validation=validation,
        base_fingerprint=result.skill.fingerprint or draft.base_fingerprint,
        reason=reason or draft.reason,
        updated_at=updated_at,
    )
