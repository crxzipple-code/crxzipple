from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal, Protocol

from crxzipple.modules.memory.application.models import (
    MemoryExcerpt,
    MemorySearchHit,
    MemoryUseContext,
    MemoryWriteResult,
)
from crxzipple.modules.memory.application.policies import (
    MemoryPolicyProvider,
    MemoryRuntimePolicy,
)
from crxzipple.modules.memory.domain import MemorySpace, MemorySpaceOwnerKind


MemoryIntent = Literal[
    "fact",
    "preference",
    "episode",
    "project_note",
    "skill_learning",
    "freeform",
]
MemoryRetentionHint = Literal["engine_default", "durable", "session", "temporary"]
MemoryLayerKind = Literal["private", "shared", "project", "team", "system"]
MemoryLayerAccess = Literal["read", "read_write"]


@dataclass(frozen=True, slots=True)
class MemoryActorContext:
    agent_id: str | None = None
    run_id: str | None = None
    session_key: str | None = None
    active_session_id: str | None = None
    workspace_dir: str | None = None
    scope_ref: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "agent_id",
            "run_id",
            "session_key",
            "active_session_id",
            "workspace_dir",
            "scope_ref",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_text(getattr(self, field_name)),
            )

    @classmethod
    def from_attrs(cls, attrs: Mapping[str, Any] | None) -> "MemoryActorContext":
        attrs = attrs or {}
        return cls(
            agent_id=_optional_text(attrs.get("agent_id")),
            run_id=_optional_text(attrs.get("run_id")),
            session_key=_optional_text(attrs.get("session_key")),
            active_session_id=_optional_text(attrs.get("active_session_id")),
            workspace_dir=_optional_text(attrs.get("workspace_dir")),
            scope_ref=(
                _optional_text(attrs.get("memory_scope_ref"))
                or _optional_text(attrs.get("scope_ref"))
            ),
        )

    @property
    def requested_scope_ref(self) -> str | None:
        return self.scope_ref or self.agent_id


@dataclass(frozen=True, slots=True)
class MemoryResolvedScope:
    context: MemoryUseContext
    scope_ref: str
    engine_id: str
    auto_created: bool = False


@dataclass(frozen=True, slots=True)
class MemoryLayerRef:
    scope_ref: str
    owner_kind: MemorySpaceOwnerKind
    layer_kind: MemoryLayerKind
    access: MemoryLayerAccess = "read"
    default_write: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope_ref", _required_text(self.scope_ref, "scope_ref"))


@dataclass(frozen=True, slots=True)
class MemoryResolvedLayer:
    context: MemoryUseContext
    layer: MemoryLayerRef
    engine_id: str

    @property
    def scope_ref(self) -> str:
        return self.layer.scope_ref

    def as_scope(self) -> MemoryResolvedScope:
        return MemoryResolvedScope(
            context=self.context,
            scope_ref=self.layer.scope_ref,
            engine_id=self.engine_id,
        )


@dataclass(frozen=True, slots=True)
class MemoryAccessPlan:
    actor: MemoryActorContext
    identity_scope_ref: str
    private_layer: MemoryResolvedLayer
    readable_layers: tuple[MemoryResolvedLayer, ...]
    writable_layers: tuple[MemoryResolvedLayer, ...]
    default_write_layer: MemoryResolvedLayer
    policy: MemoryRuntimePolicy

    @property
    def scope(self) -> MemoryResolvedScope:
        return self.private_layer.as_scope()


@dataclass(frozen=True, slots=True)
class MemoryRecallRequest:
    actor: MemoryActorContext
    query: str | None = None
    citation: str | None = None
    intent: MemoryIntent | None = None
    max_items: int = 6
    max_tokens: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "query", _optional_text(self.query))
        object.__setattr__(self, "citation", _optional_text(self.citation))
        object.__setattr__(self, "max_items", max(1, int(self.max_items)))
        if self.max_tokens is not None:
            object.__setattr__(self, "max_tokens", max(1, int(self.max_tokens)))


@dataclass(frozen=True, slots=True)
class MemoryRecallItem:
    path: str
    kind: str
    citation: str
    text: str
    start_line: int
    end_line: int
    score: float | None = None
    hit: MemorySearchHit | None = None
    excerpt: MemoryExcerpt | None = None
    source_scope_ref: str | None = None
    source_layer_kind: MemoryLayerKind | None = None
    source_owner_kind: MemorySpaceOwnerKind | None = None


@dataclass(frozen=True, slots=True)
class MemoryRecallResult:
    scope: MemoryResolvedScope
    items: tuple[MemoryRecallItem, ...]
    query: str | None = None
    citation: str | None = None
    searched_layers: tuple[MemoryResolvedLayer, ...] = ()
    access_plan: MemoryAccessPlan | None = None

    @property
    def hits(self) -> tuple[MemorySearchHit, ...]:
        return tuple(item.hit for item in self.items if item.hit is not None)

    @property
    def excerpt(self) -> MemoryExcerpt | None:
        for item in self.items:
            if item.excerpt is not None:
                return item.excerpt
        return None


@dataclass(frozen=True, slots=True)
class MemoryRememberRequest:
    actor: MemoryActorContext
    content: str
    intent: MemoryIntent = "freeform"
    retention: MemoryRetentionHint = "engine_default"
    title: str | None = None
    target_scope_ref: str | None = None
    target_layer_kind: MemoryLayerKind | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        content = self.content.strip()
        if not content:
            raise ValueError("Memory remember content cannot be empty.")
        object.__setattr__(self, "content", content)
        object.__setattr__(self, "title", _optional_text(self.title))
        object.__setattr__(
            self,
            "target_scope_ref",
            _optional_text(self.target_scope_ref),
        )


@dataclass(frozen=True, slots=True)
class MemoryRememberResult:
    scope: MemoryResolvedScope
    status: str
    write_result: MemoryWriteResult | None = None
    target_layer: MemoryResolvedLayer | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MemoryEngineCapabilities:
    supports_recall: bool = True
    supports_remember: bool = True
    supports_citations: bool = True
    supports_keyword_search: bool = True
    supports_vector_search: bool = False
    supports_rebuild: bool = True
    supports_shared_space: bool = True
    requires_credentials: bool = False
    credential_requirement_ids: tuple[str, ...] = ()


class MemoryScopeResolver(Protocol):
    def resolve(self, space_ref: str | None) -> MemoryUseContext | None:
        ...


class MemorySpaceInventory(Protocol):
    def get_space(self, scope_ref: str) -> MemorySpace | None:
        ...

    def list_spaces(self, *, include_disabled: bool = False) -> tuple[MemorySpace, ...]:
        ...


class MemoryEngine(Protocol):
    @property
    def engine_id(self) -> str:
        ...

    def capabilities(self) -> MemoryEngineCapabilities:
        ...

    def recall(
        self,
        *,
        layers: Sequence[MemoryResolvedLayer],
        request: MemoryRecallRequest,
    ) -> MemoryRecallResult:
        ...

    def remember(
        self,
        *,
        layer: MemoryResolvedLayer,
        request: MemoryRememberRequest,
    ) -> MemoryRememberResult:
        ...


class MemoryRuntimePort(Protocol):
    def resolve_access_plan(self, actor: MemoryActorContext) -> MemoryAccessPlan:
        ...

    def recall(self, request: MemoryRecallRequest) -> MemoryRecallResult:
        ...

    def remember(self, request: MemoryRememberRequest) -> MemoryRememberResult:
        ...


@dataclass(frozen=True, slots=True)
class MemoryRuntimeService:
    scope_resolver: MemoryScopeResolver
    engine: MemoryEngine
    policy_provider: MemoryPolicyProvider | None = None
    space_inventory: MemorySpaceInventory | None = None

    def resolve_access_plan(self, actor: MemoryActorContext) -> MemoryAccessPlan:
        scope_ref = actor.requested_scope_ref
        if scope_ref is None:
            raise ValueError("Memory scope resolution requires agent_id or scope_ref.")
        private_context = self.scope_resolver.resolve(scope_ref)
        if private_context is None:
            raise ValueError(f"Memory scope '{scope_ref}' is not available.")
        private_layer = self._resolved_layer(
            context=private_context,
            scope_ref=scope_ref,
            owner_kind=self._owner_kind_for_scope(scope_ref, actor),
            layer_kind="private",
            access="read_write",
            default_write=True,
        )
        readable_layers: list[MemoryResolvedLayer] = []
        writable_layers: list[MemoryResolvedLayer] = []
        private_policy = self._effective_policy(private_layer, actor)
        if private_policy.recall_enabled:
            readable_layers.append(private_layer)
        if private_policy.remember_enabled:
            writable_layers.append(private_layer)

        aggregate_policy = private_policy
        for layer in self._default_shared_layers(scope_ref):
            layer_policy = self._effective_policy(layer, actor)
            if not layer_policy.recall_enabled:
                continue
            aggregate_policy = _combine_runtime_policies(aggregate_policy, layer_policy)
            layer_is_writable = (
                layer_policy.remember_enabled
                and _space_allows_default_write(self._space_for_scope(layer.scope_ref))
            )
            resolved_layer = replace(
                layer,
                layer=replace(
                    layer.layer,
                    access="read_write" if layer_is_writable else "read",
                ),
            )
            readable_layers.append(resolved_layer)
            if layer_is_writable:
                writable_layers.append(resolved_layer)

        max_recall_items = min(
            [aggregate_policy.max_recall_items, *[
                self._effective_policy(layer, actor).max_recall_items
                for layer in readable_layers
            ]],
        )
        aggregate_policy = replace(
            aggregate_policy,
            max_recall_items=max_recall_items,
            recall_enabled=bool(readable_layers),
            remember_enabled=bool(writable_layers),
        )
        return MemoryAccessPlan(
            actor=actor,
            identity_scope_ref=scope_ref,
            private_layer=private_layer,
            readable_layers=tuple(readable_layers),
            writable_layers=tuple(writable_layers),
            default_write_layer=private_layer,
            policy=aggregate_policy,
        )

    def recall(self, request: MemoryRecallRequest) -> MemoryRecallResult:
        plan = self.resolve_access_plan(request.actor)
        if not plan.readable_layers:
            raise ValueError(
                f"Memory recall is disabled for scope '{plan.identity_scope_ref}'.",
            )
        request = replace(
            request,
            max_items=min(request.max_items, plan.policy.max_recall_items),
        )
        result = self.engine.recall(layers=plan.readable_layers, request=request)
        return replace(
            result,
            scope=plan.scope,
            searched_layers=tuple(plan.readable_layers),
            access_plan=plan,
        )

    def remember(self, request: MemoryRememberRequest) -> MemoryRememberResult:
        plan = self.resolve_access_plan(request.actor)
        target_layer = self._remember_target_layer(plan, request)
        policy = self._effective_policy(target_layer, request.actor)
        if not policy.remember_enabled:
            raise ValueError(
                f"Memory remember is disabled for scope '{target_layer.scope_ref}'.",
            )
        if request.retention == "engine_default" and policy.retention != "engine_default":
            request = replace(request, retention=policy.retention)  # type: ignore[arg-type]
        result = self.engine.remember(layer=target_layer, request=request)
        return replace(
            result,
            scope=target_layer.as_scope(),
            target_layer=target_layer,
        )

    def _effective_policy(
        self,
        layer: MemoryResolvedLayer,
        actor: MemoryActorContext,
    ) -> MemoryRuntimePolicy:
        if self.policy_provider is None:
            return MemoryRuntimePolicy()
        return self.policy_provider.effective_policy_for_scope(
            scope_ref=layer.scope_ref,
            agent_id=actor.agent_id,
        )

    def _resolved_layer(
        self,
        *,
        context: MemoryUseContext,
        scope_ref: str,
        owner_kind: MemorySpaceOwnerKind,
        layer_kind: MemoryLayerKind,
        access: MemoryLayerAccess,
        default_write: bool = False,
    ) -> MemoryResolvedLayer:
        return MemoryResolvedLayer(
            context=context,
            layer=MemoryLayerRef(
                scope_ref=scope_ref,
                owner_kind=owner_kind,
                layer_kind=layer_kind,
                access=access,
                default_write=default_write,
            ),
            engine_id=self.engine.engine_id,
        )

    def _default_shared_layers(
        self,
        identity_scope_ref: str,
    ) -> tuple[MemoryResolvedLayer, ...]:
        if self.space_inventory is None:
            return ()
        layers: list[MemoryResolvedLayer] = []
        for space in self.space_inventory.list_spaces(include_disabled=False):
            if space.scope_ref == identity_scope_ref:
                continue
            if space.owner_kind not in {"shared", "project", "team", "system"}:
                continue
            if not _space_participates_in_default_recall(space):
                continue
            context = MemoryUseContext(
                space_id=space.scope_ref,
                storage_root=space.storage_root,
                retrieval_backend=space.retrieval_backend,  # type: ignore[arg-type]
            )
            layers.append(
                self._resolved_layer(
                    context=context,
                    scope_ref=space.scope_ref,
                    owner_kind=space.owner_kind,
                    layer_kind=_layer_kind_from_owner(space.owner_kind),
                    access="read",
                ),
            )
        return tuple(layers)

    def _remember_target_layer(
        self,
        plan: MemoryAccessPlan,
        request: MemoryRememberRequest,
    ) -> MemoryResolvedLayer:
        if request.target_scope_ref:
            target = next(
                (
                    layer
                    for layer in plan.writable_layers
                    if layer.scope_ref == request.target_scope_ref
                ),
                None,
            )
            if target is None:
                raise ValueError(
                    f"Memory target scope '{request.target_scope_ref}' is not writable.",
                )
            if request.target_layer_kind and target.layer.layer_kind != request.target_layer_kind:
                raise ValueError(
                    "Memory target layer does not match requested layer kind.",
                )
            return target
        if plan.default_write_layer not in plan.writable_layers:
            raise ValueError(
                f"Memory remember is disabled for scope '{plan.default_write_layer.scope_ref}'.",
            )
        return plan.default_write_layer

    def _space_for_scope(self, scope_ref: str) -> MemorySpace | None:
        if self.space_inventory is None:
            return None
        return self.space_inventory.get_space(scope_ref)

    def _owner_kind_for_scope(
        self,
        scope_ref: str,
        actor: MemoryActorContext,
    ) -> MemorySpaceOwnerKind:
        space = self._space_for_scope(scope_ref)
        if space is not None:
            return space.owner_kind
        if actor.agent_id and scope_ref == actor.agent_id:
            return "agent"
        return "shared"


def memory_citation(path: str, start_line: int, end_line: int) -> str:
    if end_line <= start_line:
        return f"{path}:{start_line}"
    return f"{path}:{start_line}-{end_line}"


def parse_memory_citation(citation: str) -> tuple[str, int, int]:
    normalized = citation.strip()
    if ":" not in normalized:
        raise ValueError("Memory citation must look like path:start or path:start-end.")
    path, raw_range = normalized.rsplit(":", 1)
    path = path.strip()
    raw_range = raw_range.strip()
    if not path or not raw_range:
        raise ValueError("Memory citation must look like path:start or path:start-end.")
    if "-" in raw_range:
        raw_start, raw_end = raw_range.split("-", 1)
    else:
        raw_start = raw_range
        raw_end = raw_range
    start_line = int(raw_start)
    end_line = int(raw_end)
    if start_line <= 0:
        raise ValueError("Memory citation start line must be positive.")
    if end_line < start_line:
        raise ValueError("Memory citation end line must be greater than or equal to start line.")
    return path, start_line, end_line


def recall_items_from_hits(
    hits: Sequence[MemorySearchHit],
    *,
    layer: MemoryResolvedLayer | None = None,
) -> tuple[MemoryRecallItem, ...]:
    return tuple(
        MemoryRecallItem(
            path=hit.path,
            kind=hit.kind,
            citation=memory_citation(hit.path, hit.start_line, hit.end_line),
            text=hit.snippet,
            start_line=hit.start_line,
            end_line=hit.end_line,
            score=hit.score,
            hit=hit,
            source_scope_ref=layer.scope_ref if layer is not None else None,
            source_layer_kind=layer.layer.layer_kind if layer is not None else None,
            source_owner_kind=layer.layer.owner_kind if layer is not None else None,
        )
        for hit in hits
    )


def recall_item_from_excerpt(
    excerpt: MemoryExcerpt,
    *,
    layer: MemoryResolvedLayer | None = None,
) -> MemoryRecallItem:
    return MemoryRecallItem(
        path=excerpt.path,
        kind=excerpt.kind,
        citation=memory_citation(excerpt.path, excerpt.start_line, excerpt.end_line),
        text=excerpt.text,
        start_line=excerpt.start_line,
        end_line=excerpt.end_line,
        excerpt=excerpt,
        source_scope_ref=layer.scope_ref if layer is not None else None,
        source_layer_kind=layer.layer.layer_kind if layer is not None else None,
        source_owner_kind=layer.layer.owner_kind if layer is not None else None,
    )


def _combine_runtime_policies(
    left: MemoryRuntimePolicy,
    right: MemoryRuntimePolicy,
) -> MemoryRuntimePolicy:
    retention = right.retention if right.retention != "engine_default" else left.retention
    return MemoryRuntimePolicy(
        recall_enabled=left.recall_enabled and right.recall_enabled,
        remember_enabled=left.remember_enabled and right.remember_enabled,
        max_recall_items=min(left.max_recall_items, right.max_recall_items),
        retention=retention,
    )


def _space_participates_in_default_recall(space: MemorySpace) -> bool:
    return _metadata_truthy(
        space.metadata,
        "default_recall",
        "default_recall_enabled",
        "include_in_default_recall",
        "common_recall",
    )


def _space_allows_default_write(space: MemorySpace | None) -> bool:
    if space is None:
        return False
    return _metadata_truthy(
        space.metadata,
        "default_write",
        "default_write_enabled",
        "allow_remember",
        "shared_write_enabled",
    )


def _metadata_truthy(metadata: Mapping[str, Any], *keys: str) -> bool:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, bool):
            if value:
                return True
            continue
        if isinstance(value, (int, float)) and value != 0:
            return True
        if isinstance(value, str) and value.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
            "enabled",
        }:
            return True
    return False


def _layer_kind_from_owner(owner_kind: MemorySpaceOwnerKind) -> MemoryLayerKind:
    if owner_kind in {"project", "team", "system"}:
        return owner_kind
    return "shared"


def _required_text(value: object, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"Memory {field_name} cannot be empty.")
    return normalized


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
