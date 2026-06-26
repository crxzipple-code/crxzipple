from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from crxzipple.modules.authorization.domain import (
    AuthorizationGrantScope,
    TemporaryAuthorizationGrant,
    TemporaryAuthorizationGrantRepository,
)

from .grant_helpers import (
    grant_matches_agent,
    normalize_values,
    run_grant_id,
    session_grant_id,
)
from .tool_execution_authorization import GrantedAuthorizationPayload


def build_run_authorization_grant(
    *,
    run_id: str,
    agent_id: str | None,
    approval_request_id: str | None,
    effect_ids: tuple[str, ...],
    tool_ids: tuple[str, ...],
) -> TemporaryAuthorizationGrant:
    normalized_run_id = run_id.strip()
    if not normalized_run_id:
        raise ValueError("run_id cannot be empty.")
    return TemporaryAuthorizationGrant(
        id=run_grant_id(normalized_run_id, approval_request_id),
        scope=AuthorizationGrantScope.RUN,
        run_id=normalized_run_id,
        agent_id=(agent_id or "").strip() or None,
        approval_request_id=(approval_request_id or "").strip() or None,
        effect_ids=normalize_values(effect_ids),
        tool_ids=normalize_values(tool_ids),
        created_at=datetime.now(timezone.utc),
    )


def build_session_authorization_grant(
    *,
    session_key: str,
    agent_id: str | None,
    approval_request_id: str | None,
    effect_ids: tuple[str, ...],
    tool_ids: tuple[str, ...],
) -> TemporaryAuthorizationGrant:
    normalized_session_key = session_key.strip()
    if not normalized_session_key:
        raise ValueError("session_key cannot be empty.")
    return TemporaryAuthorizationGrant(
        id=session_grant_id(normalized_session_key, approval_request_id),
        scope=AuthorizationGrantScope.SESSION,
        session_key=normalized_session_key,
        agent_id=(agent_id or "").strip() or None,
        approval_request_id=(approval_request_id or "").strip() or None,
        effect_ids=normalize_values(effect_ids),
        tool_ids=normalize_values(tool_ids),
        created_at=datetime.now(timezone.utc),
    )


def collect_temporary_granted_authorization(
    context_attrs: dict[str, object],
    repository_factory: Callable[[], TemporaryAuthorizationGrantRepository] | None,
) -> GrantedAuthorizationPayload:
    if repository_factory is None:
        return GrantedAuthorizationPayload()
    repository = repository_factory()
    run_id = str(context_attrs.get("run_id", "")).strip()
    session_key = str(context_attrs.get("session_key", "")).strip()
    agent_id = str(context_attrs.get("agent_id", "")).strip()
    tool_ids: set[str] = set()
    effect_ids: set[str] = set()
    if run_id:
        for grant in repository.list_for_run(run_id):
            if not grant_matches_agent(grant, agent_id):
                continue
            tool_ids.update(grant.tool_ids)
            effect_ids.update(grant.effect_ids)
    if session_key:
        for grant in repository.list_for_session(session_key):
            if not grant_matches_agent(grant, agent_id):
                continue
            tool_ids.update(grant.tool_ids)
            effect_ids.update(grant.effect_ids)
    return GrantedAuthorizationPayload(
        tool_ids=tuple(sorted(tool_ids)),
        effect_ids=tuple(sorted(effect_ids)),
    )
