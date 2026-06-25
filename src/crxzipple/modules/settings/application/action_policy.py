from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

SettingsActionName = Literal[
    "dry-run",
    "validate",
    "publish",
    "rollback",
    "enable",
    "disable",
    "create",
    "update",
]

WRITE_ACTIONS = frozenset(
    {"publish", "rollback", "enable", "disable", "create", "update"},
)
ALL_ACTIONS = (
    "dry-run",
    "validate",
    "publish",
    "rollback",
    "enable",
    "disable",
    "create",
    "update",
)
SUPPORTED_KINDS = (
    "agent-profiles",
    "llm-profiles",
    "tool-catalog",
    "skill-catalog",
    "memory-config",
    "access-assets",
    "channel-profiles",
    "event-registry",
    "runtime-defaults",
    "environment",
    "audit-logs",
    "backup-restore",
)
KIND_ALIASES = {
    "agent": "agent-profiles",
    "agents": "agent-profiles",
    "agent_profiles": "agent-profiles",
    "llm": "llm-profiles",
    "llms": "llm-profiles",
    "llm_profiles": "llm-profiles",
    "tool": "tool-catalog",
    "tools": "tool-catalog",
    "tool_providers": "tool-catalog",
    "skill": "skill-catalog",
    "skills": "skill-catalog",
    "memory": "memory-config",
    "memory_config": "memory-config",
    "access": "access-assets",
    "access_assets": "access-assets",
    "channel": "channel-profiles",
    "channels": "channel-profiles",
    "channel_profiles": "channel-profiles",
    "event": "event-registry",
    "events": "event-registry",
    "event-contracts": "event-registry",
    "event_registry": "event-registry",
    "runtime": "runtime-defaults",
    "runtime_defaults": "runtime-defaults",
    "audit": "audit-logs",
    "audits": "audit-logs",
    "audit_logs": "audit-logs",
    "backup": "backup-restore",
    "backup_restore": "backup-restore",
}
KIND_TITLES = {
    "agent-profiles": "Agent Profiles",
    "llm-profiles": "LLM Profiles",
    "tool-catalog": "Tool Catalog",
    "skill-catalog": "Skill Catalog",
    "memory-config": "Memory Config",
    "access-assets": "Access Assets",
    "channel-profiles": "Channel Profiles",
    "event-registry": "Event Registry",
    "runtime-defaults": "Runtime Defaults",
    "environment": "Environment",
    "audit-logs": "Audit Logs",
    "backup-restore": "Backup / Restore",
}
KIND_DESCRIPTIONS = {
    "agent-profiles": (
        "Governance and validation view for Agent-owned profiles. Profile writes "
        "must go through the Agent module API."
    ),
    "llm-profiles": (
        "Governance and validation view for LLM-owned profiles. Profile writes "
        "must go through the LLM module API."
    ),
    "tool-catalog": "Tool provider, MCP provider, and local root configuration imported from bootstrap settings.",
    "skill-catalog": (
        "Governance entry for Skills-owned sources, packages, enablement "
        "policies, and readiness. Writes go through the Skills module API."
    ),
    "memory-config": "Memory retrieval and vector configuration imported from bootstrap settings.",
    "access-assets": "Settings-owned access configuration resources. Access runtime readiness remains owned by Access.",
    "channel-profiles": (
        "Governance and validation view for Channels-owned profiles. Profile "
        "writes must go through the Channels module API."
    ),
    "event-registry": (
        "Read-only Settings placeholder. Event contract definitions remain owned by the "
        "Events registry until Settings-owned registry resources are imported."
    ),
    "runtime-defaults": "Runtime defaults imported from bootstrap settings.",
    "environment": (
        "Read-only redacted environment snapshot imported from bootstrap settings. "
        "Environment override workflows are not implemented by Settings yet."
    ),
    "audit-logs": "Settings action audit records captured by the Settings action service.",
    "backup-restore": (
        "Unavailable Settings placeholder. Backup and restore workflows are not implemented "
        "by the Settings module yet."
    ),
}

_SETTINGS_OWNED_ACTIONS = ALL_ACTIONS
_MODULE_OWNED_PROFILE_ACTIONS: tuple[str, ...] = ()
_READ_ONLY_PLACEHOLDER_ACTIONS: tuple[str, ...] = ()
_KIND_ACTION_POLICY_REGISTRY: dict[str, dict[str, Any]] = {
    "agent-profiles": {
        "owner_module": "agent",
        "truth_owner": "agent",
        "truth_source": "agent_application_service",
        "allowed_actions": _MODULE_OWNED_PROFILE_ACTIONS,
        "owner_api": "/agents",
        "message": (
            "Agent profiles are owned by the Agent module. Use the Agent module API "
            "for create, update, publish, rollback, enable, or disable operations."
        ),
        "apply_policy": {
            "mode": "owner_module_api",
            "owner_module": "agent",
            "hot_apply": False,
            "requires_owner_api": True,
        },
    },
    "llm-profiles": {
        "owner_module": "llm",
        "truth_owner": "llm",
        "truth_source": "llm_application_service",
        "allowed_actions": _MODULE_OWNED_PROFILE_ACTIONS,
        "owner_api": "/llms",
        "message": (
            "LLM profiles are owned by the LLM module. Use the LLM module API "
            "for create, update, publish, rollback, enable, or disable operations."
        ),
        "apply_policy": {
            "mode": "owner_module_api",
            "owner_module": "llm",
            "hot_apply": False,
            "requires_owner_api": True,
        },
    },
    "channel-profiles": {
        "owner_module": "channels",
        "truth_owner": "channels",
        "truth_source": "channel_profile_application_service",
        "allowed_actions": _MODULE_OWNED_PROFILE_ACTIONS,
        "owner_api": "/channels",
        "message": (
            "Channel profiles are owned by the Channels module. Use the Channels "
            "module API for create, update, publish, rollback, enable, or disable "
            "operations."
        ),
        "apply_policy": {
            "mode": "owner_module_api",
            "owner_module": "channels",
            "hot_apply": False,
            "requires_owner_api": True,
        },
    },
    "skill-catalog": {
        "owner_module": "skills",
        "truth_owner": "skills",
        "truth_source": "skills_application_service",
        "allowed_actions": _MODULE_OWNED_PROFILE_ACTIONS,
        "owner_api": "/skills",
        "message": (
            "Skill catalog resources are owned by the Skills module. Use the "
            "Skills module API for source, package, enablement, readiness, "
            "manifest, or content operations."
        ),
        "apply_policy": {
            "mode": "owner_module_api",
            "owner_module": "skills",
            "hot_apply": False,
            "requires_owner_api": True,
        },
    },
    "audit-logs": {
        "owner_module": "settings",
        "truth_owner": "settings",
        "truth_source": "settings_action_audit_repository",
        "allowed_actions": (),
        "owner_api": "/settings/audit-logs",
        "message": "Audit logs are read-only Settings action records.",
        "apply_policy": {
            "mode": "read_only",
            "hot_apply": False,
            "requires_owner_api": False,
        },
    },
    "event-registry": {
        "owner_module": "events",
        "truth_owner": "events",
        "truth_source": "events_contract_registry",
        "allowed_actions": _READ_ONLY_PLACEHOLDER_ACTIONS,
        "owner_api": "/operations/events",
        "message": (
            "Event registry resources are read-only placeholders in Settings. "
            "Event contracts remain owned by the Events module."
        ),
        "apply_policy": {
            "mode": "read_only_placeholder",
            "owner_module": "events",
            "hot_apply": False,
            "requires_owner_api": True,
        },
    },
    "backup-restore": {
        "owner_module": "settings",
        "truth_owner": "settings",
        "truth_source": "not_implemented",
        "allowed_actions": (),
        "owner_api": None,
        "message": "Backup and restore workflows are not implemented by Settings yet.",
        "apply_policy": {
            "mode": "unavailable",
            "hot_apply": False,
            "requires_owner_api": False,
        },
    },
    "environment": {
        "owner_module": "settings",
        "truth_owner": "settings",
        "truth_source": "runtime_environment_snapshot",
        "allowed_actions": _READ_ONLY_PLACEHOLDER_ACTIONS,
        "owner_api": "/settings/environment",
        "message": (
            "Environment resources are redacted runtime snapshots in Settings. "
            "Create, update, publish, rollback, enable, and disable are blocked "
            "until an explicit override workflow exists."
        ),
        "apply_policy": {
            "mode": "read_only_environment_snapshot",
            "owner_module": "settings",
            "hot_apply": False,
            "requires_owner_api": False,
        },
    },
}


def normalize_kind(kind: str) -> str | None:
    normalized = kind.strip().lower().replace("_", "-")
    if normalized in SUPPORTED_KINDS:
        return normalized
    return KIND_ALIASES.get(normalized)


def kind_action_policy(kind: str) -> dict[str, Any]:
    policy = _KIND_ACTION_POLICY_REGISTRY.get(kind)
    if policy is not None:
        return policy
    owner_module = owner_module_for_kind(kind)
    return {
        "owner_module": owner_module,
        "truth_owner": "settings",
        "truth_source": "settings_application_service",
        "allowed_actions": _SETTINGS_OWNED_ACTIONS,
        "owner_api": f"/settings/{kind}",
        "message": (
            "This Settings resource kind is governed by the Settings action service."
        ),
        "apply_policy": {
            "mode": "settings_action_service",
            "owner_module": owner_module,
            "hot_apply": False,
            "requires_owner_api": False,
        },
    }


def kind_policy_payload(kind: str) -> dict[str, Any]:
    policy = kind_action_policy(kind)
    allowed_actions = ordered_actions(policy.get("allowed_actions", ()))
    blocked_actions = [
        action for action in ALL_ACTIONS if action not in allowed_actions
    ]
    owner_module = str(policy["owner_module"])
    truth_owner = str(policy["truth_owner"])
    settings_role = (
        "owner"
        if truth_owner == "settings"
        else "governance_readmodel"
    )
    action_policy = {
        "allowed_actions": allowed_actions,
        "blocked_actions": blocked_actions,
        "write_actions_allowed": any(
            action in WRITE_ACTIONS for action in allowed_actions
        ),
        "settings_write_allowed": any(
            action in WRITE_ACTIONS for action in allowed_actions
        ),
        "owner_api": policy.get("owner_api"),
        "message": policy["message"],
    }
    return {
        "ownership": {
            "owner_module": owner_module,
            "truth_owner": truth_owner,
            "truth_source": policy["truth_source"],
            "settings_role": settings_role,
        },
        "action_policy": action_policy,
        "apply_policy": deepcopy(policy["apply_policy"]),
    }


def ordered_actions(actions: Any) -> list[str]:
    allowed = set(actions or ())
    return [action for action in ALL_ACTIONS if action in allowed]


def kind_action_allowed(kind: str, action: str) -> bool:
    return action in ordered_actions(kind_action_policy(kind).get("allowed_actions", ()))


def kind_action_rejection_message(kind: str, action: str) -> str:
    del action
    return str(kind_action_policy(kind)["message"])


def owner_module_for_kind(kind: str) -> str:
    return {
        "agent-profiles": "agent",
        "llm-profiles": "llm",
        "tool-catalog": "tool",
        "skill-catalog": "skills",
        "memory-config": "memory",
        "access-assets": "access",
        "channel-profiles": "channels",
        "event-registry": "events",
        "runtime-defaults": "runtime",
        "environment": "settings",
        "backup-restore": "settings",
    }.get(kind, "settings")


def resource_tabs(kind: str) -> list[dict[str, str]]:
    labels = ["overview", "effective", "validation", "audit"]
    if kind in {"tool-catalog", "agent-profiles", "llm-profiles", "runtime-defaults"}:
        labels.insert(2, "impact")
    return [{"id": label, "label": label.replace("-", " ").title()} for label in labels]


def kind_actions(kind: str) -> list[dict[str, Any]]:
    policy = kind_policy_payload(kind)
    return [
        {
            "id": f"settings.{kind}.{action}",
            "label": action.replace("-", " ").title(),
            "method": "POST",
            "route": f"/settings/{kind}/actions/{action}",
            "requires_reason": action in WRITE_ACTIONS,
            "risk": "medium" if action in WRITE_ACTIONS else "low",
            "allowed": True,
            "owner_module": policy["ownership"]["owner_module"],
        }
        for action in ("dry-run", "validate", "create")
        if kind_action_allowed(kind, action)
    ]


def resource_actions(kind: str, resource_id: str) -> list[dict[str, Any]]:
    policy = kind_policy_payload(kind)
    return [
        {
            "id": f"settings.{kind}.{resource_id}.{action}",
            "label": action.replace("-", " ").title(),
            "method": "POST",
            "route": f"/settings/{kind}/{resource_id}/actions/{action}",
            "requires_reason": action in WRITE_ACTIONS,
            "risk": "medium" if action in WRITE_ACTIONS else "low",
            "allowed": True,
            "owner_module": policy["ownership"]["owner_module"],
        }
        for action in (
            "dry-run",
            "validate",
            "publish",
            "rollback",
            "enable",
            "disable",
            "update",
        )
        if kind_action_allowed(kind, action)
    ]


def overview_actions() -> list[dict[str, Any]]:
    return [
        {
            "id": "settings.bootstrap_import",
            "label": "Bootstrap Import",
            "method": "POST",
            "route": "/settings/bootstrap-import",
            "requires_reason": True,
            "risk": "low",
        },
        {
            "id": "settings.validate_all",
            "label": "Validate All",
            "method": "POST",
            "route": "/settings/runtime-defaults/defaults/actions/validate",
            "requires_reason": False,
            "risk": "low",
        },
    ]
