from __future__ import annotations

from dataclasses import dataclass

from crxzipple.core.logger import get_logger
from crxzipple.modules.orchestration.application.services import (
    OrchestrationApplicationService,
)
from crxzipple.shared.domain.events import DomainEvent


logger = get_logger(__name__)


@dataclass(slots=True)
class OrchestrationToolEventSubscriber:
    service: OrchestrationApplicationService

    def handle_terminal_tool_run(self, event: DomainEvent) -> None:
        tool_run_id = event.payload.get("run_id")
        if not isinstance(tool_run_id, str) or not tool_run_id.strip():
            return
        try:
            resumed = self.service.handle_terminal_tool_run(tool_run_id)
        except Exception:
            logger.exception(
                "failed to handle orchestration tool event",
                extra={
                    "event_name": event.name,
                    "tool_run_id": tool_run_id,
                },
            )
            return
        if resumed:
            logger.info(
                "resumed waiting orchestration runs from tool event",
                extra={
                    "event_name": event.name,
                    "tool_run_id": tool_run_id,
                    "run_ids": [run.id for run in resumed],
                },
            )
