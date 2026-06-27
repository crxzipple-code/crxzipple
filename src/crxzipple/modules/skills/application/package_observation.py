from __future__ import annotations

from time import perf_counter

from crxzipple.modules.skills.application.events import (
    SKILL_CREATE_SUCCEEDED_EVENT,
    SKILL_DELETE_SUCCEEDED_EVENT,
    SKILL_INSTALL_FAILED_EVENT,
    SKILL_INSTALL_SUCCEEDED_EVENT,
    SKILL_READ_FAILED_EVENT,
    SKILL_READ_SUCCEEDED_EVENT,
    SKILL_UPDATE_SUCCEEDED_EVENT,
    SKILL_VALIDATE_FAILED_EVENT,
    SKILL_VALIDATE_SUCCEEDED_EVENT,
    SkillEventEmitter,
    emit_skill_event,
)
from crxzipple.modules.skills.application.models import (
    InstalledSkill,
    SkillMutationResult,
    SkillPackage,
    SkillReadResult,
)
from crxzipple.modules.skills.application.owner_state import SkillOwnerStateService
from crxzipple.modules.skills.domain import SkillInstallationStatus


def emit_package_created(
    event_emitter: SkillEventEmitter | None,
    result: SkillMutationResult,
    *,
    workspace_dir: str | None,
) -> None:
    emit_skill_event(
        event_emitter,
        SKILL_CREATE_SUCCEEDED_EVENT,
        status="succeeded",
        payload={
            "skill": result.skill.name,
            "skill_name": result.skill.name,
            "source": result.skill.source,
            "workspace_dir": workspace_dir or "",
            "path": result.skill.root_path,
        },
    )


def emit_package_updated(
    event_emitter: SkillEventEmitter | None,
    result: SkillMutationResult,
    *,
    workspace_dir: str | None,
    update_kind: str,
    path: str,
) -> None:
    emit_skill_event(
        event_emitter,
        SKILL_UPDATE_SUCCEEDED_EVENT,
        status="succeeded",
        payload={
            "skill": result.skill.name,
            "skill_name": result.skill.name,
            "source": result.skill.source,
            "workspace_dir": workspace_dir or "",
            "path": path,
            "update_kind": update_kind,
        },
    )


def emit_package_deleted(
    event_emitter: SkillEventEmitter | None,
    result: SkillMutationResult,
    *,
    workspace_dir: str | None,
) -> None:
    emit_skill_event(
        event_emitter,
        SKILL_DELETE_SUCCEEDED_EVENT,
        status="succeeded",
        payload={
            "skill": result.skill.name,
            "skill_name": result.skill.name,
            "source": result.skill.source,
            "workspace_dir": workspace_dir or "",
            "path": result.skill.root_path,
        },
    )


def emit_package_read_failed(
    event_emitter: SkillEventEmitter | None,
    *,
    skill_name: str,
    surface: str,
    workspace_dir: str | None,
    path: str | None,
    started_at: float,
    error: BaseException,
) -> None:
    emit_skill_event(
        event_emitter,
        SKILL_READ_FAILED_EVENT,
        status="failed",
        level="error",
        payload={
            "skill": skill_name,
            "skill_name": skill_name,
            "surface": surface,
            "workspace_dir": workspace_dir or "",
            "path": path or "",
            "duration_ms": duration_ms(started_at),
            "error_message": str(error),
        },
    )


def emit_package_read_succeeded(
    event_emitter: SkillEventEmitter | None,
    result: SkillReadResult,
    *,
    surface: str,
    workspace_dir: str | None,
    started_at: float,
) -> None:
    emit_skill_event(
        event_emitter,
        SKILL_READ_SUCCEEDED_EVENT,
        status="succeeded",
        payload={
            "skill": result.package.name,
            "skill_name": result.package.name,
            "surface": surface,
            "workspace_dir": workspace_dir or "",
            "path": result.requested_path,
            "resolved_path": result.resolved_path,
            "source": result.package.source,
            "duration_ms": duration_ms(started_at),
        },
    )


def emit_package_validate_failed(
    event_emitter: SkillEventEmitter | None,
    *,
    path: str,
    started_at: float,
    error: BaseException,
) -> None:
    emit_skill_event(
        event_emitter,
        SKILL_VALIDATE_FAILED_EVENT,
        status="failed",
        level="error",
        payload={
            "path": path,
            "duration_ms": duration_ms(started_at),
            "error_message": str(error),
        },
    )


def emit_package_validate_succeeded(
    event_emitter: SkillEventEmitter | None,
    package: SkillPackage,
    *,
    path: str,
    started_at: float,
) -> None:
    emit_skill_event(
        event_emitter,
        SKILL_VALIDATE_SUCCEEDED_EVENT,
        status="succeeded",
        payload={
            "skill": package.name,
            "skill_name": package.name,
            "path": path,
            "source": package.source,
            "root_path": package.root_path,
            "required_tools": list(package.requirements.required_tools),
            "duration_ms": duration_ms(started_at),
        },
    )


def emit_package_install_failed(
    event_emitter: SkillEventEmitter | None,
    *,
    source_dir: str,
    scope: str,
    workspace_dir: str | None,
    started_at: float,
    error: BaseException,
) -> None:
    emit_skill_event(
        event_emitter,
        SKILL_INSTALL_FAILED_EVENT,
        status="failed",
        level="error",
        payload={
            "source_dir": source_dir,
            "scope": scope,
            "workspace_dir": workspace_dir or "",
            "duration_ms": duration_ms(started_at),
            "error_message": str(error),
        },
    )


def emit_package_install_succeeded(
    event_emitter: SkillEventEmitter | None,
    result: InstalledSkill,
    *,
    source_dir: str,
    workspace_dir: str | None,
    started_at: float,
) -> None:
    emit_skill_event(
        event_emitter,
        SKILL_INSTALL_SUCCEEDED_EVENT,
        status="succeeded",
        payload={
            "skill": result.package.name,
            "skill_name": result.package.name,
            "source": result.package.source,
            "source_dir": source_dir,
            "scope": result.scope.value,
            "workspace_dir": workspace_dir or "",
            "target_root": result.target_root,
            "target_path": result.target_path,
            "required_tools": list(result.package.requirements.required_tools),
            "duration_ms": duration_ms(started_at),
        },
    )


def record_package_installation(
    owner_state: SkillOwnerStateService,
    *,
    action: str,
    status: SkillInstallationStatus,
    package: SkillPackage | None = None,
    source_uri: str | None = None,
    target_uri: str | None = None,
    workspace_dir: str | None = None,
    message: str | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    owner_state.record_installation(
        action=action,
        status=status,
        package=package,
        source_uri=source_uri,
        target_uri=target_uri,
        workspace_dir=workspace_dir,
        message=message,
        metadata=metadata,
    )


def duration_ms(started_at: float) -> int:
    return max(0, round((perf_counter() - started_at) * 1000))
