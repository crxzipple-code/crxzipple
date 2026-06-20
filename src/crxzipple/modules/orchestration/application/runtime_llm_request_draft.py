from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from crxzipple.modules.llm.domain import (
    LlmCapability,
    LlmInputItem,
    LlmMessage,
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
    EventPublishPort,
    LlmPort,
    SessionTranscriptPort,
)
from crxzipple.modules.orchestration.application.runtime_request_mode import RuntimeRequestMode
from crxzipple.modules.orchestration.application.runtime_request_report import (
    RuntimeRequestReport,
    RunSurfacePolicy,
    resolve_run_surface_policy,
)
from crxzipple.modules.llm.application.session_runtime_transcript import (
    RuntimeTranscript,
    RuntimeTranscriptReport,
    RuntimeReplayWindowBuilder,
    build_current_inbound_runtime_transcript,
)
from crxzipple.modules.orchestration.application.tool_resolver import ResolvedToolSet
from crxzipple.modules.session.application import (
    GetSessionItemBySourceInput,
    ListSessionItemsInput,
    SessionReplayWindow,
)
from crxzipple.modules.session.domain import Session, SessionItem, SessionItemKind
from crxzipple.modules.session.domain import SessionRuntimeBinding
from crxzipple.shared.content_blocks import (
    content_blocks_from_payload,
    normalize_content_blocks,
)
from crxzipple.shared.domain.events import Event
from crxzipple.shared.runtime_metrics import (
    RuntimeMetricsRegistry,
    get_runtime_metrics_registry,
)

def _available_tool_ids(resolved_tools: ResolvedToolSet | None) -> tuple[str, ...]:
    if resolved_tools is None:
        return ()
    return tuple(item.tool.id for item in resolved_tools.tools)


def _runtime_context_facts(
    run: OrchestrationRun,
    *,
    llm_id: str,
    home_dir: str | None,
    workspace_dir: str | None,
    available_tool_ids: tuple[str, ...],
) -> dict[str, object]:
    normalized_home_dir = home_dir.strip() if home_dir is not None and home_dir.strip() else None
    normalized_workspace_dir = (
        workspace_dir.strip()
        if workspace_dir is not None and workspace_dir.strip()
        else normalized_home_dir
    )
    return {
        "agent_id": run.agent_id,
        "llm_id": llm_id,
        "agent_home_dir": normalized_home_dir,
        "workspace_dir": normalized_workspace_dir,
        "available_tool_ids": tuple(available_tool_ids),
        "current_step": run.current_step,
        "max_steps": run.max_steps,
        "remaining_steps": max(run.max_steps - run.current_step, 0),
        "step_budget_status": _step_budget_status(
            current_step=run.current_step,
            max_steps=run.max_steps,
        ),
    }


def _step_budget_status(*, current_step: int, max_steps: int) -> str:
    remaining_steps = max(max_steps - current_step, 0)
    if remaining_steps <= 1:
        return "finalize_now"
    if remaining_steps <= 3:
        return "critical"
    if remaining_steps <= 6:
        return "constrained"
    return "available"


class ExecutionContinuationQueryPort(Protocol):
    def list_execution_chains(self, turn_id: str) -> list[object]:
        ...

    def list_execution_steps(self, chain_id: str) -> list[object]:
        ...

    def list_execution_step_items(self, step_id: str) -> list[object]:
        ...


class SkillRuntimeRequestResolutionPort(Protocol):
    def resolve_runtime_request_catalog(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
        available_tool_ids: tuple[str, ...],
        interface: str | None = None,
        agent_id: str | None = None,
        run_id: str | None = None,
        session_key: str | None = None,
        active_session_id: str | None = None,
    ) -> Any:
        ...


@dataclass(frozen=True, slots=True)
class RuntimeLlmRequestDraft:
    llm_id: str
    session_key: str
    active_session_id: str
    messages: tuple[LlmMessage, ...]
    input_items: tuple[LlmInputItem, ...] = ()
    transcript_policy: dict[str, object] = field(default_factory=dict)
    llm_capabilities: tuple[LlmCapability, ...] = ()
    llm_api_family: str | None = None
    runtime_llm_defaults: dict[str, object] = field(default_factory=dict)
    llm_defaults: dict[str, object] = field(default_factory=dict)
    llm_policy: dict[str, object] = field(default_factory=dict)
    mode: RuntimeRequestMode = RuntimeRequestMode.NORMAL_TURN
    report: RuntimeRequestReport | None = None
    agent_instruction: str | None = None
    runtime_context: dict[str, object] = field(default_factory=dict)
    workspace_dir: str | None = None
    tool_schemas: tuple[ToolSchema, ...] = ()
    flow_hint: dict[str, object] = field(default_factory=dict)
    surface_policy: RunSurfacePolicy = field(default_factory=RunSurfacePolicy)
    skill_runtime_request_metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _SessionDraftContext:
    session: Session
    lightweight_items: tuple[SessionItem, ...] = ()
    replay_window: object | None = None

    @property
    def replay_items(self) -> tuple[SessionItem, ...]:
        if self.replay_window is None:
            return self.lightweight_items
        items = getattr(self.replay_window, "items", ())
        return tuple(items or ())


@dataclass(slots=True)
class RuntimeLlmRequestDraftCollector:
    """Collects run facts for a canonical runtime LLM request draft.

    This collector does not render provider input. Context Workspace owns the
    tree snapshot and attachment mirror; the LLM renderer owns provider wire
    rendering. This object only gathers transcript, routing, context refs, and
    the initially resolved tool surface for the downstream request envelope.
    """

    agent_service: AgentProfileCatalogPort
    llm_port: LlmPort
    session_service: SessionTranscriptPort
    access_port: AccessReadinessPort | None = None
    events_service: EventPublishPort | None = None
    llm_resolver: LlmResolver | None = None
    execution_query: ExecutionContinuationQueryPort | None = None
    skill_runtime_request_resolver: SkillRuntimeRequestResolutionPort | None = None
    context_block_max_chars: int = 120_000
    context_block_max_tokens: int = 30_000
    context_block_context_window_ratio: float = 0.15
    session_item_transcript_max_chars: int = 120_000
    memory_flush_transcript_max_chars: int = 4_000
    runtime_llm_defaults: dict[str, object] = field(default_factory=dict)
    runtime_replay_window_builder: RuntimeReplayWindowBuilder = field(
        default_factory=RuntimeReplayWindowBuilder,
    )
    detailed_phase_metrics_enabled: bool = False
    metrics: RuntimeMetricsRegistry = field(
        default_factory=get_runtime_metrics_registry,
    )

    def build(
        self,
        run: OrchestrationRun,
        *,
        resolved_tools: ResolvedToolSet | None = None,
        mode: RuntimeRequestMode | None = None,
        validate_llm_access: bool = True,
    ) -> RuntimeLlmRequestDraft:
        if run.agent_id is None or not run.agent_id.strip():
            raise OrchestrationValidationError(
                "Orchestration run agent_id is required for runtime request collection.",
            )
        if run.active_session_id is None or not run.active_session_id.strip():
            raise OrchestrationValidationError(
                "Orchestration run active_session_id is required for runtime request collection.",
            )

        session_key = str(run.metadata.get("session_key", "")).strip()
        if not session_key:
            raise OrchestrationValidationError(
                "Orchestration run metadata.session_key is required for runtime request collection.",
            )

        with self._timed_phase("profile_read"):
            profile = self.agent_service.get_profile(run.agent_id)
        resolved_mode = self._resolve_runtime_request_mode(run, mode=mode)
        with self._timed_phase("session_context_read"):
            session_context = self._session_draft_context(
                run=run,
                session_key=session_key,
                mode=resolved_mode,
            )
        session = session_context.session
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
            transcript = self._build_runtime_replay_window(
                run,
                session_items=session_context.replay_items,
                mode=resolved_mode,
            )
            transcript_policy = _transcript_policy_payload(
                session_key=session.id,
                session_replay_window=session_context.replay_window,
                mode=resolved_mode,
            )
        with self._timed_phase("llm_resolve"):
            routing_input_content = (
                _routing_input_content(
                    transcript_messages=transcript.messages,
                    session_items=(),
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
                    validate_access=validate_llm_access,
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
                    routing_input_content=routing_input_content,
                    session_replay_window=session_context.replay_window,
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
                routing_input_content=routing_input_content,
                session_replay_window=session_context.replay_window,
            )
            llm_transcript_messages = transcript.messages
        surface_policy = self._resolve_surface_policy(resolved_mode)
        runtime_request_flow_hint = self._runtime_request_flow_hint_payload(run)
        with self._timed_phase("runtime_context_facts_build"):
            available_tool_ids = _available_tool_ids(resolved_tools)
            agent_instruction = profile.instruction_policy.system_prompt.strip() or None
            runtime_context = _runtime_context_facts(
                run,
                llm_id=llm_selection.resolved_llm_id,
                home_dir=agent_home_dir,
                workspace_dir=workspace_dir,
                available_tool_ids=available_tool_ids,
            )
            effective_context_max_tokens, context_budget_source = (
                self._resolve_context_block_budget(
                    llm_profile.context_window_tokens,
                )
            )
            effective_context_max_chars = min(
                self.context_block_max_chars,
                max(1, effective_context_max_tokens * 4),
            )
        llm_messages: list[LlmMessage] = list(llm_transcript_messages)
        if not llm_messages and not agent_instruction:
            raise OrchestrationValidationError(
                "Runtime LLM request draft collection requires at least one transcript message or agent instruction fact.",
            )
        with self._timed_phase("runtime_request_report_build"):
            base_transcript_budget = _transcript_budget_with_lightweight_item_refs(
                dict(transcript.report.budget),
                session_items=session_context.replay_items,
                mode=resolved_mode,
            )
            transcript_budget = _transcript_budget_with_execution_chain_refs(
                base_transcript_budget,
                execution_query=self.execution_query,
                turn_id=run.id,
            )
            report = RuntimeRequestReport(
                mode=resolved_mode,
                context_budget_source=context_budget_source,
                context_budget_chars=effective_context_max_chars,
                context_budget_estimated_tokens=effective_context_max_tokens,
                llm_context_window_tokens=llm_profile.context_window_tokens,
                context_chars=0,
                context_estimated_tokens=0,
                transcript_message_count=transcript.report.message_count,
                transcript_chars=transcript.report.chars,
                transcript_estimated_tokens=transcript.report.estimated_tokens,
                transcript_tool_result_stats=dict(transcript.report.tool_result_stats),
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
        with self._timed_phase("skill_runtime_request_resolve"):
            skill_runtime_request_metadata = (
                self._resolve_skill_runtime_request_metadata(
                    run,
                    workspace_dir=workspace_dir,
                    surface=surface_policy.surface,
                    session_key=session_key,
                    available_tool_ids=available_tool_ids,
                )
            )

        return RuntimeLlmRequestDraft(
            llm_id=llm_selection.resolved_llm_id,
            llm_capabilities=tuple(llm_profile.capabilities),
            llm_api_family=llm_profile.api_family.value,
            runtime_llm_defaults=dict(self.runtime_llm_defaults),
            llm_defaults=llm_profile.default_params.to_payload(),
            llm_policy=profile.llm_policy.to_payload(),
            session_key=session_key,
            active_session_id=run.active_session_id,
            messages=tuple(llm_messages),
            input_items=transcript.input_items,
            transcript_policy=transcript_policy,
            mode=resolved_mode,
            report=report,
            agent_instruction=agent_instruction,
            runtime_context=runtime_context,
            workspace_dir=workspace_dir,
            tool_schemas=tool_schemas,
            flow_hint=runtime_request_flow_hint,
            surface_policy=surface_policy,
            skill_runtime_request_metadata=skill_runtime_request_metadata,
        )

    @staticmethod
    def _should_include_tool_schemas(
        run: OrchestrationRun,
        *,
        resolved_mode: RuntimeRequestMode,
        surface_policy: RunSurfacePolicy,
        resolved_tools: ResolvedToolSet | None,
        transcript_messages: tuple[LlmMessage, ...],
    ) -> bool:
        if resolved_tools is None or not resolved_tools.tools:
            return False
        if not surface_policy.include_tool_schemas:
            return False
        if (
            resolved_mode is RuntimeRequestMode.NORMAL_TURN
            and max(run.max_steps - run.current_step, 0) <= 1
        ):
            return False
        return True

    def resolve_mode(
        self,
        run: OrchestrationRun,
        *,
        mode: RuntimeRequestMode | None = None,
    ) -> RuntimeRequestMode:
        return self._resolve_runtime_request_mode(run, mode=mode)

    def _timed_phase(self, phase: str):
        if not self.detailed_phase_metrics_enabled:
            return nullcontext()
        return self.metrics.timed(
            "orchestration.runtime_request_drafts.phase_seconds",
            labels={"phase": phase},
        )

    @staticmethod
    def _resolve_surface_policy(mode: RuntimeRequestMode) -> RunSurfacePolicy:
        return resolve_run_surface_policy(mode)

    def _session_draft_context(
        self,
        *,
        run: OrchestrationRun,
        session_key: str,
        mode: RuntimeRequestMode,
    ) -> _SessionDraftContext:
        if mode is RuntimeRequestMode.MEMORY_FLUSH or _mode_includes_direct_history(mode):
            bundle = self.session_service.get_session_with_items(
                ListSessionItemsInput(
                    session_key=session_key,
                    active_session_only=True,
                ),
            )
            replay_window = _session_replay_window_from_items(
                session=bundle.session,
                items=tuple(bundle.items),
                active_session_only=True,
            )
            return _SessionDraftContext(
                session=replay_window.session,
                replay_window=replay_window,
            )
        current_item = _get_current_inbound_session_item(
            self.session_service,
            run=run,
            session_key=session_key,
        )
        if current_item is not None:
            bundle = self.session_service.get_session_with_items(
                ListSessionItemsInput(
                    session_key=session_key,
                    active_session_only=True,
                    limit=0,
                ),
            )
            return _SessionDraftContext(
                session=bundle.session,
                lightweight_items=(current_item,),
            )
        bundle = self.session_service.get_session_with_items(
            ListSessionItemsInput(
                session_key=session_key,
                active_session_only=True,
                limit=1,
            ),
        )
        return _SessionDraftContext(
            session=bundle.session,
            lightweight_items=tuple(bundle.items),
        )

    def _build_runtime_replay_window(
        self,
        run: OrchestrationRun,
        *,
        session_items: tuple[SessionItem, ...] = (),
        mode: RuntimeRequestMode,
    ) -> RuntimeTranscript:
        if mode is RuntimeRequestMode.MEMORY_FLUSH:
            return self.runtime_replay_window_builder.build_from_session_items(
                session_items,
                max_chars=self.memory_flush_transcript_max_chars,
                include_non_protocol_history=True,
            )
        if mode in {
            RuntimeRequestMode.NORMAL_TURN,
            RuntimeRequestMode.SESSION_START,
        }:
            return _current_inbound_transcript(run)
        if session_items:
            transcript = self.runtime_replay_window_builder.build_from_session_items(
                session_items,
                max_chars=self.session_item_transcript_max_chars,
                include_non_protocol_history=_mode_includes_direct_history(mode),
            )
            if transcript.input_items or transcript.messages:
                return transcript
            if mode in {
                RuntimeRequestMode.NORMAL_TURN,
                RuntimeRequestMode.SESSION_START,
            }:
                return _current_inbound_transcript(run)
            return transcript
        if mode not in {
            RuntimeRequestMode.NORMAL_TURN,
            RuntimeRequestMode.SESSION_START,
        }:
            return RuntimeTranscript(
                messages=(),
                report=RuntimeTranscriptReport(
                    message_count=0,
                    chars=0,
                    estimated_tokens=0,
                    tool_result_stats={},
                ),
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

    def _resolve_skill_runtime_request_metadata(
        self,
        run: OrchestrationRun,
        *,
        workspace_dir: str | None,
        surface: str,
        session_key: str,
        available_tool_ids: tuple[str, ...],
    ) -> dict[str, object]:
        if self.skill_runtime_request_resolver is None:
            return {}
        resolution = self.skill_runtime_request_resolver.resolve_runtime_request_catalog(
            workspace_dir=workspace_dir,
            surface=surface,
            available_tool_ids=available_tool_ids,
            interface=run.inbound_instruction.source,
            agent_id=run.agent_id,
            run_id=run.id,
            session_key=session_key,
            active_session_id=run.active_session_id,
        )
        catalog = getattr(resolution, "runtime_request_catalog", None)
        if catalog is None:
            return {}
        metadata = getattr(catalog, "metadata", None)
        if not isinstance(metadata, dict):
            return {}
        return dict(metadata)

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
        routing_input_content: dict[str, object] | None = None,
        session_replay_window=None,
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
        input_block_count = _routing_input_block_count(routing_input_content)
        if input_block_count is not None:
            payload["routing_input_block_count"] = input_block_count
        replay_window_payload = _session_replay_window_event_payload(
            session_replay_window,
        )
        if replay_window_payload:
            payload["session_replay_window"] = replay_window_payload
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

    @staticmethod
    def _resolve_runtime_request_mode(
        run: OrchestrationRun,
        *,
        mode: RuntimeRequestMode | None,
    ) -> RuntimeRequestMode:
        if mode is not None:
            return mode
        hint_payload = RuntimeLlmRequestDraftCollector._runtime_request_flow_hint_payload(run)
        raw_mode = hint_payload.get("mode")
        if isinstance(raw_mode, str) and raw_mode.strip():
            try:
                return RuntimeRequestMode(raw_mode.strip())
            except ValueError:
                pass
        return RuntimeRequestMode.NORMAL_TURN

    @staticmethod
    def _runtime_request_flow_hint_payload(run: OrchestrationRun) -> dict[str, object]:
        raw_hint = run.metadata.get("runtime_request_flow_hint")
        if not isinstance(raw_hint, dict):
            return _runtime_request_bootstrap_hint_from_metadata(run.metadata)
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
    transcript_payload = _routing_input_content_from_transcript(transcript_messages)
    if isinstance(transcript_payload, dict):
        raw_blocks = transcript_payload.get("blocks")
        if isinstance(raw_blocks, list):
            transcript_blocks = [
                dict(block) for block in raw_blocks if isinstance(block, dict)
            ]
            if transcript_blocks:
                return {"blocks": transcript_blocks}
    blocks: list[dict[str, object]] = []
    for item in session_items:
        blocks.extend(content_blocks_from_payload(item.content_payload))
    if not blocks:
        return None
    return {"blocks": blocks}


def _get_current_inbound_session_item(
    session_service: object,
    *,
    run: OrchestrationRun,
    session_key: str,
) -> SessionItem | None:
    lookup = getattr(session_service, "get_item_by_source", None)
    if not callable(lookup):
        return None
    active_session_id = _optional_text(run.active_session_id)
    if active_session_id is None:
        return None
    try:
        item = lookup(
            GetSessionItemBySourceInput(
                session_key=session_key,
                session_id=active_session_id,
                source_module="orchestration",
                source_kind="orchestration_run",
                source_id=run.id,
            ),
        )
    except Exception:
        return None
    if isinstance(item, SessionItem) and item.role == "user":
        return item
    return None


def _transcript_budget_with_lightweight_item_refs(
    budget: dict[str, object],
    *,
    session_items: tuple[SessionItem, ...],
    mode: RuntimeRequestMode,
) -> dict[str, object]:
    if mode not in {RuntimeRequestMode.NORMAL_TURN, RuntimeRequestMode.SESSION_START}:
        return budget
    refs = _session_item_required_refs(session_items)
    if not refs:
        return budget
    existing_refs = tuple(
        dict(ref)
        for ref in budget.get("protocol_required_refs", ())
        if isinstance(ref, dict)
    )
    merged = dict(budget)
    merged["protocol_required_refs"] = [
        dict(ref) for ref in _dedupe_protocol_required_refs((*existing_refs, *refs))
    ]
    return merged


def _session_item_required_refs(
    session_items: tuple[SessionItem, ...],
) -> tuple[dict[str, object], ...]:
    refs: list[dict[str, object]] = []
    for item in session_items:
        if item.role != "user" or item.kind is not SessionItemKind.USER_MESSAGE:
            continue
        if item.source_module != "orchestration" or item.source_kind != "orchestration_run":
            continue
        ref: dict[str, object] = {
            "owner_module": "session",
            "owner_kind": "session_item",
            "owner_id": item.id,
            "item_id": item.id,
            "session_id": item.session_id,
            "sequence_no": item.sequence_no,
            "role": item.role,
            "kind": item.kind.value,
            "render_mode": "full",
            "render_scope": "provider_replay",
            "budget_class": "current_inbound",
        }
        for key, value in {
            "source_module": item.source_module,
            "source_kind": item.source_kind,
            "source_id": item.source_id,
            "provider_item_id": item.provider_item_id,
            "tool_call_id": item.call_id,
            "tool_name": item.tool_name,
        }.items():
            text = _optional_text(value)
            if text is not None:
                ref[key] = text
        refs.append(ref)
    return tuple(refs)


def _routing_input_block_count(value: dict[str, object] | None) -> int | None:
    if not isinstance(value, dict):
        return None
    blocks = value.get("blocks")
    if not isinstance(blocks, list):
        return None
    return len(tuple(block for block in blocks if isinstance(block, dict)))


def _session_replay_window_event_payload(value: object) -> dict[str, object]:
    if value is None:
        return {}
    payload: dict[str, object] = {}
    for attr in (
        "active_session_only",
        "from_sequence_no",
        "to_sequence_no",
        "item_count",
    ):
        item = getattr(value, attr, None)
        if item is not None:
            payload[attr] = item
    protocol_call_ids = getattr(value, "protocol_call_ids", None)
    if protocol_call_ids:
        payload["protocol_call_ids"] = list(protocol_call_ids)
    return payload


def _session_replay_window_policy_payload(
    value: object,
    *,
    session_key: str,
) -> dict[str, object]:
    payload = _session_replay_window_event_payload(value)
    payload["session_key"] = session_key
    return payload


def _transcript_policy_payload(
    *,
    session_key: str,
    session_replay_window: object | None,
    mode: RuntimeRequestMode,
) -> dict[str, object]:
    if session_replay_window is not None:
        return {
            "session_replay_window": _session_replay_window_policy_payload(
                session_replay_window,
                session_key=session_key,
            ),
        }
    return {
        "session_binding_lookup": {
            "session_key": session_key,
            "active_session_only": True,
            "item_limit": 0,
            "mode": mode.value,
        },
    }


def _runtime_request_bootstrap_hint_from_metadata(
    metadata: dict[str, object],
) -> dict[str, object]:
    policy = _metadata_mapping(metadata.get("runtime_request_bootstrap_policy"))
    runtime_task_policy = _metadata_mapping(metadata.get("runtime_task_policy"))
    runtime_request_bootstrap = _metadata_mapping(
        runtime_task_policy.get("runtime_request_bootstrap"),
    )
    if runtime_request_bootstrap:
        policy = {**runtime_request_bootstrap, **policy}
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
        payload["default_tool_schema_source"] = "runtime_request_bootstrap_policy"
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


def _current_inbound_transcript(run: OrchestrationRun) -> RuntimeTranscript:
    try:
        return build_current_inbound_runtime_transcript(
            run.inbound_instruction.content,
            source=run.inbound_instruction.source,
            source_id=run.id,
        )
    except ValueError as exc:
        raise OrchestrationValidationError(
            "Current inbound instruction content must be structured content blocks.",
        ) from exc


def _session_replay_window_from_items(
    *,
    session: Session,
    items: tuple[SessionItem, ...],
    active_session_only: bool,
) -> SessionReplayWindow:
    return SessionReplayWindow(
        session=session,
        items=items,
        active_session_only=active_session_only,
        from_sequence_no=items[0].sequence_no if items else None,
        to_sequence_no=items[-1].sequence_no if items else None,
        item_count=len(items),
        protocol_call_ids=tuple(
            dict.fromkeys(item.call_id for item in items if item.call_id),
        ),
    )


def _mode_includes_direct_history(mode: RuntimeRequestMode) -> bool:
    return mode in {
        RuntimeRequestMode.COMPACTION,
        RuntimeRequestMode.MEMORY_FLUSH,
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
        "render_scope": "provider_replay",
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
        "call_session_item_id",
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
