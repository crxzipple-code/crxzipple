from __future__ import annotations

from typing import Any

from crxzipple.modules.authorization.domain import AuthorizationPolicy

from .payloads import policy_payload as _policy_payload


class AuthorizationPolicyFacadeMixin:
    def upsert_policy(
        self,
        policy: AuthorizationPolicy,
        *,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy:
        return self._policy_lifecycle().upsert_policy(
            policy,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )

    def create_policy(
        self,
        policy: AuthorizationPolicy,
        *,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy:
        return self._policy_lifecycle().create_policy(
            policy,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )

    def update_policy(
        self,
        policy: AuthorizationPolicy,
        *,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy:
        return self._policy_lifecycle().update_policy(
            policy,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )

    def set_policy_enabled(
        self,
        policy_id: str,
        *,
        enabled: bool,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy:
        return self._policy_lifecycle().set_policy_enabled(
            policy_id,
            enabled=enabled,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )

    def delete_policy(
        self,
        policy_id: str,
        *,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy:
        return self._policy_lifecycle().delete_policy(
            policy_id,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )

    def import_policies(
        self,
        policies: tuple[AuthorizationPolicy, ...],
        *,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
        source: str = "inline",
    ) -> tuple[AuthorizationPolicy, ...]:
        return self._policy_lifecycle().import_policies(
            policies,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            source=source,
        )

    def export_policy_bundle(self) -> dict[str, Any]:
        return {
            "kind": "authorization.policy_bundle",
            "version": 1,
            "policies": [
                _policy_payload(policy)
                for policy in self._policy_snapshot()
            ],
        }
