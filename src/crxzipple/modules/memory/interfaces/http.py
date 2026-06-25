from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.memory.application import (
    MemoryRecallRequest,
    MemoryRememberRequest,
)
from crxzipple.modules.settings.application import UpdateSettingsResourceInput
from crxzipple.shared.settings import MemoryConfig
from crxzipple.modules.memory.interfaces.http_common import (
    indexed_file_count as _indexed_file_count,
    memory_runtime_defaults_payload as _memory_runtime_defaults_payload,
    resolve_memory_context as _resolve_memory_context,
    resolve_memory_space_context as _resolve_memory_space_context,
    runtime_actor_context as _runtime_actor_context,
    utc_now as _utc_now,
)
from crxzipple.modules.memory.interfaces.http_models import (
    LegacyMemoryAgentMigrationReportResponse,
    LegacyMemoryMigrationRequest,
    LegacyMemoryMigrationResponse,
    MemoryExcerptResponse,
    MemoryFileSummaryResponse,
    MemoryOverviewResponse,
    MemoryPolicyResponse,
    MemoryRuntimeDefaultsResponse,
    MemoryRuntimeRecallRequest,
    MemoryRuntimeRecallResponse,
    MemoryRuntimeRememberRequest,
    MemoryRuntimeRememberResponse,
    MemorySearchHitResponse,
    MemorySpaceActionResponse,
    MemorySpaceExportResponse,
    MemorySpaceResponse,
    MemoryWriteResultResponse,
    UpdateMemoryRuntimeDefaultsRequest,
    UpsertMemoryPolicyRequest,
    UpsertMemorySpaceRequest,
    WriteDailyMemoryRequest,
    WriteLongTermMemoryRequest,
)

router = APIRouter()


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
