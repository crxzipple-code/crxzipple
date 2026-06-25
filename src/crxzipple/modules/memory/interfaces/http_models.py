from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from crxzipple.modules.memory.application import (
    MemoryExcerpt,
    MemoryFileSummary,
    MemoryRecallItem,
    MemoryRecallResult,
    MemoryRememberResult,
    MemoryResolvedLayer,
    MemorySearchHit,
    MemoryWriteResult,
)
from crxzipple.modules.memory.domain import MemoryPolicy, MemorySpace
from crxzipple.shared.settings import MemoryConfig


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
            scope=resolved_scope_response(result.scope),
            searched_layers=[
                resolved_layer_response(layer)
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
            scope=resolved_scope_response(result.scope),
            target_layer=(
                resolved_layer_response(result.target_layer)
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


def resolved_scope_response(scope) -> MemoryResolvedScopeResponse:  # noqa: ANN001
    return MemoryResolvedScopeResponse(
        scope_ref=scope.scope_ref,
        space_id=scope.context.space_id,
        storage_root=scope.context.storage_root,
        retrieval_backend=scope.context.retrieval_backend,
        engine_id=scope.engine_id,
    )


def resolved_layer_response(layer: MemoryResolvedLayer) -> MemoryResolvedLayerResponse:
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
