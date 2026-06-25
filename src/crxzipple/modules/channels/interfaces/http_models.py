from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from crxzipple.modules.orchestration.domain import OrchestrationQueuePolicy
from crxzipple.modules.session.domain import DirectSessionScope


class WebChannelSubscriptionUpdateRequest(BaseModel):
    conversation_id: str | None = None
    channel_account_id: str | None = None


class WebChannelSubscriptionResponse(BaseModel):
    runtime_id: str
    channel_account_id: str | None = None
    connection_id: str
    conversation_id: str | None = None
    supports_streaming: bool
    updated_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelRuntimeSummaryResponse(BaseModel):
    runtime_id: str
    channel_type: str
    service_key: str | None = None
    status: str
    registered_at: str
    last_heartbeat_at: str
    account_count: int
    connection_count: int


class ChannelAccountBindingResponse(BaseModel):
    channel_type: str
    channel_account_id: str
    runtime_id: str
    updated_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelConnectionBindingResponse(BaseModel):
    channel_type: str
    connection_id: str
    runtime_id: str
    channel_account_id: str | None = None
    conversation_id: str | None = None
    supports_streaming: bool
    updated_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelRuntimeDetailResponse(BaseModel):
    runtime_id: str
    channel_type: str
    service_key: str | None = None
    status: str
    capabilities: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    registered_at: str
    last_heartbeat_at: str
    account_bindings: list[ChannelAccountBindingResponse] = Field(default_factory=list)
    connection_bindings: list[ChannelConnectionBindingResponse] = Field(default_factory=list)


class ChannelDeadLetterRecordResponse(BaseModel):
    cursor: str
    topic: str
    event_id: str
    kind: str
    created_at: str
    payload: dict[str, Any] = Field(default_factory=dict)
    target: dict[str, Any] = Field(default_factory=dict)


class ChannelDeadLetterReplayRequest(BaseModel):
    runtime_id: str | None = None
    cursor: str | None = None
    event_id: str | None = None


class ChannelDeadLetterReplayResponse(BaseModel):
    replayed: bool
    dead_letter_topic: str
    dead_letter_cursor: str
    dead_letter_event_id: str
    outbound_id: str
    replay_mode: str
    callback_status: str | None = None


class WebhookInboundRequest(BaseModel):
    content: Any
    callback_url: str
    idempotency_key: str | None = None
    agent_id: str | None = None
    llm_id: str | None = None
    chat_type: str = "direct"
    peer_id: str | None = None
    conversation_id: str
    thread_id: str | None = None
    main_key: str = "main"
    direct_scope: DirectSessionScope = DirectSessionScope.MAIN
    source: str = "webhook"
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.JUMP_QUEUE
    priority: int = Field(default=100, ge=0)
    max_steps: int | None = Field(default=None, ge=1)
    callback_metadata: dict[str, Any] = Field(default_factory=dict)


class WebhookInboundAcceptedResponse(BaseModel):
    run_id: str
    status: str
    session_key: str | None = None
    active_session_id: str | None = None
    callback_url: str


class LarkEventAcceptedResponse(BaseModel):
    code: int = 0
    msg: str = "ok"
    challenge: str | None = None
    run_id: str | None = None
    status: str | None = None
    session_key: str | None = None
    active_session_id: str | None = None


class ChannelProfileUpsertRequest(BaseModel):
    channel_type: str | None = None
    enabled: bool = True
    capabilities: dict[str, Any] = Field(default_factory=dict)
    accounts: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelProfileResponse(BaseModel):
    channel_type: str
    enabled: bool
    capabilities: dict[str, Any] = Field(default_factory=dict)
    accounts: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
