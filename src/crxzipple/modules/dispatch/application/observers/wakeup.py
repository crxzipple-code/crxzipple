from __future__ import annotations

from dataclasses import dataclass

from crxzipple.core.logger import get_logger
from crxzipple.modules.events import EventsApplicationService
from crxzipple.shared.domain.events import Event

logger = get_logger(__name__)


def dispatch_wakeup_topic(owner_kind: str) -> str:
    normalized = owner_kind.strip()
    if not normalized:
        raise ValueError("owner_kind is required to build a dispatch wakeup topic.")
    return f"dispatch.wakeup.{normalized}"


@dataclass(slots=True)
class DispatchWakeupObserver:
    events_service: EventsApplicationService

    def observe_task_queued(self, event: Event) -> None:
        self._observe_wakeup(event)

    def observe_task_requeued(self, event: Event) -> None:
        self._observe_wakeup(event)

    def observe_task_recovered(self, event: Event) -> None:
        self._observe_wakeup(event)

    def _observe_wakeup(self, event: Event) -> None:
        owner_kind = event.payload.get("owner_kind")
        owner_id = event.payload.get("owner_id")
        if not isinstance(owner_kind, str) or not owner_kind.strip():
            logger.debug(
                "skipping dispatch wakeup observation without owner_kind",
                extra={"event_name": event.name, "payload": event.payload},
            )
            return
        try:
            topic = dispatch_wakeup_topic(owner_kind)
        except ValueError:
            logger.debug(
                "skipping invalid dispatch wakeup topic",
                extra={"event_name": event.name, "owner_kind": owner_kind},
            )
            return
        payload: dict[str, object] = {
            "event_name": event.name,
            "owner_kind": owner_kind,
        }
        if isinstance(owner_id, str) and owner_id.strip():
            payload["owner_id"] = owner_id
        lane_key = event.payload.get("lane_key")
        if isinstance(lane_key, str) and lane_key.strip():
            payload["lane_key"] = lane_key
        task_id = event.payload.get("task_id")
        dedupe_key = (
            f"{event.name}:{task_id}"
            if isinstance(task_id, str) and task_id.strip()
            else event.name
        )
        self.events_service.publish(
            Event(
                topic=topic,
                kind="command",
                ordering_key=(
                    payload["owner_id"]
                    if isinstance(payload.get("owner_id"), str)
                    else None
                ),
                dedupe_key=dedupe_key,
                payload=payload,
            ),
        )
