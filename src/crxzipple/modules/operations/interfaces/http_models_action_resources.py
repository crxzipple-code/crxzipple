from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from crxzipple.modules.operations.interfaces.http_models_action_base import (
    OperationsActionRequest,
)


class OperationsToolWorkerPruneRequest(OperationsActionRequest):
    retention_seconds: int = 3600


class OperationsLlmWarmupResponse(BaseModel):
    llm_id: str
    status: str
    details: dict[str, Any] = Field(default_factory=dict)


class OperationsSkillValidateRequest(OperationsActionRequest):
    path: str


class OperationsSkillInstallRequest(OperationsActionRequest):
    source_dir: str


class OperationsSkillSyncRequest(OperationsActionRequest):
    workspace_dir: str | None = None
    source_id: str | None = None
    surface: str = "interactive"


class OperationsAccessCheckRequest(OperationsActionRequest):
    requirements: list[str] = Field(default_factory=list)
    credential_bindings: list[str] = Field(default_factory=list)
    workspace_dir: str | None = None
    allow_literal_credentials: bool = False


class OperationsMemoryWriteLongTermRequest(OperationsActionRequest):
    agent_id: str
    content: str


class OperationsToolRunActionResponse(BaseModel):
    id: str
    tool_id: str
    status: str
    cancel_requested_at: str | None = None


class OperationsToolWorkerPruneResponse(BaseModel):
    pruned_count: int
    worker_ids: list[str]
    cutoff: str


class OperationsMemoryWriteResultResponse(BaseModel):
    path: str
    line_start: int
    line_end: int
    kind: str
