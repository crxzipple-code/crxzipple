from __future__ import annotations

from datetime import datetime, timezone
from collections.abc import Mapping
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.memory.application import (
    MemoryActorContext,
    MemoryExcerpt,
    MemoryFileSummary,
    MemoryRecallItem,
    MemoryRecallRequest,
    MemoryRecallResult,
    MemoryRememberRequest,
    MemoryRememberResult,
    MemoryResolvedLayer,
    MemorySearchHit,
    MemoryUseContext,
    MemoryWriteResult,
)
from crxzipple.modules.memory.domain import MemoryPolicy, MemorySpace
from crxzipple.modules.settings.application import UpdateSettingsResourceInput
from crxzipple.modules.settings.domain import SettingsNotFoundError
from crxzipple.shared.settings import MemoryConfig

router = APIRouter()


def _resolve_memory_context(
    container: AppContainer,
    agent_id: str | None,
):
    context = container.require(AppKey.MEMORY_CONTEXT_RESOLVER).resolve(agent_id)
    if context is None:
        raise HTTPException(
            status_code=404,
            detail="No file-backed memory context is available for this agent.",
        )
    return context


def _resolve_memory_space_context(
    container: AppContainer,
    scope_ref: str,
    *,
    require_enabled: bool = True,
) -> tuple[MemorySpace, MemoryUseContext]:
    space = container.require(AppKey.MEMORY_SPACE_SERVICE).get_space(scope_ref)
    if space is None:
        raise HTTPException(status_code=404, detail="Memory space was not found.")
    if require_enabled and not space.enabled:
        raise HTTPException(status_code=409, detail="Memory space is disabled.")
    return space, MemoryUseContext(
        space_id=space.scope_ref,
        storage_root=space.storage_root,
        retrieval_backend=space.retrieval_backend,  # type: ignore[arg-type]
    )


def _indexed_file_count(
    container: AppContainer,
    context: MemoryUseContext,
) -> int | None:
    index_manager = getattr(
        container.require(AppKey.FILE_MEMORY_SERVICE),
        "index_manager",
        None,
    )
    index_store = getattr(index_manager, "index_store", None)
    indexed_file_hashes = getattr(index_store, "indexed_file_hashes", None)
    if not callable(indexed_file_hashes):
        return None
    try:
        return len(
            indexed_file_hashes(
                storage_root=context.storage_root,
                space_id=context.space_id,
            )
        )
    except Exception:
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _memory_runtime_defaults_payload(container: AppContainer) -> dict[str, Any]:
    query = container.require(AppKey.SETTINGS_QUERY_SERVICE)
    try:
        resource = query.get_resource("default")
        if resource.resource_kind != "memory-config":
            raise SettingsNotFoundError("memory default settings resource was not found.")
        effective = query.get_effective(resource.id).effective_value
    except SettingsNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Memory runtime defaults are not available.",
        ) from exc
    if not isinstance(effective, Mapping):
        raise HTTPException(
            status_code=500,
            detail="Memory runtime defaults payload is invalid.",
        )
    payload = {"id": "default", **dict(effective)}
    try:
        config = MemoryConfig.from_payload(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Memory runtime defaults payload is invalid: {exc}",
        ) from exc
    return config.to_payload()


class MemoryExcerptResponse(BaseModel):
    path: str
    text: str
    start_line: int
    end_line: int
    kind: str

    @classmethod
    def from_entity(cls, excerpt: MemoryExcerpt) -> "MemoryExcerptResponse":
        return cls(
            path=excerpt.path,
            text=excerpt.text,
            start_line=excerpt.start_line,
            end_line=excerpt.end_line,
            kind=excerpt.kind,
        )


class MemoryFileSummaryResponse(BaseModel):
    path: str
    kind: str
    title: str
    preview: str
    updated_at: str

    @classmethod
    def from_entity(cls, item: MemoryFileSummary) -> "MemoryFileSummaryResponse":
        return cls(
            path=item.path,
            kind=item.kind,
            title=item.title,
            preview=item.preview,
            updated_at=item.updated_at,
        )


class MemorySearchHitResponse(BaseModel):
    path: str
    snippet: str
    start_line: int
    end_line: int
    score: float
    kind: str

    @classmethod
    def from_entity(cls, item: MemorySearchHit) -> "MemorySearchHitResponse":
        return cls(
            path=item.path,
            snippet=item.snippet,
            start_line=item.start_line,
            end_line=item.end_line,
            score=item.score,
            kind=item.kind,
        )


class MemoryWriteResultResponse(BaseModel):
    path: str
    line_start: int
    line_end: int
    kind: str

    @classmethod
    def from_entity(cls, result: MemoryWriteResult) -> "MemoryWriteResultResponse":
        return cls(
            path=result.path,
            line_start=result.line_start,
            line_end=result.line_end,
            kind=result.kind,
        )


class MemoryOverviewResponse(BaseModel):
    agent_id: str
    space_id: str
    long_term: MemoryExcerptResponse | None = None
    recent_files: list[MemoryFileSummaryResponse] = Field(default_factory=list)


class MemorySpaceActionResponse(BaseModel):
    scope_ref: str
    action: str
    status: str
    rebuilt: bool = False
    file_count: int = 0
    indexed_file_count: int | None = None
    generated_at: str


class MemorySpaceExportResponse(BaseModel):
    scope_ref: str
    generated_at: str
    space: dict[str, object]
    policies: list[dict[str, object]] = Field(default_factory=list)
    files: list[MemoryFileSummaryResponse] = Field(default_factory=list)


class LegacyMemoryAgentMigrationReportResponse(BaseModel):
    agent_id: str
    home_dir: str | None = None
    scope_ref: str
    sidecar_path: str | None = None
    sidecar_imported: bool = False
    sidecar_deleted: bool = False
    profile_updated: bool = False
    space_created: bool = False
    copied_paths: list[str] = Field(default_factory=list)
    skipped_paths: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class LegacyMemoryMigrationRequest(BaseModel):
    agent_ids: list[str] = Field(default_factory=list)
    dry_run: bool = True
    delete_sidecar: bool = False


class LegacyMemoryMigrationResponse(BaseModel):
    dry_run: bool
    scanned: int
    updated_profiles: int
    created_spaces: int
    copied_files: int
    agents: list[LegacyMemoryAgentMigrationReportResponse]


class MemoryRuntimeDefaultsResponse(BaseModel):
    id: str
    storage_root: str | None = None
    retrieval_backend: str
    vector_provider: str
    vector_model: str | None = None
    vector_base_url: str | None = None
    vector_credential_binding_id: str | None = None
    vector_timeout_seconds: int
    watch_interval_seconds: float | None = None
    enabled: bool

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
    ) -> "MemoryRuntimeDefaultsResponse":
        config = MemoryConfig.from_payload(payload)
        return cls(
            id=config.config_id,
            storage_root=config.storage_root,
            retrieval_backend=config.retrieval_backend,
            vector_provider=config.vector_provider,
            vector_model=config.vector_model,
            vector_base_url=config.vector_base_url,
            vector_credential_binding_id=config.vector_credential_binding_id,
            vector_timeout_seconds=config.vector_timeout_seconds,
            watch_interval_seconds=config.watch_interval_seconds,
            enabled=config.enabled,
        )


class MemorySpaceResponse(BaseModel):
    scope_ref: str
    owner_kind: str
    owner_id: str
    engine_id: str
    storage_root: str
    retrieval_backend: str
    status: str
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: str
    updated_at: str

    @classmethod
    def from_entity(cls, space: MemorySpace) -> "MemorySpaceResponse":
        return cls(
            scope_ref=space.scope_ref,
            owner_kind=space.owner_kind,
            owner_id=space.owner_id,
            engine_id=space.engine_id,
            storage_root=space.storage_root,
            retrieval_backend=space.retrieval_backend,
            status=space.status,
            metadata=dict(space.metadata),
            created_at=space.created_at.isoformat(),
            updated_at=space.updated_at.isoformat(),
        )


class MemoryPolicyResponse(BaseModel):
    policy_id: str
    target_kind: str
    target_id: str | None = None
    recall_enabled: bool
    remember_enabled: bool
    max_recall_items: int
    retention: str
    status: str
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: str
    updated_at: str

    @classmethod
    def from_entity(cls, policy: MemoryPolicy) -> "MemoryPolicyResponse":
        return cls(
            policy_id=policy.policy_id,
            target_kind=policy.target_kind,
            target_id=policy.target_id,
            recall_enabled=policy.recall_enabled,
            remember_enabled=policy.remember_enabled,
            max_recall_items=policy.max_recall_items,
            retention=policy.retention,
            status=policy.status,
            metadata=dict(policy.metadata),
            created_at=policy.created_at.isoformat(),
            updated_at=policy.updated_at.isoformat(),
        )


class UpsertMemorySpaceRequest(BaseModel):
    owner_kind: str = Field(pattern="^(agent|shared|project|team|system)$")
    owner_id: str = Field(min_length=1)
    storage_root: str | None = None
    retrieval_backend: str = Field(default="file")
    engine_id: str = Field(default="file_markdown", min_length=1)
    status: str = Field(default="active", pattern="^(active|disabled)$")
    metadata: dict[str, object] = Field(default_factory=dict)


class UpsertMemoryPolicyRequest(BaseModel):
    target_kind: str = Field(pattern="^(global|space|agent)$")
    target_id: str | None = None
    recall_enabled: bool = True
    remember_enabled: bool = True
    max_recall_items: int = Field(default=6, ge=1, le=100)
    retention: str = Field(
        default="engine_default",
        pattern="^(engine_default|durable|session|temporary)$",
    )
    status: str = Field(default="active", pattern="^(active|disabled)$")
    metadata: dict[str, object] = Field(default_factory=dict)


class UpdateMemoryRuntimeDefaultsRequest(BaseModel):
    storage_root: str | None = None
    retrieval_backend: str | None = Field(default=None, pattern="^(keyword|hybrid|vector)$")
    vector_provider: str | None = Field(default=None, pattern="^(local|openai_compatible)$")
    vector_model: str | None = None
    vector_base_url: str | None = None
    vector_credential_binding_id: str | None = None
    vector_timeout_seconds: int | None = Field(default=None, ge=1)
    watch_interval_seconds: float | None = Field(default=None, ge=0)
    enabled: bool | None = None


class WriteDailyMemoryRequest(BaseModel):
    agent_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    title: str | None = None


class WriteLongTermMemoryRequest(BaseModel):
    agent_id: str = Field(min_length=1)
    content: str = Field(min_length=1)


class MemoryRuntimeRecallRequest(BaseModel):
    agent_id: str | None = None
    scope_ref: str | None = None
    query: str | None = None
    citation: str | None = None
    intent: str | None = None
    max_items: int = Field(default=6, ge=1, le=100)
    max_tokens: int | None = Field(default=None, ge=1)
    metadata: dict[str, object] = Field(default_factory=dict)


class MemoryRuntimeRememberRequest(BaseModel):
    agent_id: str | None = None
    scope_ref: str | None = None
    target_scope_ref: str | None = None
    target_layer_kind: str | None = Field(
        default=None,
        pattern="^(private|shared|project|team|system)$",
    )
    content: str = Field(min_length=1)
    title: str | None = None
    intent: str = Field(default="freeform")
    retention: str = Field(
        default="engine_default",
        pattern="^(engine_default|durable|session|temporary)$",
    )
    metadata: dict[str, object] = Field(default_factory=dict)


class MemoryResolvedScopeResponse(BaseModel):
    scope_ref: str
    space_id: str
    storage_root: str
    retrieval_backend: str
    engine_id: str


class MemoryResolvedLayerResponse(BaseModel):
    scope_ref: str
    space_id: str
    storage_root: str
    retrieval_backend: str
    engine_id: str
    owner_kind: str
    layer_kind: str
    access: str
    default_write: bool


class MemoryRuntimeRecallItemResponse(BaseModel):
    path: str
    kind: str
    citation: str
    text: str
    start_line: int
    end_line: int
    score: float | None = None
    source_scope_ref: str | None = None
    source_layer_kind: str | None = None
    source_owner_kind: str | None = None

    @classmethod
    def from_entity(
        cls,
        item: MemoryRecallItem,
        *,
        fallback_scope_ref: str | None = None,
    ) -> "MemoryRuntimeRecallItemResponse":
        return cls(
            path=item.path,
            kind=item.kind,
            citation=item.citation,
            text=item.text,
            start_line=item.start_line,
            end_line=item.end_line,
            score=item.score,
            source_scope_ref=item.source_scope_ref or fallback_scope_ref,
            source_layer_kind=item.source_layer_kind,
            source_owner_kind=item.source_owner_kind,
        )


class MemoryRuntimeRecallResponse(BaseModel):
    scope: MemoryResolvedScopeResponse
    searched_layers: list[MemoryResolvedLayerResponse] = Field(default_factory=list)
    query: str | None = None
    citation: str | None = None
    items: list[MemoryRuntimeRecallItemResponse] = Field(default_factory=list)

    @classmethod
    def from_entity(cls, result: MemoryRecallResult) -> "MemoryRuntimeRecallResponse":
        return cls(
            scope=_resolved_scope_response(result.scope),
            searched_layers=[
                _resolved_layer_response(layer)
                for layer in result.searched_layers
            ],
            query=result.query,
            citation=result.citation,
            items=[
                MemoryRuntimeRecallItemResponse.from_entity(
                    item,
                    fallback_scope_ref=result.scope.scope_ref,
                )
                for item in result.items
            ],
        )


class MemoryRuntimeRememberResponse(BaseModel):
    scope: MemoryResolvedScopeResponse
    target_layer: MemoryResolvedLayerResponse | None = None
    status: str
    write_result: MemoryWriteResultResponse | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @classmethod
    def from_entity(
        cls,
        result: MemoryRememberResult,
    ) -> "MemoryRuntimeRememberResponse":
        return cls(
            scope=_resolved_scope_response(result.scope),
            target_layer=(
                _resolved_layer_response(result.target_layer)
                if result.target_layer is not None
                else None
            ),
            status=result.status,
            write_result=(
                MemoryWriteResultResponse.from_entity(result.write_result)
                if result.write_result is not None
                else None
            ),
            metadata=dict(result.metadata),
        )


@router.get("/memory/runtime-defaults", response_model=MemoryRuntimeDefaultsResponse)
def get_memory_runtime_defaults(
    container: Annotated[AppContainer, Depends(get_container)],
) -> MemoryRuntimeDefaultsResponse:
    return MemoryRuntimeDefaultsResponse.from_payload(
        _memory_runtime_defaults_payload(container),
    )


@router.put("/memory/runtime-defaults", response_model=MemoryRuntimeDefaultsResponse)
def update_memory_runtime_defaults(
    payload: UpdateMemoryRuntimeDefaultsRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> MemoryRuntimeDefaultsResponse:
    current = _memory_runtime_defaults_payload(container)
    updates = payload.model_dump(exclude_unset=True)
    merged = {"id": "default", **current, **updates}
    try:
        config = MemoryConfig.from_payload(merged)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = container.require(AppKey.SETTINGS_ACTION_SERVICE).update_resource(
        UpdateSettingsResourceInput(
            resource_id="default",
            payload=config.to_payload(),
            actor="memory.owner_api",
            reason="update memory runtime defaults",
            publish=True,
            source="memory_owner_api",
            metadata={"owner_api": "/memory/runtime-defaults"},
        ),
    )
    if not result.validation.ok:
        raise HTTPException(
            status_code=400,
            detail=result.validation.to_payload(),
        )
    return MemoryRuntimeDefaultsResponse.from_payload(
        _memory_runtime_defaults_payload(container),
    )


@router.get("/memory/spaces", response_model=list[MemorySpaceResponse])
def list_memory_spaces(
    container: Annotated[AppContainer, Depends(get_container)],
    include_disabled: bool = Query(default=False),
) -> list[MemorySpaceResponse]:
    spaces = container.require(AppKey.MEMORY_SPACE_SERVICE).list_spaces(
        include_disabled=include_disabled,
    )
    return [MemorySpaceResponse.from_entity(space) for space in spaces]


@router.get("/memory/spaces/{scope_ref}", response_model=MemorySpaceResponse)
def get_memory_space(
    scope_ref: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> MemorySpaceResponse:
    space = container.require(AppKey.MEMORY_SPACE_SERVICE).get_space(scope_ref)
    if space is None:
        raise HTTPException(status_code=404, detail="Memory space was not found.")
    return MemorySpaceResponse.from_entity(space)


@router.put("/memory/spaces/{scope_ref}", response_model=MemorySpaceResponse)
def upsert_memory_space(
    scope_ref: str,
    payload: UpsertMemorySpaceRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> MemorySpaceResponse:
    try:
        space = container.require(AppKey.MEMORY_SPACE_SERVICE).upsert_space(
            scope_ref=scope_ref,
            owner_kind=payload.owner_kind,  # type: ignore[arg-type]
            owner_id=payload.owner_id,
            storage_root=payload.storage_root,
            retrieval_backend=payload.retrieval_backend,
            engine_id=payload.engine_id,
            status=payload.status,  # type: ignore[arg-type]
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MemorySpaceResponse.from_entity(space)


@router.post("/memory/spaces/{scope_ref}/disable", response_model=MemorySpaceResponse)
def disable_memory_space(
    scope_ref: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> MemorySpaceResponse:
    space = container.require(AppKey.MEMORY_SPACE_SERVICE).disable_space(scope_ref)
    if space is None:
        raise HTTPException(status_code=404, detail="Memory space was not found.")
    return MemorySpaceResponse.from_entity(space)


@router.delete("/memory/spaces/{scope_ref}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory_space(
    scope_ref: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> Response:
    container.require(AppKey.MEMORY_SPACE_SERVICE).delete_space(scope_ref)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/memory/spaces/{scope_ref}/actions/rebuild-index",
    response_model=MemorySpaceActionResponse,
)
def rebuild_memory_space_index(
    scope_ref: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> MemorySpaceActionResponse:
    space, context = _resolve_memory_space_context(container, scope_ref)
    rebuilt = container.require(AppKey.FILE_MEMORY_SERVICE).rebuild_index(
        context=context,
    )
    files = container.require(AppKey.FILE_MEMORY_SERVICE).list_files(
        context=context,
        limit=None,
    )
    return MemorySpaceActionResponse(
        scope_ref=space.scope_ref,
        action="rebuild-index",
        status="rebuilt" if rebuilt else "up_to_date",
        rebuilt=rebuilt,
        file_count=len(files),
        indexed_file_count=_indexed_file_count(container, context),
        generated_at=_utc_now(),
    )


@router.post(
    "/memory/spaces/{scope_ref}/actions/export",
    response_model=MemorySpaceExportResponse,
)
def export_memory_space(
    scope_ref: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> MemorySpaceExportResponse:
    space, context = _resolve_memory_space_context(
        container,
        scope_ref,
        require_enabled=False,
    )
    policies = container.require(AppKey.MEMORY_POLICY_SERVICE).list_policies(
        include_disabled=True,
    )
    files = container.require(AppKey.FILE_MEMORY_SERVICE).list_files(
        context=context,
        limit=None,
    )
    return MemorySpaceExportResponse(
        scope_ref=space.scope_ref,
        generated_at=_utc_now(),
        space=MemorySpaceResponse.from_entity(space).model_dump(),
        policies=[
            MemoryPolicyResponse.from_entity(policy).model_dump()
            for policy in policies
            if policy.target_kind == "global"
            or (policy.target_kind == "space" and policy.target_id == space.scope_ref)
        ],
        files=[MemoryFileSummaryResponse.from_entity(item) for item in files],
    )


@router.post(
    "/memory/actions/migrate-legacy-agent-homes",
    response_model=LegacyMemoryMigrationResponse,
)
def migrate_legacy_agent_homes(
    payload: LegacyMemoryMigrationRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> LegacyMemoryMigrationResponse:
    report = container.require(AppKey.MEMORY_LEGACY_MIGRATION_SERVICE).migrate_agent_homes(
        agent_ids=tuple(payload.agent_ids),
        dry_run=payload.dry_run,
        delete_sidecar=payload.delete_sidecar,
    )
    return LegacyMemoryMigrationResponse(
        dry_run=report.dry_run,
        scanned=report.scanned,
        updated_profiles=report.updated_profiles,
        created_spaces=report.created_spaces,
        copied_files=report.copied_files,
        agents=[
            LegacyMemoryAgentMigrationReportResponse(
                agent_id=agent.agent_id,
                home_dir=agent.home_dir,
                scope_ref=agent.scope_ref,
                sidecar_path=agent.sidecar_path,
                sidecar_imported=agent.sidecar_imported,
                sidecar_deleted=agent.sidecar_deleted,
                profile_updated=agent.profile_updated,
                space_created=agent.space_created,
                copied_paths=list(agent.copied_paths),
                skipped_paths=list(agent.skipped_paths),
                errors=list(agent.errors),
            )
            for agent in report.agents
        ],
    )


@router.get("/memory/policies", response_model=list[MemoryPolicyResponse])
def list_memory_policies(
    container: Annotated[AppContainer, Depends(get_container)],
    include_disabled: bool = Query(default=False),
) -> list[MemoryPolicyResponse]:
    policies = container.require(AppKey.MEMORY_POLICY_SERVICE).list_policies(
        include_disabled=include_disabled,
    )
    return [MemoryPolicyResponse.from_entity(policy) for policy in policies]


@router.put("/memory/policies/{policy_id}", response_model=MemoryPolicyResponse)
def upsert_memory_policy(
    policy_id: str,
    payload: UpsertMemoryPolicyRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> MemoryPolicyResponse:
    policy = container.require(AppKey.MEMORY_POLICY_SERVICE).upsert_policy(
        policy_id=policy_id,
        target_kind=payload.target_kind,  # type: ignore[arg-type]
        target_id=payload.target_id,
        recall_enabled=payload.recall_enabled,
        remember_enabled=payload.remember_enabled,
        max_recall_items=payload.max_recall_items,
        retention=payload.retention,
        status=payload.status,  # type: ignore[arg-type]
        metadata=payload.metadata,
    )
    return MemoryPolicyResponse.from_entity(policy)


@router.post("/memory/policies/{policy_id}/disable", response_model=MemoryPolicyResponse)
def disable_memory_policy(
    policy_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> MemoryPolicyResponse:
    policy = container.require(AppKey.MEMORY_POLICY_SERVICE).disable_policy(policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Memory policy was not found.")
    return MemoryPolicyResponse.from_entity(policy)


@router.delete("/memory/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory_policy(
    policy_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> Response:
    container.require(AppKey.MEMORY_POLICY_SERVICE).delete_policy(policy_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/memory/runtime/recall", response_model=MemoryRuntimeRecallResponse)
def recall_memory_runtime(
    payload: MemoryRuntimeRecallRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> MemoryRuntimeRecallResponse:
    try:
        result = container.require(AppKey.MEMORY_RUNTIME_SERVICE).recall(
            MemoryRecallRequest(
                actor=_runtime_actor_context(payload.agent_id, payload.scope_ref),
                query=payload.query,
                citation=payload.citation,
                intent=payload.intent,  # type: ignore[arg-type]
                max_items=payload.max_items,
                max_tokens=payload.max_tokens,
                metadata=payload.metadata,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return MemoryRuntimeRecallResponse.from_entity(result)


@router.post(
    "/memory/runtime/remember",
    response_model=MemoryRuntimeRememberResponse,
    status_code=status.HTTP_201_CREATED,
)
def remember_memory_runtime(
    payload: MemoryRuntimeRememberRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> MemoryRuntimeRememberResponse:
    try:
        result = container.require(AppKey.MEMORY_RUNTIME_SERVICE).remember(
            MemoryRememberRequest(
                actor=_runtime_actor_context(payload.agent_id, payload.scope_ref),
                content=payload.content,
                title=payload.title,
                intent=payload.intent,  # type: ignore[arg-type]
                retention=payload.retention,  # type: ignore[arg-type]
                target_scope_ref=payload.target_scope_ref,
                target_layer_kind=payload.target_layer_kind,  # type: ignore[arg-type]
                metadata=payload.metadata,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return MemoryRuntimeRememberResponse.from_entity(result)


@router.get("/memory/overview", response_model=MemoryOverviewResponse)
def get_memory_overview(
    container: Annotated[AppContainer, Depends(get_container)],
    agent_id: str = Query(..., min_length=1),
    recent_limit: int = Query(default=12, ge=1, le=50),
) -> MemoryOverviewResponse:
    context = _resolve_memory_context(container, agent_id)
    long_term = container.require(AppKey.FILE_MEMORY_SERVICE).get(
        context=context,
        path="MEMORY.md",
    )
    if long_term is None:
        long_term = container.require(AppKey.FILE_MEMORY_SERVICE).get(
            context=context,
            path="memory.md",
        )
    recent_files = container.require(AppKey.FILE_MEMORY_SERVICE).list_files(
        context=context,
        limit=recent_limit,
    )
    return MemoryOverviewResponse(
        agent_id=agent_id,
        space_id=context.space_id,
        long_term=(
            MemoryExcerptResponse.from_entity(long_term)
            if long_term is not None
            else None
        ),
        recent_files=[
            MemoryFileSummaryResponse.from_entity(item)
            for item in recent_files
        ],
    )


@router.get("/memory/search", response_model=list[MemorySearchHitResponse])
def search_memory(
    container: Annotated[AppContainer, Depends(get_container)],
    agent_id: str = Query(..., min_length=1),
    query: str = Query(..., min_length=1),
    limit: int = Query(default=12, ge=1, le=50),
) -> list[MemorySearchHitResponse]:
    context = _resolve_memory_context(container, agent_id)
    items = container.require(AppKey.FILE_MEMORY_SERVICE).search(
        context=context,
        query=query,
        limit=limit,
    )
    return [MemorySearchHitResponse.from_entity(item) for item in items]


@router.get("/memory/excerpt", response_model=MemoryExcerptResponse)
def get_memory_excerpt(
    container: Annotated[AppContainer, Depends(get_container)],
    agent_id: str = Query(..., min_length=1),
    path: str = Query(..., min_length=1),
    start_line: int | None = Query(default=None, ge=1),
    line_count: int | None = Query(default=None, ge=1, le=500),
) -> MemoryExcerptResponse:
    context = _resolve_memory_context(container, agent_id)
    excerpt = container.require(AppKey.FILE_MEMORY_SERVICE).get(
        context=context,
        path=path,
        start_line=start_line,
        line_count=line_count,
    )
    if excerpt is None:
        raise HTTPException(status_code=404, detail="Memory excerpt was not found.")
    return MemoryExcerptResponse.from_entity(excerpt)


@router.post(
    "/memory/daily",
    response_model=MemoryWriteResultResponse,
    status_code=status.HTTP_201_CREATED,
)
def write_daily_memory(
    payload: WriteDailyMemoryRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> MemoryWriteResultResponse:
    context = _resolve_memory_context(container, payload.agent_id)
    result = container.require(AppKey.FILE_MEMORY_SERVICE).append_daily(
        context=context,
        content=payload.content,
        title=payload.title,
    )
    return MemoryWriteResultResponse.from_entity(result)


@router.post(
    "/memory/long-term",
    response_model=MemoryWriteResultResponse,
    status_code=status.HTTP_201_CREATED,
)
def write_long_term_memory(
    payload: WriteLongTermMemoryRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> MemoryWriteResultResponse:
    context = _resolve_memory_context(container, payload.agent_id)
    result = container.require(AppKey.FILE_MEMORY_SERVICE).write_long_term(
        context=context,
        content=payload.content,
    )
    return MemoryWriteResultResponse.from_entity(result)


def _runtime_actor_context(
    agent_id: str | None,
    scope_ref: str | None,
) -> MemoryActorContext:
    normalized_agent = agent_id.strip() if agent_id else None
    normalized_scope = scope_ref.strip() if scope_ref else None
    if not normalized_agent and not normalized_scope:
        raise ValueError("Memory runtime test requires agent_id or scope_ref.")
    return MemoryActorContext(agent_id=normalized_agent, scope_ref=normalized_scope)


def _resolved_scope_response(scope) -> MemoryResolvedScopeResponse:
    return MemoryResolvedScopeResponse(
        scope_ref=scope.scope_ref,
        space_id=scope.context.space_id,
        storage_root=scope.context.storage_root,
        retrieval_backend=scope.context.retrieval_backend,
        engine_id=scope.engine_id,
    )


def _resolved_layer_response(layer: MemoryResolvedLayer) -> MemoryResolvedLayerResponse:
    return MemoryResolvedLayerResponse(
        scope_ref=layer.scope_ref,
        space_id=layer.context.space_id,
        storage_root=layer.context.storage_root,
        retrieval_backend=layer.context.retrieval_backend,
        engine_id=layer.engine_id,
        owner_kind=layer.layer.owner_kind,
        layer_kind=layer.layer.layer_kind,
        access=layer.layer.access,
        default_write=layer.layer.default_write,
    )
