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
from crxzipple.modules.orchestration.application.runtime_request_bootstrap_hint import (
    runtime_request_bootstrap_hint_from_metadata,
)
from crxzipple.modules.orchestration.application.runtime_request_report import (
    RuntimeRequestReport,
    RunSurfacePolicy,
    resolve_run_surface_policy,
)
from crxzipple.modules.orchestration.application.runtime_request_report_builder import (
    ExecutionContinuationQueryPort,
    RuntimeRequestReportBuilder,
)
from crxzipple.modules.orchestration.application.runtime_step_budget_policy import (
    RuntimeStepBudgetPolicy,
)
from crxzipple.modules.orchestration.application.runtime_tool_schema_policy import (
    RuntimeToolSchemaPolicy,
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
from crxzipple.modules.session.domain import Session, SessionItem
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
    step_budget_policy: RuntimeStepBudgetPolicy | None = None,
) -> dict[str, object]:
    normalized_home_dir = home_dir.strip() if home_dir is not None and home_dir.strip() else None
    normalized_workspace_dir = (
        workspace_dir.strip()
        if workspace_dir is not None and workspace_dir.strip()
        else normalized_home_dir
    )
    step_budget = (step_budget_policy or RuntimeStepBudgetPolicy()).for_run(run)
    return {
        "agent_id": run.agent_id,
        "llm_id": llm_id,
        "agent_home_dir": normalized_home_dir,
        "workspace_dir": normalized_workspace_dir,
        "available_tool_ids": tuple(available_tool_ids),
        **step_budget.to_payload(),
    }


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
    step_budget_policy: RuntimeStepBudgetPolicy = field(
        default_factory=RuntimeStepBudgetPolicy,
    )
    tool_schema_policy: RuntimeToolSchemaPolicy = field(
        default_factory=RuntimeToolSchemaPolicy,
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
                step_budget_policy=self.step_budget_policy,
            )
            report_builder = RuntimeRequestReportBuilder(
                context_block_max_tokens=self.context_block_max_tokens,
                context_block_context_window_ratio=(
                    self.context_block_context_window_ratio
                ),
            )
            effective_context_max_tokens, context_budget_source = (
                report_builder.resolve_context_block_budget(
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
            report = report_builder.build(
                mode=resolved_mode,
                transcript=transcript,
                session_items=session_context.replay_items,
                context_budget_source=context_budget_source,
                context_budget_chars=effective_context_max_chars,
                context_budget_estimated_tokens=effective_context_max_tokens,
                llm_context_window_tokens=llm_profile.context_window_tokens,
                execution_query=self.execution_query,
                turn_id=run.id,
            )
        tool_schemas = (
            resolved_tools.schemas
            if self.tool_schema_policy.should_include_tool_schemas(
                resolved_mode=resolved_mode,
                surface_policy=surface_policy,
                resolved_tools=resolved_tools,
                step_budget=self.step_budget_policy.for_run(run),
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
            return runtime_request_bootstrap_hint_from_metadata(run.metadata)
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


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
