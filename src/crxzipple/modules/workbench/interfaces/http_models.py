from __future__ import annotations

from pydantic import BaseModel, Field


class WorkbenchToolExecutionPolicyResponse(BaseModel):
    timeout_seconds: int
    requires_confirmation: bool
    mutates_state: bool


class WorkbenchToolSummaryResponse(BaseModel):
    id: str
    name: str
    description: str
    kind: str
    tags: list[str] = Field(default_factory=list)
    required_effect_ids: list[str] = Field(default_factory=list)
    execution_policy: WorkbenchToolExecutionPolicyResponse
    enabled: bool


class WorkbenchAgentLlmRoutingPolicyResponse(BaseModel):
    default_llm_id: str
    fallback_llm_ids: list[str] = Field(default_factory=list)
    image_llm_id: str | None = None
    document_llm_id: str | None = None


class WorkbenchAgentMemoryResponse(BaseModel):
    enabled: bool = False
    scope_ref: str | None = None
    access: str = "private"


class WorkbenchAgentProfileResponse(BaseModel):
    id: str
    name: str
    description: str
    enabled: bool
    llm_routing_policy: WorkbenchAgentLlmRoutingPolicyResponse
    memory: WorkbenchAgentMemoryResponse | None = None


class WorkbenchLlmProfileResponse(BaseModel):
    id: str
    provider: str
    api_family: str
    model_name: str
    model_family: str
    capabilities: list[str] = Field(default_factory=list)
    enabled: bool
