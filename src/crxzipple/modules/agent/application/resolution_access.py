from __future__ import annotations

from typing import Any

from crxzipple.modules.agent.application.resolution_models import AgentAccessGrant
from crxzipple.modules.agent.application.resolution_values import optional_text


def pending_access_grant(
    *,
    source_type: str,
    source_id: str,
    requirement: str,
    grant_kind: str,
) -> AgentAccessGrant:
    return AgentAccessGrant(
        source_type=source_type,
        source_id=source_id,
        requirement=requirement,
        grant_kind=grant_kind,
        _raw_requirement=requirement,
    )


def flatten_requirements(
    requirements: tuple[str, ...],
    requirement_sets: tuple[tuple[str, ...], ...],
) -> tuple[str, ...]:
    values: list[str] = []
    values.extend(requirements)
    for group in requirement_sets:
        values.extend(group)
    return tuple(dict.fromkeys(item for item in values if item))


def resolve_access_grants(
    grants: list[AgentAccessGrant],
    *,
    access_readiness: Any | None,
    workspace_dir: str | None,
) -> list[AgentAccessGrant]:
    resolved: list[AgentAccessGrant] = []
    seen: set[tuple[str, str, str, str]] = set()
    for grant in grants:
        raw_requirement = grant._raw_requirement or grant.requirement
        key = (
            grant.source_type,
            grant.source_id,
            grant.grant_kind,
            raw_requirement,
        )
        if key in seen:
            continue
        seen.add(key)
        if access_readiness is None:
            resolved.append(grant)
            continue
        try:
            readiness = (
                access_readiness.check_credential_binding(
                    raw_requirement,
                    workspace_dir=workspace_dir,
                )
                if grant.grant_kind == "credential_binding"
                else access_readiness.check_requirement(
                    raw_requirement,
                    workspace_dir=workspace_dir,
                )
            )
            payload = readiness.to_payload()
            resolved.append(
                AgentAccessGrant(
                    source_type=grant.source_type,
                    source_id=grant.source_id,
                    requirement=grant.requirement,
                    grant_kind=grant.grant_kind,
                    status=str(payload.get("status", "unknown")),
                    ready=bool(payload.get("ready", False)),
                    setup_available=bool(payload.get("setup_available", False)),
                    reason=optional_text(payload.get("reason")),
                ),
            )
        except Exception as exc:  # pragma: no cover - host access setup may vary
            resolved.append(
                AgentAccessGrant(
                    source_type=grant.source_type,
                    source_id=grant.source_id,
                    requirement=grant.requirement,
                    grant_kind=grant.grant_kind,
                    status="unknown",
                    ready=False,
                    setup_available=False,
                    reason=str(exc),
                ),
            )
    return resolved


__all__ = [
    "flatten_requirements",
    "pending_access_grant",
    "resolve_access_grants",
]
