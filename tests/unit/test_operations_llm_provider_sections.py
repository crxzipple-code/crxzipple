from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmInputItem,
    LlmInputItemKind,
    LlmInvocation,
    LlmInvocationStatus,
    LlmMessage,
    LlmMessageRole,
    LlmProfile,
    LlmProviderKind,
)
from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.llm_provider_readiness import (
    blocked_profiles,
    profile_access_readiness,
)
from crxzipple.modules.operations.application.read_models.llm_provider_sections import (
    model_availability_section,
    provider_access_health_section,
    provider_auth_blocked_section,
)
from crxzipple.modules.operations.application.read_models.llm_provider_warmup import (
    latest_warmup_events_by_profile,
    warmup_next_action,
    warmup_status_label,
)


class _AccessService:
    def __init__(self, *, ready: bool, status: str = "ready", reason: str = "ok") -> None:
        self._readiness = SimpleNamespace(
            ready=ready,
            status=SimpleNamespace(value=status),
            reason=reason,
        )

    def check_credential_binding(self, binding_id: str) -> SimpleNamespace:
        assert binding_id == "cred-openai"
        return self._readiness


def _profile(
    profile_id: str = "openai.gpt",
    *,
    enabled: bool = True,
    credential_binding_id: str | None = "cred-openai",
) -> LlmProfile:
    return LlmProfile(
        id=profile_id,
        provider=LlmProviderKind.OPENAI,
        api_family=LlmApiFamily.OPENAI_RESPONSES,
        model_name="gpt-5",
        enabled=enabled,
        credential_binding_id=credential_binding_id,
        context_window_tokens=4096,
        max_concurrency=2,
        timeout_seconds=30,
    )


def _invocation(invocation_id: str, *, llm_id: str = "openai.gpt") -> LlmInvocation:
    now = datetime(2026, 6, 21, 12, tzinfo=timezone.utc)
    return LlmInvocation(
        id=invocation_id,
        llm_id=llm_id,
        status=LlmInvocationStatus.SUCCEEDED,
        messages=(LlmMessage(role=LlmMessageRole.USER, content="hello"),),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "hello"},
            ),
        ),
        created_at=now,
    )


def _event(
    event_id: str,
    *,
    event_name: str,
    profile_id: str = "openai.gpt",
    occurred_at: datetime | None = None,
    payload: dict[str, object] | None = None,
) -> OperationsObservedEvent:
    occurred_at = occurred_at or datetime(2026, 6, 21, 12, tzinfo=timezone.utc)
    return OperationsObservedEvent(
        id=event_id,
        cursor=event_id,
        topic=f"events.named.{event_name}",
        event_name=event_name,
        module="llm",
        owner="llm",
        kind="fact",
        level="info",
        status="observed",
        entity_id=profile_id,
        run_id=None,
        trace_id=None,
        source_event_name=event_name,
        occurred_at=occurred_at,
        payload={"llm_id": profile_id, **dict(payload or {})},
    )


def test_profile_access_readiness_and_blocked_profiles_use_access_port() -> None:
    profile = _profile()
    disabled = _profile("disabled", enabled=False)

    ready = profile_access_readiness(
        profile,
        access_service=_AccessService(ready=True),
    )
    blocked = profile_access_readiness(
        profile,
        access_service=_AccessService(ready=False, status="waiting_user", reason="login"),
    )

    assert ready["ready"] is True
    assert blocked["status"] == "waiting_user"
    assert [item.id for item in blocked_profiles([profile, disabled], access_service=None)] == [
        "openai.gpt",
        "disabled",
    ]


def test_warmup_event_projection_keeps_latest_event_per_profile() -> None:
    older = _event(
        "old",
        event_name="llm.profile_warmup_failed",
        occurred_at=datetime(2026, 6, 21, 11, tzinfo=timezone.utc),
        payload={"reason": "token expired"},
    )
    newer = _event(
        "new",
        event_name="llm.profile_warmup_succeeded",
        occurred_at=datetime(2026, 6, 21, 12, tzinfo=timezone.utc),
        payload={"transport": "websocket"},
    )

    events = latest_warmup_events_by_profile((older, newer))

    assert events["openai.gpt"].id == "new"
    assert warmup_status_label(newer) == "Warmed (websocket)"
    assert warmup_next_action(newer, readiness={"ready": True}) == "Ready for run"


def test_provider_sections_project_access_health_blockers_and_model_availability() -> None:
    profile = _profile()
    no_credential = _profile("missing-cred", credential_binding_id=None)
    warmup = _event(
        "warmup",
        event_name="llm.profile_warmup_succeeded",
        payload={"transport": "websocket"},
    )

    access_health = provider_access_health_section(
        [profile, no_credential],
        invocations=[_invocation("invocation-1")],
        access_service=_AccessService(ready=True),
        warmup_events_by_profile={"openai.gpt": warmup},
    )
    blocked = provider_auth_blocked_section(
        [profile, no_credential],
        invocations=[_invocation("invocation-1")],
        access_service=_AccessService(ready=True),
        warmup_events_by_profile={"openai.gpt": warmup},
    )
    availability = model_availability_section(
        [profile, no_credential],
        access_service=_AccessService(ready=True),
    )

    access_rows = {row.id: row.cells for row in access_health.rows}
    blocked_rows = {row.id: row.cells for row in blocked.rows}
    availability_rows = {row.id: row.cells for row in availability.rows}

    assert access_health.id == "provider_access_health"
    assert access_rows["openai.gpt"]["status"] == "Available"
    assert access_rows["openai.gpt"]["warmup"] == "Warmed (websocket)"
    assert blocked_rows["missing-cred"]["issue"] == "profile has no access credential binding id"
    assert availability_rows["missing-cred"]["availability"] == "Auth Required"
