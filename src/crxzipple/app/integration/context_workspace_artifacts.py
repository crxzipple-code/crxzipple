"""Artifact context tree adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

from crxzipple.modules.artifacts.domain.entities import Artifact, ArtifactKind
from crxzipple.modules.artifacts.domain.exceptions import ArtifactNotFoundError
from crxzipple.modules.context_workspace.application import ContextChildrenRequest
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextEstimate,
    ContextNodeSeed,
    ContextNodeState,
)
from crxzipple.modules.session.application import (
    ListSessionItemsInput,
)
from crxzipple.modules.session.domain import SessionItem, SessionNotFoundError
from crxzipple.shared.content_blocks import (
    FILE_REF_BLOCK_TYPE,
    IMAGE_REF_BLOCK_TYPE,
    content_blocks_from_payload,
)


class ArtifactContextService(Protocol):
    def get_artifact(self, artifact_id: str) -> Artifact:
        ...


class ArtifactSessionItemService(Protocol):
    def list_items(
        self,
        data: ListSessionItemsInput,
    ) -> list[SessionItem]:
        ...


class ArtifactContextNodeProvider:
    owner = "artifacts"

    def __init__(
        self,
        *,
        session_service: ArtifactSessionItemService,
        artifact_service: ArtifactContextService,
        item_limit: int = 200,
    ) -> None:
        self._session_service = session_service
        self._artifact_service = artifact_service
        self._item_limit = max(int(item_limit), 1)

    def children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        if request.node.id != "artifacts.session":
            return ()
        try:
            items = self._session_service.list_items(
                ListSessionItemsInput(
                    session_key=request.workspace.session_key,
                    active_session_only=False,
                    limit=self._item_limit,
                ),
            )
        except SessionNotFoundError:
            return ()
        refs = _artifact_refs_from_items(tuple(items))
        seeds: list[ContextNodeSeed] = []
        for index, ref in enumerate(refs, start=1):
            try:
                artifact = self._artifact_service.get_artifact(ref.artifact_id)
            except ArtifactNotFoundError:
                continue
            seeds.append(
                _artifact_node_seed(
                    artifact=artifact,
                    ref=ref,
                    parent_id=request.node.id,
                    display_order=index * 10,
                ),
            )
        return tuple(seeds)


@dataclass(frozen=True, slots=True)
class _ArtifactRef:
    artifact_id: str
    block_type: str
    session_item_id: str
    session_id: str
    sequence_no: int
    role: str | None
    name: str | None = None
    mime_type: str | None = None
    preview_url: str | None = None
    original_url: str | None = None
    download_url: str | None = None


_ARTIFACT_ACTIONS = (
    ContextAction.PIN,
    ContextAction.UNPIN,
    ContextAction.ESTIMATE,
)


def _artifact_refs_from_items(
    items: tuple[SessionItem, ...],
) -> tuple[_ArtifactRef, ...]:
    refs: list[_ArtifactRef] = []
    seen: set[str] = set()
    for item in items:
        for block in content_blocks_from_payload(item.content_payload):
            block_type = block.get("type")
            if block_type not in {IMAGE_REF_BLOCK_TYPE, FILE_REF_BLOCK_TYPE}:
                continue
            artifact_id = _optional_text(block.get("artifact_id"))
            if artifact_id is None or artifact_id in seen:
                continue
            seen.add(artifact_id)
            refs.append(
                _ArtifactRef(
                    artifact_id=artifact_id,
                    block_type=str(block_type),
                    session_item_id=item.id,
                    session_id=item.session_id,
                    sequence_no=item.sequence_no,
                    role=item.role,
                    name=_optional_text(block.get("name")),
                    mime_type=_optional_text(block.get("mime_type")),
                    preview_url=_optional_text(block.get("preview_url")),
                    original_url=_optional_text(block.get("original_url")),
                    download_url=_optional_text(block.get("download_url")),
                ),
            )
    return tuple(refs)


def _artifact_node_seed(
    *,
    artifact: Artifact,
    ref: _ArtifactRef,
    parent_id: str,
    display_order: int,
) -> ContextNodeSeed:
    kind = (
        "artifact_image"
        if artifact.kind is ArtifactKind.IMAGE or ref.block_type == IMAGE_REF_BLOCK_TYPE
        else "artifact_file"
    )
    title = artifact.name or ref.name or artifact.id
    summary = _artifact_summary(artifact, ref=ref)
    preferred_variant = "llm" if kind == "artifact_image" else "original"
    return ContextNodeSeed(
        node_id=f"artifacts.artifact.{_node_token(artifact.id)}",
        parent_id=parent_id,
        owner="artifacts",
        kind=kind,
        title=title,
        summary=summary,
        state=ContextNodeState(loaded=True),
        actions=_ARTIFACT_ACTIONS,
        owner_ref={
            "artifact_id": artifact.id,
            "session_item_id": ref.session_item_id,
            "session_id": ref.session_id,
            "sequence_no": ref.sequence_no,
            "preferred_variant": preferred_variant,
        },
        estimate=_artifact_estimate(artifact, summary=summary),
        display_order=display_order,
        metadata={
            "artifact_id": artifact.id,
            "kind": artifact.kind.value,
            "mime_type": artifact.mime_type,
            "name": artifact.name,
            "size_bytes": artifact.size_bytes,
            "width": artifact.width,
            "height": artifact.height,
            "checksum_sha256": artifact.checksum_sha256,
            "preview_url": ref.preview_url or f"/artifacts/{artifact.id}/preview",
            "original_url": ref.original_url or f"/artifacts/{artifact.id}/original",
            "download_url": ref.download_url or f"/artifacts/{artifact.id}/download",
            "preferred_variant": preferred_variant,
            "referenced_by": {
                "session_item_id": ref.session_item_id,
                "session_id": ref.session_id,
                "sequence_no": ref.sequence_no,
                "role": ref.role,
            },
            "created_at": artifact.created_at.isoformat(),
        },
    )


def _artifact_summary(artifact: Artifact, *, ref: _ArtifactRef) -> str:
    parts = [artifact.mime_type]
    if artifact.width is not None and artifact.height is not None:
        parts.append(f"{artifact.width}x{artifact.height}")
    if artifact.size_bytes:
        parts.append(_format_bytes(artifact.size_bytes))
    return (
        f"{artifact.name or ref.name or artifact.id} "
        f"({', '.join(parts)}) referenced by session item #{ref.sequence_no}."
    )


def _artifact_estimate(artifact: Artifact, *, summary: str) -> ContextEstimate:
    if artifact.kind is ArtifactKind.IMAGE:
        return ContextEstimate(
            text_chars=len(summary),
            text_tokens=max((len(summary) + 3) // 4, 1),
            image_count=1,
        )
    return ContextEstimate(
        text_chars=len(summary),
        text_tokens=max((len(summary) + 3) // 4, 1),
        file_count=1,
    )


def _format_bytes(size_bytes: int) -> str:
    value = float(max(size_bytes, 0))
    units = ("B", "KB", "MB", "GB")
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{int(size_bytes)} B"


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _node_token(value: str) -> str:
    return quote(value.strip(), safe="")


__all__ = ["ArtifactContextNodeProvider"]
