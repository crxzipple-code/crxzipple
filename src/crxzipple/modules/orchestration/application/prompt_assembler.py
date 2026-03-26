from __future__ import annotations

from dataclasses import dataclass, field

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
from crxzipple.modules.orchestration.application.ports import LlmPort, MemoryPort
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
from crxzipple.modules.orchestration.application.prompt_transcript import (
    build_prompt_transcript,
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
from crxzipple.modules.session.domain import SessionRuntimeBinding
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
    llm_port: LlmPort
    memory_port: MemoryPort | None
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
        llm_profile = self.llm_port.get_profile(llm_id)

        resolved_mode = self._resolve_prompt_mode(run, mode=mode)
        surface_policy = self._resolve_surface_policy(resolved_mode)
        prompt_flow_hint = self._prompt_flow_hint_payload(run)
        agent_home_dir = profile.runtime_preferences.resolved_home_dir
        workdir = profile.runtime_preferences.resolved_workdir
        context_files = load_workspace_context_files(agent_home_dir)
        recalled_memories = (
            recall_prompt_memories(
                self.memory_port,
                run=run,
            )
            if surface_policy.auto_recall_memories and self.memory_port is not None
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
        filtered_session_messages = tuple(
            message
            for message in session_messages
            if message.session_id == run.active_session_id
            and message.visibility is not SessionMessageVisibility.ARCHIVED
        )
        transcript = build_prompt_transcript(filtered_session_messages)
        llm_messages.extend(transcript.messages)
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

    def _memory_lookup_instruction(
        self,
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
        if self.memory_port is None:
            return None
        return self.memory_port.memory_lookup_instruction()

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
