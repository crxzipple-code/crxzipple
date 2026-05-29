from __future__ import annotations

from dataclasses import dataclass

from crxzipple.app.integration.context_workspace_memory import (
    MemoryContextNodeProvider,
)
from crxzipple.modules.context_workspace.application import (
    ContextActionInput,
    ContextOwnerRegistry,
    ContextTreeService,
    ContextWorkspaceService,
    EnsureContextWorkspaceInput,
)
from crxzipple.modules.context_workspace.domain import ContextAction
from crxzipple.modules.context_workspace.infrastructure import (
    InMemoryContextNodeRepository,
    InMemoryContextOperationRepository,
    InMemoryContextWorkspaceRepository,
)
from crxzipple.modules.memory.application import (
    MemoryAccessPlan,
    MemoryActorContext,
    MemoryLayerRef,
    MemoryResolvedLayer,
    MemoryRuntimePolicy,
    MemoryUseContext,
)


def test_memory_adapter_exposes_governed_memory_layer_nodes() -> None:
    services = _context_services(
        _MemoryRuntimeStub(
            layers=(
                _layer("assistant", "agent", "private", "read_write", default_write=True),
                _layer("shared:common", "shared", "shared", "read"),
                _layer("project:runtime", "project", "project", "read"),
                _layer("team:ops", "team", "team", "read"),
                _layer("system:base", "system", "system", "read"),
            ),
        ),
    )

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:memory",
            agent_id="assistant",
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:memory",
            node_id="memory.visible",
            action=ContextAction.EXPAND,
        ),
    )
    tree = services["tree"].list_tree("session:memory")
    memory_nodes = [node for node in tree.nodes if node.parent_id == "memory.visible"]

    assert [node.metadata["governance_scope"] for node in memory_nodes] == [
        "private",
        "shared",
        "project",
        "team",
        "system",
    ]
    private_node = memory_nodes[0]
    assert private_node.owner_ref["readable"] is True
    assert private_node.owner_ref["writable"] is True
    assert private_node.owner_ref["default_write"] is True


def _context_services(memory_runtime_service: _MemoryRuntimeStub):
    registry = ContextOwnerRegistry()
    registry.register(MemoryContextNodeProvider(memory_runtime_service))
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    operations = InMemoryContextOperationRepository()
    return {
        "workspace": ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
            owner_registry=registry,
        ),
        "tree": ContextTreeService(
            workspace_repository=workspaces,
            node_repository=nodes,
            operation_repository=operations,
            owner_registry=registry,
        ),
    }


def _layer(
    scope_ref: str,
    owner_kind: str,
    layer_kind: str,
    access: str,
    *,
    default_write: bool = False,
) -> MemoryResolvedLayer:
    return MemoryResolvedLayer(
        context=MemoryUseContext(
            space_id=scope_ref,
            storage_root=f"/memory/{scope_ref}",
            retrieval_backend="hybrid",
        ),
        layer=MemoryLayerRef(
            scope_ref=scope_ref,
            owner_kind=owner_kind,  # type: ignore[arg-type]
            layer_kind=layer_kind,  # type: ignore[arg-type]
            access=access,  # type: ignore[arg-type]
            default_write=default_write,
        ),
        engine_id="file_markdown",
    )


@dataclass(frozen=True, slots=True)
class _MemoryRuntimeStub:
    layers: tuple[MemoryResolvedLayer, ...]

    def resolve_access_plan(self, actor: MemoryActorContext) -> MemoryAccessPlan:
        private_layer = self.layers[0]
        writable_layers = tuple(
            layer for layer in self.layers if layer.layer.access == "read_write"
        )
        return MemoryAccessPlan(
            actor=actor,
            identity_scope_ref=actor.requested_scope_ref or "assistant",
            private_layer=private_layer,
            readable_layers=self.layers,
            writable_layers=writable_layers,
            default_write_layer=private_layer,
            policy=MemoryRuntimePolicy(),
        )
