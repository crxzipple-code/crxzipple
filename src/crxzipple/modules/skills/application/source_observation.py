from __future__ import annotations

from crxzipple.modules.skills.application.events import (
    SKILL_SOURCE_SYNCED_EVENT,
    SkillEventEmitter,
    emit_skill_event,
)
from crxzipple.modules.skills.application.models import (
    SkillSource,
    SkillSyncResult,
)
from crxzipple.modules.skills.application.owner_state import SkillOwnerStateService
from crxzipple.modules.skills.domain import SkillInstallationStatus


def emit_source_event(
    event_emitter: SkillEventEmitter | None,
    event_name: str,
    source: SkillSource,
) -> None:
    emit_skill_event(
        event_emitter,
        event_name,
        status="succeeded",
        payload={
            "source": source.source_id,
            "source_id": source.source_id,
            "source_kind": source.source_kind.value,
            "root_path": source.root_path,
            "enabled": source.enabled,
            "readonly": source.readonly,
            "package_count": source.package_count,
            "status": source.status,
            "sync_status": source.sync_status,
        },
    )


def emit_source_synced(
    event_emitter: SkillEventEmitter | None,
    result: SkillSyncResult,
    *,
    workspace_dir: str | None,
    surface: str,
) -> None:
    emit_skill_event(
        event_emitter,
        SKILL_SOURCE_SYNCED_EVENT,
        status="succeeded",
        payload={
            "source": result.source_id or "",
            "source_id": result.source_id or "",
            "workspace_dir": workspace_dir or "",
            "surface": surface,
            "synced_count": result.synced_count,
            "skills": [package.name for package in result.packages],
        },
    )


def record_source_mutation(
    owner_state: SkillOwnerStateService,
    *,
    action: str,
    source: SkillSource,
    message: str,
) -> None:
    owner_state.record_installation(
        action=action,
        status=SkillInstallationStatus.SUCCEEDED,
        source_id=source.source_id,
        target_uri=source.root_path,
        message=message,
        metadata={"source_kind": source.source_kind.value},
    )


def record_source_sync(
    owner_state: SkillOwnerStateService,
    result: SkillSyncResult,
    *,
    workspace_dir: str | None,
    surface: str,
) -> None:
    owner_state.record_installation(
        action="source_sync",
        status=SkillInstallationStatus.SUCCEEDED,
        source_id=result.source_id,
        workspace_dir=workspace_dir,
        message="Skill source synchronized.",
        metadata={
            "surface": surface,
            "synced_count": result.synced_count,
            "skills": [package.name for package in result.packages],
        },
    )
