from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import mimetypes
from pathlib import Path
from uuid import uuid4

from PIL import Image

from crxzipple.modules.artifacts.domain.entities import (
    Artifact,
    ArtifactKind,
    ArtifactVariant,
)
from crxzipple.modules.artifacts.domain.exceptions import (
    ArtifactNotFoundError,
    ArtifactValidationError,
)
from crxzipple.modules.artifacts.application.ports import ArtifactStorePort


@dataclass(frozen=True, slots=True)
class ArtifactBinary:
    artifact: Artifact
    path: Path
    variant: ArtifactVariant


class ArtifactApplicationService:
    DEFAULT_PREVIEW_MAX_DIMENSION = 1024
    DEFAULT_LLM_MAX_DIMENSION = 1568
    DEFAULT_LLM_IMAGE_MAX_BYTES = 1_500_000

    def __init__(
        self,
        store: ArtifactStorePort,
        *,
        preview_max_dimension: int = DEFAULT_PREVIEW_MAX_DIMENSION,
        llm_max_dimension: int = DEFAULT_LLM_MAX_DIMENSION,
        llm_image_max_bytes: int = DEFAULT_LLM_IMAGE_MAX_BYTES,
    ) -> None:
        self.store = store
        self.preview_max_dimension = max(int(preview_max_dimension), 1)
        self.llm_max_dimension = max(int(llm_max_dimension), 1)
        self.llm_image_max_bytes = max(int(llm_image_max_bytes), 1)

    def create_artifact(
        self,
        *,
        data: bytes,
        mime_type: str,
        name: str | None = None,
        kind: ArtifactKind | None = None,
        metadata: dict[str, object] | None = None,
    ) -> Artifact:
        normalized_name = (name or "").strip() or None
        normalized_mime_type = (mime_type or "").strip()
        if not normalized_mime_type:
            if normalized_name:
                guessed, _ = mimetypes.guess_type(normalized_name)
                normalized_mime_type = guessed or "application/octet-stream"
            else:
                normalized_mime_type = "application/octet-stream"
        resolved_kind = kind or self._infer_kind(normalized_mime_type)
        artifact_id = uuid4().hex
        checksum = hashlib.sha256(data).hexdigest()
        extension = self._guess_extension(
            mime_type=normalized_mime_type,
            name=normalized_name,
        )
        storage_key = f"{artifact_id}/original{extension}"
        artifact = Artifact(
            id=artifact_id,
            kind=resolved_kind,
            mime_type=normalized_mime_type,
            storage_key=storage_key,
            name=normalized_name,
            size_bytes=len(data),
            checksum_sha256=checksum,
            metadata=dict(metadata or {}),
        )
        self.store.save_bytes(storage_key=storage_key, data=data)
        artifact = self._with_generated_variants(artifact, data=data)
        self.store.save_metadata(artifact)
        return artifact

    def get_artifact(self, artifact_id: str) -> Artifact:
        return self.store.load_metadata(artifact_id)

    def resolve_variant(
        self,
        artifact_id: str,
        *,
        variant: ArtifactVariant = ArtifactVariant.ORIGINAL,
    ) -> ArtifactBinary:
        artifact = self.get_artifact(artifact_id)
        storage_key = artifact.variant_storage_key(variant)
        path = self.store.resolve_path(storage_key)
        if not path.is_file():
            raise ArtifactNotFoundError(
                f"Artifact '{artifact_id}' variant '{variant.value}' was not found.",
            )
        return ArtifactBinary(
            artifact=artifact,
            path=path,
            variant=variant,
        )

    @staticmethod
    def _infer_kind(mime_type: str) -> ArtifactKind:
        if mime_type.startswith("image/"):
            return ArtifactKind.IMAGE
        return ArtifactKind.FILE

    @staticmethod
    def _guess_extension(*, mime_type: str, name: str | None) -> str:
        if name:
            suffix = Path(name).suffix.strip()
            if suffix:
                return suffix if suffix.startswith(".") else f".{suffix}"
        guessed = mimetypes.guess_extension(mime_type) or ""
        if guessed == ".jpe":
            return ".jpg"
        return guessed

    def _with_generated_variants(
        self,
        artifact: Artifact,
        *,
        data: bytes,
    ) -> Artifact:
        if artifact.kind is not ArtifactKind.IMAGE:
            return artifact
        try:
            preview_bytes, llm_bytes, width, height = self._render_image_variants(
                data=data,
                mime_type=artifact.mime_type,
            )
        except Exception:  # noqa: BLE001
            return artifact

        preview_storage_key = f"{artifact.id}/preview{Path(artifact.storage_key).suffix}"
        llm_storage_key = f"{artifact.id}/llm{Path(artifact.storage_key).suffix}"
        self.store.save_bytes(storage_key=preview_storage_key, data=preview_bytes)
        self.store.save_bytes(storage_key=llm_storage_key, data=llm_bytes)
        return Artifact(
            id=artifact.id,
            kind=artifact.kind,
            mime_type=artifact.mime_type,
            storage_key=artifact.storage_key,
            name=artifact.name,
            preview_storage_key=preview_storage_key,
            llm_storage_key=llm_storage_key,
            size_bytes=artifact.size_bytes,
            width=width,
            height=height,
            checksum_sha256=artifact.checksum_sha256,
            metadata=dict(artifact.metadata),
            created_at=artifact.created_at,
        )

    def _render_image_variants(
        self,
        *,
        data: bytes,
        mime_type: str,
    ) -> tuple[bytes, bytes, int, int]:
        with Image.open(io.BytesIO(data)) as original:
            width, height = original.size
            preview_bytes = self._encode_image_variant(
                original,
                mime_type=mime_type,
                max_dimension=self.preview_max_dimension,
            )
            llm_bytes = self._encode_image_variant(
                original,
                mime_type=mime_type,
                max_dimension=self.llm_max_dimension,
                target_max_bytes=self.llm_image_max_bytes,
            )
        return preview_bytes, llm_bytes, width, height

    def _encode_image_variant(
        self,
        image: Image.Image,
        *,
        mime_type: str,
        max_dimension: int,
        target_max_bytes: int | None = None,
    ) -> bytes:
        format_name = self._image_format_for_mime_type(mime_type)
        current_max_dimension = max_dimension
        current_quality = 85 if format_name == "JPEG" else 80
        while True:
            variant = image.copy()
            variant.thumbnail((current_max_dimension, current_max_dimension))
            if format_name == "JPEG" and variant.mode not in {"RGB", "L"}:
                variant = variant.convert("RGB")
            buffer = io.BytesIO()
            save_kwargs: dict[str, object]
            if format_name == "JPEG":
                save_kwargs = {
                    "format": format_name,
                    "quality": current_quality,
                    "optimize": True,
                }
            elif format_name == "PNG":
                save_kwargs = {
                    "format": format_name,
                    "optimize": True,
                    "compress_level": 9,
                }
            elif format_name == "WEBP":
                save_kwargs = {
                    "format": format_name,
                    "quality": current_quality,
                    "method": 6,
                }
            else:
                raise ArtifactValidationError(
                    f"Unsupported image mime type '{mime_type}' for artifact variants.",
                )
            variant.save(buffer, **save_kwargs)
            encoded = buffer.getvalue()
            if target_max_bytes is None or len(encoded) <= target_max_bytes:
                return encoded
            if current_max_dimension > 256:
                current_max_dimension = max(256, int(current_max_dimension * 0.8))
                continue
            if format_name in {"JPEG", "WEBP"} and current_quality > 40:
                current_quality = max(40, current_quality - 10)
                continue
            return encoded

    @staticmethod
    def _image_format_for_mime_type(mime_type: str) -> str:
        normalized = mime_type.strip().lower()
        if normalized in {"image/jpeg", "image/jpg"}:
            return "JPEG"
        if normalized == "image/png":
            return "PNG"
        if normalized == "image/webp":
            return "WEBP"
        raise ArtifactValidationError(
            f"Unsupported image mime type '{mime_type}' for artifact variants.",
        )
