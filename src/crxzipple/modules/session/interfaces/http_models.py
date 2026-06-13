from __future__ import annotations

from pydantic import BaseModel, Field

from crxzipple.modules.session.application import (
    AppendSessionItemInput,
    EnsureSessionInput,
    ResolveSessionInput,
    ResetSessionInput,
)
from crxzipple.modules.session.domain import (
    DirectSessionScope,
    SessionItemKind,
    SessionItemPhase,
    SessionItemVisibility,
)
from crxzipple.modules.session.interfaces.dto import (
    ResolveSessionDTO,
    SessionDTO,
    SessionItemDTO,
    SessionInstanceDTO,
    SessionRuntimeBindingDTO,
)
from crxzipple.modules.session.interfaces.shared import (
    SessionInterfaceErrorFactory,
    build_ensure_session_input,
    build_reset_policy,
    build_resolve_session_input,
)
from crxzipple.shared.time import format_datetime_utc


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
    reply: dict[str, object] | None = None
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
            reply_payload=self.reply,
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
    reply: dict[str, object] = Field(default_factory=dict)
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
            reply=dto.reply,
            metadata=dto.metadata,
            created_at=format_datetime_utc(dto.created_at),
            updated_at=format_datetime_utc(dto.updated_at),
            last_reset_at=format_datetime_utc(dto.last_reset_at),
        )


class SessionItemVisibilityPayload(BaseModel):
    model_visible: bool = True
    user_visible: bool = False
    chat_visible: bool = False
    trace_visible: bool = True

    @classmethod
    def from_value_object(
        cls,
        visibility: dict[str, bool],
    ) -> "SessionItemVisibilityPayload":
        return cls(**visibility)

    def to_value_object(self) -> SessionItemVisibility:
        return SessionItemVisibility(
            model_visible=self.model_visible,
            user_visible=self.user_visible,
            chat_visible=self.chat_visible,
            trace_visible=self.trace_visible,
        )


class AppendSessionItemRequest(BaseModel):
    kind: SessionItemKind
    role: str | None = None
    phase: SessionItemPhase = SessionItemPhase.UNKNOWN
    content_payload: dict[str, object] = Field(default_factory=dict)
    visibility: SessionItemVisibilityPayload = Field(
        default_factory=SessionItemVisibilityPayload,
    )
    source_module: str | None = None
    source_kind: str | None = None
    source_id: str | None = None
    provider_item_id: str | None = None
    provider_item_type: str | None = None
    call_id: str | None = None
    tool_name: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    session_id: str | None = None

    def to_input(self, *, session_key: str) -> AppendSessionItemInput:
        return AppendSessionItemInput(
            session_key=session_key,
            kind=self.kind,
            role=self.role,
            phase=self.phase,
            content_payload=self.content_payload,
            visibility=self.visibility.to_value_object(),
            source_module=self.source_module,
            source_kind=self.source_kind,
            source_id=self.source_id,
            provider_item_id=self.provider_item_id,
            provider_item_type=self.provider_item_type,
            call_id=self.call_id,
            tool_name=self.tool_name,
            metadata=self.metadata,
            session_id=self.session_id,
        )


class SessionItemResponse(BaseModel):
    id: str
    session_key: str
    session_id: str
    sequence_no: int
    role: str | None = None
    kind: str
    phase: str
    content_payload: dict[str, object] = Field(default_factory=dict)
    visibility: SessionItemVisibilityPayload
    visibility_state: str = "active"
    source_module: str | None = None
    source_kind: str | None = None
    source_id: str | None = None
    provider_item_id: str | None = None
    provider_item_type: str | None = None
    call_id: str | None = None
    tool_name: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: str

    @classmethod
    def from_dto(cls, dto: SessionItemDTO) -> "SessionItemResponse":
        return cls(
            id=dto.id,
            session_key=dto.session_key,
            session_id=dto.session_id,
            sequence_no=dto.sequence_no,
            role=dto.role,
            kind=dto.kind,
            phase=dto.phase,
            content_payload=dto.content_payload,
            visibility=SessionItemVisibilityPayload.from_value_object(dto.visibility),
            visibility_state=_session_item_visibility_state(dto),
            source_module=dto.source_module,
            source_kind=dto.source_kind,
            source_id=dto.source_id,
            provider_item_id=dto.provider_item_id,
            provider_item_type=dto.provider_item_type,
            call_id=dto.call_id,
            tool_name=dto.tool_name,
            metadata=dto.metadata,
            created_at=format_datetime_utc(dto.created_at),
        )


def _session_item_visibility_state(dto: SessionItemDTO) -> str:
    return "archived" if dto.metadata.get("archived_by_compaction_run_id") else "active"


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
            opened_at=format_datetime_utc(dto.opened_at),
            closed_at=(
                format_datetime_utc(dto.closed_at)
                if dto.closed_at is not None
                else None
            ),
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

    def to_input(self) -> ResolveSessionInput:
        return build_resolve_session_input(
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
