from __future__ import annotations

from typing import Protocol

from crxzipple.modules.authorization.domain.entities import (
    AuthorizationPolicy,
    TemporaryAuthorizationGrant,
)


class AuthorizationPolicyRepository(Protocol):
    def list(self) -> list[AuthorizationPolicy]:
        ...

    def upsert(self, policy: AuthorizationPolicy) -> None:
        ...


class TemporaryAuthorizationGrantRepository(Protocol):
    def add(self, grant: TemporaryAuthorizationGrant) -> None:
        ...

    def list_for_run(self, run_id: str) -> list[TemporaryAuthorizationGrant]:
        ...

    def list_for_session(self, session_key: str) -> list[TemporaryAuthorizationGrant]:
        ...
