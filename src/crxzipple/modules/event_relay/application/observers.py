from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.core.logger import get_logger
from crxzipple.modules.orchestration.application.ports import (
    OrchestrationRunLookupPort,
    ToolExecutionPort,
)
from crxzipple.modules.orchestration.domain import OrchestrationRunNotFoundError
from crxzipple.modules.tool.domain.exceptions import ToolRunNotFoundError
from crxzipple.shared.domain.events import Event
from crxzipple.shared.orchestration_observation import (
    ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT,
)

from .events import (
    EVENT_RELAY_WORKBENCH_UPDATED_EVENT,
    WorkbenchRelayUpdate,
    workbench_home_topic,
    workbench_run_topic,
    workbench_session_topic,
    workbench_steps_topic,
)
from .ports import EventRelayPublishPort

logger = get_logger(__name__)


@dataclass(slots=True)
class WorkbenchEventRelayObserver:
    events_service: EventRelayPublishPort
    run_lookup: OrchestrationRunLookupPort | None = None
    tool_execution_port: ToolExecutionPort | None = None

    def observe_run_event(self, event: Event) -> None:
        run_id = _optional_text(event.payload.get("run_id"))
        if run_id is None:
            logger.debug(
                "skipping workbench relay run observation without run_id",
                extra={"event_name": event.name, "payload": event.payload},
            )
            return
        session_key = _optional_text(event.payload.get("session_key"))
        if self.run_lookup is not None:
            try:
                run = self.run_lookup.get_run(run_id)
                session_key = _optional_text(run.session_key) or session_key
            except OrchestrationRunNotFoundError:
                logger.debug(
                    "workbench relay could not look up run",
                    extra={"event_name": event.name, "run_id": run_id},
                )
        self._publish_workbench_updates(
            event,
            run_id=run_id,
            session_key=session_key,
            target="run",
            refresh=("home", "run", "steps"),
        )

    def observe_session_item_event(self, event: Event) -> None:
        session_key = _optional_text(event.payload.get("session_key"))
        if session_key is None:
            logger.debug(
                "skipping workbench relay session item observation without session_key",
                extra={"event_name": event.name, "payload": event.payload},
            )
            return
        self._publish_workbench_updates(
            event,
            run_id=_optional_text(event.payload.get("run_id")),
            session_key=session_key,
            target="session",
            refresh=("home",),
        )

    def observe_tool_event(self, event: Event) -> None:
        if self.tool_execution_port is None:
            return
        tool_run_id = _optional_text(event.payload.get("run_id"))
        if tool_run_id is None:
            return
        try:
            tool_run = self.tool_execution_port.get_tool_run(tool_run_id)
        except ToolRunNotFoundError:
            return

        invocation_context = tool_run.invocation_context
        run_id = (
            invocation_context.get_str("run_id")
            if invocation_context is not None
            else None
        )
        session_key = (
            invocation_context.get_str("session_key")
            if invocation_context is not None
            else None
        )
        if run_id is None:
            return
        if self.run_lookup is not None:
            try:
                run = self.run_lookup.get_run(run_id)
                session_key = _optional_text(run.session_key) or session_key
            except OrchestrationRunNotFoundError:
                pass
        self._publish_workbench_updates(
            event,
            run_id=run_id,
            session_key=session_key,
            target="steps",
            refresh=("home", "run", "steps"),
            metadata={"tool_run_id": tool_run.id, "tool_id": tool_run.tool_id},
        )

    def observe_live_llm_event(self, event: Event) -> None:
        run_id = _optional_text(event.payload.get("run_id"))
        session_key = _optional_text(event.payload.get("session_key"))
        if run_id is None or session_key is None:
            return
        self._publish_workbench_updates(
            event,
            run_id=run_id,
            session_key=session_key,
            target="llm_delta",
            refresh=("run", "steps"),
            delta={
                "kind": ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT,
                "text_delta": event.payload.get("text_delta"),
                "text": event.payload.get("text"),
                "text_length": event.payload.get("text_length"),
            },
        )

    def _publish_workbench_updates(
        self,
        source_event: Event,
        *,
        run_id: str | None,
        session_key: str | None,
        target: str,
        refresh: tuple[str, ...],
        delta: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        source_event_name = source_event.event_name or source_event.name or ""
        update = WorkbenchRelayUpdate(
            target=target,
            refresh=refresh,
            reason=source_event_name,
            run_id=run_id,
            session_key=session_key,
            source_event_id=source_event.id,
            source_event_name=source_event_name,
            delta=delta,
            metadata=metadata or {},
        )
        topics: list[str] = [workbench_home_topic()]
        if session_key:
            topics.append(workbench_session_topic(session_key))
        if run_id:
            topics.append(workbench_run_topic(run_id))
            if "steps" in refresh:
                topics.append(workbench_steps_topic(run_id))

        events = tuple(
            Event(
                name=EVENT_RELAY_WORKBENCH_UPDATED_EVENT,
                topic=topic,
                kind="broadcast",
                ordering_key=run_id or session_key or "workbench",
                dedupe_key=f"{source_event.id}:{topic}",
                payload=update.to_payload(),
                trace=dict(source_event.trace),
            )
            for topic in dict.fromkeys(topics)
        )
        self.events_service.publish_many(events)


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
