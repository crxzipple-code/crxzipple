from __future__ import annotations

import json
from dataclasses import dataclass

from crxzipple.modules.agent.application import AgentApplicationService
from crxzipple.modules.llm.domain import LlmMessage, LlmMessageRole
from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
    OrchestrationValidationError,
)
from crxzipple.modules.session.application import (
    ListSessionMessagesInput,
    SessionApplicationService,
)
from crxzipple.modules.session.domain import SessionMessage, SessionRuntimeBinding


@dataclass(frozen=True, slots=True)
class PromptEnvelope:
    llm_id: str
    session_key: str
    active_session_id: str
    messages: tuple[LlmMessage, ...]


@dataclass(slots=True)
class PromptAssembler:
    agent_service: AgentApplicationService
    session_service: SessionApplicationService

    def assemble(self, run: OrchestrationRun) -> PromptEnvelope:
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

        llm_messages: list[LlmMessage] = []
        system_prompt = profile.instruction_policy.system_prompt.strip()
        if system_prompt:
            llm_messages.append(
                LlmMessage(
                    role=LlmMessageRole.SYSTEM,
                    content=system_prompt,
                ),
            )

        session_messages = self.session_service.list_messages(
            ListSessionMessagesInput(
                session_key=session_key,
                active_session_only=True,
            ),
        )
        llm_messages.extend(
            self._to_llm_message(message)
            for message in session_messages
            if message.session_id == run.active_session_id
        )
        if not llm_messages:
            raise OrchestrationValidationError(
                "Prompt assembly requires at least one llm message.",
            )

        return PromptEnvelope(
            llm_id=llm_id,
            session_key=session_key,
            active_session_id=run.active_session_id,
            messages=tuple(llm_messages),
        )

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
