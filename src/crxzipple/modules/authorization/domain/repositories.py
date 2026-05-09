from __future__ import annotations

from typing import Protocol

from crxzipple.modules.authorization.domain.entities import (
    AuthorizationAuditRecord,
    AuthorizationPolicy,
    TemporaryAuthorizationGrant,
)


class AuthorizationPolicyRepository(Protocol):
    def get(self, policy_id: str) -> AuthorizationPolicy | None:
        ...

    def list(self) -> list[AuthorizationPolicy]:
        ...

    def upsert(self, policy: AuthorizationPolicy) -> None:
        ...

    def delete(self, policy_id: str) -> bool:
        ...


class TemporaryAuthorizationGrantRepository(Protocol):
    def add(self, grant: TemporaryAuthorizationGrant) -> None:
        ...

    def list_for_run(self, run_id: str) -> list[TemporaryAuthorizationGrant]:
        ...

    def list_for_session(self, session_key: str) -> list[TemporaryAuthorizationGrant]:
        ...


class AuthorizationAuditRepository(Protocol):
    def add(self, record: AuthorizationAuditRecord) -> None:
        ...

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        action: str | None = None,
        target_policy_id: str | None = None,
    ) -> list[AuthorizationAuditRecord]:
        ...
