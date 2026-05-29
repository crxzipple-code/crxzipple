from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from crxzipple.modules.artifacts.domain import Artifact, ArtifactKind


class ToolArtifactWritePort(Protocol):
    def create_artifact(
        self,
        *,
        data: bytes,
        mime_type: str,
        name: str | None = None,
        kind: "ArtifactKind | None" = None,
        metadata: dict[str, object] | None = None,
    ) -> "Artifact":
        ...
