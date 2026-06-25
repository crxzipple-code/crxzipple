from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.operations.application.read_models.access_target_projection import (
    setup_flow_records,
)
from crxzipple.modules.operations.application.read_models.access_values import (
    bool_value,
    normalized_filter,
)
from crxzipple.modules.operations.application.read_models.access_charts import (
    auth_success_rate,
    credential_health,
    credentials_by_kind,
)
from crxzipple.modules.operations.application.read_models.access_details import (
    target_details,
)
from crxzipple.modules.operations.application.read_models.access_events import (
    recent_access_events,
)
from crxzipple.modules.operations.application.read_models.access_event_tables import (
    access_audit_summary_table,
    access_events_table,
    fallback_problems_table,
)
from crxzipple.modules.operations.application.read_models.access_health import (
    actions,
    health as access_health,
    metrics,
    tabs,
)
from crxzipple.modules.operations.application.read_models.access_inventory import (
    collect_inventory,
    filter_targets,
    target_dicts,
)
from crxzipple.modules.operations.application.read_models.access_models import (
    AccessOperationsPage,
    AccessOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.access_requirement_tables import (
    access_requirements_table,
)
from crxzipple.modules.operations.application.read_models.access_target_tables import (
    access_targets_table,
    authentication_status_table,
    missing_access_table,
    provider_auth_blocked_table,
)
from crxzipple.modules.operations.application.read_models.access_usage_tables import (
    access_usage_table,
    expiring_soon_table,
    setup_flows_table,
)
from crxzipple.modules.operations.application.read_models.event_buckets import (
    recent_event_buckets,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleRoleModel,
)
from crxzipple.shared.time import format_datetime_utc


def access_operations_page(
    *,
    provider: Any,
    query: AccessOperationsQuery | None = None,
) -> AccessOperationsPage:
    query = normalize_access_query(query)
    now = datetime.now(timezone.utc)
    inventory = collect_inventory(provider, query=query)
    targets = target_dicts(inventory)
    filtered_targets = filter_targets(targets, query)
    visible_targets = filtered_targets[query.offset : query.offset + query.limit]
    missing_targets = tuple(
        item for item in filtered_targets if not bool_value(item.get("ready"))
    )
    observed_events = recent_access_events(
        operations_observation=provider.operations_observation,
        events_service=provider.events_service,
        definition_registry=provider.event_definition_registry,
    )
    event_buckets = recent_event_buckets(
        provider.operations_observation,
        module="access",
        hours=24,
        limit=1000,
    )
    health = access_health(access_service=provider.access_service, targets=targets)
    access_targets = access_targets_table(
        visible_targets,
        total=len(filtered_targets),
    )
    missing_access = missing_access_table(missing_targets)
    authentication_status = authentication_status_table(
        visible_targets,
        total=len(filtered_targets),
    )
    access_usage = access_usage_table(visible_targets)
    access_requirements = access_requirements_table(
        visible_targets,
        total=len(filtered_targets),
    )
    access_audit_summary = access_audit_summary_table(observed_events)

    return AccessOperationsPage(
        module="access",
        title="Access",
        subtitle="观察凭证绑定、访问要求、授权缺口、setup flow 与访问相关事件的运维视图。",
        health=health,
        updated_at=format_datetime_utc(now),
        auto_refresh=True,
        role=OperationsModuleRoleModel(
            label="Access operator",
            can_operate=True,
            scope="access",
        ),
        metrics=metrics(
            health=health,
            targets=targets,
            observed_events=observed_events,
            event_buckets=event_buckets,
        ),
        tabs=tabs(
            targets=len(filtered_targets),
            missing=len(missing_targets),
            requirements=access_requirements.total,
            usage=access_usage.total,
            setup=len(setup_flow_records(filtered_targets)),
            events=len(observed_events),
            audit=access_audit_summary.total,
        ),
        active_tab="targets",
        actions=actions(),
        access_targets=access_targets,
        access_requirements=access_requirements,
        access_audit_summary=access_audit_summary,
        missing_access=missing_access,
        credential_health=credential_health(targets),
        provider_auth_blocked=provider_auth_blocked_table(missing_targets),
        credentials_by_kind=credentials_by_kind(targets),
        expiring_soon=expiring_soon_table(filtered_targets),
        auth_success_rate=auth_success_rate(
            observed_events,
            event_buckets=event_buckets,
        ),
        authentication_status=authentication_status,
        access_usage=access_usage,
        recent_access_events=access_events_table(observed_events),
        fallback_problems=fallback_problems_table(
            targets=missing_targets,
            events=observed_events,
        ),
        setup_flows=setup_flows_table(filtered_targets),
        target_details=target_details(
            visible_targets,
            observed_events=observed_events,
        ),
    )


def normalize_access_query(
    query: AccessOperationsQuery | None,
) -> AccessOperationsQuery:
    if query is None:
        return AccessOperationsQuery()
    return AccessOperationsQuery(
        status=normalized_filter(query.status),
        kind=normalized_filter(query.kind),
        usage_type=normalized_filter(query.usage_type),
        search=query.search.strip() if isinstance(query.search, str) else "",
        include_ready=bool(query.include_ready),
        include_disabled=bool(query.include_disabled),
        limit=max(1, min(int(query.limit), 200)),
        offset=max(0, int(query.offset)),
    )
