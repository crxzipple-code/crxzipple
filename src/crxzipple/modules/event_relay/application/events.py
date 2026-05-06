from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


EVENT_RELAY_WORKBENCH_UPDATED_EVENT = "event_relay.workbench.updated"


def workbench_home_topic() -> str:
    return "event_relay.workbench.home"


def workbench_session_topic(session_key: str) -> str:
    normalized = session_key.strip()
    if not normalized:
        raise ValueError("session_key is required to build a workbench relay topic.")
    return f"event_relay.workbench.session.{normalized}"


def workbench_run_topic(run_id: str) -> str:
    normalized = run_id.strip()
    if not normalized:
        raise ValueError("run_id is required to build a workbench relay topic.")
    return f"event_relay.workbench.run.{normalized}"


def workbench_steps_topic(run_id: str) -> str:
    normalized = run_id.strip()
    if not normalized:
        raise ValueError("run_id is required to build a workbench steps relay topic.")
    return f"event_relay.workbench.run.{normalized}.steps"


@dataclass(frozen=True, slots=True)
class WorkbenchRelayUpdate:
    target: str
    refresh: tuple[str, ...]
    reason: str
    run_id: str | None = None
    session_key: str | None = None
    source_event_id: str | None = None
    source_event_name: str | None = None
    delta: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "surface": "workbench",
            "target": self.target,
            "refresh": list(self.refresh),
            "reason": self.reason,
            "run_id": self.run_id,
            "session_key": self.session_key,
            "source_event_id": self.source_event_id,
            "source_event_name": self.source_event_name,
        }
        if self.delta is not None:
            payload["delta"] = dict(self.delta)
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload
