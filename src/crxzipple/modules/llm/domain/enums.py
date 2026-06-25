from __future__ import annotations

from enum import StrEnum


class LlmProviderKind(StrEnum):
    OPENAI = "openai"
    OPENAI_CODEX = "openai_codex"
    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"


class LlmApiFamily(StrEnum):
    OPENAI_RESPONSES = "openai_responses"
    OPENAI_CODEX_RESPONSES = "openai_codex_responses"
    OPENAI_CHAT_COMPATIBLE = "openai_chat_compatible"
    ANTHROPIC_MESSAGES = "anthropic_messages"
    GEMINI_GENERATE_CONTENT = "gemini_generate_content"
    OLLAMA_NATIVE = "ollama_native"


class LlmModelFamily(StrEnum):
    GENERAL = "general"
    CODEX = "codex"
    REASONING = "reasoning"
    VISION = "vision"


class LlmCapability(StrEnum):
    TOOL_CALLING = "tool_calling"
    STRUCTURED_OUTPUT = "structured_output"
    VISION_INPUT = "vision_input"
    STREAMING = "streaming"
    REASONING = "reasoning"
    PROVIDER_NATIVE_CONTINUATION = "provider_native_continuation"
    PROVIDER_WEBSOCKET_TRANSPORT = "provider_websocket_transport"
    PROVIDER_INCREMENTAL_INPUT = "provider_incremental_input"


class LlmSourceKind(StrEnum):
    MANUAL = "manual"
    DISCOVERED = "discovered"
    IMPORTED = "imported"


class LlmInvocationStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LlmMessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class LlmResponseItemKind(StrEnum):
    ASSISTANT_MESSAGE = "assistant_message"
    REASONING = "reasoning"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    STRUCTURED_OUTPUT = "structured_output"
    PROVIDER_EXTERNAL_ITEM = "provider_external_item"
    COMPACTION = "compaction"
    UNKNOWN = "unknown"


class LlmInputItemKind(StrEnum):
    MESSAGE = "message"
    FUNCTION_CALL = "function_call"
    FUNCTION_CALL_OUTPUT = "function_call_output"
    REASONING = "reasoning"
    PROVIDER_EXTERNAL_ITEM = "provider_external_item"


class LlmMessagePhase(StrEnum):
    COMMENTARY = "commentary"
    FINAL_ANSWER = "final_answer"
    UNKNOWN = "unknown"


class LlmResponseEventType(StrEnum):
    INVOCATION_STARTED = "invocation_started"
    ITEM_STARTED = "item_started"
    TEXT_DELTA = "text_delta"
    REASONING_SUMMARY_DELTA = "reasoning_summary_delta"
    REASONING_RAW_DELTA = "reasoning_raw_delta"
    TOOL_ARGUMENT_DELTA = "tool_argument_delta"
    ITEM_COMPLETED = "item_completed"
    COMPLETED = "completed"
    FAILED = "failed"


class LlmContinuationReason(StrEnum):
    NONE = "none"
    TOOL_CALL = "tool_call"
    PROVIDER_END_TURN_FALSE = "provider_end_turn_false"
    TOOL_ERROR_RESPONSE = "tool_error_response"
    PENDING_EXTERNAL = "pending_external"


__all__ = [
    "LlmApiFamily",
    "LlmCapability",
    "LlmContinuationReason",
    "LlmInputItemKind",
    "LlmInvocationStatus",
    "LlmMessagePhase",
    "LlmMessageRole",
    "LlmModelFamily",
    "LlmProviderKind",
    "LlmResponseEventType",
    "LlmResponseItemKind",
    "LlmSourceKind",
]
