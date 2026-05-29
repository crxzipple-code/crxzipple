"""Orchestration to Context Workspace integration."""

from __future__ import annotations

import base64

from crxzipple.modules.artifacts.domain.entities import ArtifactVariant
from crxzipple.modules.context_workspace.application import (
    ContextRenderService,
    ContextWorkspaceService,
    EnsureContextWorkspaceInput,
    RecordContextRenderSnapshotInput,
    RenderContextPromptInput,
)
from crxzipple.modules.llm.domain import ToolSchema
from crxzipple.modules.orchestration.application.flow_context import (
    build_flow_context_payload,
)
from crxzipple.modules.orchestration.application.ports import (
    ContextRenderSnapshotRecord,
)
from crxzipple.modules.orchestration.application.prompt_surface import (
    PromptSurface,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun


class ContextWorkspacePromptSnapshotAdapter:
    """Records a tree-backed prompt snapshot for real orchestration runs.

    The adapter is intentionally side-effect narrow: it materializes Context
    Workspace state alongside the existing PromptSurfaceBuilder output and returns
    the rendered prompt body to the orchestration engine for provider delivery.
    """

    def __init__(
        self,
        *,
        workspace_service: ContextWorkspaceService,
        render_service: ContextRenderService,
        artifact_service: object | None = None,
    ) -> None:
        self._workspace_service = workspace_service
        self._render_service = render_service
        self._artifact_service = artifact_service

    def record_run_prompt_snapshot(
        self,
        *,
        run: OrchestrationRun,
        prompt: PromptSurface,
    ) -> ContextRenderSnapshotRecord | None:
        session_key = prompt.session_key.strip()
        agent_id = str(run.agent_id or "").strip()
        if not session_key or not agent_id:
            return None
        flow_context = build_flow_context_payload(
            mode=prompt.mode,
            hint_payload=prompt.flow_hint,
        )
        self._workspace_service.ensure_workspace(
            EnsureContextWorkspaceInput(
                session_key=session_key,
                agent_id=agent_id,
                metadata={
                    "source": "orchestration",
                    "last_run_id": run.id,
                    "workspace_dir": prompt.workspace_dir,
                    "prompt_surface": prompt.surface_policy.surface,
                    "prompt_mode": prompt.mode.value,
                    "agent_instruction_node": _context_node_payload(
                        prompt,
                        kind="agent_instruction",
                    ),
                    "runtime_context_node": _context_node_payload(
                        prompt,
                        kind="runtime_context",
                    ),
                    "run_flow_node": flow_context.to_payload(),
                    "available_skill_names": _available_skill_names(prompt),
                    "available_tool_names": _available_tool_names(prompt),
                },
            ),
        )
        rendered = self._render_service.render_prompt_body(
            RenderContextPromptInput(
                session_key=session_key,
                run_id=run.id,
            ),
        )
        snapshot = self._render_service.record_render_snapshot(
            RecordContextRenderSnapshotInput(
                session_key=session_key,
                run_id=run.id,
                prompt_body=rendered.prompt_body,
                provider_attachments=_snapshot_provider_attachments(
                    rendered.provider_attachments,
                    prompt=prompt,
                ),
                estimate=rendered.estimate,
                included_node_ids=rendered.included_node_ids,
                mirrored_node_ids=rendered.mirrored_node_ids,
                metadata={
                    "parallel_recording": True,
                    "active_session_id": prompt.active_session_id,
                    "mode": prompt.mode.value,
                    "flow_context": flow_context.to_payload(),
                    "workspace_dir": prompt.workspace_dir,
                    "prompt_report": (
                        prompt.report.to_payload() if prompt.report is not None else None
                    ),
                },
            ),
        )
        return ContextRenderSnapshotRecord(
            snapshot_id=snapshot.id,
            prompt_body=rendered.prompt_body,
            estimate=rendered.estimate.to_payload(),
            included_node_ids=rendered.included_node_ids,
            mirrored_node_ids=rendered.mirrored_node_ids,
            tool_schemas=_mirrored_tool_schemas(
                rendered.provider_attachments,
                mirror_available=rendered.tool_schema_mirror_available,
            ),
            tool_schema_mirror_available=rendered.tool_schema_mirror_available,
            artifact_content_blocks=_artifact_content_blocks(
                rendered.provider_attachments,
                artifact_service=self._artifact_service,
            ),
        )


__all__ = ["ContextWorkspacePromptSnapshotAdapter"]


def _available_skill_names(prompt: PromptSurface) -> list[str]:
    catalog = prompt.skills_catalog
    if catalog is None:
        return []
    raw_names = catalog.metadata.get("available_skill_names")
    if not isinstance(raw_names, list):
        return []
    names: list[str] = []
    for item in raw_names:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if normalized and normalized not in names:
            names.append(normalized)
    return names


def _available_tool_names(prompt: PromptSurface) -> list[str]:
    return [
        schema.name
        for schema in prompt.tool_schemas
        if schema.name.strip()
    ]


def _snapshot_provider_attachments(
    rendered_attachments: dict[str, object],
    *,
    prompt: PromptSurface,
) -> dict[str, object]:
    payload = dict(rendered_attachments)
    payload["prompt_surface"] = {
        "llm_id": prompt.llm_id,
        "message_count": len(prompt.messages),
        "tool_schema_count": len(prompt.tool_schemas),
        "context_block_count": len(prompt.context_blocks),
    }
    return payload


def _context_node_payload(
    prompt: PromptSurface,
    *,
    kind: str,
) -> dict[str, object] | None:
    for block in prompt.context_blocks:
        if block.kind != kind:
            continue
        return {
            "summary": _summary_for_context_block(block.kind, block.metadata),
            "content": block.content,
            "metadata": {
                **dict(block.metadata),
                "kind": block.kind,
                "estimated_tokens": _estimate_text_tokens(block.content),
                "truncated": block.truncated,
            },
            "truncated": block.truncated,
        }
    return None


def _summary_for_context_block(
    kind: str,
    metadata: dict[str, object],
) -> str:
    if kind == "agent_instruction":
        return "Agent identity, role, and operating instructions."
    if kind == "runtime_context":
        agent_id = metadata.get("agent_id")
        llm_id = metadata.get("llm_id")
        if agent_id and llm_id:
            return f"Run context for agent '{agent_id}' using LLM '{llm_id}'."
        return "Current run runtime bindings and provider context."
    return "Prompt context block."


def _estimate_text_tokens(text: str) -> int:
    normalized = text or ""
    return max((len(normalized) + 3) // 4, 1) if normalized else 0


def _mirrored_tool_schemas(
    provider_attachments: dict[str, object],
    *,
    mirror_available: bool,
) -> tuple[ToolSchema, ...] | None:
    if not mirror_available:
        return None
    raw_schemas = provider_attachments.get("tool_schemas")
    if not isinstance(raw_schemas, list):
        return ()
    schemas: list[ToolSchema] = []
    for raw_schema in raw_schemas:
        if not isinstance(raw_schema, dict):
            continue
        name = raw_schema.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        input_schema = raw_schema.get("input_schema")
        schemas.append(
            ToolSchema(
                name=name,
                description=(
                    str(raw_schema.get("description"))
                    if raw_schema.get("description") is not None
                    else ""
                ),
                input_schema=(
                    dict(input_schema) if isinstance(input_schema, dict) else {}
                ),
            ),
        )
    return tuple(schemas)


_MAX_LLM_IMAGE_BYTES = 1_500_000
_MAX_LLM_FILE_BYTES = 4_000_000


def _artifact_content_blocks(
    provider_attachments: dict[str, object],
    *,
    artifact_service: object | None,
) -> tuple[dict[str, object], ...]:
    if artifact_service is None:
        return ()
    raw_candidates = provider_attachments.get("artifact_content_candidates")
    if not isinstance(raw_candidates, list):
        return ()
    blocks: list[dict[str, object]] = []
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, dict):
            continue
        artifact_id = raw_candidate.get("artifact_id")
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            continue
        variant = _artifact_variant(raw_candidate)
        try:
            resolved = artifact_service.resolve_variant(artifact_id, variant=variant)
        except Exception:  # noqa: BLE001
            continue
        try:
            raw_bytes = resolved.path.read_bytes()
        except OSError:
            continue
        artifact = resolved.artifact
        if str(raw_candidate.get("kind")) == "artifact_image":
            if len(raw_bytes) > _MAX_LLM_IMAGE_BYTES:
                continue
            blocks.append(
                {
                    "type": "image",
                    "mime_type": artifact.mime_type,
                    "data": base64.b64encode(raw_bytes).decode("ascii"),
                },
            )
            continue
        if len(raw_bytes) > _MAX_LLM_FILE_BYTES:
            continue
        block: dict[str, object] = {
            "type": "file",
            "mime_type": artifact.mime_type,
            "data": base64.b64encode(raw_bytes).decode("ascii"),
        }
        name = artifact.name or raw_candidate.get("name")
        if isinstance(name, str) and name.strip():
            block["name"] = name.strip()
        blocks.append(block)
    return tuple(blocks)


def _artifact_variant(candidate: dict[str, object]) -> ArtifactVariant:
    raw = candidate.get("preferred_variant")
    if not isinstance(raw, str) or not raw.strip():
        raw = "llm" if candidate.get("kind") == "artifact_image" else "original"
    try:
        return ArtifactVariant(raw.strip())
    except ValueError:
        return ArtifactVariant.ORIGINAL
