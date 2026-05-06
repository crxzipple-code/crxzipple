from __future__ import annotations

from pathlib import Path
from typing import Protocol

from crxzipple.modules.artifacts.domain.entities import Artifact


class ArtifactStorePort(Protocol):
    def save_bytes(self, *, storage_key: str, data: bytes) -> Path:
        ...

    def save_metadata(self, artifact: Artifact) -> Path:
        ...

    def load_metadata(self, artifact_id: str) -> Artifact:
        ...

    def resolve_path(self, storage_key: str) -> Path:
        ...
