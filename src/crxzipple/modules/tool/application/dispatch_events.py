from __future__ import annotations

from dataclasses import dataclass

from crxzipple.core.logger import get_logger
from crxzipple.modules.tool.application.services import ToolApplicationService
from crxzipple.shared.domain.events import DomainEvent


logger = get_logger(__name__)


@dataclass(slots=True)
class ToolDispatchEventSubscriber:
    service: ToolApplicationService

    def handle_recovered_dispatch_task(self, event: DomainEvent) -> None:
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
