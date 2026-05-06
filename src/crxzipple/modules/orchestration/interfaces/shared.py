from __future__ import annotations

import json
from collections.abc import Callable

from crxzipple.modules.orchestration.application.turn_submission import (
    build_accept_run_input,
    build_inbound_instruction,
    build_reply_target,
    build_session_route_context,
    build_submit_turn_input,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationQueuePolicy,
    OrchestrationRunStage,
    OrchestrationRunStatus,
)
from crxzipple.modules.session.domain import (
    DirectSessionScope,
    SessionResetPolicy,
)


OrchestrationInterfaceErrorFactory = Callable[[str], Exception]


def parse_json_object(
    raw: str | None,
    *,
    option_name: str,
    error_factory: OrchestrationInterfaceErrorFactory,
) -> dict[str, object]:
    if raw is None or not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise error_factory(f"{option_name} must be valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise error_factory(f"{option_name} must decode to a JSON object.")
    return dict(payload)


def parse_direct_scope(
    raw: str,
    *,
    option_name: str,
    error_factory: OrchestrationInterfaceErrorFactory,
) -> DirectSessionScope:
    try:
        return DirectSessionScope(raw)
    except ValueError as exc:
        values = ", ".join(scope.value for scope in DirectSessionScope)
        raise error_factory(f"{option_name} must be one of: {values}") from exc


def parse_run_status(
    raw: str | None,
    *,
    option_name: str,
    error_factory: OrchestrationInterfaceErrorFactory,
) -> OrchestrationRunStatus | None:
    if raw is None:
        return None
    try:
        return OrchestrationRunStatus(raw)
    except ValueError as exc:
        values = ", ".join(item.value for item in OrchestrationRunStatus)
        raise error_factory(f"{option_name} must be one of: {values}") from exc


def parse_queue_policy(
    raw: str | None,
    *,
    option_name: str,
    error_factory: OrchestrationInterfaceErrorFactory,
) -> OrchestrationQueuePolicy | None:
    if raw is None:
        return None
    try:
        return OrchestrationQueuePolicy(raw)
    except ValueError as exc:
        values = ", ".join(item.value for item in OrchestrationQueuePolicy)
        raise error_factory(f"{option_name} must be one of: {values}") from exc


def parse_run_stage(
    raw: str,
    *,
    option_name: str,
    error_factory: OrchestrationInterfaceErrorFactory,
) -> OrchestrationRunStage:
    try:
        return OrchestrationRunStage(raw)
    except ValueError as exc:
        values = ", ".join(
            stage.value
            for stage in (
                OrchestrationRunStage.RUNNING,
                OrchestrationRunStage.LLM,
                OrchestrationRunStage.TOOL,
                OrchestrationRunStage.FINALIZING,
            )
        )
        raise error_factory(f"{option_name} must be one of: {values}") from exc


def build_reset_policy(
    *,
    idle_minutes: int | None,
    daily_reset_hour_utc: int | None,
) -> SessionResetPolicy | None:
    if idle_minutes is None and daily_reset_hour_utc is None:
        return None
    return SessionResetPolicy(
        idle_minutes=idle_minutes,
        daily_reset_hour_utc=daily_reset_hour_utc,
    )
