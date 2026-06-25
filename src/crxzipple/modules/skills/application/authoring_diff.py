from __future__ import annotations

from collections.abc import Mapping
from difflib import unified_diff

from crxzipple.modules.skills.application.authoring_conversions import (
    draft_manifest_payload,
    package_manifest_payload,
)
from crxzipple.modules.skills.application.models import (
    SkillDraft,
    SkillDraftDiff,
    SkillDraftFileDiff,
    SkillDraftIntent,
    SkillPackage,
)


def build_draft_diff(
    draft: SkillDraft,
    *,
    current: SkillPackage | None,
    current_instructions: str,
    current_support_files: Mapping[str, str],
) -> SkillDraftDiff:
    old_manifest = package_manifest_payload(current) if current is not None else {}
    new_manifest = draft_manifest_payload(draft)
    instructions_diff = unified_text_diff(
        old=current_instructions if current is not None else "",
        new=draft.instructions_body,
        fromfile=f"{draft.skill_name}/SKILL.md (current)",
        tofile=f"{draft.skill_name}/SKILL.md (draft)",
    )
    file_diffs = tuple(
        SkillDraftFileDiff(
            path=item.path,
            status=(
                "added"
                if current is None or not current_support_files.get(item.path)
                else "modified"
            ),
            unified_diff=unified_text_diff(
                old=current_support_files.get(item.path, "") if current is not None else "",
                new=item.content,
                fromfile=f"{draft.skill_name}/{item.path} (current)",
                tofile=f"{draft.skill_name}/{item.path} (draft)",
            ),
        )
        for item in draft.support_files
    )
    summary = [
        (
            f"Create skill '{draft.skill_name}'"
            if draft.intent is SkillDraftIntent.CREATE
            else f"Update skill '{draft.skill_name}'"
        ),
    ]
    if old_manifest != new_manifest:
        summary.append("Manifest metadata changes")
    if instructions_diff:
        summary.append("Instructions changes")
    if file_diffs:
        summary.append(f"{len(file_diffs)} support file changes")
    return SkillDraftDiff(
        manifest_diff={
            "status": "added" if current is None else "modified",
            "old": old_manifest,
            "new": new_manifest,
        },
        instructions_diff=instructions_diff,
        file_diffs=file_diffs,
        summary=tuple(summary),
    )


def unified_text_diff(
    *,
    old: str,
    new: str,
    fromfile: str,
    tofile: str,
) -> str:
    if old == new:
        return ""
    return "".join(
        unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=fromfile,
            tofile=tofile,
        ),
    )
