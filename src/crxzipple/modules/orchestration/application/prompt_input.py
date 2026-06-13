from __future__ import annotations

import base64
from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from typing import Protocol

from crxzipple.modules.artifacts.domain.entities import ArtifactVariant
from crxzipple.modules.llm.domain import (
    LlmCapability,
    LlmMessage,
    LlmMessageRole,
    LlmProfile,
    ToolSchema,
)
from crxzipple.modules.orchestration.domain import (
    ExecutionStepItemKind,
    ExecutionStepItemStatus,
    OrchestrationRun,
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.application.llm_resolver import (
    LlmResolver,
    is_auto_llm_id,
    normalize_requested_llm_id,
)
from crxzipple.modules.orchestration.application.ports import (
    AccessReadinessPort,
    AgentProfileCatalogPort,
    ArtifactVariantReadPort,
    EventPublishPort,
    LlmPort,
    SessionTranscriptPort,
)
from crxzipple.modules.orchestration.application.ports.skill import SkillCatalogPort
from crxzipple.modules.orchestration.application.prompting import (
    PromptBlock,
    PromptMode,
    PromptReport,
    PromptReportBlock,
    RunSurfacePolicy,
    apply_system_prompt_budget,
    build_agent_instruction_block,
    build_runtime_context_block,
    estimate_text_tokens,
    resolve_run_surface_policy,
)
from crxzipple.modules.orchestration.application.prompt_transcript import (
    PromptTranscript,
    build_model_visible_session_item_prompt_window,
)
from crxzipple.modules.orchestration.application.tool_resolver import ResolvedToolSet
from crxzipple.modules.session.application import (
    ListSessionItemsInput,
)
from crxzipple.modules.session.domain import SessionItem
from crxzipple.modules.session.domain import SessionRuntimeBinding
from crxzipple.modules.skills.application import (
    SKILL_RESOLUTION_COMPLETED_EVENT,
    SkillCatalogPrompt,
    skill_event_from_payload,
)
from crxzipple.shared.content_blocks import (
    FILE_REF_BLOCK_TYPE,
    IMAGE_REF_BLOCK_TYPE,
    content_blocks_from_payload,
    describe_content_for_text_fallback,
    extract_text_content,
    normalize_content_blocks,
    text_content_block,
)
from crxzipple.shared.domain.events import Event
from crxzipple.shared.runtime_metrics import (
    RuntimeMetricsRegistry,
    get_runtime_metrics_registry,
)

DEFAULT_LLM_IMAGE_MAX_BYTES = 1_500_000


def _available_tool_ids(resolved_tools: ResolvedToolSet | None) -> tuple[str, ...]:
    if resolved_tools is None:
        return ()
    return tuple(item.tool.id for item in resolved_tools.tools)


class ExecutionContinuationQueryPort(Protocol):
    def list_execution_chains(self, turn_id: str) -> list[object]:
        ...

    def list_execution_steps(self, chain_id: str) -> list[object]:
        ...

    def list_execution_step_items(self, step_id: str) -> list[object]:
        ...


@dataclass(frozen=True, slots=True)
class RunPromptInput:
    llm_id: str
    session_key: str
    active_session_id: str
    messages: tuple[LlmMessage, ...]
    llm_capabilities: tuple[LlmCapability, ...] = ()
    runtime_llm_defaults: dict[str, object] = field(default_factory=dict)
    llm_defaults: dict[str, object] = field(default_factory=dict)
    llm_policy: dict[str, object] = field(default_factory=dict)
    mode: PromptMode = PromptMode.NORMAL_TURN
    report: PromptReport | None = None
    context_blocks: tuple[PromptBlock, ...] = ()
    workspace_dir: str | None = None
    skills_catalog: SkillCatalogPrompt | None = None
    tool_schemas: tuple[ToolSchema, ...] = ()
    flow_hint: dict[str, object] = field(default_factory=dict)
    surface_policy: RunSurfacePolicy = field(default_factory=RunSurfacePolicy)


@dataclass(slots=True)
class RunPromptInputCollector:
    """Collects run inputs for Context Workspace and provider invocation.

    This collector does not render the final prompt body. Context Workspace owns
    the tree render and provider attachment mirror; this object only gathers
    transcript messages, routing, context blocks, and the initially resolved
    tool surface needed by that render step.
    """

    agent_service: AgentProfileCatalogPort
    llm_port: LlmPort
    skill_catalog_port: SkillCatalogPort
    session_service: SessionTranscriptPort
    artifact_service: ArtifactVariantReadPort | None = None
    access_port: AccessReadinessPort | None = None
    events_service: EventPublishPort | None = None
    llm_resolver: LlmResolver | None = None
    execution_query: ExecutionContinuationQueryPort | None = None
    context_block_max_chars: int = 120_000
    context_block_max_tokens: int = 30_000
    context_block_context_window_ratio: float = 0.15
    session_item_transcript_max_chars: int = 120_000
    memory_flush_transcript_max_chars: int = 120_000
    llm_image_max_bytes: int = DEFAULT_LLM_IMAGE_MAX_BYTES
    llm_file_max_bytes: int = 4_000_000
    llm_text_file_max_chars: int = 20_000
    runtime_llm_defaults: dict[str, object] = field(default_factory=dict)
    detailed_phase_metrics_enabled: bool = False
    metrics: RuntimeMetricsRegistry = field(
        default_factory=get_runtime_metrics_registry,
    )

    def build(
        self,
        run: OrchestrationRun,
        *,
        resolved_tools: ResolvedToolSet | None = None,
        mode: PromptMode | None = None,
    ) -> RunPromptInput:
        if run.agent_id is None or not run.agent_id.strip():
            raise OrchestrationValidationError(
                "Orchestration run agent_id is required for prompt input collection.",
            )
        if run.active_session_id is None or not run.active_session_id.strip():
            raise OrchestrationValidationError(
                "Orchestration run active_session_id is required for prompt input collection.",
            )

        session_key = str(run.metadata.get("session_key", "")).strip()
        if not session_key:
            raise OrchestrationValidationError(
                "Orchestration run metadata.session_key is required for prompt input collection.",
            )

        with self._timed_phase("profile_read"):
            profile = self.agent_service.get_profile(run.agent_id)
        resolved_mode = self._resolve_prompt_mode(run, mode=mode)
        with self._timed_phase("session_bundle_read"):
            session_item_bundle = self.session_service.get_session_with_items(
                ListSessionItemsInput(
                    session_key=session_key,
                    active_session_only=True,
                    model_visible=True,
                ),
            )
        session = session_item_bundle.session
        session_binding = session.runtime_binding()
        agent_home_dir = profile.runtime_preferences.resolved_home_dir
        workspace_dir = self._resolve_workspace_dir(
            session_binding=session_binding,
            profile=profile,
        )
        requested_llm_id = self._resolve_requested_llm_id(
            run_metadata=run.metadata,
            routing_policy=profile.llm_routing_policy,
        )

        with self._timed_phase("transcript_build"):
            filtered_session_items = tuple(
                item
                for item in session_item_bundle.items
                if item.session_id == run.active_session_id
                and item.visibility.model_visible
            )
            transcript = self._build_provider_input_transcript(
                run,
                session_items=filtered_session_items,
                mode=resolved_mode,
            )
        with self._timed_phase("llm_resolve"):
            routing_input_content = (
                _routing_input_content(
                    transcript_messages=transcript.messages,
                    session_items=filtered_session_items,
                )
                if is_auto_llm_id(requested_llm_id)
                else None
            )
            try:
                llm_selection = self._resolver().resolve(
                    requested_llm_id=requested_llm_id,
                    routing_policy=profile.llm_routing_policy,
                    input_content=routing_input_content,
                    workspace_dir=workspace_dir,
                )
            except Exception as exc:
                self._publish_llm_resolution_event(
                    run,
                    session_key=session_key,
                    requested_llm_id=requested_llm_id,
                    resolved_llm_id=None,
                    strategy="unresolved",
                    input_has_image=False,
                    input_has_file=False,
                    status="failed",
                    reason=str(exc),
                )
                raise
            llm_profile = self.llm_port.get_profile(llm_selection.resolved_llm_id)
            self._publish_llm_resolution_event(
                run,
                session_key=session_key,
                requested_llm_id=llm_selection.requested_llm_id,
                resolved_llm_id=llm_selection.resolved_llm_id,
                strategy=llm_selection.strategy,
                input_has_image=llm_selection.input_has_image,
                input_has_file=llm_selection.input_has_file,
                status="resolved",
                profile=llm_profile,
            )
            llm_transcript_messages = self._materialize_artifact_refs(
                transcript.messages,
                allow_vision=LlmCapability.VISION_INPUT in llm_profile.capabilities,
            )
        surface_policy = self._resolve_surface_policy(resolved_mode)
        prompt_flow_hint = self._prompt_flow_hint_payload(run)
        with self._timed_phase("skills_catalog_build"):
            if not surface_policy.include_skills_catalog:
                skills_catalog = None
            else:
                resolved_skill_catalog = self.skill_catalog_port.resolve_prompt_catalog(
                    workspace_dir=workspace_dir,
                    surface=surface_policy.surface,
                    available_tool_ids=_available_tool_ids(resolved_tools),
                    interface=run.inbound_instruction.source,
                    agent_id=run.agent_id,
                    run_id=run.id,
                    session_key=session_key,
                    active_session_id=run.active_session_id,
                )
                self._publish_skill_resolution_event(
                    run=run,
                    session_key=session_key,
                    workspace_dir=workspace_dir,
                    surface=surface_policy.surface,
                    resolved_skill_catalog=resolved_skill_catalog,
                )
                skills_catalog = resolved_skill_catalog.prompt_catalog
        with self._timed_phase("context_blocks_build"):
            effective_context_max_tokens, context_budget_source = (
                self._resolve_context_block_budget(
                    llm_profile.context_window_tokens,
                )
            )
            effective_context_max_chars = min(
                self.context_block_max_chars,
                max(1, effective_context_max_tokens * 4),
            )
            context_blocks = apply_system_prompt_budget(
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
                            available_tool_ids=_available_tool_ids(resolved_tools),
                        ),
                    )
                    if block is not None
                ),
                mode=resolved_mode,
                total_max_chars=effective_context_max_chars,
                total_max_tokens=effective_context_max_tokens,
            )
        llm_messages: list[LlmMessage] = list(llm_transcript_messages)
        if not llm_messages and not context_blocks:
            raise OrchestrationValidationError(
                "Prompt input collection requires at least one llm message or context block.",
            )
        with self._timed_phase("prompt_report_build"):
            context_chars = sum(len(block.content) for block in context_blocks)
            context_estimated_tokens = sum(
                estimate_text_tokens(block.content)
                for block in context_blocks
            )
            transcript_budget = _transcript_budget_with_execution_chain_refs(
                dict(transcript.budget),
                execution_query=self.execution_query,
                turn_id=run.id,
            )
            report = PromptReport(
                mode=resolved_mode,
                context_blocks=tuple(
                    PromptReportBlock(
                        kind=block.kind,
                        chars=len(block.content),
                        estimated_tokens=estimate_text_tokens(block.content),
                        metadata=dict(block.metadata),
                        truncated=block.truncated,
                        policy=block.policy,
                    )
                    for block in context_blocks
                ),
                context_budget_source=context_budget_source,
                context_budget_chars=effective_context_max_chars,
                context_budget_estimated_tokens=effective_context_max_tokens,
                llm_context_window_tokens=llm_profile.context_window_tokens,
                context_chars=context_chars,
                context_estimated_tokens=context_estimated_tokens,
                transcript_message_count=transcript.message_count,
                transcript_chars=transcript.chars,
                transcript_estimated_tokens=transcript.estimated_tokens,
                transcript_tool_result_stats=dict(transcript.tool_result_stats),
                transcript_budget=transcript_budget,
            )
        tool_schemas = (
            resolved_tools.schemas
            if self._should_include_tool_schemas(
                run,
                resolved_mode=resolved_mode,
                surface_policy=surface_policy,
                resolved_tools=resolved_tools,
                transcript_messages=tuple(llm_transcript_messages),
            )
            else ()
        )

        return RunPromptInput(
            llm_id=llm_selection.resolved_llm_id,
            llm_capabilities=tuple(llm_profile.capabilities),
            runtime_llm_defaults=dict(self.runtime_llm_defaults),
            llm_defaults=llm_profile.default_params.to_payload(),
            llm_policy=profile.llm_policy.to_payload(),
            session_key=session_key,
            active_session_id=run.active_session_id,
            messages=tuple(llm_messages),
            mode=resolved_mode,
            report=report,
            context_blocks=context_blocks,
            workspace_dir=workspace_dir,
            skills_catalog=skills_catalog,
            tool_schemas=tool_schemas,
            flow_hint=prompt_flow_hint,
            surface_policy=surface_policy,
        )

    @staticmethod
    def _should_include_tool_schemas(
        run: OrchestrationRun,
        *,
        resolved_mode: PromptMode,
        surface_policy: RunSurfacePolicy,
        resolved_tools: ResolvedToolSet | None,
        transcript_messages: tuple[LlmMessage, ...],
    ) -> bool:
        if resolved_tools is None or not resolved_tools.tools:
            return False
        if not surface_policy.include_tool_schemas:
            return False
        return True

    def resolve_mode(
        self,
        run: OrchestrationRun,
        *,
        mode: PromptMode | None = None,
    ) -> PromptMode:
        return self._resolve_prompt_mode(run, mode=mode)

    def _timed_phase(self, phase: str):
        if not self.detailed_phase_metrics_enabled:
            return nullcontext()
        return self.metrics.timed(
            "orchestration.prompt_inputs.phase_seconds",
            labels={"phase": phase},
        )

    @staticmethod
    def _resolve_surface_policy(mode: PromptMode) -> RunSurfacePolicy:
        return resolve_run_surface_policy(mode)

    def _build_provider_input_transcript(
        self,
        run: OrchestrationRun,
        *,
        session_items: tuple[SessionItem, ...] = (),
        mode: PromptMode,
    ) -> PromptTranscript:
        if mode is PromptMode.MEMORY_FLUSH:
            return build_model_visible_session_item_prompt_window(
                session_items,
                max_chars=self.memory_flush_transcript_max_chars,
                include_non_protocol_history=True,
            )
        if session_items:
            return build_model_visible_session_item_prompt_window(
                session_items,
                max_chars=self.session_item_transcript_max_chars,
                include_non_protocol_history=_mode_includes_direct_history(mode),
            )
        if mode is not PromptMode.NORMAL_TURN:
            return PromptTranscript(
                messages=(),
                message_count=0,
                chars=0,
                estimated_tokens=0,
                tool_result_stats={},
            )
        return _current_inbound_transcript(run)

    def _resolve_context_block_budget(
        self,
        context_window_tokens: int | None,
    ) -> tuple[int, str]:
        if context_window_tokens is None or context_window_tokens <= 0:
            return self.context_block_max_tokens, "fixed"
        dynamic_budget = max(
            256,
            int(context_window_tokens * self.context_block_context_window_ratio),
        )
        effective_budget = min(
            self.context_block_max_tokens,
            dynamic_budget,
            context_window_tokens,
        )
        budget_source = (
            "context_window_scaled"
            if effective_budget < self.context_block_max_tokens
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
        self.llm_resolver = LlmResolver(self.llm_port, access_port=self.access_port)
        return self.llm_resolver

    def _publish_skill_resolution_event(
        self,
        *,
        run: OrchestrationRun,
        session_key: str,
        workspace_dir: str | None,
        surface: str,
        resolved_skill_catalog,
    ) -> None:
        if self.events_service is None:
            return
        resolved_skills = tuple(getattr(resolved_skill_catalog, "skills", ()) or ())
        ready_skills = tuple(item for item in resolved_skills if bool(getattr(item, "ready", False)))
        setup_needed_skills = tuple(item for item in resolved_skills if not bool(getattr(item, "ready", False)))
        missing_tools = tuple(
            dict.fromkeys(
                tool_id
                for item in setup_needed_skills
                for tool_id in tuple(getattr(getattr(item, "readiness", None), "missing_tools", ()) or ())
                if isinstance(tool_id, str) and tool_id.strip()
            )
        )
        missing_access = tuple(
            dict.fromkeys(
                requirement
                for item in setup_needed_skills
                for requirement in tuple(getattr(getattr(item, "readiness", None), "missing_access", ()) or ())
                if isinstance(requirement, str) and requirement.strip()
            )
        )
        missing_effects = tuple(
            dict.fromkeys(
                effect_id
                for item in setup_needed_skills
                for effect_id in tuple(getattr(getattr(item, "readiness", None), "missing_effects", ()) or ())
                if isinstance(effect_id, str) and effect_id.strip()
            )
        )
        payload: dict[str, object] = {
            "event_name": SKILL_RESOLUTION_COMPLETED_EVENT,
            "status": "setup_needed" if setup_needed_skills else "ready",
            "level": "warning" if setup_needed_skills else "info",
            "run_id": run.id,
            "agent_id": run.agent_id or "",
            "session_key": session_key,
            "active_session_id": run.active_session_id or "",
            "surface": surface,
            "workspace_dir": workspace_dir or "",
            "total_count": len(resolved_skills),
            "ready_count": len(ready_skills),
            "setup_needed_count": len(setup_needed_skills),
            "missing_tools": list(missing_tools),
            "missing_access": list(missing_access),
            "missing_effects": list(missing_effects),
            "skills": [
                {
                    "skill": getattr(getattr(item, "package", None), "name", ""),
                    "source": getattr(getattr(item, "package", None), "source", ""),
                    "status": getattr(getattr(item, "readiness", None), "status", ""),
                    "missing_tools": list(getattr(getattr(item, "readiness", None), "missing_tools", ()) or ()),
                    "missing_access": list(getattr(getattr(item, "readiness", None), "missing_access", ()) or ()),
                    "missing_effects": list(getattr(getattr(item, "readiness", None), "missing_effects", ()) or ()),
                }
                for item in resolved_skills[:40]
            ],
        }
        self.events_service.publish(
            skill_event_from_payload(
                SKILL_RESOLUTION_COMPLETED_EVENT,
                payload,
            )
        )

    def _publish_llm_resolution_event(
        self,
        run: OrchestrationRun,
        *,
        session_key: str,
        requested_llm_id: str,
        resolved_llm_id: str | None,
        strategy: str,
        input_has_image: bool,
        input_has_file: bool,
        status: str,
        profile: LlmProfile | None = None,
        reason: str | None = None,
    ) -> None:
        if self.events_service is None:
            return
        payload: dict[str, object] = {
            "event_name": "orchestration.llm_resolved",
            "status": status,
            "level": "error" if status == "failed" else "info",
            "run_id": run.id,
            "agent_id": run.agent_id or "",
            "session_key": session_key,
            "active_session_id": run.active_session_id or "",
            "requested_llm_id": requested_llm_id,
            "strategy": strategy,
            "input_has_image": input_has_image,
            "input_has_file": input_has_file,
            "current_step": run.current_step,
            "stage": run.stage.value,
        }
        if resolved_llm_id:
            payload["resolved_llm_id"] = resolved_llm_id
        if reason:
            payload["reason"] = reason
        if profile is not None:
            payload.update(
                {
                    "provider": profile.provider.value,
                    "api_family": profile.api_family.value,
                    "model_name": profile.model_name,
                    "model_family": profile.model_family or "",
                    "context_window_tokens": profile.context_window_tokens or 0,
                    "capabilities": [capability.value for capability in profile.capabilities],
                }
            )
        self.events_service.publish(
            Event(
                name="orchestration.llm_resolved",
                kind="observe",
                ordering_key=run.id,
                payload=payload,
            )
        )

    def _materialize_artifact_refs(
        self,
        messages: tuple[LlmMessage, ...],
        *,
        allow_vision: bool = True,
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
                    content=self._materialize_artifact_blocks(
                        blocks,
                        allow_vision=allow_vision,
                    ),
                ),
            )
        return tuple(materialized)

    def _materialize_artifact_blocks(
        self,
        blocks: list[dict[str, object]],
        *,
        allow_vision: bool = True,
    ) -> list[dict[str, object]]:
        materialized: list[dict[str, object]] = []
        for block in blocks:
            block_type = str(block.get("type") or "").strip()
            if block_type == IMAGE_REF_BLOCK_TYPE:
                materialized.append(
                    self._materialize_image_ref_block(
                        block,
                        allow_vision=allow_vision,
                    ),
                )
                continue
            if block_type == FILE_REF_BLOCK_TYPE:
                materialized.append(self._materialize_file_ref_block(block))
                continue
            materialized.append(dict(block))
        return materialized

    def _materialize_image_ref_block(
        self,
        block: dict[str, object],
        *,
        allow_vision: bool = True,
    ) -> dict[str, object]:
        artifact_id = str(block.get("artifact_id") or "").strip()
        mime_type = str(block.get("mime_type") or "").strip()
        name = block.get("name")
        normalized_name = name.strip() if isinstance(name, str) and name.strip() else None
        if not allow_vision:
            label = f":{normalized_name}" if normalized_name is not None else ""
            return text_content_block(
                f"[image attachment omitted for non-vision model{label}]",
            )
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
            label = f":{normalized_name}" if normalized_name is not None else ""
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
        hint_payload = RunPromptInputCollector._prompt_flow_hint_payload(run)
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
            return _prompt_bootstrap_hint_from_metadata(run.metadata)
        return dict(raw_hint)

    @staticmethod
    def _resolve_workspace_dir(
        *,
        session_binding: SessionRuntimeBinding,
        profile,
    ) -> str | None:
        for candidate in (
            session_binding.workspace,
            profile.runtime_preferences.workspace,
            profile.runtime_preferences.workdir,
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


def _routing_input_content(
    *,
    transcript_messages: tuple[LlmMessage, ...],
    session_items: tuple[SessionItem, ...],
) -> dict[str, object] | None:
    blocks: list[dict[str, object]] = []
    transcript_payload = _routing_input_content_from_transcript(transcript_messages)
    if isinstance(transcript_payload, dict):
        raw_blocks = transcript_payload.get("blocks")
        if isinstance(raw_blocks, list):
            blocks.extend(dict(block) for block in raw_blocks if isinstance(block, dict))
    for item in session_items:
        blocks.extend(content_blocks_from_payload(item.content_payload))
    if not blocks:
        return None
    return {"blocks": blocks}


def _prompt_bootstrap_hint_from_metadata(
    metadata: dict[str, object],
) -> dict[str, object]:
    policy = _metadata_mapping(metadata.get("prompt_bootstrap_policy"))
    runtime_task_policy = _metadata_mapping(metadata.get("runtime_task_policy"))
    runtime_prompt_bootstrap = _metadata_mapping(
        runtime_task_policy.get("prompt_bootstrap"),
    )
    if runtime_prompt_bootstrap:
        policy = {**runtime_prompt_bootstrap, **policy}
    if not policy:
        return {}
    payload: dict[str, object] = {}
    schema_ids = _metadata_string_list(policy.get("default_tool_schema_ids"))
    if schema_ids:
        payload["default_tool_schema_ids"] = schema_ids
    group_refs = _metadata_tool_schema_group_refs(
        policy.get("default_tool_schema_group_refs")
        or policy.get("tool_schema_group_refs"),
    )
    if group_refs:
        payload["default_tool_schema_group_refs"] = group_refs
    source = _metadata_text(policy.get("default_tool_schema_source"))
    if source is not None:
        payload["default_tool_schema_source"] = source
    elif payload:
        payload["default_tool_schema_source"] = "prompt_bootstrap_policy"
    return payload


def _metadata_mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _metadata_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _metadata_string_list(value: object) -> list[str]:
    if isinstance(value, str):
        candidates: tuple[object, ...] = (value,)
    elif isinstance(value, (list, tuple, set, frozenset)):
        candidates = tuple(value)
    else:
        return []
    items: list[str] = []
    for item in candidates:
        text = _metadata_text(item)
        if text is not None and text not in items:
            items.append(text)
    return items


def _metadata_tool_schema_group_refs(value: object) -> list[dict[str, str]]:
    if isinstance(value, dict):
        candidates: tuple[object, ...] = (value,)
    elif isinstance(value, str):
        candidates = (value,)
    elif isinstance(value, (list, tuple)):
        candidates = tuple(value)
    else:
        return []
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in candidates:
        ref = _metadata_tool_schema_group_ref(item)
        if ref is None:
            continue
        key = (
            ref.get("node_id", ""),
            ref.get("source_id", ""),
            ref.get("group_key", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
    return refs


def _metadata_tool_schema_group_ref(value: object) -> dict[str, str] | None:
    if isinstance(value, dict):
        node_id = _metadata_text(value.get("node_id"))
        source_id = _metadata_text(value.get("source_id"))
        group_key = _metadata_text(value.get("group_key"))
        reason = _metadata_text(value.get("reason"))
        if node_id is not None:
            payload = {"node_id": node_id}
            if source_id is not None:
                payload["source_id"] = source_id
            if group_key is not None:
                payload["group_key"] = group_key
            if reason is not None:
                payload["reason"] = reason
            return payload
        if source_id is None or group_key is None:
            return None
        payload = {"source_id": source_id, "group_key": group_key}
        if reason is not None:
            payload["reason"] = reason
        return payload
    text = _metadata_text(value)
    if text is None:
        return None
    if text.startswith("tools."):
        return {"node_id": text}
    for separator in (":", "#", "/"):
        if separator not in text:
            continue
        source_id, group_key = text.rsplit(separator, 1)
        source_id = source_id.strip()
        group_key = group_key.strip()
        if source_id and group_key:
            return {"source_id": source_id, "group_key": group_key}
    return None


def _current_inbound_transcript(run: OrchestrationRun) -> PromptTranscript:
    try:
        blocks = normalize_content_blocks(run.inbound_instruction.content)
    except ValueError as exc:
        raise OrchestrationValidationError(
            "Current inbound instruction content must be structured content blocks.",
        ) from exc
    if not blocks:
        return PromptTranscript(
            messages=(),
            message_count=0,
            chars=0,
            estimated_tokens=0,
            tool_result_stats={},
        )
    message = LlmMessage(
        role=LlmMessageRole.USER,
        content=blocks,
        metadata={
            "prompt_block_kind": "current_inbound",
            "source": run.inbound_instruction.source,
            "source_kind": "orchestration_run",
            "source_id": run.id,
        },
    )
    chars = _message_content_chars(message.content)
    return PromptTranscript(
        messages=(message,),
        message_count=1,
        chars=chars,
        estimated_tokens=_message_content_tokens(message.content),
        tool_result_stats={},
    )


def _mode_includes_direct_history(mode: PromptMode) -> bool:
    return mode in {
        PromptMode.COMPACTION,
        PromptMode.MEMORY_FLUSH,
    }


def _transcript_budget_with_execution_chain_refs(
    budget: dict[str, object],
    *,
    execution_query: ExecutionContinuationQueryPort | None,
    turn_id: str,
) -> dict[str, object]:
    execution_refs = _execution_chain_protocol_required_refs(
        execution_query,
        turn_id,
    )
    if not execution_refs:
        return budget
    merged = dict(budget)
    existing_refs = tuple(
        dict(ref)
        for ref in merged.get("protocol_required_refs", ())
        if isinstance(ref, dict)
    )
    merged_refs = _dedupe_protocol_required_refs(
        (*existing_refs, *execution_refs),
    )
    merged["protocol_required_refs"] = [dict(ref) for ref in merged_refs]
    merged["execution_chain_protocol_required_refs"] = [
        dict(ref) for ref in execution_refs
    ]
    merged["execution_chain_protocol_required_ref_count"] = len(execution_refs)
    if "protocol_required_preserved" not in merged:
        merged["protocol_required_preserved"] = True
    return {
        key: value
        for key, value in merged.items()
        if value not in (None, [], {})
    }


def _execution_chain_protocol_required_refs(
    execution_query: ExecutionContinuationQueryPort | None,
    turn_id: str,
) -> tuple[dict[str, object], ...]:
    if execution_query is None:
        return ()
    refs: list[dict[str, object]] = []
    for chain in execution_query.list_execution_chains(turn_id):
        chain_id = getattr(chain, "id", None)
        if not isinstance(chain_id, str) or not chain_id.strip():
            continue
        for step in execution_query.list_execution_steps(chain_id):
            step_id = getattr(step, "id", None)
            if not isinstance(step_id, str) or not step_id.strip():
                continue
            for item in execution_query.list_execution_step_items(step_id):
                ref = _execution_step_item_protocol_required_ref(item)
                if ref is not None:
                    refs.append(ref)
    return _dedupe_protocol_required_refs(tuple(refs))


def _execution_step_item_protocol_required_ref(
    item: object,
) -> dict[str, object] | None:
    kind = getattr(item, "kind", None)
    if kind not in {
        ExecutionStepItemKind.TOOL_CALL,
        ExecutionStepItemKind.TOOL_RESULT,
    }:
        return None
    summary = getattr(item, "summary_payload", None)
    if not isinstance(summary, dict):
        return None
    tool_call_id = _optional_text(summary.get("tool_call_id"))
    if tool_call_id is None:
        return None
    status = getattr(item, "status", None)
    owner = getattr(item, "owner", None)
    owner_kind = getattr(owner, "owner_kind", None)
    owner_id = getattr(owner, "owner_id", None)
    ref: dict[str, object] = {
        "owner_module": "orchestration",
        "owner_kind": "execution_step_item",
        "owner_id": getattr(item, "id", ""),
        "execution_step_item_id": getattr(item, "id", ""),
        "execution_step_id": getattr(item, "step_id", ""),
        "execution_chain_id": getattr(item, "chain_id", ""),
        "turn_id": getattr(item, "turn_id", ""),
        "kind": kind.value if isinstance(kind, ExecutionStepItemKind) else str(kind),
        "tool_call_id": tool_call_id,
        "protocol_required": True,
        "budget_class": "protocol_required",
        "render_mode": "ref",
        "visibility": "model_visible",
    }
    if isinstance(status, ExecutionStepItemStatus):
        ref["status"] = status.value
    elif isinstance(status, str) and status.strip():
        ref["status"] = status.strip()
    if isinstance(owner_kind, str) and owner_kind.strip():
        ref["source_owner_kind"] = owner_kind.strip()
    if isinstance(owner_id, str) and owner_id.strip():
        ref["source_owner_id"] = owner_id.strip()
    for key in (
        "tool_name",
        "tool_id",
        "tool_run_id",
        "result_session_item_id",
    ):
        value = _optional_text(summary.get(key))
        if value is not None:
            ref[key] = value
    tool_execution_plan = summary.get("tool_execution_plan")
    if isinstance(tool_execution_plan, dict):
        ref["tool_execution_plan"] = dict(tool_execution_plan)
    tool_lifecycle = summary.get("tool_lifecycle")
    if isinstance(tool_lifecycle, dict):
        ref["tool_lifecycle"] = dict(tool_lifecycle)
    return {
        key: value
        for key, value in ref.items()
        if value not in (None, "", {}, [])
    }


def _dedupe_protocol_required_refs(
    refs: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    deduped: list[dict[str, object]] = []
    seen: set[tuple[object, object, object, object]] = set()
    for ref in refs:
        identity = (
            ref.get("owner_module"),
            ref.get("owner_kind"),
            ref.get("owner_id"),
            ref.get("tool_call_id"),
        )
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(dict(ref))
    return tuple(deduped)


def _execution_step_item_summaries(
    execution_query: ExecutionContinuationQueryPort,
    turn_id: str,
) -> tuple[dict[str, object], ...]:
    summaries: list[dict[str, object]] = []
    for chain in execution_query.list_execution_chains(turn_id):
        chain_id = getattr(chain, "id", None)
        if not isinstance(chain_id, str) or not chain_id.strip():
            continue
        for step in execution_query.list_execution_steps(chain_id):
            step_id = getattr(step, "id", None)
            if not isinstance(step_id, str) or not step_id.strip():
                continue
            for item in execution_query.list_execution_step_items(step_id):
                summary = getattr(item, "summary_payload", None)
                if isinstance(summary, dict):
                    summaries.append(summary)
    return tuple(summaries)


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _message_content_chars(content: object) -> int:
    text_content = extract_text_content(content)
    if text_content is not None:
        return len(text_content)
    return len(describe_content_for_text_fallback(content))


def _message_content_tokens(content: object) -> int:
    text_content = extract_text_content(content)
    if text_content is not None:
        return estimate_text_tokens(text_content)
    return estimate_text_tokens(describe_content_for_text_fallback(content))


def _is_text_like_file_mime_type(mime_type: str) -> bool:
    normalized = mime_type.strip().lower()
    return normalized in {
        "text/plain",
        "text/markdown",
        "application/json",
    }
