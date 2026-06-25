from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.daemon_charts import (
    daemon_lease_health,
    daemon_process_health,
    daemon_state_summary,
)
from crxzipple.modules.operations.application.read_models.daemon_drain import (
    daemon_drain_overview,
)
from crxzipple.modules.operations.application.read_models.daemon_events import (
    daemon_events_table,
)
from crxzipple.modules.operations.application.read_models.daemon_metrics import (
    daemon_metrics,
    daemon_tabs,
)
from crxzipple.modules.operations.application.read_models.daemon_instance_details import (
    daemon_instance_details,
)
from crxzipple.modules.operations.application.read_models.daemon_lease_details import (
    daemon_lease_details,
)
from crxzipple.modules.operations.application.read_models.daemon_models import (
    DaemonOperationsPage,
    DaemonOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.daemon_page_facts import (
    collect_daemon_page_facts,
)
from crxzipple.modules.operations.application.read_models.daemon_page_helpers import (
    daemon_actions,
    daemon_links_to_operations,
)
from crxzipple.modules.operations.application.read_models.daemon_process_details import (
    daemon_process_details,
)
from crxzipple.modules.operations.application.read_models.daemon_process_tables import (
    daemon_processes_table,
)
from crxzipple.modules.operations.application.read_models.daemon_runtime_facts import (
    daemon_service_groups,
)
from crxzipple.modules.operations.application.read_models.daemon_tables import (
    daemon_dependency_health_table,
    daemon_instances_table,
    daemon_leases_table,
    daemon_service_sets_table,
    daemon_services_table,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleRoleModel,
)
from crxzipple.shared.time import format_datetime_utc


def daemon_operations_page(
    *,
    query: DaemonOperationsQuery | None = None,
    daemon_service: Any | None = None,
    daemon_manager: Any | None = None,
    events_service: Any | None = None,
    event_definition_registry: Any | None = None,
    operations_observation: Any | None = None,
    process_service: Any | None = None,
    runtime_bootstrap_config: Any | None = None,
) -> DaemonOperationsPage:
    facts = collect_daemon_page_facts(
        query=query,
        daemon_service=daemon_service,
        daemon_manager=daemon_manager,
        events_service=events_service,
        event_definition_registry=event_definition_registry,
        operations_observation=operations_observation,
        process_service=process_service,
    )

    actions = daemon_actions()
    service_sets_table = daemon_service_sets_table(
        service_sets=facts.service_sets,
        services=facts.services,
        instances_by_service=facts.instances_by_service,
        leases_by_service=facts.leases_by_service,
    )
    services_table = daemon_services_table(
        services=facts.services,
        instances_by_service=facts.instances_by_service,
        leases_by_service=facts.leases_by_service,
    )
    instances_table = daemon_instances_table(
        facts.visible_instances,
        total=len(facts.filtered_instances),
        service_by_key=facts.service_by_key,
    )
    leases_table = daemon_leases_table(
        facts.visible_leases,
        total=len(facts.filtered_leases),
        service_by_key=facts.service_by_key,
    )
    processes_table = daemon_processes_table(
        facts.visible_process_rows,
        total=len(facts.filtered_process_rows),
        now=facts.now,
    )
    events_table = daemon_events_table(facts.observed_events)

    return DaemonOperationsPage(
        module="daemon",
        title="Daemons",
        subtitle="观察守护进程服务集、服务规格、进程实例、租约与运行事件的运维视图。",
        health=facts.health,
        updated_at=format_datetime_utc(facts.now),
        auto_refresh=True,
        role=OperationsModuleRoleModel(
            label="Daemon operator",
            can_operate=True,
            scope="daemon",
        ),
        metrics=daemon_metrics(
            health=facts.health,
            service_sets=facts.service_sets,
            services=facts.services,
            instances=facts.current_instances,
            leases=facts.current_leases,
            process_rows=facts.current_process_rows,
            observed_events=facts.observed_events,
            instances_by_service=facts.current_instances_by_service,
        ),
        tabs=daemon_tabs(
            service_sets=service_sets_table.total,
            services=services_table.total,
            instances=len(facts.filtered_instances),
            leases=len(facts.filtered_leases),
            processes=len(facts.filtered_process_rows),
            dependencies=len(daemon_service_groups(facts.services)),
            events=len(facts.observed_events),
        ),
        active_tab="instances",
        actions=actions,
        service_sets=service_sets_table,
        services=services_table,
        instances=instances_table,
        leases=leases_table,
        processes=processes_table,
        process_health=daemon_process_health(facts.current_process_rows),
        restart_summary=daemon_state_summary(facts.current_instances),
        lease_health=daemon_lease_health(facts.current_leases),
        dependency_health=daemon_dependency_health_table(
            services=facts.services,
            instances_by_service=facts.instances_by_service,
            leases_by_service=facts.leases_by_service,
        ),
        drain_overview=daemon_drain_overview(
            services=facts.services,
            instances=facts.current_instances,
            leases=facts.current_leases,
            process_rows=facts.current_process_rows,
            instances_by_service=facts.current_instances_by_service,
            leases_by_service=facts.leases_by_service,
            runtime_bootstrap_config=runtime_bootstrap_config,
        ),
        daemon_events=events_table,
        quick_actions=actions,
        links_to_operations=daemon_links_to_operations(),
        instance_details=daemon_instance_details(
            instances=facts.visible_instances,
            service_by_key=facts.service_by_key,
            leases_by_instance=facts.leases_by_instance,
            events=facts.observed_events,
        ),
        lease_details=daemon_lease_details(
            leases=facts.visible_leases,
            service_by_key=facts.service_by_key,
            events=facts.observed_events,
        ),
        process_details=daemon_process_details(
            process_rows=facts.visible_process_rows,
            process_service=process_service,
        ),
    )
