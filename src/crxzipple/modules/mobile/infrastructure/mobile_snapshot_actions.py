from __future__ import annotations

from typing import Any

from crxzipple.modules.artifacts.application.services import ArtifactApplicationService
from crxzipple.modules.artifacts.domain.entities import ArtifactVariant
from crxzipple.modules.mobile.application.ports import MobileRefStore
from crxzipple.modules.mobile.domain import (
    MobileActionCommand,
    MobileActionResult,
    MobileDeviceRuntimeState,
    MobileExecutionError,
    MobileExecutionPlan,
    MobileStoredRef,
)
from crxzipple.modules.ocr.application.services import OcrApplicationService

from .adb_client import AndroidAdbClient
from .snapshot_builders import (
    snapshot_from_ocr_result,
    snapshot_from_source,
    ui_tree_looks_low_quality,
)
from .vision_layout import detect_visual_layout_candidates


def execute_snapshot(
    *,
    plan: MobileExecutionPlan,
    command: MobileActionCommand,
    runtime_state: MobileDeviceRuntimeState,
    client: AndroidAdbClient,
    ref_store: MobileRefStore,
    artifact_service: ArtifactApplicationService | None,
    ocr_service: OcrApplicationService | None,
) -> tuple[MobileActionResult, MobileDeviceRuntimeState]:
    generation = runtime_state.next_ref_generation()
    previous_generation = runtime_state.current_ref_generation
    source_length: int | None = None
    mitigations_applied: tuple[str, ...] = ()
    observation_mode = "ui_tree"
    ocr_artifact_id: str | None = None
    low_quality_ui_tree = False
    try:
        capture = client.capture_ui_xml()
        source = capture.xml
        focus = {
            "package": capture.current_package,
            "activity": capture.current_activity,
        }
        tree_text, refs, text_excerpt, node_count = snapshot_from_source(
            source=source,
            generation=generation,
        )
        source_length = len(source)
        mitigations_applied = capture.mitigations_applied
        if (
            artifact_service is not None
            and ocr_service is not None
            and ui_tree_looks_low_quality(
                refs=refs,
                text_excerpt=text_excerpt,
                node_count=node_count,
                current_package=capture.current_package,
            )
        ):
            try:
                tree_text, refs, text_excerpt, node_count, ocr_artifact_id, focus = (
                    capture_ocr_snapshot(
                        plan=plan,
                        client=client,
                        generation=generation,
                        artifact_service=artifact_service,
                        ocr_service=ocr_service,
                    )
                )
                observation_mode = "ocr"
                low_quality_ui_tree = True
            except MobileExecutionError as ocr_error:
                runtime_state.metadata["last_snapshot_fallback_error"] = str(ocr_error)
    except MobileExecutionError as xml_error:
        tree_text, refs, text_excerpt, node_count, ocr_artifact_id, focus = (
            capture_ocr_snapshot(
                plan=plan,
                client=client,
                generation=generation,
                artifact_service=artifact_service,
                ocr_service=ocr_service,
            )
        )
        observation_mode = "ocr"
        mitigations_applied = ()
        source_length = None
        runtime_state.metadata["last_snapshot_fallback_error"] = str(xml_error)
    if low_quality_ui_tree:
        runtime_state.metadata["last_snapshot_fallback_error"] = "low_quality_ui_tree"
    if previous_generation is not None and previous_generation != generation:
        ref_store.delete_refs(
            device_name=plan.device.name,
            generation=previous_generation,
        )
    ref_store.save_refs(
        device_name=plan.device.name,
        generation=generation,
        refs=refs,
    )
    format_name = str(command.payload.get("format") or "interactive_text").strip().lower()
    runtime_state.remember_snapshot(
        generation=generation,
        ref_count=len(refs),
        snapshot_format=format_name,
        package_name=(focus.get("package") or None),
        activity_name=(focus.get("activity") or None),
        source_length=source_length,
    )
    if format_name == "text":
        snapshot_body = text_excerpt
    elif format_name == "interactive_text":
        snapshot_body = f"{tree_text}\n\nText:\n{text_excerpt}".strip()
    else:
        snapshot_body = tree_text
    return (
        MobileActionResult(
            ok=True,
            device_name=plan.device.name,
            message="Captured mobile UI snapshot.",
            command=command,
            value={
                "format": format_name,
                "snapshot": snapshot_body,
                "text": text_excerpt,
                "source_length": source_length,
                "observation_mode": observation_mode,
                "node_count": node_count,
                "refs": refs,
                "ref_count": len(refs),
                "generation": generation,
                "current_package": focus.get("package"),
                "current_activity": focus.get("activity"),
                "mitigations_applied": mitigations_applied,
                "ocr_artifact_id": ocr_artifact_id,
                "ref_source_counts": {
                    "ui_tree": sum(1 for ref in refs if ref.source == "ui_tree"),
                    "ocr": sum(1 for ref in refs if ref.source == "ocr"),
                    "vision": sum(1 for ref in refs if ref.source == "vision"),
                },
            },
        ),
        runtime_state,
    )


def capture_ocr_snapshot(
    *,
    plan: MobileExecutionPlan,
    client: AndroidAdbClient,
    generation: int,
    artifact_service: ArtifactApplicationService | None,
    ocr_service: OcrApplicationService | None,
) -> tuple[str, tuple[MobileStoredRef, ...], str, int, str, dict[str, str | None]]:
    if artifact_service is None or ocr_service is None:
        raise MobileExecutionError(
            "OCR fallback is unavailable because OCR services are not configured.",
        )
    image_bytes = client.take_screenshot()
    artifact = artifact_service.create_artifact(
        data=image_bytes,
        mime_type="image/png",
        name=f"{plan.device.name}-ocr-fallback.png",
    )
    ocr_result = ocr_service.analyze_artifact(
        artifact_id=artifact.id,
        variant=ArtifactVariant.ORIGINAL,
    )
    vision_candidates = detect_visual_layout_candidates(
        image_bytes=image_bytes,
        ocr_result=ocr_result,
    )
    focus = client.current_focus()
    tree_text, refs, text_excerpt, node_count = snapshot_from_ocr_result(
        result=ocr_result,
        generation=generation,
        vision_candidates=vision_candidates,
    )
    return tree_text, refs, text_excerpt, node_count, artifact.id, focus


def execute_screenshot(
    *,
    plan: MobileExecutionPlan,
    command: MobileActionCommand,
    runtime_state: MobileDeviceRuntimeState,
    client: AndroidAdbClient,
    artifact_service: ArtifactApplicationService | None,
) -> tuple[MobileActionResult, MobileDeviceRuntimeState]:
    image_bytes = client.take_screenshot()
    runtime_state.clear_error()
    if artifact_service is not None:
        artifact = artifact_service.create_artifact(
            data=image_bytes,
            mime_type="image/png",
            name=f"{plan.device.name}-screenshot.png",
        )
        value: dict[str, Any] = {
            "artifact_id": artifact.id,
            "mime_type": artifact.mime_type,
            "name": artifact.name,
            "width": artifact.width,
            "height": artifact.height,
        }
    else:
        value = {
            "mime_type": "image/png",
            "bytes": len(image_bytes),
        }
    return (
        MobileActionResult(
            ok=True,
            device_name=plan.device.name,
            message="Captured mobile screenshot.",
            command=command,
            value=value,
        ),
        runtime_state,
    )
