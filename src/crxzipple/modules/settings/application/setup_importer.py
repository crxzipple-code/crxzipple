from __future__ import annotations

from crxzipple.modules.settings.application.models import (
    CreateSettingsResourceInput,
    UpdateSettingsResourceInput,
)
from crxzipple.modules.settings.application.services import (
    SettingsActionService,
    SettingsQueryService,
)
from crxzipple.modules.settings.application.service_bundle import SettingsServices
from crxzipple.modules.settings.application.setup_payloads import (
    effective_payload_matches_seed,
    get_existing_resource,
)
from crxzipple.modules.settings.application.setup_resources import (
    SETTINGS_GOVERNANCE_RESOURCE_KINDS,
    collect_core_settings_resources,
)
from crxzipple.modules.settings.application.setup_results import (
    SettingsBootstrapImportResult,
)


def import_core_settings_resources(
    settings: object,
    *,
    services: SettingsServices | None = None,
    actions: SettingsActionService | None = None,
    queries: SettingsQueryService | None = None,
    actor: str | None = None,
    reason: str = "import core settings resources",
) -> SettingsBootstrapImportResult:
    if services is not None:
        actions = services.actions
        queries = services.queries
    if actions is None or queries is None:
        raise ValueError("settings actions and queries are required to import resources.")

    counts = {kind: 0 for kind in SETTINGS_GOVERNANCE_RESOURCE_KINDS}
    created = 0
    updated = 0
    skipped = 0
    audit_refs: list[str] = []

    for seed in collect_core_settings_resources(settings):
        counts[seed.ref.resource_kind] = counts.get(seed.ref.resource_kind, 0) + 1
        existing = get_existing_resource(queries, seed.ref.resource_id)
        if existing is None:
            result = actions.create_resource(
                CreateSettingsResourceInput(
                    resource_id=seed.ref.resource_id,
                    resource_kind=seed.ref.resource_kind,
                    owner_module=seed.ref.owner_module,
                    scope=seed.ref.scope,
                    display_name=seed.ref.display_name,
                    payload=seed.payload,
                    actor=actor,
                    reason=reason,
                    publish=True,
                    source=seed.source,
                    metadata=seed.metadata,
                    trace_context={"bootstrap_source": seed.source},
                ),
            )
            created += 1
            audit_refs.append(result.audit_ref)
            continue
        if existing.resource_kind != seed.ref.resource_kind:
            skipped += 1
            continue
        if effective_payload_matches_seed(queries, existing.id, seed.payload):
            skipped += 1
            continue
        result = actions.update_resource(
            UpdateSettingsResourceInput(
                resource_id=seed.ref.resource_id,
                payload=seed.payload,
                actor=actor,
                reason=reason,
                publish=True,
                source=seed.source,
                metadata=seed.metadata,
                trace_context={"bootstrap_source": seed.source},
            ),
        )
        updated += 1
        audit_refs.append(result.audit_ref)

    return SettingsBootstrapImportResult(
        imported_counts=counts,
        created=created,
        updated=updated,
        skipped=skipped,
        audit_refs=tuple(audit_refs),
    )
