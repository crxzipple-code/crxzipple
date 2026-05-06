from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from crxzipple.core.logger import get_logger
from crxzipple.modules.orchestration.application.scheduler_service import (
    OrchestrationSchedulerService,
)
from crxzipple.shared.domain.events import Event

logger = get_logger(__name__)


@dataclass(slots=True)
class OrchestrationToolTerminalReaction:
    scheduler_service: OrchestrationSchedulerService
    tool_run_lookup: Callable[[str], object] | None = None

    def react_to_terminal_tool_run(self, event: Event) -> None:
        tool_run_id = event.payload.get("run_id")
        if not isinstance(tool_run_id, str) or not tool_run_id.strip():
            return
        mode = event.payload.get("mode")
        normalized_mode = mode.strip().lower() if isinstance(mode, str) else ""
        if not normalized_mode:
            normalized_mode = self._lookup_tool_run_mode(tool_run_id)
        if normalized_mode != "background":
            logger.debug(
                "ignored non-background or unresolved tool terminal event for orchestration resume",
                extra={
                    "event_name": event.name,
                    "tool_run_id": tool_run_id,
                    "mode": normalized_mode or None,
                },
            )
            return
        try:
            signal = self.scheduler_service.queue_tool_terminal_signal(
                tool_run_id=tool_run_id,
            )
        except Exception:
            logger.exception(
                "failed to handle orchestration tool reaction",
                extra={
                    "event_name": event.name,
                    "tool_run_id": tool_run_id,
                },
            )
            return
        logger.info(
            "queued orchestration scheduler signal from tool reaction",
            extra={
                "event_name": event.name,
                "tool_run_id": tool_run_id,
                "signal_id": signal.id,
            },
        )

    def _lookup_tool_run_mode(self, tool_run_id: str) -> str:
        if self.tool_run_lookup is None:
            return ""
        try:
            tool_run = self.tool_run_lookup(tool_run_id)
        except Exception:
            logger.debug(
                "could not resolve tool run mode for terminal event",
                exc_info=True,
                extra={"tool_run_id": tool_run_id},
            )
            return ""
        target = getattr(tool_run, "target", None)
        mode = getattr(target, "mode", None)
        raw_mode = getattr(mode, "value", mode)
        return raw_mode.strip().lower() if isinstance(raw_mode, str) else ""
