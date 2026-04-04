from __future__ import annotations

import base64
from dataclasses import dataclass, field, replace

from crxzipple.modules.artifacts.application.services import ArtifactApplicationService
from crxzipple.modules.artifacts.domain.entities import ArtifactVariant
from crxzipple.modules.agent.application import AgentApplicationService
from crxzipple.modules.llm.domain import LlmMessage, LlmMessageRole, ToolSchema
from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.application.memory_context import (
    RecalledMemory,
    recall_prompt_memories,
)
from crxzipple.modules.orchestration.application.llm_resolver import (
    LlmResolver,
    normalize_requested_llm_id,
)
from crxzipple.modules.orchestration.application.ports import LlmPort, MemoryPort
from crxzipple.modules.orchestration.application.ports.skill import SkillCatalogPort
from crxzipple.modules.orchestration.application.prompting import (
    PromptMode,
    PromptReport,
    PromptReportBlock,
    RunSurfacePolicy,
    apply_system_prompt_budget,
    build_agent_instruction_block,
    build_flow_prompt_block,
    build_recalled_memory_block,
    build_runtime_context_block,
    build_skills_catalog_block,
    build_workspace_context_block,
    estimate_text_tokens,
    resolve_run_surface_policy,
)
from crxzipple.modules.orchestration.application.prompt_transcript import (
    build_prompt_transcript,
)
from crxzipple.modules.orchestration.application.tool_resolver import ResolvedToolSet
from crxzipple.modules.orchestration.application.workspace_context import (
    PromptContextFile,
    load_workspace_context_files,
)
from crxzipple.modules.session.application import (
    ListSessionMessagesInput,
    SessionApplicationService,
)
from crxzipple.modules.session.domain import SessionRuntimeBinding
from crxzipple.modules.session.domain import SessionMessageVisibility
from crxzipple.modules.skills.application import SkillCatalogPrompt
from crxzipple.shared.content_blocks import (
    FILE_REF_BLOCK_TYPE,
    IMAGE_REF_BLOCK_TYPE,
    normalize_content_blocks,
    text_content_block,
)


@dataclass(frozen=True, slots=True)
class PromptEnvelope:
    llm_id: str
    session_key: str
    active_session_id: str
    messages: tuple[LlmMessage, ...]
    mode: PromptMode = PromptMode.NORMAL_TURN
    report: PromptReport | None = None
    workspace_dir: str | None = None
    context_files: tuple[PromptContextFile, ...] = ()
    recalled_memories: tuple[RecalledMemory, ...] = ()
    skills_catalog: SkillCatalogPrompt | None = None
    tool_schemas: tuple[ToolSchema, ...] = ()
    surface_policy: RunSurfacePolicy = field(default_factory=RunSurfacePolicy)


@dataclass(slots=True)
class PromptAssembler:
    agent_service: AgentApplicationService
    llm_port: LlmPort
    memory_port: MemoryPort | None
    skill_catalog_port: SkillCatalogPort
    session_service: SessionApplicationService
    artifact_service: ArtifactApplicationService | None = None
    llm_resolver: LlmResolver | None = None
    system_prompt_max_chars: int = 120_000
    system_prompt_max_tokens: int = 30_000
    system_prompt_context_window_ratio: float = 0.15
    memory_flush_transcript_max_chars: int = 120_000
    llm_image_max_bytes: int = ArtifactApplicationService.DEFAULT_LLM_IMAGE_MAX_BYTES
    llm_file_max_bytes: int = 4_000_000
    llm_text_file_max_chars: int = 20_000

    def assemble(
        self,
        run: OrchestrationRun,
        *,
        resolved_tools: ResolvedToolSet | None = None,
        mode: PromptMode | None = None,
    ) -> PromptEnvelope:
        if run.agent_id is None or not run.agent_id.strip():
            raise OrchestrationValidationError(
                "Orchestration run agent_id is required for prompt assembly.",
            )
        if run.active_session_id is None or not run.active_session_id.strip():
            raise OrchestrationValidationError(
                "Orchestration run active_session_id is required for prompt assembly.",
            )

        session_key = str(run.metadata.get("session_key", "")).strip()
        if not session_key:
            raise OrchestrationValidationError(
                "Orchestration run metadata.session_key is required for prompt assembly.",
            )

        profile = self.agent_service.get_profile(run.agent_id)
        session = self.session_service.get_session(session_key)
        session_binding = session.runtime_binding()
        requested_llm_id = self._resolve_requested_llm_id(
            run_metadata=run.metadata,
            routing_policy=profile.llm_routing_policy,
        )
        resolved_mode = self._resolve_prompt_mode(run, mode=mode)

        session_messages = self.session_service.list_messages(
            ListSessionMessagesInput(
                session_key=session_key,
                active_session_only=True,
            ),
        )
        filtered_session_messages = tuple(
            message
            for message in session_messages
                if message.session_id == run.active_session_id
            and message.visibility is not SessionMessageVisibility.ARCHIVED
        )
        transcript = build_prompt_transcript(
            filtered_session_messages,
            max_chars=self._transcript_max_chars_for_mode(resolved_mode),
        )
        llm_transcript_messages = self._materialize_artifact_refs(transcript.messages)
        llm_selection = self._resolver().resolve(
            requested_llm_id=requested_llm_id,
            routing_policy=profile.llm_routing_policy,
            input_content=_routing_input_content_from_transcript(llm_transcript_messages),
        )
        llm_profile = self.llm_port.get_profile(llm_selection.resolved_llm_id)
        surface_policy = self._resolve_surface_policy(resolved_mode)
        prompt_flow_hint = self._prompt_flow_hint_payload(run)
        agent_home_dir = profile.runtime_preferences.resolved_home_dir
        workspace_dir = self._resolve_workspace_dir(
            session_binding=session_binding,
            profile=profile,
        )
        context_files = load_workspace_context_files(workspace_dir)
        recalled_memories = (
            recall_prompt_memories(
                self.memory_port,
                run=run,
            )
            if surface_policy.auto_recall_memories and self.memory_port is not None
            else ()
        )
        skills_catalog = (
            None
            if not surface_policy.include_skills_catalog
            else self.skill_catalog_port.build_prompt_catalog(
                workspace_dir=workspace_dir,
                surface=surface_policy.surface,
            )
        )
        effective_system_max_tokens, system_budget_source = self._resolve_system_prompt_budget(
            llm_profile.context_window_tokens,
        )
        effective_system_max_chars = min(
            self.system_prompt_max_chars,
            max(1, effective_system_max_tokens * 4),
        )
        system_blocks = apply_system_prompt_budget(
            tuple(
                block
                for block in (
                    build_agent_instruction_block(
                        profile.instruction_policy.system_prompt,
                    ),
                    build_runtime_context_block(
                        run,
                        llm_id=llm_selection.resolved_llm_id,
                        home_dir=agent_home_dir,
                        workspace_dir=workspace_dir,
                    ),
                    build_flow_prompt_block(
                        mode=resolved_mode,
                        hint_payload=prompt_flow_hint,
                    ),
                    build_workspace_context_block(
                        context_files,
                        home_dir=agent_home_dir,
                        workspace_dir=workspace_dir,
                    ),
                    build_recalled_memory_block(recalled_memories),
                    build_skills_catalog_block(
                        skills_catalog if surface_policy.include_skills_catalog else None
                    ),
                )
                if block is not None
            ),
            mode=resolved_mode,
            total_max_chars=effective_system_max_chars,
            total_max_tokens=effective_system_max_tokens,
        )
        llm_messages: list[LlmMessage] = [
            LlmMessage(
                role=LlmMessageRole.SYSTEM,
                content=block.content,
            )
            for block in system_blocks
        ]
        llm_messages.extend(llm_transcript_messages)
        if not llm_messages:
            raise OrchestrationValidationError(
                "Prompt assembly requires at least one llm message.",
            )
        system_chars = sum(len(block.content) for block in system_blocks)
        system_estimated_tokens = sum(
            estimate_text_tokens(block.content)
            for block in system_blocks
        )
        report = PromptReport(
            mode=resolved_mode,
            system_blocks=tuple(
                PromptReportBlock(
                    kind=block.kind,
                    chars=len(block.content),
                    estimated_tokens=estimate_text_tokens(block.content),
                    metadata=dict(block.metadata),
                    truncated=block.truncated,
                    policy=block.policy,
                )
                for block in system_blocks
            ),
            system_budget_source=system_budget_source,
            system_budget_chars=effective_system_max_chars,
            system_budget_estimated_tokens=effective_system_max_tokens,
            llm_context_window_tokens=llm_profile.context_window_tokens,
            system_chars=system_chars,
            system_estimated_tokens=system_estimated_tokens,
            transcript_message_count=transcript.message_count,
            transcript_chars=transcript.chars,
            transcript_estimated_tokens=transcript.estimated_tokens,
        )
        tool_schemas = (
            resolved_tools.schemas
            if resolved_tools is not None and surface_policy.include_tool_schemas
            else ()
        )

        return PromptEnvelope(
            llm_id=llm_selection.resolved_llm_id,
            session_key=session_key,
            active_session_id=run.active_session_id,
            messages=tuple(llm_messages),
            mode=resolved_mode,
            report=report,
            workspace_dir=workspace_dir,
            context_files=context_files,
            recalled_memories=recalled_memories,
            skills_catalog=skills_catalog,
            tool_schemas=tool_schemas,
            surface_policy=surface_policy,
        )

    def resolve_mode(
        self,
        run: OrchestrationRun,
        *,
        mode: PromptMode | None = None,
    ) -> PromptMode:
        return self._resolve_prompt_mode(run, mode=mode)

    @staticmethod
    def _resolve_surface_policy(mode: PromptMode) -> RunSurfacePolicy:
        return resolve_run_surface_policy(mode)

    def _transcript_max_chars_for_mode(self, mode: PromptMode) -> int | None:
        if mode is PromptMode.MEMORY_FLUSH:
            return self.memory_flush_transcript_max_chars
        return None

    def _resolve_system_prompt_budget(
        self,
        context_window_tokens: int | None,
    ) -> tuple[int, str]:
        if context_window_tokens is None or context_window_tokens <= 0:
            return self.system_prompt_max_tokens, "fixed"
        dynamic_budget = max(
            256,
            int(context_window_tokens * self.system_prompt_context_window_ratio),
        )
        effective_budget = min(
            self.system_prompt_max_tokens,
            dynamic_budget,
            context_window_tokens,
        )
        budget_source = (
            "context_window_scaled"
            if effective_budget < self.system_prompt_max_tokens
            else "fixed"
        )
        return effective_budget, budget_source

    @staticmethod
    def _resolve_requested_llm_id(
        *,
        run_metadata: dict[str, object],
        routing_policy,
    ) -> str:
        requested_llm_id = (
            str(run_metadata.get("requested_llm_id", "")).strip() or None
            if run_metadata.get("requested_llm_id") is not None
            else None
        )
        return normalize_requested_llm_id(
            requested_llm_id=requested_llm_id,
            routing_policy=routing_policy,
        )

    def _resolver(self) -> LlmResolver:
        if self.llm_resolver is not None:
            return self.llm_resolver
        self.llm_resolver = LlmResolver(self.llm_port)
        return self.llm_resolver

    def _materialize_artifact_refs(
        self,
        messages: tuple[LlmMessage, ...],
    ) -> tuple[LlmMessage, ...]:
        if self.artifact_service is None:
            return messages
        materialized: list[LlmMessage] = []
        for message in messages:
            if (
                isinstance(message.content, dict)
                and message.content.get("type") == "function_call"
            ):
                materialized.append(message)
                continue
            try:
                blocks = normalize_content_blocks(message.content)
            except ValueError:
                materialized.append(message)
                continue
            if not any(
                block.get("type") in {IMAGE_REF_BLOCK_TYPE, FILE_REF_BLOCK_TYPE}
                for block in blocks
            ):
                materialized.append(message)
                continue
            materialized.append(
                replace(
                    message,
                    content=self._materialize_artifact_blocks(blocks),
                ),
            )
        return tuple(materialized)

    def _materialize_artifact_blocks(
        self,
        blocks: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        materialized: list[dict[str, object]] = []
        for block in blocks:
            block_type = str(block.get("type") or "").strip()
            if block_type == IMAGE_REF_BLOCK_TYPE:
                materialized.append(self._materialize_image_ref_block(block))
                continue
            if block_type == FILE_REF_BLOCK_TYPE:
                materialized.append(self._materialize_file_ref_block(block))
                continue
            materialized.append(dict(block))
        return materialized

    def _materialize_image_ref_block(
        self,
        block: dict[str, object],
    ) -> dict[str, object]:
        artifact_id = str(block.get("artifact_id") or "").strip()
        mime_type = str(block.get("mime_type") or "").strip()
        if not artifact_id or not mime_type or self.artifact_service is None:
            return text_content_block("[missing image attachment]")
        try:
            resolved = self.artifact_service.resolve_variant(
                artifact_id,
                variant=ArtifactVariant.LLM,
            )
        except Exception:  # noqa: BLE001
            return text_content_block(f"[missing image attachment:{artifact_id}]")
        raw_bytes = resolved.path.read_bytes()
        if len(raw_bytes) > self.llm_image_max_bytes:
            name = block.get("name")
            label = f":{name.strip()}" if isinstance(name, str) and name.strip() else ""
            return text_content_block(
                f"[image attachment omitted - exceeds llm size budget{label}]",
            )
        return {
            "type": "image",
            "mime_type": mime_type,
            "data": base64.b64encode(raw_bytes).decode("ascii"),
        }

    def _materialize_file_ref_block(
        self,
        block: dict[str, object],
    ) -> dict[str, object]:
        artifact_id = str(block.get("artifact_id") or "").strip()
        mime_type = str(block.get("mime_type") or "").strip()
        if not artifact_id or not mime_type or self.artifact_service is None:
            return text_content_block("[missing file attachment]")
        try:
            resolved = self.artifact_service.resolve_variant(
                artifact_id,
                variant=ArtifactVariant.LLM,
            )
        except Exception:  # noqa: BLE001
            return text_content_block(f"[missing file attachment:{artifact_id}]")
        raw_bytes = resolved.path.read_bytes()
        name = block.get("name")
        normalized_name = name.strip() if isinstance(name, str) and name.strip() else None
        if _is_text_like_file_mime_type(mime_type):
            decoded = raw_bytes.decode("utf-8", errors="replace")
            if len(decoded) > self.llm_text_file_max_chars:
                decoded = (
                    decoded[: self.llm_text_file_max_chars].rstrip()
                    + "\n\n[file truncated for llm budget]"
                )
            header = f"[file:{normalized_name}]\n" if normalized_name is not None else "[file]\n"
            return text_content_block(f"{header}{decoded}")
        if len(raw_bytes) > self.llm_file_max_bytes:
            label = f":{normalized_name}" if normalized_name is not None else ""
            return text_content_block(
                f"[file attachment omitted - exceeds llm size budget{label}]",
            )
        materialized = {
            "type": "file",
            "mime_type": mime_type,
            "data": base64.b64encode(raw_bytes).decode("ascii"),
        }
        if normalized_name is not None:
            materialized["name"] = normalized_name
        return materialized

    @staticmethod
    def _resolve_prompt_mode(
        run: OrchestrationRun,
        *,
        mode: PromptMode | None,
    ) -> PromptMode:
        if mode is not None:
            return mode
        hint_payload = PromptAssembler._prompt_flow_hint_payload(run)
        raw_mode = hint_payload.get("mode")
        if isinstance(raw_mode, str) and raw_mode.strip():
            try:
                return PromptMode(raw_mode.strip())
            except ValueError:
                pass
        return PromptMode.NORMAL_TURN

    @staticmethod
    def _prompt_flow_hint_payload(run: OrchestrationRun) -> dict[str, object]:
        raw_hint = run.metadata.get("prompt_flow_hint")
        if not isinstance(raw_hint, dict):
            return {}
        return dict(raw_hint)

    @staticmethod
    def _resolve_workspace_dir(
        *,
        session_binding: SessionRuntimeBinding,
        profile,
    ) -> str | None:
        for candidate in (
            session_binding.workspace,
            profile.runtime_preferences.resolved_home_dir,
        ):
            if candidate is not None and candidate.strip():
                return candidate.strip()
        return None


def _routing_input_content_from_transcript(
    messages: tuple[LlmMessage, ...],
) -> dict[str, object] | None:
    blocks: list[dict[str, object]] = []
    for message in messages:
        try:
            normalized_blocks = normalize_content_blocks(message.content)
        except ValueError:
            continue
        blocks.extend(normalized_blocks)
    if not blocks:
        return None
    return {"blocks": blocks}


def _is_text_like_file_mime_type(mime_type: str) -> bool:
    normalized = mime_type.strip().lower()
    return normalized in {
        "text/plain",
        "text/markdown",
        "application/json",
    }
