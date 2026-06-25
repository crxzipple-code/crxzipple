"""Session context tree adapter.

This module lives in app integration because it maps Session-owned application
facts into Context Workspace node handles without making either module import
the other module's internals.
"""

from __future__ import annotations

from typing import Any, Protocol

from crxzipple.modules.context_workspace.application import (
    ContextChildrenRequest,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextNodeSeed,
    ContextNodeState,
)
from crxzipple.modules.session.application import (
    ListSessionInstancesInput,
    ListSessionItemsInput,
)
from crxzipple.modules.session.domain import (
    Session,
    SessionInstance,
    SessionItem,
    SessionNotFoundError,
)
from crxzipple.app.integration.context_workspace_session_content import (
    items_estimate as _items_estimate,
)
from crxzipple.app.integration.context_workspace_session_content_values import (
    optional_int as _optional_int,
    optional_text as _optional_text,
    text_estimate as _text_estimate,
    truncate as _truncate,
)
from crxzipple.app.integration.context_workspace_session_execution import (
    execution_step_item_node_seeds as _execution_step_item_node_seeds,
    execution_step_item_summaries as _execution_step_item_summaries,
    execution_step_node_seeds as _execution_step_node_seeds,
)
from crxzipple.app.integration.context_workspace_session_item_nodes import (
    current_items_range_prompt_content as _current_items_range_prompt_content,
    message_node_seeds as _message_node_seeds,
)
from crxzipple.app.integration.context_workspace_session_segment_ranges import (
    range_notice_seed as _range_notice_seed,
    segment_message_range_seed as _segment_message_range_seed,
    split_segment_message_range_seeds as _split_segment_message_range_seeds,
)
from crxzipple.app.integration.context_workspace_session_segment_values import (
    chunks as _chunks,
    historical_segment_kind as _historical_segment_kind,
    is_archived_transcript_entry as _is_archived_transcript_entry,
    is_historical_segment_node_id as _is_historical_segment_node_id,
    is_session_instance_node_id as _is_session_instance_node_id,
    is_session_segment_node_id as _is_session_segment_node_id,
    is_session_segments_root_node_id as _is_session_segments_root_node_id,
    matches_message_scope as _matches_message_scope,
    node_part as _node_part,
    segment_messages as _segment_messages,
    session_segments_root_id as _session_segments_root_id,
)
from crxzipple.app.integration.context_workspace_session_segments import (
    current_turn_seed as _current_turn_seed,
    historical_segment_seed as _historical_segment_seed,
    session_instance_seed as _session_instance_seed,
    session_segment_seed as _session_segment_seed,
)
from crxzipple.app.integration.context_workspace_session_tool_lifecycle import (
    nested_tool_lifecycle_sources,
)


class SessionContextService(Protocol):
    def get_session(self, session_key: str) -> Session:
        ...

    def list_instances(
        self,
        data: ListSessionInstancesInput,
    ) -> list[SessionInstance]:
        ...

    def list_items(
        self,
        data: ListSessionItemsInput,
    ) -> list[SessionItem]:
        ...


class SessionContextNodeProvider:
    owner = "session"

    def __init__(
        self,
        session_service: SessionContextService,
        *,
        execution_query: Any | None = None,
        recent_limit: int = 8,
        historical_range_limit: int = 24,
        range_token_soft_limit: int = 1200,
        active_consumed_tool_history_limit: int = 8,
    ) -> None:
        self._session_service = session_service
        self._execution_query = execution_query
        self._recent_limit = max(int(recent_limit), 1)
        self._historical_range_limit = max(int(historical_range_limit), 1)
        self._range_token_soft_limit = max(int(range_token_soft_limit), 1)
        self._active_consumed_tool_history_limit = max(
            int(active_consumed_tool_history_limit),
            0,
        )

    def children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        if request.node.id == "session.current":
            return self._current_session_children(request)
        if _is_session_instance_node_id(request.node.id):
            return self._session_instance_children(request)
        if _is_session_segments_root_node_id(request.node.id):
            return self._session_segments_children(request)
        if _is_session_segment_node_id(request.node.id):
            return self._session_segment_children(request)
        if request.node.id == "session.turn.current":
            return self._current_turn_children(request)
        if request.node.id == "session.steps.current":
            return self._current_steps_children(request)
        if request.node.id.startswith("session.step."):
            return self._session_step_children(request)
        if _is_historical_segment_node_id(request.node.id):
            return self._historical_segment_range_children(request)
        if request.node.id.startswith("session.segment.items."):
            return self._segment_range_item_children(request)
        if request.node.id.startswith("session.tool_interactions.consumed."):
            return self._current_consumed_tool_history_children(request)
        if request.node.id == "session.items.current":
            return self._current_item_children(request)
        return ()

    def _current_session_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        session_key = request.workspace.session_key
        try:
            session = self._session_service.get_session(session_key)
            instances = self._session_service.list_instances(
                ListSessionInstancesInput(session_key=session_key),
            )
            active_messages = self._active_transcript_items_or_messages(session_key)
        except SessionNotFoundError:
            return ()

        active_item_count = len(active_messages)
        active_instance = next(
            (item for item in instances if item.id == session.active_session_id),
            None,
        )
        seeds: list[ContextNodeSeed] = []
        if active_instance is not None:
            seeds.append(
                _session_instance_seed(
                    instance=active_instance,
                    item_count=active_item_count,
                    parent_id="session.current",
                    active=True,
                    display_order=10,
                ),
            )

        display_order = 20
        for instance in instances:
            if instance.id == session.active_session_id:
                continue
            seeds.append(
                _session_instance_seed(
                    instance=instance,
                    parent_id="session.current",
                    item_count=None,
                    active=False,
                    display_order=display_order,
                ),
            )
            display_order += 10
        return tuple(seeds)

    def _session_instance_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        session_key = request.workspace.session_key
        try:
            session = self._session_service.get_session(session_key)
            instances = self._session_service.list_instances(
                ListSessionInstancesInput(session_key=session_key),
            )
        except SessionNotFoundError:
            return ()
        instance_id = _optional_text(request.node.owner_ref.get("session_id"))
        instance = next((item for item in instances if item.id == instance_id), None)
        if instance is None:
            return ()
        active = instance.id == session.active_session_id
        root_id = _session_segments_root_id(instance, active=active)
        summary = f"Segments for session instance #{instance.sequence_no}."
        return (
            ContextNodeSeed(
                node_id=root_id,
                parent_id=request.node.id,
                owner="session",
                kind="session_segments_root",
                title="Segments",
                summary=summary,
                state=ContextNodeState(collapsed=False, loaded=True),
                actions=_BASIC_ACTIONS,
                owner_ref={
                    "session_key": session_key,
                    "session_id": instance.id,
                    "active": active,
                },
                estimate=_text_estimate(summary),
                display_order=10,
            ),
        )

    def _session_segments_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        session_key = request.workspace.session_key
        try:
            session = self._session_service.get_session(session_key)
            instances = self._session_service.list_instances(
                ListSessionInstancesInput(session_key=session_key),
            )
            active_messages = self._active_transcript_items_or_messages(session_key)
        except SessionNotFoundError:
            return ()
        instance_id = _optional_text(request.node.owner_ref.get("session_id"))
        instance = next((item for item in instances if item.id == instance_id), None)
        if instance is None:
            return ()
        active = instance.id == session.active_session_id
        if active:
            return (
                _session_segment_seed(
                    instance=instance,
                    item_count=len(active_messages),
                    parent_id=request.node.id,
                    active=True,
                    display_order=10,
                ),
            )
        segment_kind = _historical_segment_kind(instance)
        return (
            _historical_segment_seed(
                instance=instance,
                messages=None,
                parent_id=request.node.id,
                segment_kind=segment_kind,
                message_scope=(
                    "archived" if segment_kind == "compacted" else "all"
                ),
                fallback_summary=None,
                display_order=10,
            ),
        )

    def _session_segment_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        session_key = request.workspace.session_key
        try:
            session = self._session_service.get_session(session_key)
            active_messages = self._active_transcript_items_or_messages(session_key)
        except SessionNotFoundError:
            return ()
        if request.node.id != "session.segment.active":
            return self._historical_segment_range_children(request)
        if not active_messages:
            return ()
        first_sequence = active_messages[0].sequence_no
        last_sequence = active_messages[-1].sequence_no
        current_run_id = _optional_text(request.workspace.metadata.get("last_run_id"))
        seeds: list[ContextNodeSeed] = []
        if current_run_id is not None:
            seeds.append(
                _current_turn_seed(
                    run_id=current_run_id,
                    session_key=session_key,
                    session_id=session.active_session_id,
                    parent_id=request.node.id,
                    display_order=5,
                ),
            )
        current_items_content = _current_items_range_prompt_content(
            tuple(active_messages),
            current_run_id=current_run_id,
            visible_tool_limit=self._active_consumed_tool_history_limit,
        )
        seeds.append(
            ContextNodeSeed(
                node_id="session.items.current",
                parent_id=request.node.id,
                owner="session",
                kind="session_item_range",
                title="Current Items",
                summary=_truncate(current_items_content.replace("\n", " "), 320),
                content=current_items_content,
                state=ContextNodeState(
                    collapsed=False,
                    loaded=True,
                ),
                actions=_BASIC_ACTIONS,
                owner_ref={
                    "session_key": session_key,
                    "session_id": session.active_session_id,
                    "from_sequence_no": first_sequence,
                    "to_sequence_no": last_sequence,
                    "segment_id": request.node.id,
                },
                estimate=_items_estimate(
                    tuple(active_messages),
                    current_run_id=current_run_id,
                ),
                revision=(
                    f"{_CURRENT_MESSAGES_RANGE_REVISION}.run"
                    if current_run_id is not None
                    else f"{_CURRENT_MESSAGES_RANGE_REVISION}.inspect"
                ),
                display_order=10,
                metadata={"item_count": len(active_messages)},
            ),
        )
        return tuple(seeds)

    def _current_turn_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        run_id = _optional_text(request.node.owner_ref.get("run_id"))
        if run_id is None:
            return ()
        summary = f"Runtime steps for current turn {run_id}."
        return (
            ContextNodeSeed(
                node_id="session.steps.current",
                parent_id=request.node.id,
                owner="session",
                kind="session_steps_root",
                title="Steps",
                summary=summary,
                state=ContextNodeState(collapsed=False, loaded=True),
                actions=_BASIC_ACTIONS,
                owner_ref={
                    "session_key": request.workspace.session_key,
                    "run_id": run_id,
                    "turn_id": run_id,
                },
                estimate=_text_estimate(summary),
                display_order=10,
            ),
        )

    def _current_steps_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        run_id = _optional_text(request.node.owner_ref.get("run_id"))
        if run_id is None or self._execution_query is None:
            return ()
        return _execution_step_node_seeds(
            self._execution_query,
            run_id,
            parent_id=request.node.id,
        )

    def _session_step_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        step_id = _optional_text(request.node.owner_ref.get("step_id"))
        if step_id is None or self._execution_query is None:
            return ()
        return _execution_step_item_node_seeds(
            self._execution_query,
            step_id,
            parent_id=request.node.id,
        )

    def _active_transcript_items_or_messages(
        self,
        session_key: str,
    ) -> list[Any]:
        return self._active_transcript_range_items_or_messages(
            session_key,
            after_sequence_no=None,
            before_sequence_no=None,
        )

    def _active_transcript_range_items_or_messages(
        self,
        session_key: str,
        *,
        after_sequence_no: int | None,
        before_sequence_no: int | None,
    ) -> list[Any]:
        list_items = getattr(self._session_service, "list_items", None)
        if list_items is None:
            return []
        return list(
            item
            for item in list_items(
                ListSessionItemsInput(
                    session_key=session_key,
                    active_session_only=True,
                    after_sequence_no=(
                        after_sequence_no - 1
                        if after_sequence_no is not None
                        else None
                    ),
                    before_sequence_no=(
                        before_sequence_no + 1
                        if before_sequence_no is not None
                        else None
                    ),
                ),
            )
            if not _is_archived_transcript_entry(item)
        )

    def _transcript_items_or_messages(
        self,
        session_key: str,
        *,
        active_session_only: bool,
        after_sequence_no: int | None = None,
        before_sequence_no: int | None = None,
    ) -> list[Any]:
        list_items = getattr(self._session_service, "list_items", None)
        if list_items is None:
            return []
        return list(
            list_items(
                ListSessionItemsInput(
                    session_key=session_key,
                    active_session_only=active_session_only,
                    after_sequence_no=after_sequence_no,
                    before_sequence_no=before_sequence_no,
                ),
            ),
        )

    def _current_item_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        session_key = request.workspace.session_key
        owner_ref = request.node.owner_ref
        after_sequence_no = _optional_int(owner_ref.get("from_sequence_no"))
        before_sequence_no = _optional_int(owner_ref.get("to_sequence_no"))
        try:
            messages = self._active_transcript_range_items_or_messages(
                session_key,
                after_sequence_no=after_sequence_no,
                before_sequence_no=before_sequence_no,
            )
        except SessionNotFoundError:
            return ()
        current_run_id = _optional_text(request.workspace.metadata.get("last_run_id"))
        session_id = _optional_text(owner_ref.get("session_id"))
        execution_summaries = (
            _execution_step_item_summaries(self._execution_query, current_run_id)
            if self._execution_query is not None and current_run_id is not None
            else ()
        )
        consumed_through_sequence_no = (
            _consumed_draft_input_through_sequence_no_from_summaries(
                execution_summaries,
                session_id=session_id,
            )
            if current_run_id is not None and session_id is not None
            else None
        )
        tool_lifecycle_facts = _tool_lifecycle_facts_from_execution_summaries(
            execution_summaries,
        )
        return _message_node_seeds(
            tuple(messages),
            parent_id=request.node.id,
            current_run_id=current_run_id,
            consumed_through_sequence_no=consumed_through_sequence_no,
            tool_lifecycle_facts=tool_lifecycle_facts,
            collapse_consumed_tool_history=True,
            consumed_tool_history_visible_limit=(
                self._active_consumed_tool_history_limit
            ),
        )

    def _current_consumed_tool_history_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        session_key = request.workspace.session_key
        owner_ref = request.node.owner_ref
        session_id = _optional_text(owner_ref.get("session_id"))
        from_sequence_no = _optional_int(owner_ref.get("from_sequence_no"))
        to_sequence_no = _optional_int(owner_ref.get("to_sequence_no"))
        if session_id is None or from_sequence_no is None or to_sequence_no is None:
            return ()
        try:
            messages = self._transcript_items_or_messages(
                session_key,
                active_session_only=True,
                after_sequence_no=from_sequence_no - 1,
                before_sequence_no=to_sequence_no + 1,
            )
        except SessionNotFoundError:
            return ()
        range_messages = tuple(
            message
            for message in messages
            if message.session_id == session_id
            and from_sequence_no <= message.sequence_no <= to_sequence_no
        )
        current_run_id = _optional_text(request.workspace.metadata.get("last_run_id"))
        execution_summaries = (
            _execution_step_item_summaries(self._execution_query, current_run_id)
            if self._execution_query is not None and current_run_id is not None
            else ()
        )
        consumed_through_sequence_no = (
            _consumed_draft_input_through_sequence_no_from_summaries(
                execution_summaries,
                session_id=session_id,
            )
            if current_run_id is not None
            else None
        )
        return _message_node_seeds(
            range_messages,
            parent_id=request.node.id,
            current_run_id=current_run_id,
            consumed_through_sequence_no=consumed_through_sequence_no,
            tool_lifecycle_facts=_tool_lifecycle_facts_from_execution_summaries(
                execution_summaries,
            ),
            collapse_consumed_tool_history=False,
            only_tool_interactions=True,
        )

    def _historical_segment_range_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        session_key = request.workspace.session_key
        owner_ref = request.node.owner_ref
        session_id = _optional_text(owner_ref.get("session_id"))
        message_scope = _optional_text(owner_ref.get("message_scope")) or "all"
        if session_id is None:
            return ()
        try:
            messages = self._transcript_items_or_messages(
                session_key,
                active_session_only=False,
            )
        except SessionNotFoundError:
            return ()
        segment_messages = _segment_messages(
            tuple(messages),
            session_id=session_id,
            message_scope=message_scope,
        )
        ranges: list[ContextNodeSeed] = []
        display_order = 10
        chunks = _chunks(segment_messages, self._recent_limit)
        visible_chunks = chunks[: self._historical_range_limit]
        for chunk in visible_chunks:
            ranges.append(
                _segment_message_range_seed(
                    parent_id=request.node.id,
                    session_key=session_key,
                    session_id=session_id,
                    messages=chunk,
                    segment_kind=owner_ref.get("segment_kind"),
                    message_scope=message_scope,
                    range_token_soft_limit=self._range_token_soft_limit,
                    display_order=display_order,
                )
            )
            display_order += 10
        omitted_chunks = chunks[self._historical_range_limit :]
        if omitted_chunks:
            omitted_item_count = sum(len(chunk) for chunk in omitted_chunks)
            ranges.append(
                _range_notice_seed(
                    node_id=f"session.segment.ranges.more.{_node_part(session_id)}",
                    parent_id=request.node.id,
                    title="More Message Ranges",
                    summary=(
                        f"{len(omitted_chunks)} more range pages with "
                        f"{omitted_item_count} messages are hidden by the "
                        "session range page limit."
                    ),
                    display_order=display_order,
                    metadata={
                        "notice_kind": "range_limit",
                        "range_reason_code": "range_page_limit",
                        "segment_kind": owner_ref.get("segment_kind"),
                        "message_scope": message_scope,
                        "omitted_range_count": len(omitted_chunks),
                        "omitted_item_count": omitted_item_count,
                        "range_page_limit": self._historical_range_limit,
                    },
                ),
            )
        return tuple(ranges)

    def _segment_range_item_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        session_key = request.workspace.session_key
        owner_ref = request.node.owner_ref
        session_id = _optional_text(owner_ref.get("session_id"))
        message_scope = _optional_text(owner_ref.get("message_scope")) or "all"
        from_sequence_no = _optional_int(owner_ref.get("from_sequence_no"))
        to_sequence_no = _optional_int(owner_ref.get("to_sequence_no"))
        if session_id is None or from_sequence_no is None or to_sequence_no is None:
            return ()
        try:
            messages = self._transcript_items_or_messages(
                session_key,
                active_session_only=False,
                after_sequence_no=from_sequence_no - 1,
                before_sequence_no=to_sequence_no + 1,
            )
        except SessionNotFoundError:
            return ()
        range_messages = tuple(
            message
            for message in messages
            if message.session_id == session_id
            and _matches_message_scope(
                message,
                message_scope=message_scope,
            )
        )
        range_estimate = _items_estimate(
            range_messages,
            current_run_id=_optional_text(request.workspace.metadata.get("last_run_id")),
        )
        if range_estimate.text_tokens > self._range_token_soft_limit:
            if len(range_messages) > 1:
                return _split_segment_message_range_seeds(
                    parent_id=request.node.id,
                    session_key=session_key,
                    session_id=session_id,
                    messages=range_messages,
                    segment_kind=owner_ref.get("segment_kind"),
                    message_scope=message_scope,
                    range_token_soft_limit=self._range_token_soft_limit,
                )
            return (
                _range_notice_seed(
                    node_id=f"session.segment.range.blocked.{_node_part(session_id)}.{from_sequence_no}.{to_sequence_no}",
                    parent_id=request.node.id,
                    title="Range Over Budget",
                    summary=(
                        "This message range exceeds the session prompt budget. "
                        "Keep the segment summary visible or use session owner tools "
                        "such as sessions_history with a narrower limit."
                    ),
                    display_order=10,
                    metadata={
                        "notice_kind": "range_budget",
                        "range_budget_status": "blocked",
                        "range_reason_code": "over_budget",
                        "range_budget_soft_limit": self._range_token_soft_limit,
                        "estimated_expanded_text_tokens": range_estimate.text_tokens,
                        "estimated_expanded_text_chars": range_estimate.text_chars,
                        "item_count": len(range_messages),
                        "segment_kind": owner_ref.get("segment_kind"),
                        "message_scope": message_scope,
                    },
                ),
            )
        return _message_node_seeds(
            range_messages,
            parent_id=request.node.id,
            current_run_id=_optional_text(request.workspace.metadata.get("last_run_id")),
            consumed_through_sequence_no=None,
            tool_lifecycle_facts={},
        )


_BASIC_ACTIONS = (
    ContextAction.EXPAND,
    ContextAction.COLLAPSE,
    ContextAction.PIN,
    ContextAction.UNPIN,
    ContextAction.ESTIMATE,
)

_CURRENT_MESSAGES_RANGE_REVISION = "2026-06-09.current_messages_visible_history.v2"
_TOOL_INTERACTION_NODE_REVISION = "2026-06-09.tool_interaction_visible_result.v2"


def _consumed_draft_input_through_sequence_no_from_summaries(
    summaries: tuple[dict[str, object], ...],
    *,
    session_id: str,
) -> int | None:
    consumed_through: int | None = None
    for summary in summaries:
        consumption = summary.get("llm_transcript_consumption")
        if not isinstance(consumption, dict):
            continue
        sequence_range = consumption.get("draft_input_sequence_range")
        if not isinstance(sequence_range, dict):
            continue
        sessions = sequence_range.get("sessions")
        if not isinstance(sessions, list):
            continue
        for item in sessions:
            if not isinstance(item, dict):
                continue
            if _optional_text(item.get("session_id")) != session_id:
                continue
            to_sequence_no = _optional_int(item.get("to_sequence_no"))
            if to_sequence_no is None:
                continue
            consumed_through = (
                to_sequence_no
                if consumed_through is None
                else max(consumed_through, to_sequence_no)
            )
    return consumed_through


def _tool_lifecycle_facts_from_execution_summaries(
    summaries: tuple[dict[str, object], ...],
) -> dict[str, dict[str, object]]:
    facts_by_ref: dict[str, dict[str, object]] = {}
    for summary in summaries:
        facts = _explicit_tool_lifecycle_fact_payload(summary)
        if not facts:
            continue
        for ref in _tool_lifecycle_fact_refs(summary, facts):
            current = facts_by_ref.setdefault(ref, {})
            current.update(facts)
        replacement_facts = _replacement_tool_lifecycle_fact_payload(summary, facts)
        for ref in _tool_lifecycle_superseded_target_refs(facts):
            current = facts_by_ref.setdefault(ref, {})
            current.update(replacement_facts)
    return facts_by_ref


def _explicit_tool_lifecycle_fact_payload(
    summary: dict[str, object],
) -> dict[str, object]:
    payload: dict[str, object] = {}
    for source in _tool_lifecycle_summary_sources(summary):
        for key in (
            "superseded",
            "superseded_by_tool_call_id",
            "replaced_by_tool_call_id",
            "replacement_tool_call_id",
            "supersedes_tool_call_id",
            "supersedes_tool_run_id",
            "supersedes_result_session_item_id",
            "lifecycle_status",
            "evidence_lifecycle_status",
            "evidence_lifecycle",
        ):
            if key in source:
                payload[key] = source[key]
    return payload


def _tool_lifecycle_summary_sources(
    summary: dict[str, object],
) -> tuple[dict[str, object], ...]:
    sources: list[dict[str, object]] = []
    sources.extend(nested_tool_lifecycle_sources(summary))
    metadata = summary.get("metadata")
    sources.extend(nested_tool_lifecycle_sources(metadata))
    return tuple(sources)


def _tool_lifecycle_fact_refs(
    summary: dict[str, object],
    facts: dict[str, object],
) -> tuple[str, ...]:
    refs: list[str] = []
    for source in (summary, facts):
        for key in ("tool_call_id", "result_session_item_id", "tool_run_id"):
            value = _optional_text(source.get(key))
            if value is not None:
                refs.append(value)
    return tuple(dict.fromkeys(refs))


def _tool_lifecycle_superseded_target_refs(
    facts: dict[str, object],
) -> tuple[str, ...]:
    refs: list[str] = []
    for key in (
        "supersedes_tool_call_id",
        "supersedes_tool_run_id",
        "supersedes_result_session_item_id",
    ):
        value = _optional_text(facts.get(key))
        if value is not None:
            refs.append(value)
    return tuple(dict.fromkeys(refs))


def _replacement_tool_lifecycle_fact_payload(
    summary: dict[str, object],
    facts: dict[str, object],
) -> dict[str, object]:
    payload: dict[str, object] = {
        "superseded": True,
        "lifecycle_status": "superseded",
    }
    replacement_tool_call_id = (
        _optional_text(summary.get("tool_call_id"))
        or _optional_text(facts.get("tool_call_id"))
        or _optional_text(facts.get("replacement_tool_call_id"))
        or _optional_text(facts.get("superseded_by_tool_call_id"))
    )
    if replacement_tool_call_id is not None:
        payload["superseded_by_tool_call_id"] = replacement_tool_call_id
    return payload


__all__ = ["SessionContextNodeProvider"]
