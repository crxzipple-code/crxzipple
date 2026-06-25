from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile

from crxzipple.modules.artifacts.domain.entities import Artifact
from crxzipple.modules.artifacts.domain.exceptions import (
    ArtifactNotFoundError,
    ArtifactValidationError,
)


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
        descriptor, temp_path_raw = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temp_path = Path(temp_path_raw)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink()
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

    def list_metadata(self) -> tuple[Artifact, ...]:
        artifacts: list[Artifact] = []
        for metadata_path in sorted(self._root_dir.glob("*/metadata.json")):
            if not metadata_path.is_file():
                continue
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            artifacts.append(Artifact.from_payload(payload))
        return tuple(artifacts)

    def delete_artifact(self, artifact_id: str) -> bool:
        path = self._metadata_path(artifact_id).parent
        if not path.exists():
            return False
        self._require_inside_root(path)
        shutil.rmtree(path)
        return True

    def resolve_path(self, storage_key: str) -> Path:
        normalized = storage_key.strip()
        if not normalized:
            raise ArtifactValidationError("Artifact storage_key cannot be empty.")
        return self._require_inside_root(self._root_dir / normalized)

    def _metadata_path(self, artifact_id: str) -> Path:
        normalized = artifact_id.strip()
        if not normalized or any(part in normalized for part in ("/", "\\")):
            raise ArtifactNotFoundError(f"Artifact '{artifact_id}' was not found.")
        return self._require_inside_root(self._root_dir / normalized / "metadata.json")

    def _require_inside_root(self, path: Path) -> Path:
        resolved = path.resolve()
        try:
            resolved.relative_to(self._root_dir)
        except ValueError as exc:
            raise ArtifactValidationError(
                "Artifact storage path must stay inside the artifact root.",
            ) from exc
        return resolved
