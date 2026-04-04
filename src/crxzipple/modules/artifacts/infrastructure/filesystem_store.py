from __future__ import annotations

import json
from pathlib import Path

from crxzipple.modules.artifacts.domain.entities import Artifact
from crxzipple.modules.artifacts.domain.exceptions import ArtifactNotFoundError


class FilesystemArtifactStore:
    def __init__(self, root_dir: str | Path) -> None:
        self._root_dir = Path(root_dir).expanduser().resolve()
        self._root_dir.mkdir(parents=True, exist_ok=True)

    @property
    def root_dir(self) -> Path:
        return self._root_dir

    def save_bytes(self, *, storage_key: str, data: bytes) -> Path:
        path = self.resolve_path(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def save_metadata(self, artifact: Artifact) -> Path:
        path = self._metadata_path(artifact.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(artifact.to_payload(), ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path

    def load_metadata(self, artifact_id: str) -> Artifact:
        path = self._metadata_path(artifact_id)
        if not path.is_file():
            raise ArtifactNotFoundError(f"Artifact '{artifact_id}' was not found.")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return Artifact.from_payload(payload)

    def resolve_path(self, storage_key: str) -> Path:
        return (self._root_dir / storage_key).resolve()

    def _metadata_path(self, artifact_id: str) -> Path:
        return self._root_dir / artifact_id / "metadata.json"
