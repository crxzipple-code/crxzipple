from __future__ import annotations

from pydantic import BaseModel, Field

from crxzipple.modules.orchestration.application import ResolveSessionBundleInput
from crxzipple.modules.session.application import (
    AppendSessionMessageInput,
    EnsureSessionInput,
    ResetSessionInput,
)
from crxzipple.modules.session.domain import (
    DirectSessionScope,
    SessionMessageKind,
    SessionMessageVisibility,
)
from crxzipple.modules.session.interfaces.dto import (
    ResolveSessionDTO,
    SessionDTO,
    SessionInstanceDTO,
    SessionMessageDTO,
    SessionRuntimeBindingDTO,
)
from crxzipple.modules.session.interfaces.shared import (
    SessionInterfaceErrorFactory,
    build_ensure_session_input,
    build_reset_policy,
    build_resolve_session_bundle_input,
)


class SessionRuntimeBindingPayload(BaseModel):
    agent_id: str | None = None
    workspace: str | None = None

    @classmethod
    def from_dto(
        cls,
        binding: SessionRuntimeBindingDTO,
    ) -> "SessionRuntimeBindingPayload":
        return cls(
            agent_id=binding.agent_id,
            workspace=binding.workspace,
        )

    def to_payload(self) -> dict[str, object]:
        return self.model_dump(exclude_none=True)


class SessionRequest(BaseModel):
    key: str
    runtime_binding: SessionRuntimeBindingPayload
    status: str = "active"
    channel: str | None = None
    chat_type: str | None = None
    origin: dict[str, object] | None = None
    delivery: dict[str, object] | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    active_session_id: str | None = None

    def to_input(
        self,
        *,
        error_factory: SessionInterfaceErrorFactory,
    ) -> EnsureSessionInput:
        return build_ensure_session_input(
            key=self.key,
            runtime_binding_payload=self.runtime_binding.to_payload(),
            status=self.status,
            channel=self.channel,
            chat_type=self.chat_type,
            origin_payload=self.origin,
            delivery_payload=self.delivery,
            metadata=self.metadata,
            active_session_id=self.active_session_id,
            error_factory=error_factory,
        )


class SessionResponse(BaseModel):
    key: str
    runtime_binding: SessionRuntimeBindingPayload
    active_session_id: str
    status: str
    channel: str | None = None
    chat_type: str | None = None
    origin: dict[str, object] = Field(default_factory=dict)
    delivery: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    last_reset_at: str

    @classmethod
    def from_dto(cls, dto: SessionDTO) -> "SessionResponse":
        return cls(
            key=dto.key,
            runtime_binding=SessionRuntimeBindingPayload.from_dto(dto.runtime_binding),
            active_session_id=dto.active_session_id,
            status=dto.status,
            channel=dto.channel,
            chat_type=dto.chat_type,
            origin=dto.origin,
            delivery=dto.delivery,
            metadata=dto.metadata,
            created_at=dto.created_at.isoformat(),
            updated_at=dto.updated_at.isoformat(),
            last_reset_at=dto.last_reset_at.isoformat(),
        )


class AppendSessionMessageRequest(BaseModel):
    role: str
    kind: SessionMessageKind = SessionMessageKind.MESSAGE
    content_payload: dict[str, object] = Field(default_factory=dict)
    source_kind: str | None = None
    source_id: str | None = None
    visibility: SessionMessageVisibility = SessionMessageVisibility.DEFAULT
    metadata: dict[str, object] = Field(default_factory=dict)
    session_id: str | None = None

    def to_input(self, *, session_key: str) -> AppendSessionMessageInput:
        return AppendSessionMessageInput(
            session_key=session_key,
            role=self.role,
            kind=self.kind,
            content_payload=self.content_payload,
            source_kind=self.source_kind,
            source_id=self.source_id,
            visibility=self.visibility,
            metadata=self.metadata,
            session_id=self.session_id,
        )


class SessionMessageResponse(BaseModel):
    id: str
    session_key: str
    session_id: str
    sequence_no: int
    role: str
    kind: str
    content_payload: dict[str, object] = Field(default_factory=dict)
    source_kind: str | None = None
    source_id: str | None = None
    visibility: str
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: str

    @classmethod
    def from_dto(cls, dto: SessionMessageDTO) -> "SessionMessageResponse":
        return cls(
            id=dto.id,
            session_key=dto.session_key,
            session_id=dto.session_id,
            sequence_no=dto.sequence_no,
            role=dto.role,
            kind=dto.kind,
            content_payload=dto.content_payload,
            source_kind=dto.source_kind,
            source_id=dto.source_id,
            visibility=dto.visibility,
            metadata=dto.metadata,
            created_at=dto.created_at.isoformat(),
        )


class SessionInstanceResponse(BaseModel):
    id: str
    session_key: str
    runtime_binding: SessionRuntimeBindingPayload
    sequence_no: int
    kind: str
    status: str
    opened_at: str
    closed_at: str | None = None
    reset_reason: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @classmethod
    def from_dto(cls, dto: SessionInstanceDTO) -> "SessionInstanceResponse":
        return cls(
            id=dto.id,
            session_key=dto.session_key,
            runtime_binding=SessionRuntimeBindingPayload.from_dto(dto.runtime_binding),
            sequence_no=dto.sequence_no,
            kind=dto.kind,
            status=dto.status,
            opened_at=dto.opened_at.isoformat(),
            closed_at=dto.closed_at.isoformat() if dto.closed_at is not None else None,
            reset_reason=dto.reset_reason,
            metadata=dto.metadata,
        )


class ResolveSessionPolicyRequest(BaseModel):
    idle_minutes: int | None = Field(default=None, ge=1)
    daily_reset_hour_utc: int | None = Field(default=None, ge=0, le=23)

    def to_value_object(self):
        return build_reset_policy(
            idle_minutes=self.idle_minutes,
            daily_reset_hour_utc=self.daily_reset_hour_utc,
        )


class ResolveSessionRequest(BaseModel):
    agent_id: str
    channel: str | None = None
    chat_type: str = "direct"
    peer_id: str | None = None
    conversation_id: str | None = None
    thread_id: str | None = None
    account_id: str | None = None
    label: str | None = None
    surface: str | None = None
    main_key: str = "main"
    direct_scope: DirectSessionScope = DirectSessionScope.MAIN
    status: str = "active"
    metadata: dict[str, object] = Field(default_factory=dict)
    ensure: bool = False
    touch_activity: bool = True
    reset_policy: ResolveSessionPolicyRequest | None = None

    def to_input(self) -> ResolveSessionBundleInput:
        return build_resolve_session_bundle_input(
            agent_id=self.agent_id,
            channel=self.channel,
            chat_type=self.chat_type,
            peer_id=self.peer_id,
            conversation_id=self.conversation_id,
            thread_id=self.thread_id,
            account_id=self.account_id,
            label=self.label,
            surface=self.surface,
            main_key=self.main_key,
            direct_scope=self.direct_scope,
            status=self.status,
            metadata=self.metadata,
            ensure=self.ensure,
            touch_activity=self.touch_activity,
            reset_policy=(
                self.reset_policy.to_value_object()
                if self.reset_policy is not None
                else None
            ),
        )


class ResolveSessionResponse(BaseModel):
    key: str
    kind: str
    created: bool
    reset: bool
    reset_reason: str | None = None
    session: SessionResponse | None = None
    active_instance: SessionInstanceResponse | None = None

    @classmethod
    def from_dto(cls, dto: ResolveSessionDTO) -> "ResolveSessionResponse":
        return cls(
            key=dto.key,
            kind=dto.kind,
            created=dto.created,
            reset=dto.reset,
            reset_reason=dto.reset_reason,
            session=SessionResponse.from_dto(dto.session) if dto.session is not None else None,
            active_instance=(
                SessionInstanceResponse.from_dto(dto.active_instance)
                if dto.active_instance is not None
                else None
            ),
        )


class ResetSessionRequest(BaseModel):
    status: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    active_session_id: str | None = None
    reason: str | None = None

    def to_input(self, *, session_key: str) -> ResetSessionInput:
        return ResetSessionInput(
            session_key=session_key,
            status=self.status,
            metadata=self.metadata,
            active_session_id=self.active_session_id,
            reason=self.reason,
        )
