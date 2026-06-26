from __future__ import annotations

from typing import Any

from crxzipple.modules.settings.application.action_policy import (
    KIND_TITLES,
    SUPPORTED_KINDS,
    overview_actions,
)
from crxzipple.modules.settings.application.read_models.pages_audits import audit_table
from crxzipple.modules.settings.application.read_models.pages_common import (
    key_value_section,
)
from crxzipple.modules.settings.application.services import SettingsQueryService


def overview_payload(query: SettingsQueryService) -> dict[str, Any]:
    counts = resource_counts(query)
    total_resources = sum(
        count for kind, count in counts.items() if kind != "audit-logs"
    )
    missing = [
        kind
        for kind in ("access-assets", "event-registry", "backup-restore")
        if counts.get(kind, 0) == 0
    ]
    health_status = "warning" if missing else "ready"
    audits = tuple(query.list_audits())
    return {
        "resource": "overview",
        "title": "Settings Overview",
        "description": "Settings governance read model backed by the Settings application service.",
        "status": health_status,
        "health": {
            "status": health_status,
            "degraded": False,
            "source": "settings_application",
            "missing_resource_kinds": missing,
        },
        "counts": {
            "resources": total_resources,
            "kinds": len(SUPPORTED_KINDS),
            "audits": len(audits),
        },
        "resource_counts": [
            {
                "id": kind,
                "label": KIND_TITLES[kind],
                "value": count,
                "tone": "warning" if count == 0 else "success",
                "route": f"/settings/{kind}",
            }
            for kind, count in counts.items()
        ],
        "contract_summary": key_value_section(
            "Ownership",
            {
                "truth_owner": "settings",
                "provider": "settings_application",
                "bootstrap_source": "core.config.Settings",
            },
        ),
        "configuration_summary": key_value_section(
            "Configuration",
            {
                "resources": total_resources,
                "resource_kinds": len(SUPPORTED_KINDS),
                "audits": len(audits),
            },
        ),
        "configuration_health": {
            "title": "Configuration Health",
            "columns": ["Resource", "Count", "Status"],
            "rows": [
                {
                    "Resource": KIND_TITLES[kind],
                    "Count": count,
                    "Status": "pending import" if count == 0 else "ready",
                }
                for kind, count in counts.items()
            ],
        },
        "recent_changes": audit_table(audits[-10:]),
        "configuration_distribution": {
            "title": "Configuration Distribution",
            "kind": "bar",
            "series": [
                {"label": KIND_TITLES[kind], "value": count}
                for kind, count in counts.items()
            ],
        },
        "configuration_issues": {
            "title": "Configuration Issues",
            "columns": ["Resource", "Issue", "Severity"],
            "rows": [
                {
                    "Resource": KIND_TITLES[kind],
                    "Issue": "No Settings-owned resources imported yet.",
                    "Severity": "warning",
                }
                for kind in missing
            ],
        },
        "configuration_inheritance": key_value_section(
            "Resolution",
            {
                "default_source": "bootstrap",
                "workspace_override": "not_configured",
                "environment_override": "settings_overrides",
            },
        ),
        "sources_versioning": key_value_section(
            "Sources",
            {
                "bootstrap": "core.config.Settings",
                "versions": sum(
                    len(query.list_versions(resource.id))
                    for resource in query.list_resources()
                ),
                "latest_audit": audits[-1].id if audits else None,
            },
        ),
        "quick_actions": overview_actions(),
        "useful_links": [
            {"label": KIND_TITLES[kind], "route": f"/settings/{kind}"}
            for kind in SUPPORTED_KINDS
        ],
    }


def resource_counts(query: SettingsQueryService) -> dict[str, int]:
    return {
        kind: (
            len(query.list_audits())
            if kind == "audit-logs"
            else len(query.list_resources(resource_kind=kind))
        )
        for kind in SUPPORTED_KINDS
    }


__all__ = ["overview_payload", "resource_counts"]
