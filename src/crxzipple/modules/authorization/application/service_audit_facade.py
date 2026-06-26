from __future__ import annotations

from crxzipple.modules.authorization.domain import AuthorizationAuditRecord


class AuthorizationAuditFacadeMixin:
    def list_audit_records(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        action: str | None = None,
        target_policy_id: str | None = None,
    ) -> list[AuthorizationAuditRecord]:
        if self.audit_repository is None:
            return []
        return self.audit_repository.list(
            limit=limit,
            offset=offset,
            action=action,
            target_policy_id=target_policy_id,
        )
