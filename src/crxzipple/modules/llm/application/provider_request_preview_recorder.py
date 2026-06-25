from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from crxzipple.modules.llm.application.adapters import LlmAdapterRequest
from crxzipple.modules.llm.application.provider_request_input_preview import (
    provider_input_preview_from_request_metadata,
)
from crxzipple.modules.llm.domain.entities import LlmInvocation, LlmProfile
from crxzipple.modules.llm.domain.exceptions import LlmInvocationNotFoundError
from crxzipple.modules.llm.domain.repositories import (
    LlmInvocationRepository,
    LlmProfileRepository,
)
from crxzipple.shared.domain.aggregates import AggregateRoot
from crxzipple.shared.domain.events import Event


class ProviderRequestPreviewUnitOfWork(Protocol):
    llm_profiles: LlmProfileRepository
    llm_invocations: LlmInvocationRepository

    def __enter__(self) -> "ProviderRequestPreviewUnitOfWork": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None: ...

    def collect(self, aggregate: AggregateRoot[Any]) -> None: ...

    def commit(self) -> None: ...


ProviderRequestPreparedPayloadBuilder = Callable[
    [LlmInvocation, LlmProfile | None],
    dict[str, Any],
]


class ProviderRequestPreviewRecorder:
    def __init__(
        self,
        uow_factory: Callable[[], ProviderRequestPreviewUnitOfWork],
        *,
        event_payload_builder: ProviderRequestPreparedPayloadBuilder,
    ) -> None:
        self._uow_factory = uow_factory
        self._event_payload_builder = event_payload_builder

    def preview(
        self,
        adapter: object,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> dict[str, object]:
        preview_request = getattr(adapter, "preview_request", None)
        if callable(preview_request):
            try:
                preview = preview_request(profile, request)
                if isinstance(preview, dict):
                    return dict(preview)
            except Exception as exc:
                return {
                    "preview_source": "provider_adapter",
                    "preview_error": str(exc) or type(exc).__name__,
                    "provider": profile.provider.value,
                    "api_family": profile.api_family.value,
                    "model": profile.model_name,
                }
        return {
            "preview_source": "normalized_fallback",
            "provider": profile.provider.value,
            "api_family": profile.api_family.value,
            "model": profile.model_name,
            "message_count": len(request.messages),
            "message_roles": [message.role.value for message in request.messages],
            "input_item_count": len(request.input_items),
            "input_item_kinds": [item.kind.value for item in request.input_items],
            "tool_count": len(request.tool_schemas),
            "response_format_configured": request.response_format is not None,
            "override_keys": sorted(str(key) for key in request.overrides),
            **provider_input_preview_from_request_metadata(request.request_metadata),
        }

    def record(
        self,
        invocation_id: str,
        preview: dict[str, object],
    ) -> None:
        with self._uow_factory() as uow:
            stored = uow.llm_invocations.get(invocation_id)
            if stored is None:
                raise LlmInvocationNotFoundError(
                    f"LLM invocation '{invocation_id}' was not found.",
                )
            stored.record_provider_request_payload_preview(preview)
            profile = uow.llm_profiles.get(stored.llm_id)
            stored.record_event(
                Event(
                    name="llm.invocation_provider_request_prepared",
                    payload=self._event_payload_builder(stored, profile),
                ),
            )
            uow.llm_invocations.add(stored)
            uow.collect(stored)
            uow.commit()

    def record_for_invocation(
        self,
        invocation: LlmInvocation,
        *,
        adapter: object,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> None:
        invocation.record_provider_request_payload_preview(
            self.preview(adapter, profile, request),
        )
