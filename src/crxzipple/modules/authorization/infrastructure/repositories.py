from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from crxzipple.modules.authorization.domain import AuthorizationPolicy


@dataclass(slots=True)
class InMemoryAuthorizationPolicyRepository:
    policies: list[AuthorizationPolicy] = field(default_factory=list)
    managed_path: Path | None = None

    def list(self) -> list[AuthorizationPolicy]:
        return sorted(
            self.policies,
            key=lambda policy: (-policy.priority, policy.id),
        )

    def upsert(self, policy: AuthorizationPolicy) -> None:
        for index, existing in enumerate(self.policies):
            if existing.id == policy.id:
                self.policies[index] = policy
                break
        else:
            self.policies.append(policy)
        self._persist_managed_policies()

    def _persist_managed_policies(self) -> None:
        if self.managed_path is None:
            return
        managed_policies = [
            policy
            for policy in self.list()
            if policy.source_kind == "local_managed"
        ]
        self.managed_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [_policy_to_payload(policy) for policy in managed_policies]
        self.managed_path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )


def _policy_to_payload(policy: AuthorizationPolicy) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": policy.id,
        "description": policy.description,
        "effect": policy.effect.value,
        "actions": list(policy.actions),
        "priority": policy.priority,
        "enabled": policy.enabled,
        "source_kind": policy.source_kind,
    }
    subject: dict[str, object] = {}
    if policy.subject_type is not None:
        subject["type"] = policy.subject_type
    if policy.subject_id is not None:
        subject["id"] = policy.subject_id
    if policy.subject_match:
        subject["match"] = dict(policy.subject_match)
    if subject:
        payload["subject"] = subject
    resource: dict[str, object] = {}
    if policy.resource_kind is not None:
        resource["kind"] = policy.resource_kind
    if policy.resource_id is not None:
        resource["id"] = policy.resource_id
    if policy.resource_match:
        resource["match"] = dict(policy.resource_match)
    if resource:
        payload["resource"] = resource
    if policy.context_match:
        payload["context"] = {"match": dict(policy.context_match)}
    if policy.condition is not None:
        payload["condition"] = dict(policy.condition)
    if policy.obligations:
        payload["obligations"] = [
            (
                {"name": obligation.name, "params": dict(obligation.params)}
                if obligation.params
                else obligation.name
            )
            for obligation in policy.obligations
        ]
    return payload
