from __future__ import annotations

from pydantic import BaseModel, Field


class AgentIdentityRequest(BaseModel):
    display_name: str | None = None
    theme: str | None = None
    emoji: str | None = None
    avatar: str | None = None


class AgentInstructionPolicyRequest(BaseModel):
    system_prompt: str = ""
    response_style: str | None = None
    thinking_default: str | None = None
    stream_by_default: bool = False


class AgentLlmRoutingPolicyRequest(BaseModel):
    default_llm_id: str
    fallback_llm_ids: list[str] = Field(default_factory=list)
    image_llm_id: str | None = None
    document_llm_id: str | None = None


class AgentLlmPolicyRequest(BaseModel):
    reasoning_summary_policy: str = "visible_and_replay_when_provider_supports"
    raw_reasoning_policy: str = "hidden_by_default"
    tool_use_policy: str = "auto"
    parallel_tool_calls_policy: str = "provider_default"
    final_answer_policy: str = "phase_or_codex_unknown_fallback"
    commentary_visibility_policy: str = "user_progress"
    provider_external_item_policy: str = "history_and_trace_no_toolrun"


class AgentExecutionPolicyRequest(BaseModel):
    timeout_seconds: int = 120
    max_turns: int = 99


class AgentRuntimePreferencesRequest(BaseModel):
    home_dir: str | None = None
    workdir: str | None = None
    workspace: str | None = None
    sandbox_mode: str | None = None
    attrs: dict[str, object] = Field(default_factory=dict)


class AgentMemoryBindingRequest(BaseModel):
    enabled: bool = True
    scope_ref: str | None = None
    access: str = "read_write"


class RegisterAgentProfileRequest(BaseModel):
    id: str
    name: str
    enabled: bool = True
    identity: AgentIdentityRequest = Field(default_factory=AgentIdentityRequest)
    instruction_policy: AgentInstructionPolicyRequest = Field(
        default_factory=AgentInstructionPolicyRequest,
    )
    llm_routing_policy: AgentLlmRoutingPolicyRequest
    llm_policy: AgentLlmPolicyRequest = Field(default_factory=AgentLlmPolicyRequest)
    execution_policy: AgentExecutionPolicyRequest = Field(
        default_factory=AgentExecutionPolicyRequest,
    )
    runtime_preferences: AgentRuntimePreferencesRequest = Field(
        default_factory=AgentRuntimePreferencesRequest,
    )
    memory: AgentMemoryBindingRequest = Field(default_factory=AgentMemoryBindingRequest)
    reason: str | None = None
    actor: str | None = None


class UpdateAgentProfileRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    identity: AgentIdentityRequest | None = None
    instruction_policy: AgentInstructionPolicyRequest | None = None
    llm_routing_policy: AgentLlmRoutingPolicyRequest | None = None
    llm_policy: AgentLlmPolicyRequest | None = None
    execution_policy: AgentExecutionPolicyRequest | None = None
    runtime_preferences: AgentRuntimePreferencesRequest | None = None
    memory: AgentMemoryBindingRequest | None = None
    reason: str | None = None
    actor: str | None = None


class AgentProfileActionRequest(BaseModel):
    reason: str | None = None
    actor: str | None = None


class MigrateAgentHomeRequest(BaseModel):
    home_dir: str
    workdir: str | None = None


class SyncAgentHomeRequest(BaseModel):
    home_dir: str | None = None


class ExportAgentHomeRequest(BaseModel):
    home_dir: str | None = None


class AgentHomeFileRequest(BaseModel):
    name: str
    content: str


class UpdateAgentHomeFilesRequest(BaseModel):
    files: list[AgentHomeFileRequest] = Field(default_factory=list)
