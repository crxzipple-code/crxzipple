from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol

from crxzipple.modules.llm.domain.entities import LlmInvocation, LlmProfile
from crxzipple.modules.llm.domain.exceptions import (
    LlmInvocationNotFoundError,
    LlmResponseItemNotFoundError,
)
from crxzipple.modules.llm.domain.repositories import (
    LlmInvocationRepository,
    LlmProfileRepository,
)
from crxzipple.modules.llm.domain import (
    LlmContinuationSignal,
    LlmErrorPayload,
    LlmResponseEvent,
    LlmResponseEventRetentionPolicy,
    LlmResponseEventType,
    LlmResponseItem,
    LlmResult,
)
from crxzipple.shared.domain.aggregates import AggregateRoot
from crxzipple.shared.domain.events import Event


class LlmInvocationUnitOfWork(Protocol):
    llm_profiles: LlmProfileRepository
    llm_invocations: LlmInvocationRepository

    def __enter__(self) -> "LlmInvocationUnitOfWork": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None: ...

    def collect(self, aggregate: AggregateRoot[Any]) -> None: ...

    def commit(self) -> None: ...


InvocationSucceededPayloadBuilder = Callable[
    [LlmInvocation, LlmProfile | None, bool],
    dict[str, Any],
]
InvocationFailedPayloadBuilder = Callable[
    [LlmInvocation, LlmProfile | None, LlmErrorPayload, bool],
    dict[str, Any],
]


class LlmInvocationService:
    def __init__(
        self,
        uow_factory: Callable[[], LlmInvocationUnitOfWork],
        *,
        response_event_retention_policy: LlmResponseEventRetentionPolicy,
        succeeded_payload_builder: InvocationSucceededPayloadBuilder,
        failed_payload_builder: InvocationFailedPayloadBuilder,
    ) -> None:
        self._uow_factory = uow_factory
        self._response_event_retention_policy = response_event_retention_policy
        self._succeeded_payload_builder = succeeded_payload_builder
        self._failed_payload_builder = failed_payload_builder

    def get_invocation(self, invocation_id: str) -> LlmInvocation:
        with self._uow_factory() as uow:
            invocation = uow.llm_invocations.get(invocation_id)
            if invocation is None:
                raise LlmInvocationNotFoundError(
                    f"LLM invocation '{invocation_id}' was not found.",
                )
            return invocation

    def get_response_item(self, item_id: str) -> LlmResponseItem:
        with self._uow_factory() as uow:
            item = uow.llm_invocations.get_response_item(item_id)
            if item is None:
                raise LlmResponseItemNotFoundError(
                    f"LLM response item '{item_id}' was not found.",
                )
            return item

    def list_invocations(
        self,
        *,
        llm_id: str | None = None,
        run_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[LlmInvocation]:
        with self._uow_factory() as uow:
            return uow.llm_invocations.list(
                llm_id=llm_id,
                run_id=run_id,
                limit=limit,
                offset=offset,
            )

    def list_response_events(
        self,
        invocation_id: str,
        *,
        limit: int | None = None,
        after_sequence: int | None = None,
    ) -> list[LlmResponseEvent]:
        with self._uow_factory() as uow:
            if uow.llm_invocations.get(invocation_id) is None:
                raise LlmInvocationNotFoundError(
                    f"LLM invocation '{invocation_id}' was not found.",
                )
            return uow.llm_invocations.list_response_events(
                invocation_id,
                limit=limit,
                after_sequence=after_sequence,
            )

    def response_event_retention_policy(self) -> LlmResponseEventRetentionPolicy:
        return self._response_event_retention_policy

    def record_response_event(
        self,
        invocation_id: str,
        *,
        sequence: int,
        event_type: str,
        data: Mapping[str, Any],
    ) -> None:
        with self._uow_factory() as uow:
            uow.llm_invocations.add_response_event(
                LlmResponseEvent(
                    id=f"{invocation_id}:event:{sequence}",
                    invocation_id=invocation_id,
                    sequence_no=sequence,
                    type=_coerce_response_event_type(event_type),
                    item_id=(
                        str(data["item_id"])
                        if data.get("item_id") not in {None, ""}
                        else None
                    ),
                    delta_payload=dict(data),
                    provider_payload=dict(data.get("provider_payload", {}))
                    if isinstance(data.get("provider_payload"), dict)
                    else {},
                ),
            )
            uow.commit()

    def store_started_invocation(self, invocation: LlmInvocation) -> None:
        with self._uow_factory() as uow:
            uow.llm_invocations.add(invocation)
            uow.collect(invocation)
            uow.commit()

    def complete_invocation(
        self,
        invocation_id: str,
        result: LlmResult,
        *,
        response_items: tuple[LlmResponseItem, ...] = (),
        continuation: LlmContinuationSignal | None = None,
        provider_request_id: str | None = None,
        streaming: bool = False,
    ) -> LlmInvocation:
        with self._uow_factory() as uow:
            stored = uow.llm_invocations.get(invocation_id)
            if stored is None:
                raise LlmInvocationNotFoundError(
                    f"LLM invocation '{invocation_id}' was not found.",
                )
            result_summary = (
                LlmResult.from_response_items(
                    response_items,
                    usage=result.usage,
                    finish_reason=result.finish_reason,
                    metadata=result.metadata,
                    structured_output=result.structured_output,
                )
                if response_items
                else result
            )
            stored.succeed(
                result_summary,
                response_items=response_items,
                continuation=continuation,
                provider_request_id=provider_request_id,
            )
            profile = uow.llm_profiles.get(stored.llm_id)
            stored.record_event(
                Event(
                    name="llm.invocation_succeeded",
                    payload=self._succeeded_payload_builder(
                        stored,
                        profile,
                        streaming,
                    ),
                ),
            )
            uow.llm_invocations.add(stored)
            uow.collect(stored)
            uow.commit()
            return stored

    def fail_invocation(
        self,
        invocation_id: str,
        error: LlmErrorPayload,
        *,
        streaming: bool = False,
    ) -> LlmInvocation:
        with self._uow_factory() as uow:
            stored = uow.llm_invocations.get(invocation_id)
            if stored is None:
                raise LlmInvocationNotFoundError(
                    f"LLM invocation '{invocation_id}' was not found.",
                )
            stored.fail(error)
            profile = uow.llm_profiles.get(stored.llm_id)
            stored.record_event(
                Event(
                    name="llm.invocation_failed",
                    payload=self._failed_payload_builder(
                        stored,
                        profile,
                        error,
                        streaming,
                    ),
                ),
            )
            uow.llm_invocations.add(stored)
            uow.collect(stored)
            uow.commit()
            return stored


def _coerce_response_event_type(event_type: str) -> LlmResponseEventType:
    try:
        return LlmResponseEventType(event_type)
    except ValueError:
        if event_type == "text_delta":
            return LlmResponseEventType.TEXT_DELTA
        if event_type == "completed":
            return LlmResponseEventType.COMPLETED
        if event_type == "failed":
            return LlmResponseEventType.FAILED
        if event_type == "invocation_started":
            return LlmResponseEventType.INVOCATION_STARTED
        return LlmResponseEventType.ITEM_COMPLETED
