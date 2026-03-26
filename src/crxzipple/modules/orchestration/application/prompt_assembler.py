from __future__ import annotations

import json
from dataclasses import dataclass, field

from crxzipple.modules.agent.application import AgentApplicationService
from crxzipple.modules.llm.application import LlmApplicationService
from crxzipple.modules.llm.domain import LlmMessage, LlmMessageRole, ToolSchema
from crxzipple.modules.memory.infrastructure import memory_lookup_instruction
from crxzipple.modules.memory.application import MemoryApplicationService
from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.application.memory_context import (
    RecalledMemory,
    recall_prompt_memories,
)
from crxzipple.modules.orchestration.application.prompting import (
    PromptMode,
    PromptReport,
    PromptReportBlock,
    RunSurfacePolicy,
    apply_system_prompt_budget,
    build_agent_instruction_block,
    build_memory_lookup_block,
    build_flow_prompt_block,
    build_recalled_memory_block,
    build_runtime_context_block,
    build_skills_catalog_block,
    build_workspace_context_block,
    estimate_text_tokens,
)
from crxzipple.modules.orchestration.application.skill_requests import SkillRequestSurface
from crxzipple.modules.orchestration.application.skills_context import (
    AvailableSkill,
    load_available_skills,
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
from crxzipple.modules.session.domain import SessionMessage, SessionRuntimeBinding
from crxzipple.modules.session.domain import SessionMessageVisibility


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
    available_skills: tuple[AvailableSkill, ...] = ()
    tool_schemas: tuple[ToolSchema, ...] = ()
    skill_request: SkillRequestSurface | None = None
    surface_policy: RunSurfacePolicy = field(default_factory=RunSurfacePolicy)


@dataclass(slots=True)
class PromptAssembler:
    agent_service: AgentApplicationService
    llm_service: LlmApplicationService
    memory_service: MemoryApplicationService
    session_service: SessionApplicationService
    system_prompt_max_chars: int = 120_000
    system_prompt_max_tokens: int = 30_000
    system_prompt_context_window_ratio: float = 0.15

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
        active_instance = self.session_service.get_instance(run.active_session_id)
        llm_id = self._resolve_llm_id(
            active_instance_metadata=active_instance.metadata,
            session_binding=session.runtime_binding(),
            default_llm_id=profile.llm_routing_policy.default_llm_id,
        )
        if not llm_id:
            raise OrchestrationValidationError(
                "Prompt assembly could not determine an llm_id.",
            )
        llm_profile = self.llm_service.get_profile(llm_id)

        resolved_mode = self._resolve_prompt_mode(run, mode=mode)
        surface_policy = self._resolve_surface_policy(resolved_mode)
        prompt_flow_hint = self._prompt_flow_hint_payload(run)
        agent_home_dir = profile.runtime_preferences.resolved_home_dir
        workdir = profile.runtime_preferences.resolved_workdir
        context_files = load_workspace_context_files(agent_home_dir)
        recalled_memories = (
            recall_prompt_memories(
                self.memory_service,
                run=run,
            )
            if surface_policy.auto_recall_memories
            else ()
        )
        available_skills = (
            ()
            if not (
                surface_policy.include_skills_catalog
                or surface_policy.include_skill_request_surface
            )
            else load_available_skills(agent_home_dir)
        )
        skill_request = (
            SkillRequestSurface(available_skills)
            if available_skills and surface_policy.include_skill_request_surface
            else None
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
                        llm_id=llm_id,
                        home_dir=agent_home_dir,
                        workdir=workdir,
                    ),
                    build_flow_prompt_block(
                        mode=resolved_mode,
                        hint_payload=prompt_flow_hint,
                    ),
                    build_workspace_context_block(
                        context_files,
                        home_dir=agent_home_dir,
                    ),
                    build_memory_lookup_block(
                        self._memory_lookup_instruction(
                            resolved_tools,
                            include_guidance=surface_policy.include_memory_lookup_guidance,
                        )
                    ),
                    build_recalled_memory_block(recalled_memories),
                    build_skills_catalog_block(
                        available_skills
                        if surface_policy.include_skills_catalog
                        else ()
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

        session_messages = self.session_service.list_messages(
            ListSessionMessagesInput(
                session_key=session_key,
                active_session_only=True,
            ),
        )
        filtered_session_messages = self._filter_transcript_messages(
            tuple(
                message
                for message in session_messages
                if message.session_id == run.active_session_id
                and message.visibility is not SessionMessageVisibility.ARCHIVED
            ),
        )
        transcript_messages = tuple(
            self._to_llm_message(message)
            for message in filtered_session_messages
        )
        llm_messages.extend(transcript_messages)
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
            transcript_message_count=len(transcript_messages),
            transcript_chars=sum(
                self._message_content_chars(message.content)
                for message in transcript_messages
            ),
            transcript_estimated_tokens=sum(
                self._message_content_tokens(message.content)
                for message in transcript_messages
            ),
        )
        tool_schemas = (
            (
                resolved_tools.schemas
                if resolved_tools is not None and surface_policy.include_tool_schemas
                else ()
            )
            + ((skill_request.schema,) if skill_request is not None else ())
        )

        return PromptEnvelope(
            llm_id=llm_id,
            session_key=session_key,
            active_session_id=run.active_session_id,
            messages=tuple(llm_messages),
            mode=resolved_mode,
            report=report,
            workspace_dir=agent_home_dir,
            context_files=context_files,
            recalled_memories=recalled_memories,
            available_skills=available_skills,
            tool_schemas=tool_schemas,
            skill_request=skill_request,
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
        maintenance_mode = mode in {
            PromptMode.COMPACTION,
            PromptMode.HEARTBEAT,
            PromptMode.MEMORY_FLUSH,
        }
        return RunSurfacePolicy(
            auto_recall_memories=mode in {
                PromptMode.SESSION_START,
            },
            include_memory_lookup_guidance=not maintenance_mode,
            include_skills_catalog=not maintenance_mode,
            include_skill_request_surface=not maintenance_mode,
            include_tool_schemas=not maintenance_mode,
        )

    @staticmethod
    def _memory_lookup_instruction(
        resolved_tools: ResolvedToolSet | None,
        *,
        include_guidance: bool,
    ) -> str | None:
        if not include_guidance or resolved_tools is None:
            return None
        if not (
            resolved_tools.by_name("memory_search") is not None
            and resolved_tools.by_name("memory_get") is not None
        ):
            return None
        return memory_lookup_instruction()

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
    def _resolve_llm_id(
        *,
        active_instance_metadata: dict[str, object],
        session_binding: SessionRuntimeBinding,
        default_llm_id: str | None,
    ) -> str:
        for candidate in (
            SessionRuntimeBinding.from_payload(active_instance_metadata).llm_id,
            session_binding.llm_id,
            (default_llm_id or "").strip() or None,
        ):
            if candidate:
                return candidate
        return ""

    @staticmethod
    def _to_llm_message(message: SessionMessage) -> LlmMessage:
        try:
            role = LlmMessageRole(message.role)
        except ValueError:
            role = LlmMessageRole.USER
        tool_call_id = message.metadata.get("tool_call_id")
        if not isinstance(tool_call_id, str) or not tool_call_id.strip():
            tool_call_id = None
        tool_name = message.metadata.get("tool_name")
        if not isinstance(tool_name, str) or not tool_name.strip():
            payload_tool_name = message.content_payload.get("tool_name")
            if isinstance(payload_tool_name, str) and payload_tool_name.strip():
                tool_name = payload_tool_name.strip()
            else:
                tool_name = None
        metadata = {
            "session_message_id": message.id,
            "kind": message.kind.value,
            "source_kind": message.source_kind,
            "source_id": message.source_id,
        }
        if tool_name is not None:
            metadata["tool_name"] = tool_name
        return LlmMessage(
            role=role,
            content=PromptAssembler._extract_content(message, role=role),
            name=tool_name,
            tool_call_id=tool_call_id,
            metadata=metadata,
        )

    @staticmethod
    def _extract_content(
        message: SessionMessage,
        *,
        role: LlmMessageRole,
    ) -> object:
        if message.content is not None and message.content.strip():
            return message.content
        if (
            role is LlmMessageRole.ASSISTANT
            and message.content_payload.get("type") == "function_call"
        ):
            return dict(message.content_payload)
        text_content = message.content_payload.get("text")
        if isinstance(text_content, str) and text_content.strip():
            return text_content
        return json.dumps(
            message.content_payload,
            ensure_ascii=True,
            sort_keys=True,
        )

    @staticmethod
    def _message_content_chars(content: object) -> int:
        if isinstance(content, str):
            return len(content)
        return len(
            json.dumps(
                content,
                ensure_ascii=True,
                sort_keys=True,
            ),
        )

    @staticmethod
    def _message_content_tokens(content: object) -> int:
        if isinstance(content, str):
            return estimate_text_tokens(content)
        return estimate_text_tokens(
            json.dumps(
                content,
                ensure_ascii=True,
                sort_keys=True,
            ),
        )

    @staticmethod
    def _filter_transcript_messages(
        messages: tuple[SessionMessage, ...],
    ) -> tuple[SessionMessage, ...]:
        completed_tool_call_ids = {
            tool_call_id.strip()
            for message in messages
            if message.role == "tool"
            for tool_call_id in (message.metadata.get("tool_call_id"),)
            if isinstance(tool_call_id, str) and tool_call_id.strip()
        }
        filtered: list[SessionMessage] = []
        for message in messages:
            is_function_call = (
                message.role == "assistant"
                and message.content_payload.get("type") == "function_call"
            )
            if not is_function_call:
                filtered.append(message)
                continue
            tool_call_id = message.metadata.get("tool_call_id")
            if (
                isinstance(tool_call_id, str)
                and tool_call_id.strip()
                and tool_call_id.strip() in completed_tool_call_ids
            ):
                filtered.append(message)
        return tuple(filtered)

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
