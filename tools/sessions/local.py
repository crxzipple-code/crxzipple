from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from crxzipple.modules.session.application import (
    AppendSessionItemInput,
    ListSessionInstancesInput,
    ListSessionItemsInput,
    SessionRuntimeControlPort,
    SessionRuntimeRunRecord,
    SubmitSessionBoundTurnInput,
    SubmitSessionSpawnTurnInput,
)
from crxzipple.modules.session.domain import (
    SessionItemKind,
    SessionItemVisibility,
    SessionNotFoundError,
)
from crxzipple.modules.session.interfaces.dto import (
    SessionDTO,
    SessionItemDTO,
    SessionInstanceDTO,
)
from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult
from crxzipple.shared.content_blocks import describe_content_for_text_fallback

if TYPE_CHECKING:
    from crxzipple.modules.session.application import SessionApplicationService


SESSION_STATUS_TOOL_ID = "session_status"
SESSIONS_LIST_TOOL_ID = "sessions_list"
SESSIONS_HISTORY_TOOL_ID = "sessions_history"
SESSIONS_SEND_TOOL_ID = "sessions_send"
SESSIONS_SPAWN_TOOL_ID = "sessions_spawn"
SUBAGENTS_TOOL_ID = "subagents"
SESSIONS_STOP_TOOL_ID = "sessions_stop"
SESSIONS_YIELD_TOOL_ID = "sessions_yield"
DEFAULT_SESSIONS_LIST_LIMIT = 12
DEFAULT_SUBAGENTS_LIMIT = 12
DEFAULT_SESSIONS_HISTORY_LIMIT = 20
MAX_SESSIONS_LIST_LIMIT = 50
MAX_SUBAGENTS_LIMIT = 50
MAX_SESSIONS_HISTORY_LIMIT = 50
MAX_RENDERED_HISTORY_CHARS = 4_000
MAX_RENDERED_MESSAGE_CHARS = 280
_SESSION_KEY_ATTR = "session_key"
_AGENT_ID_ATTR = "agent_id"
_RUN_ID_ATTR = "run_id"


@dataclass(frozen=True, slots=True)
class SessionsToolDeps:
    session_service: SessionApplicationService
    session_runtime_control: SessionRuntimeControlPort


def _coerce_sessions_deps(value: SessionsToolDeps | Any) -> SessionsToolDeps | None:
    if isinstance(value, SessionsToolDeps):
        return value
    session_service = getattr(value, "session_service", None)
    session_runtime_control = getattr(
        value,
        "session_runtime_control",
        None,
    )
    if session_service is None or session_runtime_control is None:
        return None
    return SessionsToolDeps(
        session_service=session_service,
        session_runtime_control=session_runtime_control,
    )


def session_status(deps: SessionsToolDeps | Any):
    resolved = _coerce_sessions_deps(deps)
    if resolved is None:
        return None
    session_service = resolved.session_service
    session_runtime_control = resolved.session_runtime_control

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        session_key = _resolve_session_key(arguments, execution_context, required=True)
        try:
            session = session_service.get_session(session_key)
            instances = session_service.list_instances(
                ListSessionInstancesInput(session_key=session_key),
            )
            all_items = session_service.list_items(
                ListSessionItemsInput(
                    session_key=session_key,
                ),
            )
        except SessionNotFoundError as exc:
            raise ValueError(str(exc)) from exc

        visible_items = _filter_items(
            all_items,
            include_archived=False,
            include_internal=False,
        )
        active_visible_items = [
            item
            for item in visible_items
            if item.session_id == session.active_session_id
        ]
        session_dto = SessionDTO.from_entity(session)
        instance_dtos = [SessionInstanceDTO.from_entity(item) for item in instances]
        active_instance = next(
            (item for item in instance_dtos if item.id == session.active_session_id),
            None,
        )
        requester_tree = None
        requester_agent_id = session_dto.runtime_binding.agent_id
        if requester_agent_id is not None:
            requester_tree = _build_requester_tree_status(
                requester_session_key=session.id,
                requester_agent_id=requester_agent_id,
                session_runtime_control=session_runtime_control,
                sessions=session_service.list_sessions(agent_id=requester_agent_id),
            )
        details = {
            "tool": SESSION_STATUS_TOOL_ID,
            "session": _serialize_session(session_dto),
            "active_instance": (
                _serialize_instance(active_instance)
                if active_instance is not None
                else None
            ),
            "instances": [_serialize_instance(item) for item in instance_dtos],
            "counts": {
                "instance_count": len(instance_dtos),
                "active_visible_item_count": len(active_visible_items),
                "visible_item_count": len(visible_items),
                "total_item_count": len(all_items),
            },
            "compaction": _extract_compaction_metadata(session_dto.metadata),
            "requester_tree": requester_tree,
        }
        return ToolRunResult.text(
            _render_session_status(
                session=session_dto,
                active_instance=active_instance,
                instance_count=len(instance_dtos),
                active_visible_item_count=len(active_visible_items),
                visible_item_count=len(visible_items),
                total_item_count=len(all_items),
                requester_tree=requester_tree,
            ),
            details=details,
            metadata=details,
        )

    return handler


def sessions_list(deps: SessionsToolDeps | Any):
    resolved = _coerce_sessions_deps(deps)
    if resolved is None:
        return None
    session_service = resolved.session_service

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        agent_id = _resolve_agent_id(arguments, execution_context)
        limit = _coerce_positive_int(
            arguments,
            key="limit",
            default=DEFAULT_SESSIONS_LIST_LIMIT,
            maximum=MAX_SESSIONS_LIST_LIMIT,
            label="sessions_list limit",
        )
        status_filter = _coerce_optional_text(arguments.get("status"))
        sessions = session_service.list_sessions(agent_id=agent_id)
        if status_filter is not None:
            sessions = [
                item for item in sessions if item.status.strip().lower() == status_filter
            ]
        selected = sessions[:limit]
        session_dtos = [SessionDTO.from_entity(item) for item in selected]
        details = {
            "tool": SESSIONS_LIST_TOOL_ID,
            "agent_id": agent_id,
            "status": status_filter,
            "returned_count": len(session_dtos),
            "available_count": len(sessions),
            "sessions": [_serialize_session(item) for item in session_dtos],
        }
        return ToolRunResult.text(
            _render_sessions_list(
                sessions=session_dtos,
                agent_id=agent_id,
                status_filter=status_filter,
                available_count=len(sessions),
            ),
            details=details,
            metadata=details,
        )

    return handler


def sessions_history(deps: SessionsToolDeps | Any):
    resolved = _coerce_sessions_deps(deps)
    if resolved is None:
        return None
    session_service = resolved.session_service

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        session_key = _resolve_session_key(arguments, execution_context, required=True)
        requested_session_id = _coerce_optional_text(arguments.get("session_id"))
        limit = _coerce_positive_int(
            arguments,
            key="limit",
            default=DEFAULT_SESSIONS_HISTORY_LIMIT,
            maximum=MAX_SESSIONS_HISTORY_LIMIT,
            label="sessions_history limit",
        )
        include_archived = _coerce_bool(arguments.get("include_archived"), default=False)
        include_internal = _coerce_bool(arguments.get("include_internal"), default=False)
        active_session_only = _coerce_bool(
            arguments.get("active_session_only"),
            default=True,
        )
        try:
            session = session_service.get_session(session_key)
            instances = session_service.list_instances(
                ListSessionInstancesInput(session_key=session_key),
            )
            items = session_service.list_items(
                ListSessionItemsInput(
                    session_key=session_key,
                ),
            )
        except SessionNotFoundError as exc:
            raise ValueError(str(exc)) from exc

        instance_ids = {item.id for item in instances}
        if requested_session_id is not None and requested_session_id not in instance_ids:
            raise ValueError(
                f"Session instance '{requested_session_id}' was not found in session '{session_key}'.",
            )

        if requested_session_id is not None:
            items = [
                item for item in items if item.session_id == requested_session_id
            ]
        elif active_session_only:
            items = [
                item for item in items if item.session_id == session.active_session_id
            ]

        filtered_items = _filter_items(
            items,
            include_archived=include_archived,
            include_internal=include_internal,
        )
        available_count = len(filtered_items)
        selected_items = filtered_items[-limit:]
        item_dtos = [SessionItemDTO.from_entity(item) for item in selected_items]
        rendered_history, text_truncated = _render_sessions_history(
            session=SessionDTO.from_entity(session),
            items=item_dtos,
            available_count=available_count,
            active_session_only=(
                requested_session_id is None and active_session_only
            ),
            session_id=requested_session_id,
        )
        details = {
            "tool": SESSIONS_HISTORY_TOOL_ID,
            "session_key": session_key,
            "session_id": requested_session_id,
            "active_session_id": session.active_session_id,
            "active_session_only": requested_session_id is None and active_session_only,
            "include_archived": include_archived,
            "include_internal": include_internal,
            "returned_count": len(item_dtos),
            "available_count": available_count,
            "truncated": text_truncated or available_count > len(item_dtos),
            "items": [_serialize_item(item) for item in item_dtos],
        }
        return ToolRunResult.text(
            rendered_history,
            details=details,
            metadata=details,
        )

    return handler


def sessions_send(deps: SessionsToolDeps | Any):
    resolved = _coerce_sessions_deps(deps)
    if resolved is None:
        return None
    session_service = resolved.session_service
    session_runtime_control = resolved.session_runtime_control

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        session_key = _resolve_session_key(arguments, execution_context, required=True)
        text = _require_text(arguments, key="text", label="sessions_send text")
        enqueue = _coerce_bool(arguments.get("enqueue"), default=True)
        sender_session_key = (
            execution_context.get_str(_SESSION_KEY_ATTR)
            if execution_context is not None
            else None
        )
        sender_run_id = (
            execution_context.get_str(_RUN_ID_ATTR)
            if execution_context is not None
            else None
        )
        current_agent_id = _resolve_agent_id({}, execution_context)

        try:
            session = session_service.get_session(session_key)
        except SessionNotFoundError as exc:
            raise ValueError(str(exc)) from exc

        target_binding = session.runtime_binding()
        target_agent_id = target_binding.agent_id or session.agent_id
        if target_agent_id is None:
            raise ValueError(
                f"Session '{session.id}' is missing a runtime agent binding.",
            )
        if current_agent_id is not None and target_agent_id != current_agent_id:
            raise ValueError(
                "sessions_send only supports target sessions owned by the current agent.",
            )

        item = session_service.append_item(
            AppendSessionItemInput(
                session_key=session.id,
                session_id=session.active_session_id,
                kind=SessionItemKind.USER_MESSAGE,
                role="user",
                content_payload={
                    "blocks": [
                        {
                            "type": "text",
                            "text": text,
                        }
                    ]
                },
                visibility=SessionItemVisibility(
                    model_visible=True,
                    user_visible=True,
                    chat_visible=True,
                    trace_visible=True,
                ),
                source_module="session",
                source_kind="sessions_send",
                source_id=f"sessions_send:{uuid4().hex}",
                metadata={
                    key: value
                    for key, value in {
                        "sender_session_key": sender_session_key,
                        "sender_run_id": sender_run_id,
                        "sender_agent_id": current_agent_id,
                    }.items()
                    if value is not None
                },
            ),
        )

        queued_run = None
        if enqueue:
            queued_run = session_runtime_control.submit_bound_turn(
                SubmitSessionBoundTurnInput(
                    agent_id=target_agent_id,
                    session_key=session.id,
                    active_session_id=session.active_session_id,
                    source=SESSIONS_SEND_TOOL_ID,
                    metadata={
                        "sessions_send": {
                            "session_item_id": item.id,
                            "sender_session_key": sender_session_key,
                            "sender_run_id": sender_run_id,
                        },
                    },
                    inbound_metadata={
                        "session_item_id": item.id,
                        "sender_session_key": sender_session_key,
                        "sender_run_id": sender_run_id,
                        "sender_agent_id": current_agent_id,
                        "target_session_key": session.id,
                        "target_active_session_id": session.active_session_id,
                    },
                ),
                inline_worker_id=f"{SESSIONS_SEND_TOOL_ID}:{uuid4().hex}",
            )

        details = {
            "tool": SESSIONS_SEND_TOOL_ID,
            "session_key": session.id,
            "target_active_session_id": session.active_session_id,
            "agent_id": target_agent_id,
            "item": _serialize_item(SessionItemDTO.from_entity(item)),
            "enqueued": enqueue,
            "run_id": queued_run.id if queued_run is not None else None,
            "run_status": queued_run.status if queued_run is not None else None,
            "sender_session_key": sender_session_key,
            "sender_run_id": sender_run_id,
        }
        return ToolRunResult.text(
            _render_sessions_send(
                session_key=session.id,
                active_session_id=session.active_session_id,
                item_id=item.id,
                run_id=queued_run.id if queued_run is not None else None,
                enqueue=enqueue,
            ),
            details=details,
            metadata=details,
        )

    return handler


def sessions_spawn(deps: SessionsToolDeps | Any):
    resolved = _coerce_sessions_deps(deps)
    if resolved is None:
        return None
    session_service = resolved.session_service
    session_runtime_control = resolved.session_runtime_control

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        requester_session_key = _resolve_session_key(
            {},
            execution_context,
            required=True,
        )
        requester_run_id = (
            execution_context.get_str(_RUN_ID_ATTR)
            if execution_context is not None
            else None
        )
        current_agent_id = _resolve_agent_id({}, execution_context)
        if current_agent_id is None:
            raise ValueError("sessions_spawn requires current agent context.")
        text = _require_text(arguments, key="text", label="sessions_spawn text")

        try:
            requester_session = session_service.get_session(requester_session_key)
        except SessionNotFoundError as exc:
            raise ValueError(str(exc)) from exc

        requester_binding = requester_session.runtime_binding()
        requester_agent_id = requester_binding.agent_id or requester_session.agent_id
        if requester_agent_id is None:
            raise ValueError(
                f"Session '{requester_session.id}' is missing a runtime agent binding.",
            )
        if requester_agent_id != current_agent_id:
            raise ValueError(
                "sessions_spawn only supports requester sessions owned by the current agent.",
            )

        child_suffix = uuid4().hex
        child_main_key = f"subagent:{child_suffix}"
        spawn_metadata = {
            "requester_session_key": requester_session.id,
            "requester_active_session_id": requester_session.active_session_id,
            "requester_run_id": requester_run_id,
            "requester_agent_id": current_agent_id,
            "spawned_by_tool": SESSIONS_SPAWN_TOOL_ID,
            "child_main_key": child_main_key,
        }
        queued_run = session_runtime_control.submit_spawn_turn(
            SubmitSessionSpawnTurnInput(
                agent_id=current_agent_id,
                child_main_key=child_main_key,
                text=text,
                source=SESSIONS_SPAWN_TOOL_ID,
                spawn_metadata=spawn_metadata,
            ),
            inline_worker_id=f"{SESSIONS_SPAWN_TOOL_ID}:{uuid4().hex}",
        )
        child_session_key = str(queued_run.metadata.get("session_key", "")).strip()
        if not child_session_key:
            raise RuntimeError("sessions_spawn did not resolve a child session key.")
        child_session = session_service.get_session(child_session_key)

        details = {
            "tool": SESSIONS_SPAWN_TOOL_ID,
            "requester_session_key": requester_session.id,
            "requester_run_id": requester_run_id,
            "agent_id": current_agent_id,
            "child_session_key": child_session.id,
            "child_active_session_id": child_session.active_session_id,
            "child_main_key": child_main_key,
            "run_id": queued_run.id,
            "run_status": queued_run.status,
        }
        return ToolRunResult.text(
            _render_sessions_spawn(
                requester_session_key=requester_session.id,
                child_session_key=child_session.id,
                child_active_session_id=child_session.active_session_id,
                child_main_key=child_main_key,
                run_id=queued_run.id,
            ),
            details=details,
            metadata=details,
        )

    return handler


def subagents(deps: SessionsToolDeps | Any):
    resolved = _coerce_sessions_deps(deps)
    if resolved is None:
        return None
    session_service = resolved.session_service
    session_runtime_control = resolved.session_runtime_control

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        requester_session_key = _resolve_session_key(
            arguments,
            execution_context,
            required=True,
        )
        current_agent_id = _resolve_agent_id(arguments, execution_context)
        limit = _coerce_positive_int(
            arguments,
            key="limit",
            default=DEFAULT_SUBAGENTS_LIMIT,
            maximum=MAX_SUBAGENTS_LIMIT,
            label="subagents limit",
        )
        status_filter = _coerce_optional_text(arguments.get("status"))

        try:
            requester_session = session_service.get_session(requester_session_key)
        except SessionNotFoundError as exc:
            raise ValueError(str(exc)) from exc

        requester_binding = requester_session.runtime_binding()
        requester_agent_id = requester_binding.agent_id or requester_session.agent_id
        if requester_agent_id is None:
            raise ValueError(
                f"Session '{requester_session.id}' is missing a runtime agent binding.",
            )
        if current_agent_id is not None and requester_agent_id != current_agent_id:
            raise ValueError(
                "subagents only supports requester sessions owned by the current agent.",
            )

        sessions = session_service.list_sessions(agent_id=requester_agent_id)
        tree_entries = _collect_subagent_tree_entries(
            requester_session_key=requester_session.id,
            sessions=sessions,
        )
        if status_filter is not None:
            tree_entries = [
                item
                for item in tree_entries
                if item["session"].status.strip().lower() == status_filter
            ]
        selected_entries = tree_entries[:limit]
        selected_sessions = [item["session"] for item in selected_entries]
        run_summaries_by_session_key = _collect_subagent_run_summaries(
            session_runtime_control=session_runtime_control,
            session_keys={item.id for item in selected_sessions},
        )
        details = {
            "tool": SUBAGENTS_TOOL_ID,
            "requester_session_key": requester_session.id,
            "agent_id": requester_agent_id,
            "status": status_filter,
            "returned_count": len(selected_entries),
            "available_count": len(tree_entries),
            "subagents": [
                _serialize_subagent(
                    session=SessionDTO.from_entity(item["session"]),
                    depth=int(item["depth"]),
                    parent_session_key=str(item["parent_session_key"]),
                    run_summary=run_summaries_by_session_key.get(item["session"].id),
                )
                for item in selected_entries
            ],
        }
        return ToolRunResult.text(
            _render_subagents(
                requester_session_key=requester_session.id,
                subagents=details["subagents"],
                status_filter=status_filter,
                available_count=len(tree_entries),
            ),
            details=details,
            metadata=details,
        )

    return handler


def sessions_stop(deps: SessionsToolDeps | Any):
    resolved = _coerce_sessions_deps(deps)
    if resolved is None:
        return None
    session_service = resolved.session_service
    session_runtime_control = resolved.session_runtime_control

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        session_key = _resolve_session_key(arguments, execution_context, required=True)
        current_agent_id = _resolve_agent_id(arguments, execution_context)
        reason = _coerce_optional_text(arguments.get("reason"))

        try:
            requester_session = session_service.get_session(session_key)
        except SessionNotFoundError as exc:
            raise ValueError(str(exc)) from exc

        requester_binding = requester_session.runtime_binding()
        requester_agent_id = requester_binding.agent_id or requester_session.agent_id
        if requester_agent_id is None:
            raise ValueError(
                f"Session '{requester_session.id}' is missing a runtime agent binding.",
            )
        if current_agent_id is not None and requester_agent_id != current_agent_id:
            raise ValueError(
                "sessions_stop only supports requester sessions owned by the current agent.",
            )

        summary = session_runtime_control.cancel_session_tree(
            requester_session.id,
            reason=reason,
        )
        details = {
            "tool": SESSIONS_STOP_TOOL_ID,
            "requester_session_key": requester_session.id,
            "agent_id": requester_agent_id,
            **summary,
        }
        return ToolRunResult.text(
            _render_sessions_stop(
                requester_session_key=requester_session.id,
                cancelled_run_count=int(summary["cancelled_run_count"]),
                cancelled_tool_run_count=int(summary["cancelled_tool_run_count"]),
                terminal_run_count=int(summary["terminal_run_count"]),
                reason=reason,
            ),
            details=details,
            metadata=details,
        )

    return handler


def sessions_yield(deps: SessionsToolDeps | Any):
    resolved = _coerce_sessions_deps(deps)
    if resolved is None:
        return None

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        run_id = (
            execution_context.get_str(_RUN_ID_ATTR)
            if execution_context is not None
            else None
        )
        session_key = (
            execution_context.get_str(_SESSION_KEY_ATTR)
            if execution_context is not None
            else None
        )
        if run_id is None:
            raise ValueError("sessions_yield requires orchestration run context.")
        reason = _coerce_optional_text(arguments.get("reason"))
        details = {
            "tool": SESSIONS_YIELD_TOOL_ID,
            "run_id": run_id,
            "session_key": session_key,
            "yield_requested": True,
            "yield_reason": reason,
        }
        return ToolRunResult.text(
            _render_sessions_yield(reason=reason),
            details=details,
            metadata={
                **details,
                "session_control": {
                    "yield": True,
                    "reason": reason,
                },
            },
        )

    return handler


def _resolve_session_key(
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
    *,
    required: bool,
) -> str | None:
    explicit = _coerce_optional_text(arguments.get("session_key"))
    if explicit is not None:
        return explicit
    if execution_context is not None:
        implicit = execution_context.get_str(_SESSION_KEY_ATTR)
        if implicit is not None:
            return implicit
    if required:
        raise ValueError("A session_key is required for this tool.")
    return None


def _resolve_agent_id(
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> str | None:
    explicit = _coerce_optional_text(arguments.get("agent_id"))
    if explicit is not None:
        return explicit
    if execution_context is not None:
        return execution_context.get_str(_AGENT_ID_ATTR)
    return None


def _coerce_optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _coerce_positive_int(
    arguments: dict[str, Any],
    *,
    key: str,
    default: int,
    maximum: int,
    label: str,
) -> int:
    raw = arguments.get(key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer.") from exc
    if value <= 0:
        raise ValueError(f"{label} must be greater than zero.")
    return min(value, maximum)


def _coerce_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("Boolean parameters must be true/false.")


def _require_text(arguments: dict[str, Any], *, key: str, label: str) -> str:
    value = _coerce_optional_text(arguments.get(key))
    if value is None:
        raise ValueError(f"{label} is required.")
    return value


def _filter_items(
    items: list[Any],
    *,
    include_archived: bool,
    include_internal: bool,
) -> list[Any]:
    filtered: list[Any] = []
    for item in items:
        metadata = dict(getattr(item, "metadata", {}) or {})
        visibility = getattr(item, "visibility", SessionItemVisibility())
        if not include_archived and (
            metadata.get("archived_reason") is not None
            or metadata.get("compacted_segment_id") is not None
        ):
            continue
        if not include_internal and not visibility.model_visible:
            continue
        filtered.append(item)
    return filtered


def _serialize_session(session: SessionDTO) -> dict[str, Any]:
    return {
        "key": session.key,
        "runtime_binding": {
            "agent_id": session.runtime_binding.agent_id,
            "workspace": session.runtime_binding.workspace,
        },
        "active_session_id": session.active_session_id,
        "status": session.status,
        "channel": session.channel,
        "chat_type": session.chat_type,
        "created_at": _isoformat(session.created_at),
        "updated_at": _isoformat(session.updated_at),
        "last_reset_at": _isoformat(session.last_reset_at),
        "metadata": dict(session.metadata),
    }


def _serialize_instance(instance: SessionInstanceDTO) -> dict[str, Any]:
    return {
        "id": instance.id,
        "session_key": instance.session_key,
        "runtime_binding": {
            "agent_id": instance.runtime_binding.agent_id,
            "workspace": instance.runtime_binding.workspace,
        },
        "sequence_no": instance.sequence_no,
        "kind": instance.kind,
        "status": instance.status,
        "opened_at": _isoformat(instance.opened_at),
        "closed_at": _isoformat(instance.closed_at),
        "reset_reason": instance.reset_reason,
    }


def _serialize_item(item: SessionItemDTO) -> dict[str, Any]:
    return {
        "id": item.id,
        "session_key": item.session_key,
        "session_id": item.session_id,
        "sequence_no": item.sequence_no,
        "role": item.role,
        "kind": item.kind,
        "phase": item.phase,
        "visibility": dict(item.visibility),
        "content": _truncate_text(
            describe_content_for_text_fallback(item.content_payload),
            limit=MAX_RENDERED_MESSAGE_CHARS,
        ),
        "created_at": _isoformat(item.created_at),
        "source_module": item.source_module,
        "source_kind": item.source_kind,
        "source_id": item.source_id,
        "provider_item_type": item.provider_item_type,
        "call_id": item.call_id,
        "tool_name": item.tool_name,
    }


def _serialize_subagent(
    *,
    session: SessionDTO,
    depth: int,
    parent_session_key: str,
    run_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    spawn_payload = (
        dict(session.metadata["spawn"])
        if isinstance(session.metadata.get("spawn"), dict)
        else {}
    )
    return {
        "key": session.key,
        "depth": depth,
        "parent_session_key": parent_session_key,
        "active_session_id": session.active_session_id,
        "status": session.status,
        "updated_at": _isoformat(session.updated_at),
        "requester_session_key": spawn_payload.get("requester_session_key"),
        "requester_run_id": spawn_payload.get("requester_run_id"),
        "spawned_by_tool": spawn_payload.get("spawned_by_tool"),
        "latest_run": (
            dict(run_summary["latest_run"])
            if isinstance(run_summary, dict)
            and isinstance(run_summary.get("latest_run"), dict)
            else None
        ),
        "inflight_run_count": (
            int(run_summary["inflight_run_count"])
            if isinstance(run_summary, dict)
            and isinstance(run_summary.get("inflight_run_count"), int)
            else 0
        ),
        "inflight_runs": (
            [dict(item) for item in run_summary.get("inflight_runs", ())]
            if isinstance(run_summary, dict)
            else []
        ),
    }


def _build_requester_tree_status(
    *,
    requester_session_key: str,
    requester_agent_id: str,
    session_runtime_control: SessionRuntimeControlPort,
    sessions: list[Any],
) -> dict[str, Any]:
    tree_entries = _collect_subagent_tree_entries(
        requester_session_key=requester_session_key,
        sessions=sessions,
    )
    session_keys = {item["session"].id for item in tree_entries}
    run_summaries_by_session_key = _collect_subagent_run_summaries(
        session_runtime_control=session_runtime_control,
        session_keys=session_keys,
    )
    inflight_child_session_count = 0
    inflight_child_run_count = 0
    deepest_depth = 0
    for item in tree_entries:
        deepest_depth = max(deepest_depth, int(item["depth"]))
        run_summary = run_summaries_by_session_key.get(item["session"].id)
        inflight_count = (
            int(run_summary["inflight_run_count"])
            if isinstance(run_summary, dict)
            and isinstance(run_summary.get("inflight_run_count"), int)
            else 0
        )
        if inflight_count > 0:
            inflight_child_session_count += 1
            inflight_child_run_count += inflight_count
    followup = _collect_requester_followup_status(
        requester_session_key=requester_session_key,
        session_runtime_control=session_runtime_control,
    )
    return {
        "requester_session_key": requester_session_key,
        "agent_id": requester_agent_id,
        "subagent_tree": {
            "child_session_count": len(tree_entries),
            "inflight_child_session_count": inflight_child_session_count,
            "inflight_child_run_count": inflight_child_run_count,
            "deepest_depth": deepest_depth,
        },
        "followup": followup,
    }


def _collect_subagent_tree_entries(
    *,
    requester_session_key: str,
    sessions: list[Any],
) -> list[dict[str, Any]]:
    children_by_requester: dict[str, list[Any]] = {}
    for session in sessions:
        spawn_payload = session.metadata.get("spawn")
        if not isinstance(spawn_payload, dict):
            continue
        parent_session_key = str(
            spawn_payload.get("requester_session_key", ""),
        ).strip()
        if not parent_session_key:
            continue
        children_by_requester.setdefault(parent_session_key, []).append(session)

    entries: list[dict[str, Any]] = []
    pending: list[tuple[str, int]] = [(requester_session_key, 0)]
    seen: set[str] = {requester_session_key}
    while pending:
        parent_session_key, parent_depth = pending.pop(0)
        for child in children_by_requester.get(parent_session_key, ()):
            if child.id in seen:
                continue
            seen.add(child.id)
            depth = parent_depth + 1
            entries.append(
                {
                    "session": child,
                    "depth": depth,
                    "parent_session_key": parent_session_key,
                },
            )
            pending.append((child.id, depth))
    return entries


def _collect_subagent_run_summaries(
    *,
    session_runtime_control: SessionRuntimeControlPort,
    session_keys: set[str],
) -> dict[str, dict[str, Any]]:
    if not session_keys:
        return {}
    summaries: dict[str, dict[str, Any]] = {}
    runs = session_runtime_control.list_runs()
    runs_by_session_key: dict[str, list[SessionRuntimeRunRecord]] = {}
    for run in runs:
        session_key = run.session_key
        if session_key is None or session_key not in session_keys:
            continue
        runs_by_session_key.setdefault(session_key, []).append(run)
    for session_key, session_runs in runs_by_session_key.items():
        ordered = sorted(
            session_runs,
            key=lambda item: (
                item.updated_at,
                item.created_at,
            ),
            reverse=True,
        )
        inflight = [
            item
            for item in ordered
            if not _is_terminal_run_status(item.status)
        ]
        summaries[session_key] = {
            "latest_run": _serialize_run_summary(ordered[0]) if ordered else None,
            "inflight_run_count": len(inflight),
            "inflight_runs": [_serialize_run_summary(item) for item in inflight],
        }
    return summaries


def _collect_requester_followup_status(
    *,
    requester_session_key: str,
    session_runtime_control: SessionRuntimeControlPort,
) -> dict[str, Any]:
    runs = []
    for run in session_runtime_control.list_runs():
        if run.session_key != requester_session_key:
            continue
        payload = run.metadata.get("sessions_spawn_followup")
        if not isinstance(payload, dict):
            continue
        runs.append(run)
    ordered = sorted(
        runs,
        key=lambda item: (
            item.updated_at,
            item.created_at,
        ),
        reverse=True,
    )
    inflight = [
        item
        for item in ordered
        if not _is_terminal_run_status(item.status)
    ]
    return {
        "run_count": len(ordered),
        "inflight_run_count": len(inflight),
        "latest_run": _serialize_followup_run_summary(ordered[0]) if ordered else None,
        "inflight_runs": [_serialize_followup_run_summary(item) for item in inflight],
    }


def _serialize_run_summary(run: SessionRuntimeRunRecord) -> dict[str, Any]:
    return {
        "id": run.id,
        "status": run.status,
        "stage": run.stage,
        "current_step": run.current_step,
        "max_steps": run.max_steps,
        "waiting_reason": run.waiting_reason,
        "prompt_mode": run.prompt_mode,
        "worker_id": run.worker_id,
        "updated_at": _isoformat(run.updated_at),
        "queued_at": _isoformat(run.queued_at),
        "started_at": _isoformat(run.started_at),
        "completed_at": _isoformat(run.completed_at),
    }


def _serialize_followup_run_summary(run: SessionRuntimeRunRecord) -> dict[str, Any]:
    summary = _serialize_run_summary(run)
    payload = (
        dict(run.metadata.get("sessions_spawn_followup", {}))
        if isinstance(run.metadata.get("sessions_spawn_followup"), dict)
        else {}
    )
    summary.update(
        {
            "child_run_id": payload.get("child_run_id"),
            "child_session_key": payload.get("child_session_key"),
            "requester_session_key": payload.get("requester_session_key"),
            "requester_run_id": payload.get("requester_run_id"),
        },
    )
    return summary


def _is_terminal_run_status(status: str) -> bool:
    return status in {"completed", "failed", "cancelled"}


def _extract_compaction_metadata(metadata: dict[str, object]) -> dict[str, Any] | None:
    payload = metadata.get("compaction")
    if not isinstance(payload, dict):
        return None
    return dict(payload)


def _render_session_status(
    *,
    session: SessionDTO,
    active_instance: SessionInstanceDTO | None,
    instance_count: int,
    active_visible_item_count: int,
    visible_item_count: int,
    total_item_count: int,
    requester_tree: dict[str, Any] | None,
) -> str:
    lines = [
        "# Session Status",
        "",
        f"- key: {session.key}",
        f"- agent: {session.runtime_binding.agent_id or 'unknown'}",
        f"- active_session_id: {session.active_session_id}",
        f"- status: {session.status}",
        f"- channel: {session.channel or 'n/a'}",
        f"- chat_type: {session.chat_type or 'n/a'}",
        f"- updated_at: {_isoformat(session.updated_at)}",
        f"- last_reset_at: {_isoformat(session.last_reset_at)}",
        f"- instance_count: {instance_count}",
        f"- active_visible_item_count: {active_visible_item_count}",
        f"- visible_item_count: {visible_item_count}",
        f"- total_item_count: {total_item_count}",
    ]
    compaction = _extract_compaction_metadata(session.metadata)
    if compaction is not None:
        lines.append(
            f"- compaction: present ({', '.join(sorted(compaction.keys()))})",
        )
    else:
        lines.append("- compaction: none")
    if active_instance is not None:
        lines.extend(
            [
                "",
                "## Active Instance",
                f"- id: {active_instance.id}",
                f"- sequence_no: {active_instance.sequence_no}",
                f"- kind: {active_instance.kind}",
                f"- status: {active_instance.status}",
                f"- opened_at: {_isoformat(active_instance.opened_at)}",
                f"- closed_at: {_isoformat(active_instance.closed_at) if active_instance.closed_at else 'n/a'}",
            ],
        )
    if isinstance(requester_tree, dict):
        subagent_tree = requester_tree.get("subagent_tree")
        followup = requester_tree.get("followup")
        if isinstance(subagent_tree, dict):
            lines.extend(
                [
                    "",
                    "## Requester Tree",
                    f"- child_session_count: {subagent_tree.get('child_session_count', 0)}",
                    f"- inflight_child_session_count: {subagent_tree.get('inflight_child_session_count', 0)}",
                    f"- inflight_child_run_count: {subagent_tree.get('inflight_child_run_count', 0)}",
                    f"- deepest_depth: {subagent_tree.get('deepest_depth', 0)}",
                ],
            )
        if isinstance(followup, dict):
            lines.extend(
                [
                    "",
                    "## Follow-up Scheduling",
                    f"- followup_run_count: {followup.get('run_count', 0)}",
                    f"- inflight_followup_run_count: {followup.get('inflight_run_count', 0)}",
                ],
            )
            latest_followup = followup.get("latest_run")
            if isinstance(latest_followup, dict):
                lines.extend(
                    [
                        f"- latest_followup_run_id: {latest_followup.get('id')}",
                        f"- latest_followup_status: {latest_followup.get('status')}",
                        f"- latest_followup_stage: {latest_followup.get('stage')}",
                        f"- latest_followup_child_session_key: {latest_followup.get('child_session_key') or 'n/a'}",
                        f"- latest_followup_updated_at: {latest_followup.get('updated_at')}",
                    ],
                )
    return "\n".join(lines).strip()


def _render_sessions_list(
    *,
    sessions: list[SessionDTO],
    agent_id: str | None,
    status_filter: str | None,
    available_count: int,
) -> str:
    lines = [
        "# Sessions",
        "",
        f"- scope_agent: {agent_id or 'all'}",
        f"- status_filter: {status_filter or 'none'}",
        f"- returned: {len(sessions)}",
        f"- available: {available_count}",
        "",
    ]
    if not sessions:
        lines.append("No sessions matched the current filter.")
        return "\n".join(lines).strip()
    for index, session in enumerate(sessions, start=1):
        lines.extend(
            [
                f"## Session {index}",
                f"- key: {session.key}",
                f"- agent: {session.runtime_binding.agent_id or 'unknown'}",
                f"- active_session_id: {session.active_session_id}",
                f"- status: {session.status}",
                f"- updated_at: {_isoformat(session.updated_at)}",
                f"- channel: {session.channel or 'n/a'}",
                f"- chat_type: {session.chat_type or 'n/a'}",
                "",
            ],
        )
    return "\n".join(lines).strip()


def _render_sessions_history(
    *,
    session: SessionDTO,
    items: list[SessionItemDTO],
    available_count: int,
    active_session_only: bool,
    session_id: str | None,
) -> tuple[str, bool]:
    lines = [
        "# Session History",
        "",
        f"- session_key: {session.key}",
        f"- requested_session_id: {session_id or 'active'}",
        f"- active_session_only: {'true' if active_session_only else 'false'}",
        f"- returned: {len(items)}",
        f"- available: {available_count}",
        "",
    ]
    if not items:
        lines.append("No transcript items matched the current filter.")
        return "\n".join(lines).strip(), False

    truncated = False
    rendered_chars = len("\n".join(lines))
    for item in items:
        content = _truncate_text(
            describe_content_for_text_fallback(item.content_payload),
            limit=MAX_RENDERED_MESSAGE_CHARS,
        )
        chunk = [
            f"## {item.role or item.kind} #{item.sequence_no}",
            f"- session_id: {item.session_id}",
            f"- kind: {item.kind}",
            f"- phase: {item.phase}",
            f"- visibility: {dict(item.visibility)}",
            f"- created_at: {_isoformat(item.created_at)}",
            f"- content: {content or '[no textual content]'}",
            "",
        ]
        candidate_rendered_chars = rendered_chars + len("\n".join(chunk))
        if rendered_chars > 0 and candidate_rendered_chars > MAX_RENDERED_HISTORY_CHARS:
            truncated = True
            break
        lines.extend(chunk)
        rendered_chars = candidate_rendered_chars

    if truncated:
        lines.append("History output truncated for prompt safety.")
    return "\n".join(lines).strip(), truncated


def _render_sessions_send(
    *,
    session_key: str,
    active_session_id: str,
    item_id: str,
    run_id: str | None,
    enqueue: bool,
) -> str:
    lines = [
        "# Session Send",
        "",
        f"- session_key: {session_key}",
        f"- active_session_id: {active_session_id}",
        f"- session_item_id: {item_id}",
        f"- enqueued: {'true' if enqueue else 'false'}",
    ]
    if run_id is not None:
        lines.append(f"- run_id: {run_id}")
    return "\n".join(lines).strip()


def _render_sessions_spawn(
    *,
    requester_session_key: str,
    child_session_key: str,
    child_active_session_id: str,
    child_main_key: str,
    run_id: str,
) -> str:
    lines = [
        "# Session Spawn",
        "",
        f"- requester_session_key: {requester_session_key}",
        f"- child_session_key: {child_session_key}",
        f"- child_active_session_id: {child_active_session_id}",
        f"- child_main_key: {child_main_key}",
        f"- run_id: {run_id}",
        "- status: accepted",
    ]
    return "\n".join(lines).strip()


def _render_subagents(
    *,
    requester_session_key: str,
    subagents: list[dict[str, Any]],
    status_filter: str | None,
    available_count: int,
) -> str:
    lines = [
        "# Subagents",
        "",
        f"- requester_session_key: {requester_session_key}",
        f"- status_filter: {status_filter or 'none'}",
        f"- returned: {len(subagents)}",
        f"- available: {available_count}",
        "",
    ]
    if not subagents:
        lines.append("No child session buckets matched the current filter.")
        return "\n".join(lines).strip()
    for index, subagent in enumerate(subagents, start=1):
        latest_run = subagent.get("latest_run")
        lines.extend(
            [
                f"## Subagent {index}",
                f"- key: {subagent['key']}",
                f"- depth: {subagent['depth']}",
                f"- parent_session_key: {subagent['parent_session_key']}",
                f"- active_session_id: {subagent['active_session_id']}",
                f"- status: {subagent['status']}",
                f"- updated_at: {subagent['updated_at']}",
                f"- requester_run_id: {subagent.get('requester_run_id') or 'n/a'}",
                f"- inflight_run_count: {subagent.get('inflight_run_count', 0)}",
                "",
            ],
        )
        if isinstance(latest_run, dict):
            lines.extend(
                [
                    "### Latest Run",
                    f"- id: {latest_run['id']}",
                    f"- status: {latest_run['status']}",
                    f"- stage: {latest_run['stage']}",
                    f"- current_step: {latest_run['current_step']}/{latest_run['max_steps']}",
                    f"- waiting_reason: {latest_run.get('waiting_reason') or 'none'}",
                    f"- prompt_mode: {latest_run.get('prompt_mode') or 'n/a'}",
                    f"- updated_at: {latest_run.get('updated_at')}",
                    "",
                ],
            )
    return "\n".join(lines).strip()


def _render_sessions_stop(
    *,
    requester_session_key: str,
    cancelled_run_count: int,
    cancelled_tool_run_count: int,
    terminal_run_count: int,
    reason: str | None,
) -> str:
    lines = [
        "# Session Stop",
        "",
        f"- requester_session_key: {requester_session_key}",
        f"- cancelled_run_count: {cancelled_run_count}",
        f"- cancelled_tool_run_count: {cancelled_tool_run_count}",
        f"- terminal_run_count: {terminal_run_count}",
        f"- reason: {reason or 'none'}",
    ]
    return "\n".join(lines).strip()


def _render_sessions_yield(*, reason: str | None) -> str:
    lines = [
        "# Session Yield",
        "",
        "- yield_requested: true",
        f"- reason: {reason or 'none'}",
    ]
    return "\n".join(lines).strip()


def _truncate_text(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(limit - 1, 0)].rstrip() + "…"


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
