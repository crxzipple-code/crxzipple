from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from crxzipple.core.logger import get_logger
from crxzipple.modules.events.domain import EventTopicWatch
from crxzipple.modules.tool.application.ports import ToolEventSubscriptionStreamPort
from crxzipple.shared.domain.events import Event, named_event_topic


logger = get_logger(__name__)


class ToolDispatchRecoveryHandler(Protocol):
    def handle_recovered_dispatch_task(
        self,
        *,
        tool_run_id: str,
        reason: str,
    ) -> object:
        ...


@dataclass(slots=True)
class ToolDispatchEventSubscriber:
    service: ToolDispatchRecoveryHandler

    def handle_recovered_dispatch_task(self, event: Event) -> None:
        if event.payload.get("owner_kind") != "tool_run":
            return
        tool_run_id = event.payload.get("owner_id")
        reason = event.payload.get("reason")
        if not isinstance(tool_run_id, str) or not tool_run_id.strip():
            return
        if not isinstance(reason, str) or not reason.strip():
            return
        try:
            self.service.handle_recovered_dispatch_task(
                tool_run_id=tool_run_id,
                reason=reason,
            )
        except Exception:
            logger.exception(
                "failed to reconcile recovered dispatch task for tool run",
                extra={
                    "event_name": event.name,
                    "tool_run_id": tool_run_id,
                },
            )


@dataclass(slots=True)
class ToolRuntimeEventService:
    """Owned event pump for tool lifecycle reactions."""

    events_service: ToolEventSubscriptionStreamPort
    dispatch_subscriber: ToolDispatchEventSubscriber
    subscription_id: str = "tool.runtime.dispatch-recovery"
    source_topic: str = named_event_topic("dispatch.task.recovered")

    def process_available_events(self, *, limit: int = 100) -> int:
        state = self.events_service.get_subscription_cursor(
            self.subscription_id,
            source_topic=self.source_topic,
        )
        records = self.events_service.read_event_topic(
            self.source_topic,
            after_cursor=state.cursor if state is not None else None,
            limit=max(int(limit), 1),
        )
        processed_count = 0
        last_cursor: str | None = None
        for record in records:
            self.dispatch_subscriber.handle_recovered_dispatch_task(record.envelope)
            processed_count += 1
            last_cursor = record.cursor
        if last_cursor is not None:
            self.events_service.set_subscription_cursor(
                self.subscription_id,
                source_topic=self.source_topic,
                cursor=last_cursor,
            )
        return processed_count

    def build_wait_watches(self) -> tuple[EventTopicWatch, ...]:
        state = self.events_service.get_subscription_cursor(
            self.subscription_id,
            source_topic=self.source_topic,
        )
        return (
            EventTopicWatch(
                topic=self.source_topic,
                after_cursor=state.cursor if state is not None else None,
            ),
        )
