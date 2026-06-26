from __future__ import annotations

from typing import Callable

from crxzipple.modules.authorization.domain import (
    TemporaryAuthorizationGrant,
    TemporaryAuthorizationGrantRepository,
)

from .payloads import grant_payload
from .temporary_grants import (
    build_run_authorization_grant,
    build_session_authorization_grant,
)


class TemporaryAuthorizationGrantService:
    def __init__(
        self,
        *,
        repository_factory: Callable[[], TemporaryAuthorizationGrantRepository]
        | None,
        record_audit: Callable[..., None],
    ) -> None:
        self._repository_factory = repository_factory
        self._record_audit = record_audit

    def grant_run_authorization(
        self,
        *,
        run_id: str,
        agent_id: str | None,
        approval_request_id: str | None,
        effect_ids: tuple[str, ...],
        tool_ids: tuple[str, ...],
    ) -> TemporaryAuthorizationGrant:
        grant = build_run_authorization_grant(
            run_id=run_id,
            agent_id=agent_id,
            approval_request_id=approval_request_id,
            effect_ids=effect_ids,
            tool_ids=tool_ids,
        )
        self._store(grant)
        self._record_audit(
            action="grant.run.create",
            status="succeeded",
            metadata={"grant": grant_payload(grant)},
        )
        return grant

    def grant_session_authorization(
        self,
        *,
        session_key: str,
        agent_id: str | None,
        approval_request_id: str | None,
        effect_ids: tuple[str, ...],
        tool_ids: tuple[str, ...],
    ) -> TemporaryAuthorizationGrant:
        grant = build_session_authorization_grant(
            session_key=session_key,
            agent_id=agent_id,
            approval_request_id=approval_request_id,
            effect_ids=effect_ids,
            tool_ids=tool_ids,
        )
        self._store(grant)
        self._record_audit(
            action="grant.session.create",
            status="succeeded",
            metadata={"grant": grant_payload(grant)},
        )
        return grant

    def _store(self, grant: TemporaryAuthorizationGrant) -> None:
        if self._repository_factory is None:
            return
        repository = self._repository_factory()
        repository.add(grant)


__all__ = ["TemporaryAuthorizationGrantService"]
