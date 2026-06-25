from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleRoleModel,
)
from crxzipple.modules.operations.application.read_models.skills_details import (
    skill_details as _skill_details,
)
from crxzipple.modules.operations.application.read_models.skills_actions import (
    actions as _actions,
    import_actions as _import_actions,
)
from crxzipple.modules.operations.application.read_models.skills_charts import (
    readiness_chart as _readiness_chart,
    source_chart as _source_chart,
)
from crxzipple.modules.operations.application.read_models.skills_health import (
    metrics as _metrics,
    tabs as _tabs,
)
from crxzipple.modules.operations.application.read_models.skills_models import (
    SkillsOperationsPage,
    SkillsOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.skills_page_facts import (
    collect_skills_page_facts,
)
from crxzipple.modules.operations.application.read_models.skills_authoring_tables import (
    authoring_backlog_table as _authoring_backlog_table,
    authoring_failures_table as _authoring_failures_table,
)
from crxzipple.modules.operations.application.read_models.skills_catalog_tables import (
    conflicts_table as _conflicts_table,
    skills_table as _skills_table,
)
from crxzipple.modules.operations.application.read_models.skills_event_tables import (
    resolution_logs_table as _resolution_logs_table,
    skill_reads_table as _skill_reads_table,
)
from crxzipple.modules.operations.application.read_models.skills_usage_tables import (
    skill_usage_table as _skill_usage_table,
)
from crxzipple.modules.operations.application.read_models.skills_missing_tables import (
    missing_capabilities_table as _missing_capabilities_table,
)
from crxzipple.modules.operations.application.read_models.skills_profile_usage_table import (
    profile_usage_table as _profile_usage_table,
)
from crxzipple.modules.operations.application.read_models.skills_requirement_tables import (
    access_requirements_table as _access_requirements_table,
    capability_requirements_table as _capability_requirements_table,
)
from crxzipple.modules.operations.application.read_models.skills_resolver_tables import (
    resolver_detail_table as _resolver_detail_table,
)
from crxzipple.shared.time import format_datetime_utc


def skills_operations_page(
    *,
    skill_manager: Any | None,
    tool_service: Any | None = None,
    access_service: Any | None = None,
    agent_service: Any | None = None,
    events_service: Any | None = None,
    event_definition_registry: Any | None = None,
    operations_observation: Any | None = None,
    query: SkillsOperationsQuery | None = None,
) -> SkillsOperationsPage:
    facts = collect_skills_page_facts(
        skill_manager=skill_manager,
        tool_service=tool_service,
        access_service=access_service,
        events_service=events_service,
        event_definition_registry=event_definition_registry,
        operations_observation=operations_observation,
        query=query,
    )
    missing_capabilities = _missing_capabilities_table(facts.records)
    access_requirements = _access_requirements_table(facts.records)
    capability_requirements = _capability_requirements_table(
        facts.records,
        facts.tool_ids,
    )
    logs = _resolution_logs_table(facts.events)
    skill_reads = _skill_reads_table(facts.events)
    resolver_detail = _resolver_detail_table(facts.records, facts.tool_ids)
    authoring_backlog = _authoring_backlog_table(facts.events)
    authoring_failures = _authoring_failures_table(facts.events)
    conflicts = _conflicts_table(facts.packages)
    profile_usage = _profile_usage_table(
        agent_service,
        surface=facts.query.surface,
        available=len(facts.records),
        ready=sum(1 for record in facts.records if record.status == "Ready"),
    )
    installed = _skills_table(
        facts.visible_records,
        total=len(facts.filtered_records),
    )
    top_used = _skill_usage_table(facts.events)
    sources = _source_chart(facts.records)

    return SkillsOperationsPage(
        module="skills",
        title="Skills",
        subtitle="观察技能包目录、声明能力、访问要求、解析结果与导入入口的运维视图。",
        health=facts.health,
        updated_at=format_datetime_utc(facts.now),
        auto_refresh=True,
        role=OperationsModuleRoleModel(
            label="Skills operator",
            can_operate=True,
            scope="skills",
        ),
        metrics=_metrics(
            health=facts.health,
            records=facts.records,
            missing=missing_capabilities,
            access=access_requirements,
            events=facts.events,
            event_buckets=facts.event_buckets,
        ),
        tabs=_tabs(
            installed=installed.total,
            missing=missing_capabilities.total,
            access=access_requirements.total,
            capability=capability_requirements.total,
            logs=logs.total,
            reads=skill_reads.total,
            resolver=resolver_detail.total,
            authoring=authoring_backlog.total,
            authoring_failures=authoring_failures.total,
            conflicts=conflicts.total,
            profile=profile_usage.total,
        ),
        active_tab="installed",
        actions=_actions(facts.query.surface),
        recently_resolved_skills=installed,
        resolution_outcomes=_readiness_chart(facts.records),
        top_used_skills=top_used,
        missing_capabilities=missing_capabilities,
        access_requirements=access_requirements,
        capability_requirements=capability_requirements,
        resolution_logs=logs,
        skill_reads=skill_reads,
        resolver_detail=resolver_detail,
        authoring_backlog=authoring_backlog,
        authoring_failures=authoring_failures,
        import_normalize=_import_actions(),
        skill_package_sources=sources,
        conflicts_overrides=conflicts,
        profile_usage=profile_usage,
        skill_details=_skill_details(facts.visible_records, facts.events),
    )
