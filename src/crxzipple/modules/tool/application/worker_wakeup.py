from __future__ import annotations

from threading import Event as ThreadEvent

from crxzipple.modules.events.domain import EventTopicWatch
from crxzipple.modules.tool.application.dispatch_events import ToolRuntimeEventService
from crxzipple.modules.tool.application.ports import ToolEventWaitPort
from crxzipple.shared.domain.events import named_event_topic


def wait_for_worker_wakeup(
    *,
    stop_event: ThreadEvent,
    timeout_seconds: float,
    events_service: ToolEventWaitPort | None,
    runtime_event_service: ToolRuntimeEventService | None,
) -> None:
    if events_service is None:
        stop_event.wait(timeout_seconds)
        return
    watches = [
        EventTopicWatch(
            topic=named_event_topic("tool.assignment.created"),
            after_cursor=events_service.snapshot_event_topic(
                named_event_topic("tool.assignment.created"),
            ),
        ),
    ]
    if runtime_event_service is not None:
        watches.extend(runtime_event_service.build_wait_watches())
    events_service.wait_for_event_topics(
        tuple(watches),
        timeout_seconds=timeout_seconds,
        stop_event=stop_event,
    )


__all__ = ["wait_for_worker_wakeup"]
