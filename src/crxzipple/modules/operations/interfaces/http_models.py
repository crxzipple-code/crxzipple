from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from crxzipple.modules.operations.application.read_models import (
    AccessOperationsPage,
    AccessTargetDetailModel,
    ChannelInteractionDetailModel,
    ChannelRecordDetailModel,
    ChannelRuntimeDetailModel,
    BrowserOperationsPage,
    ChannelsOperationsPage,
    DaemonInstanceDetailModel,
    DaemonLeaseDetailModel,
    DaemonOperationsPage,
    DaemonProcessDetailModel,
    EventsEventDetailModel,
    EventsOperationsPage,
    MetricCardModel,
    MemoryFileDetailModel,
    MemoryOperationsPage,
    OperationsModuleOverview,
    OperationsTabModel,
    OrchestrationOperationsPage,
    RuntimeActionModel,
    SkillDetailModel,
    SkillsOperationsPage,
    ToolOperationsPage,
    ToolRunDetailModel,
    OperationsChartSectionModel,
    OperationsChartSegmentModel,
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
    OperationsModuleRoleModel,
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
    LlmInvocationDetailModel,
    LlmOperationsPage,
    ToolWorkerDetailModel,
)


class MetricCardResponse(BaseModel):
    id: str
    label: str
    value: str
    delta: str
    tone: str = "neutral"

    @classmethod
    def from_value(cls, value: MetricCardModel) -> "MetricCardResponse":
        return cls(
            id=value.id,
            label=value.label,
            value=value.value,
            delta=value.delta,
            tone=value.tone,
        )


class RuntimeActionResponse(BaseModel):
    id: str
    label: str
    owner: str = "runtime"
    kind: str = "operation"
    risk: str = "normal"
    allowed: bool = True
    disabled_reason: str | None = None
    requires_confirmation: bool = False
    reason_required: bool = False
    audit_event: str | None = None
    method: str | None = None
    endpoint: str | None = None

    @classmethod
    def from_value(cls, value: RuntimeActionModel) -> "RuntimeActionResponse":
        return cls(
            id=value.id,
            label=value.label,
            owner=getattr(value, "owner", "runtime"),
            kind=getattr(value, "kind", "operation"),
            risk=value.risk,
            allowed=getattr(value, "allowed", True),
            disabled_reason=getattr(value, "disabled_reason", None),
            requires_confirmation=getattr(value, "requires_confirmation", False),
            reason_required=getattr(value, "reason_required", False),
            audit_event=getattr(value, "audit_event", None),
            method=getattr(value, "method", None),
            endpoint=getattr(value, "endpoint", None),
        )


class OperationsActionAuditRequest(BaseModel):
    operator: str | None = None
    source: str | None = "operations"
    metadata: dict[str, Any] = Field(default_factory=dict)


class OperationsActionRequest(BaseModel):
    reason: str | None = None
    confirmation: bool | str | None = None
    risk_acknowledged: bool = False
    risk_ack: bool = False
    operator: str | None = None
    source: str | None = "operations"
    metadata: dict[str, Any] = Field(default_factory=dict)
    audit: OperationsActionAuditRequest | None = None

    def acknowledged_risk(self) -> bool:
        return bool(self.risk_acknowledged or self.risk_ack)


class OperationsActionAuditResponse(BaseModel):
    audit_id: str
    audit_event: str
    action_type: str
    target_type: str
    target_id: str | None = None
    target: dict[str, Any]
    reason: str
    dangerous: bool
    risk: str
    confirmation: bool
    risk_acknowledged: bool
    operator: str | None = None
    source: str
    metadata: dict[str, Any]
    created_at: str
    updated_at: str
    status: str
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    @classmethod
    def from_value(cls, value: Any) -> "OperationsActionAuditResponse":
        from crxzipple.shared.time import format_datetime_utc

        return cls(
            audit_id=value.audit_id,
            audit_event=value.action_type,
            action_type=value.action_type,
            target_type=value.target_type,
            target_id=value.target_id,
            target=dict(value.target),
            reason=value.reason,
            dangerous=value.dangerous,
            risk=value.risk,
            confirmation=value.confirmation,
            risk_acknowledged=value.risk_acknowledged,
            operator=value.operator,
            source=value.source,
            metadata=dict(value.metadata),
            created_at=format_datetime_utc(value.created_at),
            updated_at=format_datetime_utc(value.updated_at),
            status=value.status,
            result=dict(value.result) if value.result is not None else None,
            error=dict(value.error) if value.error is not None else None,
        )


class OperationsEventSubscriptionAdvanceRequest(OperationsActionRequest):
    subscription_id: str | None = None
    source_topic: str | None = None
    status: str = "stuck"
    observer_only: bool = False
    dry_run: bool = False


class OperationsEventSubscriptionAdvanceItemResponse(BaseModel):
    subscription_id: str
    source_topic: str
    previous_cursor: str
    latest_cursor: str
    status: str
    changed: bool


class OperationsEventSubscriptionAdvanceResponse(BaseModel):
    matched_count: int
    advanced_count: int
    skipped_count: int
    dry_run: bool
    reason: str | None = None
    items: list[OperationsEventSubscriptionAdvanceItemResponse]

    @classmethod
    def from_result(cls, result: Any) -> "OperationsEventSubscriptionAdvanceResponse":
        return cls(
            matched_count=result.matched_count,
            advanced_count=result.advanced_count,
            skipped_count=result.skipped_count,
            dry_run=result.dry_run,
            reason=result.reason,
            items=[
                OperationsEventSubscriptionAdvanceItemResponse(
                    subscription_id=item.subscription_id,
                    source_topic=item.source_topic,
                    previous_cursor=item.previous_cursor,
                    latest_cursor=item.latest_cursor,
                    status=item.status,
                    changed=item.changed,
                )
                for item in result.items
            ],
        )


class OperationsChannelRuntimePruneRequest(OperationsActionRequest):
    runtime_id: str | None = None
    channel_type: str | None = None
    stale_after_seconds: float = 300.0
    dry_run: bool = False


class OperationsActionReasonRequest(OperationsActionRequest):
    pass


class OperationsDaemonServiceActionRequest(OperationsActionRequest):
    pass


class OperationsToolWorkerPruneRequest(OperationsActionRequest):
    retention_seconds: int = 3600


class OperationsLlmWarmupResponse(BaseModel):
    llm_id: str
    status: str
    details: dict[str, Any] = Field(default_factory=dict)


class OperationsChannelDeadLetterReplayRequest(OperationsActionRequest):
    runtime_id: str | None = None
    cursor: str | None = None
    event_id: str | None = None


class OperationsSkillValidateRequest(OperationsActionRequest):
    path: str


class OperationsSkillInstallRequest(OperationsActionRequest):
    source_dir: str


class OperationsSkillSyncRequest(OperationsActionRequest):
    workspace_dir: str | None = None
    source_id: str | None = None
    surface: str = "interactive"


class OperationsAccessCheckRequest(OperationsActionRequest):
    requirements: list[str] = Field(default_factory=list)
    credential_bindings: list[str] = Field(default_factory=list)
    workspace_dir: str | None = None
    allow_literal_credentials: bool = False


class OperationsMemoryWriteLongTermRequest(OperationsActionRequest):
    agent_id: str
    content: str


class OperationsToolRunActionResponse(BaseModel):
    id: str
    tool_id: str
    status: str
    cancel_requested_at: str | None = None


class OperationsToolWorkerPruneResponse(BaseModel):
    pruned_count: int
    worker_ids: list[str]
    cutoff: str


class OperationsMemoryWriteResultResponse(BaseModel):
    path: str
    line_start: int
    line_end: int
    kind: str


class OperationsChannelRuntimePruneItemResponse(BaseModel):
    runtime_id: str
    channel_type: str
    status: str
    heartbeat_age_seconds: float
    account_bindings_removed: int
    connection_bindings_removed: int
    pruned: bool


class OperationsChannelRuntimePruneResponse(BaseModel):
    matched_count: int
    pruned_count: int
    skipped_count: int
    dry_run: bool
    reason: str | None = None
    items: list[OperationsChannelRuntimePruneItemResponse]

    @classmethod
    def from_result(cls, result: Any) -> "OperationsChannelRuntimePruneResponse":
        return cls(
            matched_count=result.matched_count,
            pruned_count=result.pruned_count,
            skipped_count=result.skipped_count,
            dry_run=result.dry_run,
            reason=result.reason,
            items=[
                OperationsChannelRuntimePruneItemResponse(
                    runtime_id=item.runtime_id,
                    channel_type=item.channel_type,
                    status=item.status,
                    heartbeat_age_seconds=item.heartbeat_age_seconds,
                    account_bindings_removed=item.account_bindings_removed,
                    connection_bindings_removed=item.connection_bindings_removed,
                    pruned=item.pruned,
                )
                for item in result.items
            ],
        )


class OperationsModuleOverviewResponse(BaseModel):
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    metrics: list[MetricCardResponse]
    queue: list[dict[str, str]]
    lane_locks: list[dict[str, str]]
    executor: list[dict[str, str]]
    actions: list[RuntimeActionResponse]

    @classmethod
    def from_view(
        cls,
        view: OperationsModuleOverview,
    ) -> "OperationsModuleOverviewResponse":
        return cls(
            module=view.module,
            title=view.title,
            subtitle=view.subtitle,
            health=view.health,
            updated_at=view.updated_at,
            metrics=[MetricCardResponse.from_value(item) for item in view.metrics],
            queue=list(view.queue),
            lane_locks=list(view.lane_locks),
            executor=list(view.executor),
            actions=[RuntimeActionResponse.from_value(item) for item in view.actions],
        )


class OperationsRuntimeStatusItemResponse(BaseModel):
    id: str
    label: str
    value: str
    status: str
    tone: str = "neutral"
    details: str | None = None


class OperationsRuntimeStatusResponse(BaseModel):
    updated_at: str
    checks: list[OperationsRuntimeStatusItemResponse]


class OperationsTabResponse(BaseModel):
    id: str
    label: str
    count: int | None = None
    tone: str = "neutral"

    @classmethod
    def from_value(cls, value: OperationsTabModel) -> "OperationsTabResponse":
        return cls(
            id=value.id,
            label=value.label,
            count=value.count,
            tone=value.tone,
        )


class OperationsModuleRoleResponse(BaseModel):
    label: str
    can_operate: bool
    scope: str | None = None

    @classmethod
    def from_value(
        cls, value: OperationsModuleRoleModel
    ) -> "OperationsModuleRoleResponse":
        return cls(
            label=value.label,
            can_operate=value.can_operate,
            scope=value.scope,
        )


class OperationsKeyValueItemResponse(BaseModel):
    label: str
    value: str
    tone: str = "neutral"

    @classmethod
    def from_value(
        cls, value: OperationsKeyValueItemModel
    ) -> "OperationsKeyValueItemResponse":
        return cls(label=value.label, value=value.value, tone=value.tone)


class OperationsKeyValueSectionResponse(BaseModel):
    id: str
    title: str
    items: list[OperationsKeyValueItemResponse]

    @classmethod
    def from_value(
        cls, value: OperationsKeyValueSectionModel
    ) -> "OperationsKeyValueSectionResponse":
        return cls(
            id=value.id,
            title=value.title,
            items=[
                OperationsKeyValueItemResponse.from_value(item) for item in value.items
            ],
        )


class OperationsChartSegmentResponse(BaseModel):
    id: str
    label: str
    value: int
    tone: str = "neutral"

    @classmethod
    def from_value(
        cls, value: OperationsChartSegmentModel
    ) -> "OperationsChartSegmentResponse":
        return cls(
            id=value.id,
            label=value.label,
            value=value.value,
            tone=value.tone,
        )


class OperationsChartSectionResponse(BaseModel):
    id: str
    title: str
    kind: str
    total: int
    segments: list[OperationsChartSegmentResponse]

    @classmethod
    def from_value(
        cls, value: OperationsChartSectionModel
    ) -> "OperationsChartSectionResponse":
        return cls(
            id=value.id,
            title=value.title,
            kind=value.kind,
            total=value.total,
            segments=[
                OperationsChartSegmentResponse.from_value(item)
                for item in value.segments
            ],
        )


class OperationsTableColumnResponse(BaseModel):
    key: str
    label: str

    @classmethod
    def from_value(
        cls, value: OperationsTableColumnModel
    ) -> "OperationsTableColumnResponse":
        return cls(key=value.key, label=value.label)


class OperationsTableRowResponse(BaseModel):
    id: str
    cells: dict[str, str]
    status: str | None = None
    tone: str = "neutral"

    @classmethod
    def from_value(cls, value: OperationsTableRowModel) -> "OperationsTableRowResponse":
        return cls(
            id=value.id,
            cells=dict(value.cells),
            status=value.status,
            tone=value.tone,
        )


class OperationsTableSectionResponse(BaseModel):
    id: str
    title: str
    columns: list[OperationsTableColumnResponse]
    rows: list[OperationsTableRowResponse]
    total: int
    view_all_route: str | None = None
    empty_state: str | None = None

    @classmethod
    def from_value(
        cls, value: OperationsTableSectionModel
    ) -> "OperationsTableSectionResponse":
        return cls(
            id=value.id,
            title=value.title,
            columns=[
                OperationsTableColumnResponse.from_value(item) for item in value.columns
            ],
            rows=[OperationsTableRowResponse.from_value(item) for item in value.rows],
            total=value.total,
            view_all_route=value.view_all_route,
            empty_state=value.empty_state,
        )


class OperationsModulePageResponse(BaseModel):
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    auto_refresh: bool
    role: OperationsModuleRoleResponse
    metrics: list[MetricCardResponse]
    tabs: list[OperationsTabResponse]
    active_tab: str
    actions: list[RuntimeActionResponse]
    sections: list[OperationsTableSectionResponse]

    @classmethod
    def from_view(
        cls,
        view: Any,
    ) -> "OperationsModulePageResponse":
        return cls(
            module=view.module,
            title=view.title,
            subtitle=view.subtitle,
            health=view.health,
            updated_at=view.updated_at,
            auto_refresh=view.auto_refresh,
            role=OperationsModuleRoleResponse.from_value(view.role),
            metrics=[MetricCardResponse.from_value(item) for item in view.metrics],
            tabs=[OperationsTabResponse.from_value(item) for item in view.tabs],
            active_tab=view.active_tab,
            actions=[RuntimeActionResponse.from_value(item) for item in view.actions],
            sections=[
                OperationsTableSectionResponse.from_value(item)
                for item in view.sections
            ],
        )


class AccessTargetDetailResponse(BaseModel):
    target_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    checks: OperationsTableSectionResponse
    usages: OperationsTableSectionResponse
    setup: OperationsTableSectionResponse
    events: OperationsTableSectionResponse
    raw_payload: Any

    @classmethod
    def from_value(
        cls,
        value: AccessTargetDetailModel,
    ) -> "AccessTargetDetailResponse":
        return cls(
            target_id=value.target_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            checks=OperationsTableSectionResponse.from_value(value.checks),
            usages=OperationsTableSectionResponse.from_value(value.usages),
            setup=OperationsTableSectionResponse.from_value(value.setup),
            events=OperationsTableSectionResponse.from_value(value.events),
            raw_payload=value.raw_payload,
        )


class AccessOperationsResponse(BaseModel):
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    auto_refresh: bool
    role: OperationsModuleRoleResponse
    metrics: list[MetricCardResponse]
    tabs: list[OperationsTabResponse]
    active_tab: str
    actions: list[RuntimeActionResponse]
    access_targets: OperationsTableSectionResponse
    access_requirements: OperationsTableSectionResponse
    access_audit_summary: OperationsTableSectionResponse
    missing_access: OperationsTableSectionResponse
    credential_health: OperationsChartSectionResponse
    provider_auth_blocked: OperationsTableSectionResponse
    credentials_by_kind: OperationsChartSectionResponse
    expiring_soon: OperationsTableSectionResponse
    auth_success_rate: OperationsChartSectionResponse
    authentication_status: OperationsTableSectionResponse
    access_usage: OperationsTableSectionResponse
    recent_access_events: OperationsTableSectionResponse
    fallback_problems: OperationsTableSectionResponse
    setup_flows: OperationsTableSectionResponse
    target_details: list[AccessTargetDetailResponse]

    @classmethod
    def from_view(
        cls,
        view: AccessOperationsPage,
    ) -> "AccessOperationsResponse":
        return cls(
            module=view.module,
            title=view.title,
            subtitle=view.subtitle,
            health=view.health,
            updated_at=view.updated_at,
            auto_refresh=view.auto_refresh,
            role=OperationsModuleRoleResponse.from_value(view.role),
            metrics=[MetricCardResponse.from_value(item) for item in view.metrics],
            tabs=[OperationsTabResponse.from_value(item) for item in view.tabs],
            active_tab=view.active_tab,
            actions=[RuntimeActionResponse.from_value(item) for item in view.actions],
            access_targets=OperationsTableSectionResponse.from_value(
                view.access_targets,
            ),
            access_requirements=OperationsTableSectionResponse.from_value(
                view.access_requirements,
            ),
            access_audit_summary=OperationsTableSectionResponse.from_value(
                view.access_audit_summary,
            ),
            missing_access=OperationsTableSectionResponse.from_value(
                view.missing_access,
            ),
            credential_health=OperationsChartSectionResponse.from_value(
                view.credential_health,
            ),
            provider_auth_blocked=OperationsTableSectionResponse.from_value(
                view.provider_auth_blocked,
            ),
            credentials_by_kind=OperationsChartSectionResponse.from_value(
                view.credentials_by_kind,
            ),
            expiring_soon=OperationsTableSectionResponse.from_value(
                view.expiring_soon,
            ),
            auth_success_rate=OperationsChartSectionResponse.from_value(
                view.auth_success_rate,
            ),
            authentication_status=OperationsTableSectionResponse.from_value(
                view.authentication_status,
            ),
            access_usage=OperationsTableSectionResponse.from_value(view.access_usage),
            recent_access_events=OperationsTableSectionResponse.from_value(
                view.recent_access_events,
            ),
            fallback_problems=OperationsTableSectionResponse.from_value(
                view.fallback_problems,
            ),
            setup_flows=OperationsTableSectionResponse.from_value(view.setup_flows),
            target_details=[
                AccessTargetDetailResponse.from_value(item)
                for item in view.target_details
            ],
        )


class MemoryFileDetailResponse(BaseModel):
    file_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    excerpt: str
    related: OperationsTableSectionResponse
    raw_payload: Any

    @classmethod
    def from_value(
        cls,
        value: MemoryFileDetailModel,
    ) -> "MemoryFileDetailResponse":
        return cls(
            file_id=value.file_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            excerpt=value.excerpt,
            related=OperationsTableSectionResponse.from_value(value.related),
            raw_payload=value.raw_payload,
        )


class MemoryOperationsResponse(BaseModel):
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    auto_refresh: bool
    role: OperationsModuleRoleResponse
    metrics: list[MetricCardResponse]
    tabs: list[OperationsTabResponse]
    active_tab: str
    actions: list[RuntimeActionResponse]
    memory_stores: OperationsTableSectionResponse
    context_resolution: OperationsTableSectionResponse
    index_health: OperationsChartSectionResponse
    index_jobs: OperationsTableSectionResponse
    index_sync_activity: OperationsTableSectionResponse
    retrieval_performance: OperationsChartSectionResponse
    retrieval_trace: OperationsTableSectionResponse
    write_flush: OperationsTableSectionResponse
    memory_usage: OperationsTableSectionResponse
    recent_retrieval_logs: OperationsTableSectionResponse
    source_scan_status: OperationsTableSectionResponse
    source_files: OperationsTableSectionResponse
    file_details: list[MemoryFileDetailResponse]

    @classmethod
    def from_view(
        cls,
        view: MemoryOperationsPage,
    ) -> "MemoryOperationsResponse":
        return cls(
            module=view.module,
            title=view.title,
            subtitle=view.subtitle,
            health=view.health,
            updated_at=view.updated_at,
            auto_refresh=view.auto_refresh,
            role=OperationsModuleRoleResponse.from_value(view.role),
            metrics=[MetricCardResponse.from_value(item) for item in view.metrics],
            tabs=[OperationsTabResponse.from_value(item) for item in view.tabs],
            active_tab=view.active_tab,
            actions=[RuntimeActionResponse.from_value(item) for item in view.actions],
            memory_stores=OperationsTableSectionResponse.from_value(
                view.memory_stores,
            ),
            context_resolution=OperationsTableSectionResponse.from_value(
                view.context_resolution,
            ),
            index_health=OperationsChartSectionResponse.from_value(
                view.index_health,
            ),
            index_jobs=OperationsTableSectionResponse.from_value(view.index_jobs),
            index_sync_activity=OperationsTableSectionResponse.from_value(
                view.index_sync_activity,
            ),
            retrieval_performance=OperationsChartSectionResponse.from_value(
                view.retrieval_performance,
            ),
            retrieval_trace=OperationsTableSectionResponse.from_value(
                view.retrieval_trace,
            ),
            write_flush=OperationsTableSectionResponse.from_value(view.write_flush),
            memory_usage=OperationsTableSectionResponse.from_value(
                view.memory_usage,
            ),
            recent_retrieval_logs=OperationsTableSectionResponse.from_value(
                view.recent_retrieval_logs,
            ),
            source_scan_status=OperationsTableSectionResponse.from_value(
                view.source_scan_status,
            ),
            source_files=OperationsTableSectionResponse.from_value(view.source_files),
            file_details=[
                MemoryFileDetailResponse.from_value(item)
                for item in view.file_details
            ],
        )


class SkillDetailResponse(BaseModel):
    skill_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    requirements: OperationsTableSectionResponse
    resources: OperationsTableSectionResponse
    events: OperationsTableSectionResponse
    raw_payload: Any

    @classmethod
    def from_value(cls, value: SkillDetailModel) -> "SkillDetailResponse":
        return cls(
            skill_id=value.skill_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            requirements=OperationsTableSectionResponse.from_value(
                value.requirements,
            ),
            resources=OperationsTableSectionResponse.from_value(value.resources),
            events=OperationsTableSectionResponse.from_value(value.events),
            raw_payload=value.raw_payload,
        )


class SkillsOperationsResponse(BaseModel):
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    auto_refresh: bool
    role: OperationsModuleRoleResponse
    metrics: list[MetricCardResponse]
    tabs: list[OperationsTabResponse]
    active_tab: str
    actions: list[RuntimeActionResponse]
    recently_resolved_skills: OperationsTableSectionResponse
    resolution_outcomes: OperationsChartSectionResponse
    top_used_skills: OperationsTableSectionResponse
    missing_capabilities: OperationsTableSectionResponse
    access_requirements: OperationsTableSectionResponse
    capability_requirements: OperationsTableSectionResponse
    resolution_logs: OperationsTableSectionResponse
    skill_reads: OperationsTableSectionResponse
    resolver_detail: OperationsTableSectionResponse
    authoring_backlog: OperationsTableSectionResponse
    authoring_failures: OperationsTableSectionResponse
    import_normalize: list[RuntimeActionResponse]
    skill_package_sources: OperationsChartSectionResponse
    conflicts_overrides: OperationsTableSectionResponse
    profile_usage: OperationsTableSectionResponse
    skill_details: list[SkillDetailResponse]

    @classmethod
    def from_view(
        cls,
        view: SkillsOperationsPage,
    ) -> "SkillsOperationsResponse":
        return cls(
            module=view.module,
            title=view.title,
            subtitle=view.subtitle,
            health=view.health,
            updated_at=view.updated_at,
            auto_refresh=view.auto_refresh,
            role=OperationsModuleRoleResponse.from_value(view.role),
            metrics=[MetricCardResponse.from_value(item) for item in view.metrics],
            tabs=[OperationsTabResponse.from_value(item) for item in view.tabs],
            active_tab=view.active_tab,
            actions=[RuntimeActionResponse.from_value(item) for item in view.actions],
            recently_resolved_skills=OperationsTableSectionResponse.from_value(
                view.recently_resolved_skills,
            ),
            resolution_outcomes=OperationsChartSectionResponse.from_value(
                view.resolution_outcomes,
            ),
            top_used_skills=OperationsTableSectionResponse.from_value(
                view.top_used_skills,
            ),
            missing_capabilities=OperationsTableSectionResponse.from_value(
                view.missing_capabilities,
            ),
            access_requirements=OperationsTableSectionResponse.from_value(
                view.access_requirements,
            ),
            capability_requirements=OperationsTableSectionResponse.from_value(
                view.capability_requirements,
            ),
            resolution_logs=OperationsTableSectionResponse.from_value(
                view.resolution_logs,
            ),
            skill_reads=OperationsTableSectionResponse.from_value(
                view.skill_reads,
            ),
            resolver_detail=OperationsTableSectionResponse.from_value(
                view.resolver_detail,
            ),
            authoring_backlog=OperationsTableSectionResponse.from_value(
                view.authoring_backlog,
            ),
            authoring_failures=OperationsTableSectionResponse.from_value(
                view.authoring_failures,
            ),
            import_normalize=[
                RuntimeActionResponse.from_value(item)
                for item in view.import_normalize
            ],
            skill_package_sources=OperationsChartSectionResponse.from_value(
                view.skill_package_sources,
            ),
            conflicts_overrides=OperationsTableSectionResponse.from_value(
                view.conflicts_overrides,
            ),
            profile_usage=OperationsTableSectionResponse.from_value(
                view.profile_usage,
            ),
            skill_details=[
                SkillDetailResponse.from_value(item) for item in view.skill_details
            ],
        )


class ToolRunDetailResponse(BaseModel):
    run_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    invocation_context: list[OperationsKeyValueItemResponse]
    input_payload: Any
    result_payload: Any
    result_summary: str
    error: str
    error_facts: OperationsKeyValueSectionResponse
    assignments: OperationsTableSectionResponse
    events: OperationsTableSectionResponse
    artifacts: OperationsTableSectionResponse

    @classmethod
    def from_value(cls, value: ToolRunDetailModel) -> "ToolRunDetailResponse":
        return cls(
            run_id=value.run_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            invocation_context=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.invocation_context
            ],
            input_payload=value.input_payload,
            result_payload=value.result_payload,
            result_summary=value.result_summary,
            error=value.error,
            error_facts=OperationsKeyValueSectionResponse.from_value(
                value.error_facts,
            ),
            assignments=OperationsTableSectionResponse.from_value(value.assignments),
            events=OperationsTableSectionResponse.from_value(value.events),
            artifacts=OperationsTableSectionResponse.from_value(value.artifacts),
        )


class ToolWorkerDetailResponse(BaseModel):
    worker_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    capabilities: OperationsKeyValueSectionResponse
    runtimes: OperationsTableSectionResponse
    provider_limits: OperationsTableSectionResponse
    events: OperationsTableSectionResponse
    raw_payload: Any

    @classmethod
    def from_value(cls, value: ToolWorkerDetailModel) -> "ToolWorkerDetailResponse":
        return cls(
            worker_id=value.worker_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            capabilities=OperationsKeyValueSectionResponse.from_value(
                value.capabilities,
            ),
            runtimes=OperationsTableSectionResponse.from_value(value.runtimes),
            provider_limits=OperationsTableSectionResponse.from_value(
                value.provider_limits,
            ),
            events=OperationsTableSectionResponse.from_value(value.events),
            raw_payload=value.raw_payload,
        )


class LlmInvocationDetailResponse(BaseModel):
    invocation_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    request_context: list[OperationsKeyValueItemResponse]
    runtime_observations: OperationsKeyValueSectionResponse
    runtime_request_summary: dict[str, Any]
    request_payload: Any
    provider_render_report: dict[str, Any]
    provider_wire_preview: dict[str, Any]
    provider_context_mapping: OperationsTableSectionResponse
    result_payload: Any
    result_summary: str
    error: str
    resolver: OperationsKeyValueSectionResponse
    error_facts: OperationsKeyValueSectionResponse
    policy_trace: OperationsTableSectionResponse
    response_items: OperationsTableSectionResponse
    response_runtime_mapping: OperationsTableSectionResponse
    response_events: OperationsTableSectionResponse
    events: OperationsTableSectionResponse

    @classmethod
    def from_value(
        cls,
        value: LlmInvocationDetailModel,
    ) -> "LlmInvocationDetailResponse":
        return cls(
            invocation_id=value.invocation_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            request_context=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.request_context
            ],
            runtime_observations=OperationsKeyValueSectionResponse.from_value(
                value.runtime_observations,
            ),
            runtime_request_summary=dict(value.runtime_request_summary),
            request_payload=value.request_payload,
            provider_render_report=value.provider_render_report,
            provider_wire_preview=value.provider_wire_preview,
            provider_context_mapping=OperationsTableSectionResponse.from_value(
                value.provider_context_mapping,
            ),
            result_payload=value.result_payload,
            result_summary=value.result_summary,
            error=value.error,
            resolver=OperationsKeyValueSectionResponse.from_value(value.resolver),
            error_facts=OperationsKeyValueSectionResponse.from_value(
                value.error_facts,
            ),
            policy_trace=OperationsTableSectionResponse.from_value(
                value.policy_trace,
            ),
            response_items=OperationsTableSectionResponse.from_value(
                value.response_items,
            ),
            response_runtime_mapping=OperationsTableSectionResponse.from_value(
                value.response_runtime_mapping,
            ),
            response_events=OperationsTableSectionResponse.from_value(
                value.response_events,
            ),
            events=OperationsTableSectionResponse.from_value(value.events),
        )


class ChannelRuntimeDetailResponse(BaseModel):
    runtime_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    capabilities: OperationsKeyValueSectionResponse
    account_bindings: OperationsTableSectionResponse
    connection_bindings: OperationsTableSectionResponse
    events: OperationsTableSectionResponse
    dead_letters: OperationsTableSectionResponse
    raw_payload: Any

    @classmethod
    def from_value(
        cls,
        value: ChannelRuntimeDetailModel,
    ) -> "ChannelRuntimeDetailResponse":
        return cls(
            runtime_id=value.runtime_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            capabilities=OperationsKeyValueSectionResponse.from_value(
                value.capabilities,
            ),
            account_bindings=OperationsTableSectionResponse.from_value(
                value.account_bindings,
            ),
            connection_bindings=OperationsTableSectionResponse.from_value(
                value.connection_bindings,
            ),
            events=OperationsTableSectionResponse.from_value(value.events),
            dead_letters=OperationsTableSectionResponse.from_value(value.dead_letters),
            raw_payload=value.raw_payload,
        )


class ChannelRecordDetailResponse(BaseModel):
    record_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    payload: Any
    trace: Any
    related: OperationsTableSectionResponse

    @classmethod
    def from_value(
        cls,
        value: ChannelRecordDetailModel,
    ) -> "ChannelRecordDetailResponse":
        return cls(
            record_id=value.record_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            payload=value.payload,
            trace=value.trace,
            related=OperationsTableSectionResponse.from_value(value.related),
        )


class ChannelInteractionDetailResponse(BaseModel):
    interaction_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    routing: OperationsKeyValueSectionResponse
    reply_address: OperationsKeyValueSectionResponse
    metadata: OperationsKeyValueSectionResponse
    events: OperationsTableSectionResponse
    raw_payload: Any

    @classmethod
    def from_value(
        cls,
        value: ChannelInteractionDetailModel,
    ) -> "ChannelInteractionDetailResponse":
        return cls(
            interaction_id=value.interaction_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            routing=OperationsKeyValueSectionResponse.from_value(value.routing),
            reply_address=OperationsKeyValueSectionResponse.from_value(
                value.reply_address,
            ),
            metadata=OperationsKeyValueSectionResponse.from_value(value.metadata),
            events=OperationsTableSectionResponse.from_value(value.events),
            raw_payload=value.raw_payload,
        )


class EventsEventDetailResponse(BaseModel):
    event_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    payload: Any
    trace: Any
    contracts: OperationsTableSectionResponse
    subscriptions: OperationsTableSectionResponse

    @classmethod
    def from_value(
        cls,
        value: EventsEventDetailModel,
    ) -> "EventsEventDetailResponse":
        return cls(
            event_id=value.event_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            payload=value.payload,
            trace=value.trace,
            contracts=OperationsTableSectionResponse.from_value(value.contracts),
            subscriptions=OperationsTableSectionResponse.from_value(
                value.subscriptions,
            ),
        )


class DaemonInstanceDetailResponse(BaseModel):
    instance_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    environment: OperationsKeyValueSectionResponse
    service: OperationsKeyValueSectionResponse
    leases: OperationsTableSectionResponse
    events: OperationsTableSectionResponse
    raw_payload: Any

    @classmethod
    def from_value(
        cls,
        value: DaemonInstanceDetailModel,
    ) -> "DaemonInstanceDetailResponse":
        return cls(
            instance_id=value.instance_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            environment=OperationsKeyValueSectionResponse.from_value(
                value.environment,
            ),
            service=OperationsKeyValueSectionResponse.from_value(value.service),
            leases=OperationsTableSectionResponse.from_value(value.leases),
            events=OperationsTableSectionResponse.from_value(value.events),
            raw_payload=value.raw_payload,
        )


class DaemonLeaseDetailResponse(BaseModel):
    lease_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    metadata: OperationsKeyValueSectionResponse
    events: OperationsTableSectionResponse
    raw_payload: Any

    @classmethod
    def from_value(
        cls,
        value: DaemonLeaseDetailModel,
    ) -> "DaemonLeaseDetailResponse":
        return cls(
            lease_id=value.lease_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            metadata=OperationsKeyValueSectionResponse.from_value(value.metadata),
            events=OperationsTableSectionResponse.from_value(value.events),
            raw_payload=value.raw_payload,
        )


class DaemonProcessDetailResponse(BaseModel):
    process_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    metadata: OperationsKeyValueSectionResponse
    output: OperationsTableSectionResponse
    raw_payload: Any

    @classmethod
    def from_value(
        cls,
        value: DaemonProcessDetailModel,
    ) -> "DaemonProcessDetailResponse":
        return cls(
            process_id=value.process_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            metadata=OperationsKeyValueSectionResponse.from_value(value.metadata),
            output=OperationsTableSectionResponse.from_value(value.output),
            raw_payload=value.raw_payload,
        )


class ChannelsOperationsResponse(BaseModel):
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    auto_refresh: bool
    role: OperationsModuleRoleResponse
    metrics: list[MetricCardResponse]
    tabs: list[OperationsTabResponse]
    active_tab: str
    actions: list[RuntimeActionResponse]
    channel_status: OperationsTableSectionResponse
    message_flow: OperationsChartSectionResponse
    delivery_trend: OperationsChartSectionResponse
    top_channels: OperationsChartSectionResponse
    dead_letter_queue: OperationsTableSectionResponse
    recent_messages: OperationsTableSectionResponse
    interactions: OperationsTableSectionResponse
    failures_by_category: OperationsChartSectionResponse
    channel_bindings: OperationsTableSectionResponse
    connection_bindings: OperationsTableSectionResponse
    channel_profiles: OperationsTableSectionResponse
    channel_events: OperationsTableSectionResponse
    contracts: OperationsTableSectionResponse
    runtime_details: list[ChannelRuntimeDetailResponse]
    record_details: list[ChannelRecordDetailResponse]
    interaction_details: list[ChannelInteractionDetailResponse]

    @classmethod
    def from_view(
        cls,
        view: ChannelsOperationsPage,
    ) -> "ChannelsOperationsResponse":
        return cls(
            module=view.module,
            title=view.title,
            subtitle=view.subtitle,
            health=view.health,
            updated_at=view.updated_at,
            auto_refresh=view.auto_refresh,
            role=OperationsModuleRoleResponse.from_value(view.role),
            metrics=[MetricCardResponse.from_value(item) for item in view.metrics],
            tabs=[OperationsTabResponse.from_value(item) for item in view.tabs],
            active_tab=view.active_tab,
            actions=[RuntimeActionResponse.from_value(item) for item in view.actions],
            channel_status=OperationsTableSectionResponse.from_value(
                view.channel_status,
            ),
            message_flow=OperationsChartSectionResponse.from_value(
                view.message_flow,
            ),
            delivery_trend=OperationsChartSectionResponse.from_value(
                view.delivery_trend,
            ),
            top_channels=OperationsChartSectionResponse.from_value(
                view.top_channels,
            ),
            dead_letter_queue=OperationsTableSectionResponse.from_value(
                view.dead_letter_queue,
            ),
            recent_messages=OperationsTableSectionResponse.from_value(
                view.recent_messages,
            ),
            interactions=OperationsTableSectionResponse.from_value(
                view.interactions,
            ),
            failures_by_category=OperationsChartSectionResponse.from_value(
                view.failures_by_category,
            ),
            channel_bindings=OperationsTableSectionResponse.from_value(
                view.channel_bindings,
            ),
            connection_bindings=OperationsTableSectionResponse.from_value(
                view.connection_bindings,
            ),
            channel_profiles=OperationsTableSectionResponse.from_value(
                view.channel_profiles,
            ),
            channel_events=OperationsTableSectionResponse.from_value(
                view.channel_events,
            ),
            contracts=OperationsTableSectionResponse.from_value(view.contracts),
            runtime_details=[
                ChannelRuntimeDetailResponse.from_value(item)
                for item in view.runtime_details
            ],
            record_details=[
                ChannelRecordDetailResponse.from_value(item)
                for item in view.record_details
            ],
            interaction_details=[
                ChannelInteractionDetailResponse.from_value(item)
                for item in view.interaction_details
            ],
        )


class BrowserOperationsResponse(BaseModel):
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    auto_refresh: bool
    role: OperationsModuleRoleResponse
    metrics: list[MetricCardResponse]
    tabs: list[OperationsTabResponse]
    active_tab: str
    actions: list[RuntimeActionResponse]
    profiles: OperationsTableSectionResponse
    profile_pools: OperationsTableSectionResponse
    profile_allocations: OperationsTableSectionResponse
    page_observations: OperationsTableSectionResponse
    daemon_runtimes: OperationsTableSectionResponse
    network_activity: OperationsTableSectionResponse
    diagnostics: OperationsTableSectionResponse

    @classmethod
    def from_view(
        cls,
        view: BrowserOperationsPage,
    ) -> "BrowserOperationsResponse":
        return cls(
            module=view.module,
            title=view.title,
            subtitle=view.subtitle,
            health=view.health,
            updated_at=view.updated_at,
            auto_refresh=view.auto_refresh,
            role=OperationsModuleRoleResponse.from_value(view.role),
            metrics=[MetricCardResponse.from_value(item) for item in view.metrics],
            tabs=[OperationsTabResponse.from_value(item) for item in view.tabs],
            active_tab=view.active_tab,
            actions=[RuntimeActionResponse.from_value(item) for item in view.actions],
            profiles=OperationsTableSectionResponse.from_value(view.profiles),
            profile_pools=OperationsTableSectionResponse.from_value(
                view.profile_pools,
            ),
            profile_allocations=OperationsTableSectionResponse.from_value(
                view.profile_allocations,
            ),
            page_observations=OperationsTableSectionResponse.from_value(
                view.page_observations,
            ),
            daemon_runtimes=OperationsTableSectionResponse.from_value(
                view.daemon_runtimes,
            ),
            network_activity=OperationsTableSectionResponse.from_value(
                view.network_activity,
            ),
            diagnostics=OperationsTableSectionResponse.from_value(
                view.diagnostics,
            ),
        )


class DaemonOperationsResponse(BaseModel):
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    auto_refresh: bool
    role: OperationsModuleRoleResponse
    metrics: list[MetricCardResponse]
    tabs: list[OperationsTabResponse]
    active_tab: str
    actions: list[RuntimeActionResponse]
    service_sets: OperationsTableSectionResponse
    services: OperationsTableSectionResponse
    instances: OperationsTableSectionResponse
    leases: OperationsTableSectionResponse
    processes: OperationsTableSectionResponse
    process_health: OperationsChartSectionResponse
    restart_summary: OperationsChartSectionResponse
    lease_health: OperationsChartSectionResponse
    dependency_health: OperationsTableSectionResponse
    drain_overview: OperationsKeyValueSectionResponse
    daemon_events: OperationsTableSectionResponse
    quick_actions: list[RuntimeActionResponse]
    links_to_operations: list[dict[str, Any]]
    instance_details: list[DaemonInstanceDetailResponse]
    lease_details: list[DaemonLeaseDetailResponse]
    process_details: list[DaemonProcessDetailResponse]

    @classmethod
    def from_view(
        cls,
        view: DaemonOperationsPage,
    ) -> "DaemonOperationsResponse":
        return cls(
            module=view.module,
            title=view.title,
            subtitle=view.subtitle,
            health=view.health,
            updated_at=view.updated_at,
            auto_refresh=view.auto_refresh,
            role=OperationsModuleRoleResponse.from_value(view.role),
            metrics=[MetricCardResponse.from_value(item) for item in view.metrics],
            tabs=[OperationsTabResponse.from_value(item) for item in view.tabs],
            active_tab=view.active_tab,
            actions=[RuntimeActionResponse.from_value(item) for item in view.actions],
            service_sets=OperationsTableSectionResponse.from_value(
                view.service_sets,
            ),
            services=OperationsTableSectionResponse.from_value(view.services),
            instances=OperationsTableSectionResponse.from_value(view.instances),
            leases=OperationsTableSectionResponse.from_value(view.leases),
            processes=OperationsTableSectionResponse.from_value(view.processes),
            process_health=OperationsChartSectionResponse.from_value(
                view.process_health,
            ),
            restart_summary=OperationsChartSectionResponse.from_value(
                view.restart_summary,
            ),
            lease_health=OperationsChartSectionResponse.from_value(view.lease_health),
            dependency_health=OperationsTableSectionResponse.from_value(
                view.dependency_health,
            ),
            drain_overview=OperationsKeyValueSectionResponse.from_value(
                view.drain_overview,
            ),
            daemon_events=OperationsTableSectionResponse.from_value(
                view.daemon_events,
            ),
            quick_actions=[
                RuntimeActionResponse.from_value(item)
                for item in view.quick_actions
            ],
            links_to_operations=[dict(item) for item in view.links_to_operations],
            instance_details=[
                DaemonInstanceDetailResponse.from_value(item)
                for item in view.instance_details
            ],
            lease_details=[
                DaemonLeaseDetailResponse.from_value(item)
                for item in view.lease_details
            ],
            process_details=[
                DaemonProcessDetailResponse.from_value(item)
                for item in view.process_details
            ],
        )


class LlmOperationsResponse(BaseModel):
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    auto_refresh: bool
    role: OperationsModuleRoleResponse
    metrics: list[MetricCardResponse]
    tabs: list[OperationsTabResponse]
    active_tab: str
    actions: list[RuntimeActionResponse]
    provider_access_health: OperationsTableSectionResponse
    provider_auth_blocked: OperationsTableSectionResponse
    model_resolver: OperationsChartSectionResponse
    rate_limiter: OperationsKeyValueSectionResponse
    limiter_queue: OperationsTableSectionResponse
    streaming_requests: OperationsTableSectionResponse
    recent_invocations: OperationsTableSectionResponse
    failed_invocations: OperationsTableSectionResponse
    latency: OperationsChartSectionResponse
    token_usage: OperationsChartSectionResponse
    invocation_rate: OperationsChartSectionResponse
    stream_health: OperationsKeyValueSectionResponse
    execution_blocking_risk: OperationsKeyValueSectionResponse
    fallback_problems: OperationsTableSectionResponse
    context_pressure: OperationsChartSectionResponse
    model_availability: OperationsTableSectionResponse
    error_summary: OperationsTableSectionResponse
    llm_lifecycle_events: OperationsTableSectionResponse
    invocation_details: list[LlmInvocationDetailResponse] = Field(default_factory=list)

    @classmethod
    def from_view(
        cls,
        view: LlmOperationsPage,
    ) -> "LlmOperationsResponse":
        return cls(
            module=view.module,
            title=view.title,
            subtitle=view.subtitle,
            health=view.health,
            updated_at=view.updated_at,
            auto_refresh=view.auto_refresh,
            role=OperationsModuleRoleResponse.from_value(view.role),
            metrics=[MetricCardResponse.from_value(item) for item in view.metrics],
            tabs=[OperationsTabResponse.from_value(item) for item in view.tabs],
            active_tab=view.active_tab,
            actions=[RuntimeActionResponse.from_value(item) for item in view.actions],
            provider_access_health=OperationsTableSectionResponse.from_value(
                view.provider_access_health,
            ),
            provider_auth_blocked=OperationsTableSectionResponse.from_value(
                view.provider_auth_blocked,
            ),
            model_resolver=OperationsChartSectionResponse.from_value(
                view.model_resolver,
            ),
            rate_limiter=OperationsKeyValueSectionResponse.from_value(
                view.rate_limiter,
            ),
            limiter_queue=OperationsTableSectionResponse.from_value(
                view.limiter_queue,
            ),
            streaming_requests=OperationsTableSectionResponse.from_value(
                view.streaming_requests,
            ),
            recent_invocations=OperationsTableSectionResponse.from_value(
                view.recent_invocations,
            ),
            failed_invocations=OperationsTableSectionResponse.from_value(
                view.failed_invocations,
            ),
            latency=OperationsChartSectionResponse.from_value(view.latency),
            token_usage=OperationsChartSectionResponse.from_value(view.token_usage),
            invocation_rate=OperationsChartSectionResponse.from_value(
                view.invocation_rate,
            ),
            stream_health=OperationsKeyValueSectionResponse.from_value(
                view.stream_health,
            ),
            execution_blocking_risk=OperationsKeyValueSectionResponse.from_value(
                view.execution_blocking_risk,
            ),
            fallback_problems=OperationsTableSectionResponse.from_value(
                view.fallback_problems,
            ),
            context_pressure=OperationsChartSectionResponse.from_value(
                view.context_pressure,
            ),
            model_availability=OperationsTableSectionResponse.from_value(
                view.model_availability,
            ),
            error_summary=OperationsTableSectionResponse.from_value(
                view.error_summary,
            ),
            llm_lifecycle_events=OperationsTableSectionResponse.from_value(
                view.llm_lifecycle_events,
            ),
            invocation_details=[
                LlmInvocationDetailResponse.from_value(item)
                for item in view.invocation_details
            ],
        )


class EventsOperationsResponse(BaseModel):
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    auto_refresh: bool
    role: OperationsModuleRoleResponse
    metrics: list[MetricCardResponse]
    tabs: list[OperationsTabResponse]
    active_tab: str
    actions: list[RuntimeActionResponse]
    events_over_time: OperationsChartSectionResponse
    events_by_surface: OperationsChartSectionResponse
    owners_by_volume: OperationsTableSectionResponse
    contract_compatibility: OperationsKeyValueSectionResponse
    recent_events: OperationsTableSectionResponse
    consumer_health: OperationsTableSectionResponse
    observer_health: OperationsTableSectionResponse
    observer_lag: OperationsTableSectionResponse
    topics: OperationsTableSectionResponse
    subscriptions: OperationsTableSectionResponse
    observer_coverage: OperationsTableSectionResponse
    dead_letters: OperationsTableSectionResponse
    contracts: OperationsTableSectionResponse
    routes: OperationsTableSectionResponse
    event_details: list[EventsEventDetailResponse]

    @classmethod
    def from_view(
        cls,
        view: EventsOperationsPage,
    ) -> "EventsOperationsResponse":
        return cls(
            module=view.module,
            title=view.title,
            subtitle=view.subtitle,
            health=view.health,
            updated_at=view.updated_at,
            auto_refresh=view.auto_refresh,
            role=OperationsModuleRoleResponse.from_value(view.role),
            metrics=[MetricCardResponse.from_value(item) for item in view.metrics],
            tabs=[OperationsTabResponse.from_value(item) for item in view.tabs],
            active_tab=view.active_tab,
            actions=[RuntimeActionResponse.from_value(item) for item in view.actions],
            events_over_time=OperationsChartSectionResponse.from_value(
                view.events_over_time,
            ),
            events_by_surface=OperationsChartSectionResponse.from_value(
                view.events_by_surface,
            ),
            owners_by_volume=OperationsTableSectionResponse.from_value(
                view.owners_by_volume,
            ),
            contract_compatibility=OperationsKeyValueSectionResponse.from_value(
                view.contract_compatibility,
            ),
            recent_events=OperationsTableSectionResponse.from_value(
                view.recent_events,
            ),
            consumer_health=OperationsTableSectionResponse.from_value(
                view.consumer_health,
            ),
            observer_health=OperationsTableSectionResponse.from_value(
                view.observer_health,
            ),
            observer_lag=OperationsTableSectionResponse.from_value(
                view.observer_lag,
            ),
            topics=OperationsTableSectionResponse.from_value(view.topics),
            subscriptions=OperationsTableSectionResponse.from_value(
                view.subscriptions,
            ),
            observer_coverage=OperationsTableSectionResponse.from_value(
                view.observer_coverage,
            ),
            dead_letters=OperationsTableSectionResponse.from_value(
                view.dead_letters,
            ),
            contracts=OperationsTableSectionResponse.from_value(view.contracts),
            routes=OperationsTableSectionResponse.from_value(view.routes),
            event_details=[
                EventsEventDetailResponse.from_value(item)
                for item in view.event_details
            ],
        )


class ToolOperationsResponse(BaseModel):
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    auto_refresh: bool
    role: OperationsModuleRoleResponse
    metrics: list[MetricCardResponse]
    tabs: list[OperationsTabResponse]
    active_tab: str
    actions: list[RuntimeActionResponse]
    active_tool_runs: OperationsTableSectionResponse
    tool_queue_runs: OperationsTableSectionResponse
    tool_waiting_io: OperationsTableSectionResponse
    tool_runs: OperationsTableSectionResponse
    tool_types: OperationsChartSectionResponse
    source_health: OperationsTableSectionResponse
    discovery_failures: OperationsTableSectionResponse
    function_catalog: OperationsTableSectionResponse
    provider_backend_health: OperationsTableSectionResponse
    cli_process_health: OperationsTableSectionResponse
    auth_missing: OperationsTableSectionResponse
    worker_pool: OperationsChartSectionResponse
    workers: OperationsTableSectionResponse
    tool_queue: OperationsTableSectionResponse
    capability_limits: OperationsTableSectionResponse
    provider_limits: OperationsTableSectionResponse
    provider_history: OperationsTableSectionResponse
    run_blockers: OperationsTableSectionResponse
    inline_risk: OperationsKeyValueSectionResponse
    recent_artifacts: OperationsTableSectionResponse
    tool_lifecycle_events: OperationsTableSectionResponse
    strategies: OperationsTableSectionResponse
    worker_details: list[ToolWorkerDetailResponse]
    tool_run_details: list[ToolRunDetailResponse] = Field(default_factory=list)

    @classmethod
    def from_view(
        cls,
        view: ToolOperationsPage,
    ) -> "ToolOperationsResponse":
        return cls(
            module=view.module,
            title=view.title,
            subtitle=view.subtitle,
            health=view.health,
            updated_at=view.updated_at,
            auto_refresh=view.auto_refresh,
            role=OperationsModuleRoleResponse.from_value(view.role),
            metrics=[MetricCardResponse.from_value(item) for item in view.metrics],
            tabs=[OperationsTabResponse.from_value(item) for item in view.tabs],
            active_tab=view.active_tab,
            actions=[RuntimeActionResponse.from_value(item) for item in view.actions],
            active_tool_runs=OperationsTableSectionResponse.from_value(
                view.active_tool_runs,
            ),
            tool_queue_runs=OperationsTableSectionResponse.from_value(
                view.tool_queue_runs,
            ),
            tool_waiting_io=OperationsTableSectionResponse.from_value(
                view.tool_waiting_io,
            ),
            tool_runs=OperationsTableSectionResponse.from_value(view.tool_runs),
            tool_types=OperationsChartSectionResponse.from_value(view.tool_types),
            source_health=OperationsTableSectionResponse.from_value(
                view.source_health,
            ),
            discovery_failures=OperationsTableSectionResponse.from_value(
                view.discovery_failures,
            ),
            function_catalog=OperationsTableSectionResponse.from_value(
                view.function_catalog,
            ),
            provider_backend_health=OperationsTableSectionResponse.from_value(
                view.provider_backend_health,
            ),
            cli_process_health=OperationsTableSectionResponse.from_value(
                view.cli_process_health,
            ),
            auth_missing=OperationsTableSectionResponse.from_value(view.auth_missing),
            worker_pool=OperationsChartSectionResponse.from_value(view.worker_pool),
            workers=OperationsTableSectionResponse.from_value(view.workers),
            tool_queue=OperationsTableSectionResponse.from_value(view.tool_queue),
            capability_limits=OperationsTableSectionResponse.from_value(
                view.capability_limits,
            ),
            provider_limits=OperationsTableSectionResponse.from_value(
                view.provider_limits,
            ),
            provider_history=OperationsTableSectionResponse.from_value(
                view.provider_history,
            ),
            run_blockers=OperationsTableSectionResponse.from_value(view.run_blockers),
            inline_risk=OperationsKeyValueSectionResponse.from_value(
                view.inline_risk,
            ),
            recent_artifacts=OperationsTableSectionResponse.from_value(
                view.recent_artifacts,
            ),
            tool_lifecycle_events=OperationsTableSectionResponse.from_value(
                view.tool_lifecycle_events,
            ),
            strategies=OperationsTableSectionResponse.from_value(view.strategies),
            worker_details=[
                ToolWorkerDetailResponse.from_value(item)
                for item in view.worker_details
            ],
            tool_run_details=[
                ToolRunDetailResponse.from_value(item)
                for item in view.tool_run_details
            ],
        )


class OrchestrationOperationsResponse(BaseModel):
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    auto_refresh: bool
    role: OperationsModuleRoleResponse
    metrics: list[MetricCardResponse]
    tabs: list[OperationsTabResponse]
    active_tab: str
    actions: list[RuntimeActionResponse]
    scheduler_status: OperationsKeyValueSectionResponse
    backpressure: OperationsChartSectionResponse
    stuck_runs: OperationsTableSectionResponse
    policy_limits: OperationsKeyValueSectionResponse
    run_queue: OperationsTableSectionResponse
    execution_chains: OperationsTableSectionResponse
    lane_locks: OperationsTableSectionResponse
    executor_overview: OperationsTableSectionResponse
    ingress_queue: OperationsTableSectionResponse
    recent_failures: OperationsTableSectionResponse
    ops_event_log: OperationsTableSectionResponse

    @classmethod
    def from_view(
        cls,
        view: OrchestrationOperationsPage,
    ) -> "OrchestrationOperationsResponse":
        return cls(
            module=view.module,
            title=view.title,
            subtitle=view.subtitle,
            health=view.health,
            updated_at=view.updated_at,
            auto_refresh=view.auto_refresh,
            role=OperationsModuleRoleResponse.from_value(view.role),
            metrics=[MetricCardResponse.from_value(item) for item in view.metrics],
            tabs=[OperationsTabResponse.from_value(item) for item in view.tabs],
            active_tab=view.active_tab,
            actions=[RuntimeActionResponse.from_value(item) for item in view.actions],
            scheduler_status=OperationsKeyValueSectionResponse.from_value(
                view.scheduler_status,
            ),
            backpressure=OperationsChartSectionResponse.from_value(view.backpressure),
            stuck_runs=OperationsTableSectionResponse.from_value(view.stuck_runs),
            policy_limits=OperationsKeyValueSectionResponse.from_value(
                view.policy_limits
            ),
            run_queue=OperationsTableSectionResponse.from_value(view.run_queue),
            execution_chains=OperationsTableSectionResponse.from_value(
                view.execution_chains,
            ),
            lane_locks=OperationsTableSectionResponse.from_value(view.lane_locks),
            executor_overview=OperationsTableSectionResponse.from_value(
                view.executor_overview,
            ),
            ingress_queue=OperationsTableSectionResponse.from_value(view.ingress_queue),
            recent_failures=OperationsTableSectionResponse.from_value(
                view.recent_failures
            ),
            ops_event_log=OperationsTableSectionResponse.from_value(view.ops_event_log),
        )
