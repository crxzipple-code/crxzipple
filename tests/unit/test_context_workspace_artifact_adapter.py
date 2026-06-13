from __future__ import annotations

from crxzipple.app.integration.context_workspace_artifacts import (
    ArtifactContextNodeProvider,
)
from crxzipple.modules.artifacts.domain.entities import Artifact, ArtifactKind
from crxzipple.modules.artifacts.domain.exceptions import ArtifactNotFoundError
from crxzipple.modules.context_workspace.application import (
    ContextActionInput,
    ContextOwnerRegistry,
    ContextRenderService,
    ContextTreeService,
    ContextWorkspaceService,
    EnsureContextWorkspaceInput,
    RenderContextPromptInput,
)
from crxzipple.modules.context_workspace.domain import ContextAction
from crxzipple.modules.context_workspace.infrastructure import (
    InMemoryContextNodeRepository,
    InMemoryContextOperationRepository,
    InMemoryContextRenderSnapshotRepository,
    InMemoryContextWorkspaceRepository,
)
from crxzipple.modules.session.domain import SessionItem, SessionItemKind
from crxzipple.shared.content_blocks import (
    file_ref_content_block,
    image_ref_content_block,
)


def test_artifact_adapter_expands_session_artifact_handles() -> None:
    session_service = _FakeSessionService(
        SessionItem(
            id="item-1",
            session_key="session:artifacts",
            session_id="instance-1",
            sequence_no=1,
            kind=SessionItemKind.ASSISTANT_MESSAGE,
            role="assistant",
            content_payload={
                "blocks": [
                    image_ref_content_block(
                        artifact_id="image-1",
                        mime_type="image/png",
                        name="chart.png",
                    ),
                    file_ref_content_block(
                        artifact_id="file-1",
                        mime_type="application/json",
                        name="result.json",
                    ),
                ],
            },
        ),
    )
    artifact_service = _FakeArtifactService(
        Artifact(
            id="image-1",
            kind=ArtifactKind.IMAGE,
            mime_type="image/png",
            storage_key="image-1/original.png",
            name="chart.png",
            size_bytes=1234,
            width=640,
            height=480,
        ),
        Artifact(
            id="file-1",
            kind=ArtifactKind.FILE,
            mime_type="application/json",
            storage_key="file-1/original.json",
            name="result.json",
            size_bytes=42,
        ),
    )
    services = _context_services(session_service, artifact_service)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:artifacts",
            agent_id="assistant",
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:artifacts",
            node_id="artifacts.session",
            action=ContextAction.EXPAND,
        ),
    )
    tree = services["tree"].list_tree("session:artifacts")
    artifact_nodes = [
        node for node in tree.nodes if node.parent_id == "artifacts.session"
    ]

    assert [node.id for node in artifact_nodes] == [
        "artifacts.artifact.image-1",
        "artifacts.artifact.file-1",
    ]
    assert artifact_nodes[0].kind == "artifact_image"
    assert ContextAction.PIN in artifact_nodes[0].actions
    assert artifact_nodes[0].owner_ref["preferred_variant"] == "llm"
    assert artifact_nodes[1].kind == "artifact_file"
    assert artifact_nodes[1].owner_ref["preferred_variant"] == "original"


def test_artifact_provider_mirror_includes_pinned_artifacts() -> None:
    session_service = _FakeSessionService(
        SessionItem(
            id="item-1",
            session_key="session:artifacts",
            session_id="instance-1",
            sequence_no=1,
            kind=SessionItemKind.ASSISTANT_MESSAGE,
            role="assistant",
            content_payload={
                "blocks": [
                    image_ref_content_block(
                        artifact_id="image-1",
                        mime_type="image/png",
                        name="chart.png",
                    ),
                ],
            },
        ),
    )
    artifact_service = _FakeArtifactService(
        Artifact(
            id="image-1",
            kind=ArtifactKind.IMAGE,
            mime_type="image/png",
            storage_key="image-1/original.png",
            name="chart.png",
        ),
    )
    services = _context_services(session_service, artifact_service)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:artifacts",
            agent_id="assistant",
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:artifacts",
            node_id="artifacts.session",
            action=ContextAction.EXPAND,
        ),
    )
    before_pin = services["render"].render_prompt_body(
        RenderContextPromptInput(session_key="session:artifacts"),
    )

    assert "artifact_content_candidates" not in before_pin.provider_attachments

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:artifacts",
            node_id="artifacts.artifact.image-1",
            action=ContextAction.PIN,
        ),
    )
    after_pin = services["render"].render_prompt_body(
        RenderContextPromptInput(session_key="session:artifacts"),
    )

    assert after_pin.mirrored_node_ids == ("artifacts.artifact.image-1",)
    assert after_pin.provider_attachments["artifact_content_candidates"] == [
        {
            "node_id": "artifacts.artifact.image-1",
            "artifact_id": "image-1",
            "kind": "artifact_image",
            "mime_type": "image/png",
            "name": "chart.png",
            "preferred_variant": "llm",
        },
    ]


def _context_services(
    session_service: "_FakeSessionService",
    artifact_service: "_FakeArtifactService",
):
    registry = ContextOwnerRegistry()
    registry.register(
        ArtifactContextNodeProvider(
            session_service=session_service,
            artifact_service=artifact_service,
        ),
    )
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    operations = InMemoryContextOperationRepository()
    snapshots = InMemoryContextRenderSnapshotRepository()
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
        "render": ContextRenderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
        ),
    }


class _FakeSessionService:
    def __init__(self, *items: SessionItem) -> None:
        self._items = tuple(items)

    def list_items(self, _data):
        return list(self._items)


class _FakeArtifactService:
    def __init__(self, *artifacts: Artifact) -> None:
        self._artifacts = {artifact.id: artifact for artifact in artifacts}

    def get_artifact(self, artifact_id: str) -> Artifact:
        artifact = self._artifacts.get(artifact_id)
        if artifact is None:
            raise ArtifactNotFoundError(artifact_id)
        return artifact
