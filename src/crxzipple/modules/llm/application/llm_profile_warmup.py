from __future__ import annotations

from typing import Any, Callable, Protocol

from crxzipple.modules.llm.application.adapters import LlmAdapterGateway
from crxzipple.modules.llm.application.llm_adapter_request_builder import (
    LlmAdapterRequestBuilder,
)
from crxzipple.modules.llm.application.llm_invocation_events import (
    profile_warmup_event_payload,
)
from crxzipple.modules.llm.application.llm_invocation_inputs import (
    WarmupLlmProfileInput,
    WarmupLlmProfileResult,
)
from crxzipple.modules.llm.domain.exceptions import (
    LlmAdapterNotConfiguredError,
    LlmInvocationNotAllowedError,
    LlmNotFoundError,
)
from crxzipple.modules.llm.domain.repositories import LlmProfileRepository
from crxzipple.shared.domain.aggregates import AggregateRoot
from crxzipple.shared.domain.events import Event


class LlmProfileWarmupUnitOfWork(Protocol):
    llm_profiles: LlmProfileRepository

    def __enter__(self) -> "LlmProfileWarmupUnitOfWork": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None: ...

    def collect(self, aggregate: AggregateRoot[Any]) -> None: ...

    def commit(self) -> None: ...


class LlmProfileWarmupService:
    def __init__(
        self,
        uow_factory: Callable[[], LlmProfileWarmupUnitOfWork],
        *,
        adapter_gateway: LlmAdapterGateway,
        adapter_request_builder: LlmAdapterRequestBuilder,
    ) -> None:
        self._uow_factory = uow_factory
        self._adapter_gateway = adapter_gateway
        self._adapter_request_builder = adapter_request_builder

    def warmup_profile(
        self,
        data: WarmupLlmProfileInput,
    ) -> WarmupLlmProfileResult:
        with self._uow_factory() as uow:
            profile = uow.llm_profiles.get(data.llm_id)
            if profile is None:
                raise LlmNotFoundError(f"LLM profile '{data.llm_id}' was not found.")
            if not profile.enabled:
                raise LlmInvocationNotAllowedError(
                    f"LLM profile '{profile.id}' is disabled.",
                )

        adapter = self._adapter_gateway.get(profile.api_family)
        if adapter is None:
            self._record_warmup_event(
                profile.id,
                "llm.profile_warmup_failed",
                profile_warmup_event_payload(
                    profile,
                    status="failed",
                    details={
                        "reason": "adapter_not_configured",
                        "api_family": profile.api_family.value,
                    },
                ),
            )
            raise LlmAdapterNotConfiguredError(
                f"No llm adapter is configured for api family '{profile.api_family.value}'.",
            )
        warmup_websocket = getattr(adapter, "warmup_websocket", None)
        if not callable(warmup_websocket):
            details = {"reason": "adapter_warmup_not_supported"}
            self._record_warmup_event(
                profile.id,
                "llm.profile_warmup_skipped",
                profile_warmup_event_payload(
                    profile,
                    status="skipped",
                    details=details,
                ),
            )
            return WarmupLlmProfileResult(
                llm_id=profile.id,
                status="skipped",
                details=details,
            )
        try:
            details = warmup_websocket(
                profile,
                resolved_credential=(
                    self._adapter_request_builder.resolve_profile_credential(profile)
                ),
            )
        except Exception as exc:
            self._record_warmup_event(
                profile.id,
                "llm.profile_warmup_failed",
                profile_warmup_event_payload(
                    profile,
                    status="failed",
                    details={
                        "reason": str(exc) or type(exc).__name__,
                        "error_type": type(exc).__name__,
                    },
                ),
            )
            raise
        detail_payload = dict(details) if isinstance(details, dict) else {}
        self._record_warmup_event(
            profile.id,
            "llm.profile_warmup_succeeded",
            profile_warmup_event_payload(
                profile,
                status="warmed",
                details=detail_payload,
            ),
        )
        return WarmupLlmProfileResult(
            llm_id=profile.id,
            status="warmed",
            details=detail_payload,
        )

    def _record_warmup_event(
        self,
        llm_id: str,
        event_name: str,
        payload: dict[str, Any],
    ) -> None:
        with self._uow_factory() as uow:
            profile = uow.llm_profiles.get(llm_id)
            if profile is None:
                return
            profile.record_event(Event(name=event_name, payload=payload))
            uow.llm_profiles.add(profile)
            uow.collect(profile)
            uow.commit()
