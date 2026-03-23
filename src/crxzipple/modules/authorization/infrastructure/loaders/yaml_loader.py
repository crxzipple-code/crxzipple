from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from crxzipple.modules.authorization.domain import (
    AuthorizationEffect,
    AuthorizationObligation,
    AuthorizationPolicy,
)


class YamlAuthorizationPolicyLoader:
    def load_paths(self, paths: tuple[str, ...]) -> tuple[AuthorizationPolicy, ...]:
        policies_by_id: dict[str, AuthorizationPolicy] = {}
        for raw_path in paths:
            path = Path(raw_path).expanduser()
            if not path.exists():
                continue
            for policy in self._load_path(path):
                policies_by_id[policy.id] = policy
        return tuple(
            sorted(
                policies_by_id.values(),
                key=lambda policy: (-policy.priority, policy.id),
            ),
        )

    def _load_path(self, path: Path) -> tuple[AuthorizationPolicy, ...]:
        payload = self._load_structured_config(path)
        if isinstance(payload, dict):
            items = [payload]
        elif isinstance(payload, list):
            items = payload
        else:
            raise ValueError(
                f"Authorization policy config '{path}' must decode to an object or list.",
            )
        return tuple(
            self._build_policy(item, source_description=str(path))
            for item in items
        )

    def _load_structured_config(self, path: Path) -> Any:
        raw = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            return json.loads(raw)
        if path.suffix.lower() in {".yaml", ".yml"}:
            return yaml.safe_load(raw)
        raise ValueError(
            f"Unsupported authorization policy extension '{path.suffix}' for '{path}'.",
        )

    def _build_policy(
        self,
        raw: object,
        *,
        source_description: str,
    ) -> AuthorizationPolicy:
        if not isinstance(raw, dict):
            raise ValueError(
                f"{source_description} authorization policy items must decode to objects.",
            )

        policy_id = str(raw.get("id", "")).strip()
        if not policy_id:
            raise ValueError(f"{source_description} authorization policy id cannot be empty.")

        effect = AuthorizationEffect(str(raw.get("effect", "deny")).strip().lower())
        actions_raw = raw.get("actions", [])
        if not isinstance(actions_raw, list) or not actions_raw:
            raise ValueError(
                f"Authorization policy '{policy_id}' must define a non-empty actions list.",
            )
        actions = tuple(str(item).strip() for item in actions_raw if str(item).strip())
        if not actions:
            raise ValueError(
                f"Authorization policy '{policy_id}' must define at least one action.",
            )

        subject = raw.get("subject", {})
        resource = raw.get("resource", {})
        context = raw.get("context", {})

        if subject is None:
            subject = {}
        if resource is None:
            resource = {}
        if context is None:
            context = {}
        if not isinstance(subject, dict) or not isinstance(resource, dict) or not isinstance(context, dict):
            raise ValueError(
                f"Authorization policy '{policy_id}' subject/resource/context must decode to objects.",
            )

        obligations = self._load_obligations(raw.get("obligations", []), policy_id)

        return AuthorizationPolicy(
            id=policy_id,
            effect=effect,
            actions=actions,
            description=str(raw.get("description", "")).strip(),
            subject_type=(str(subject["type"]).strip() if subject.get("type") is not None else None),
            subject_id=(str(subject["id"]).strip() if subject.get("id") is not None else None),
            subject_match=dict(subject.get("match", {})) if isinstance(subject.get("match", {}), dict) else {},
            resource_kind=(str(resource["kind"]).strip() if resource.get("kind") is not None else None),
            resource_id=(str(resource["id"]).strip() if resource.get("id") is not None else None),
            resource_match=dict(resource.get("match", {})) if isinstance(resource.get("match", {}), dict) else {},
            context_match=dict(context.get("match", {})) if isinstance(context.get("match", {}), dict) else {},
            condition=(dict(raw["condition"]) if isinstance(raw.get("condition"), dict) else None),
            obligations=obligations,
            priority=int(raw.get("priority", 0)),
            enabled=bool(raw.get("enabled", True)),
            source_kind=str(raw.get("source_kind", "imported")).strip() or "imported",
        )

    def _load_obligations(
        self,
        raw: object,
        policy_id: str,
    ) -> tuple[AuthorizationObligation, ...]:
        if raw in (None, []):
            return ()
        if not isinstance(raw, list):
            raise ValueError(
                f"Authorization policy '{policy_id}' obligations must decode to a list.",
            )
        obligations: list[AuthorizationObligation] = []
        for item in raw:
            if isinstance(item, str):
                name = item.strip()
                if not name:
                    continue
                obligations.append(AuthorizationObligation(name=name))
                continue
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                if not name:
                    raise ValueError(
                        f"Authorization policy '{policy_id}' obligation objects require a name.",
                    )
                params = dict(item.get("params", {})) if isinstance(item.get("params", {}), dict) else {}
                obligations.append(AuthorizationObligation(name=name, params=params))
                continue
            raise ValueError(
                f"Authorization policy '{policy_id}' obligations must be strings or objects.",
            )
        return tuple(obligations)

