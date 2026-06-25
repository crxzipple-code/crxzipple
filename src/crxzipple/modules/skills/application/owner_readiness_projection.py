from __future__ import annotations

from datetime import datetime

from crxzipple.modules.skills.application.models import (
    SkillPackage,
    SkillReadiness,
    SkillReadinessStatus,
)
from crxzipple.modules.skills.application.runtime_request_resolver import (
    ResolvedSkillReadiness,
    SkillRuntimeRequestResolutionContext,
)
from crxzipple.modules.skills.domain import (
    SkillPackageIndex,
    SkillReadinessSnapshot,
    SkillReadinessStatus as DomainSkillReadinessStatus,
)


def readiness_snapshot(
    package: SkillPackage,
    readiness: SkillReadiness,
    *,
    updated_at: datetime,
) -> SkillReadinessSnapshot:
    checks: list[dict[str, object]] = []
    checks.extend(
        {"kind": "tool", "id": item, "ok": False}
        for item in readiness.missing_tools
    )
    checks.extend(
        {"kind": "access", "id": item, "ok": False}
        for item in readiness.missing_access
    )
    checks.extend(
        {"kind": "authorization_effect", "id": item, "ok": False}
        for item in readiness.missing_effects
    )
    checks.extend(
        {"kind": "surface", "id": item, "ok": False, "status": "unsupported"}
        for item in readiness.unsupported_surfaces
    )
    checks.extend(
        {"kind": "platform", "id": item, "ok": False, "status": "unsupported"}
        for item in readiness.unsupported_platforms
    )
    if not checks and readiness.ready:
        checks.append({"kind": "manifest", "id": package.name, "ok": True})
    return SkillReadinessSnapshot(
        skill_id=package.name,
        source_id=package.source,
        status=domain_readiness_status(readiness.status),
        checks=tuple(checks),
        reason=None if readiness.ready else readiness.status.value,
        metadata={
            "setup_hints": list(readiness.setup_hints),
            "validation_errors": list(readiness.validation_errors),
            "missing_effects": list(readiness.missing_effects),
            "unsupported_surfaces": list(readiness.unsupported_surfaces),
            "unsupported_platforms": list(readiness.unsupported_platforms),
        },
        updated_at=updated_at,
    )


def domain_readiness_status(
    status: SkillReadinessStatus,
) -> DomainSkillReadinessStatus:
    try:
        return DomainSkillReadinessStatus(status.value)
    except ValueError:
        return DomainSkillReadinessStatus.UNSUPPORTED


def prompt_readiness_snapshot(
    package: SkillPackage,
    readiness: ResolvedSkillReadiness,
    *,
    context: SkillRuntimeRequestResolutionContext,
    updated_at: datetime,
) -> SkillReadinessSnapshot:
    checks = prompt_readiness_checks(package, readiness)
    if not checks and readiness.ready:
        checks = ({"kind": "manifest", "id": package.name, "ok": True},)
    return SkillReadinessSnapshot(
        skill_id=package.name,
        source_id=package.source,
        status=_prompt_snapshot_status(readiness),
        checks=checks,
        reason=None if readiness.ready else readiness.status,
        metadata={
            "source": package.source,
            "surface": context.surface or "",
            "agent_id": context.agent_id or "",
            "setup_hints": list(package.requirements.setup_hints),
            "access_checks": [
                check.to_metadata()
                for check in readiness.access_checks
            ],
            "authorization": (
                readiness.authorization.to_metadata()
                if readiness.authorization is not None
                else None
            ),
        },
        updated_at=updated_at,
    )


def prompt_readiness_checks(
    package: SkillPackage,
    readiness: ResolvedSkillReadiness,
) -> tuple[dict[str, object], ...]:
    checks: list[dict[str, object]] = []
    missing_tools = set(readiness.missing_tools)
    for tool_id in package.requirements.required_tools:
        checks.append(
            {
                "kind": "tool",
                "id": tool_id,
                "ok": tool_id not in missing_tools,
            },
        )
    for check in readiness.access_checks:
        payload = check.to_metadata()
        checks.append(
            {
                "kind": "access",
                "id": check.requirement,
                "ok": check.ready,
                "status": check.status,
                "setup_available": check.setup_available,
                "reason": payload.get("reason", ""),
            },
        )
    checked_access = {check.requirement for check in readiness.access_checks}
    for requirement in readiness.missing_access:
        if requirement in checked_access:
            continue
        checks.append(
            {
                "kind": "access",
                "id": requirement,
                "ok": False,
                "status": "setup_needed",
            },
        )
    missing_effects = set(readiness.missing_effects)
    for effect_id in package.requirements.required_effects:
        checks.append(
            {
                "kind": "authorization_effect",
                "id": effect_id,
                "ok": effect_id not in missing_effects,
            },
        )
    for surface in readiness.unsupported_surfaces:
        checks.append(
            {
                "kind": "surface",
                "id": surface,
                "ok": False,
                "status": "unsupported",
            },
        )
    for platform in readiness.unsupported_platforms:
        checks.append(
            {
                "kind": "platform",
                "id": platform,
                "ok": False,
                "status": "unsupported",
            },
        )
    return tuple(checks)


def readiness_semantic(
    snapshot: SkillReadinessSnapshot | None,
) -> tuple[object, ...] | None:
    if snapshot is None:
        return None
    return (
        snapshot.status.value,
        snapshot.reason,
        tuple(normalized_check(check) for check in snapshot.checks),
    )


def normalized_check(check: dict[str, object]) -> tuple[tuple[str, object], ...]:
    return tuple(sorted(check.items(), key=lambda item: item[0]))


def readiness_changed_payload(
    *,
    package: SkillPackage,
    previous: SkillReadinessSnapshot | None,
    current: SkillReadinessSnapshot,
    context: SkillRuntimeRequestResolutionContext,
    readiness: ResolvedSkillReadiness,
) -> dict[str, object]:
    return {
        "skill": package.name,
        "skill_name": package.name,
        "source": package.source,
        "previous_status": previous.status.value if previous is not None else "",
        "status": current.status.value,
        "ready": current.status is DomainSkillReadinessStatus.READY,
        "run_id": context.run_id or "",
        "agent_id": context.agent_id or "",
        "session_key": context.session_key or "",
        "active_session_id": context.active_session_id or "",
        "surface": context.surface or "",
        "workspace_dir": context.workspace_dir or "",
        "missing_tools": list(readiness.missing_tools),
        "missing_access": list(readiness.missing_access),
        "missing_effects": list(readiness.missing_effects),
        "unsupported_surfaces": list(readiness.unsupported_surfaces),
        "unsupported_platforms": list(readiness.unsupported_platforms),
        "checks": [dict(check) for check in current.checks],
    }


def catalog_readiness_changed_payload(
    *,
    package: SkillPackage,
    previous: SkillReadinessSnapshot | None,
    current: SkillReadinessSnapshot,
    readiness: SkillReadiness,
) -> dict[str, object]:
    return {
        "skill": package.name,
        "skill_name": package.name,
        "source": package.source,
        "path": package.root_path,
        "previous_status": previous.status.value if previous is not None else "",
        "status": current.status.value,
        "ready": current.status is DomainSkillReadinessStatus.READY,
        "readiness_scope": "catalog",
        "missing_tools": list(readiness.missing_tools),
        "missing_access": list(readiness.missing_access),
        "missing_effects": list(readiness.missing_effects),
        "unsupported_surfaces": list(readiness.unsupported_surfaces),
        "unsupported_platforms": list(readiness.unsupported_platforms),
        "checks": [dict(check) for check in current.checks],
    }


def removed_readiness_changed_payload(
    *,
    package: SkillPackageIndex,
    previous: SkillReadinessSnapshot | None,
    current: SkillReadinessSnapshot,
) -> dict[str, object]:
    return {
        "skill": package.skill_id,
        "skill_name": package.name,
        "source": package.source_id,
        "path": package.root_uri,
        "previous_status": previous.status.value if previous is not None else "",
        "status": current.status.value,
        "ready": False,
        "readiness_scope": "catalog",
        "reason": current.reason or "removed",
        "missing_tools": [],
        "missing_access": [],
        "missing_effects": [],
        "unsupported_surfaces": [],
        "unsupported_platforms": [],
        "checks": [dict(check) for check in current.checks],
    }


def _prompt_snapshot_status(readiness: ResolvedSkillReadiness) -> DomainSkillReadinessStatus:
    if readiness.ready:
        return DomainSkillReadinessStatus.READY
    if readiness.unsupported_platforms:
        return DomainSkillReadinessStatus.UNSUPPORTED
    return DomainSkillReadinessStatus.SETUP_NEEDED
