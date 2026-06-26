"""OCR module app assembly."""

from __future__ import annotations

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory
from crxzipple.core.config import Settings
from crxzipple.modules.ocr import (
    OcrApplicationService,
    OcrHostClient,
    OcrResultSerializer,
    PPStructureV3Client,
)


def ocr_factories() -> tuple[ApplicationFactory, ...]:
    """Build OCR application service and result serializer."""

    return (
        ApplicationFactory(
            key="ocr.service",
            provides=(AppKey.OCR_SERVICE, AppKey.OCR_RESULT_SERIALIZER),
            requires=(AppKey.CORE_SETTINGS, AppKey.ARTIFACT_SERVICE),
            build=_build_ocr_service,
        ),
    )


def _build_ocr_service(ctx) -> dict[str, object]:
    settings = ctx.require(AppKey.CORE_SETTINGS)
    return {
        AppKey.OCR_SERVICE: OcrApplicationService(
            engine=build_ocr_engine(settings),
            artifact_service=ctx.require(AppKey.ARTIFACT_SERVICE),
            default_language=settings.ocr_language,
            max_concurrent_requests=settings.ocr_max_concurrent_requests,
        ),
        AppKey.OCR_RESULT_SERIALIZER: OcrResultSerializer(),
    }


def build_ocr_engine(settings: Settings) -> OcrHostClient | PPStructureV3Client:
    if settings.ocr_provider == "ppstructurev3":
        return PPStructureV3Client(
            base_url=settings.ocr_base_url,
            timeout_seconds=settings.ocr_request_timeout_seconds,
        )
    return OcrHostClient(
        base_url=settings.ocr_base_url,
        timeout_seconds=settings.ocr_request_timeout_seconds,
    )


__all__ = ["build_ocr_engine", "ocr_factories"]
