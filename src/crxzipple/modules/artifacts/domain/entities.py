from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum

from crxzipple.modules.artifacts.domain.exceptions import ArtifactValidationError


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ArtifactKind(StrEnum):
    IMAGE = "image"
    FILE = "file"


class ArtifactVariant(StrEnum):
    ORIGINAL = "original"
    PREVIEW = "preview"
    LLM = "llm"


@dataclass(frozen=True, slots=True)
class Artifact:
    id: str
    kind: ArtifactKind
    mime_type: str
    storage_key: str
    name: str | None = None
    preview_storage_key: str | None = None
    llm_storage_key: str | None = None
    size_bytes: int = 0
    width: int | None = None
    height: int | None = None
    checksum_sha256: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ArtifactValidationError("Artifact id cannot be empty.")
        if not self.mime_type.strip():
            raise ArtifactValidationError("Artifact mime_type cannot be empty.")
        if not self.storage_key.strip():
            raise ArtifactValidationError("Artifact storage_key cannot be empty.")
        if self.size_bytes < 0:
            raise ArtifactValidationError("Artifact size_bytes cannot be negative.")
        object.__setattr__(self, "metadata", dict(self.metadata))

    def variant_storage_key(self, variant: ArtifactVariant) -> str:
        if variant is ArtifactVariant.ORIGINAL:
            return self.storage_key
        if variant is ArtifactVariant.PREVIEW and self.preview_storage_key is not None:
            return self.preview_storage_key
        if variant is ArtifactVariant.LLM and self.llm_storage_key is not None:
            return self.llm_storage_key
        return self.storage_key

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "mime_type": self.mime_type,
            "storage_key": self.storage_key,
            "preview_storage_key": self.preview_storage_key,
            "llm_storage_key": self.llm_storage_key,
            "name": self.name,
            "size_bytes": self.size_bytes,
            "width": self.width,
            "height": self.height,
            "checksum_sha256": self.checksum_sha256,
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "Artifact":
        created_at_raw = payload.get("created_at")
        created_at = (
            datetime.fromisoformat(str(created_at_raw))
            if isinstance(created_at_raw, str) and created_at_raw.strip()
            else utcnow()
        )
        return cls(
            id=str(payload.get("id", "")),
            kind=ArtifactKind(str(payload.get("kind", ArtifactKind.FILE.value))),
            mime_type=str(payload.get("mime_type", "")),
            storage_key=str(payload.get("storage_key", "")),
            preview_storage_key=(
                str(payload["preview_storage_key"])
                if isinstance(payload.get("preview_storage_key"), str)
                and str(payload["preview_storage_key"]).strip()
                else None
            ),
            llm_storage_key=(
                str(payload["llm_storage_key"])
                if isinstance(payload.get("llm_storage_key"), str)
                and str(payload["llm_storage_key"]).strip()
                else None
            ),
            name=(
                str(payload["name"])
                if isinstance(payload.get("name"), str) and str(payload["name"]).strip()
                else None
            ),
            size_bytes=int(payload.get("size_bytes", 0) or 0),
            width=(
                int(payload["width"])
                if isinstance(payload.get("width"), int)
                else None
            ),
            height=(
                int(payload["height"])
                if isinstance(payload.get("height"), int)
                else None
            ),
            checksum_sha256=(
                str(payload["checksum_sha256"])
                if isinstance(payload.get("checksum_sha256"), str)
                and str(payload["checksum_sha256"]).strip()
                else None
            ),
            metadata=(
                dict(payload["metadata"])
                if isinstance(payload.get("metadata"), dict)
                else {}
            ),
            created_at=created_at,
        )
