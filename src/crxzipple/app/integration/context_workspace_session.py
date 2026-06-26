"""Session context tree adapter.

This module lives in app integration because it maps Session-owned application
facts into Context Workspace node handles without making either module import
the other module's internals.
"""

from __future__ import annotations

from typing import Any

from crxzipple.modules.context_workspace.application import (
    ContextChildrenRequest,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextNodeSeed,
)
from crxzipple.modules.session.domain import SessionNotFoundError
from crxzipple.app.integration.context_workspace_session_content_values import (
    optional_int as _optional_int,
    optional_text as _optional_text,
)
from crxzipple.app.integration.context_workspace_session_execution import (
    current_steps_root_seed as _current_steps_root_seed,
    execution_step_item_node_seeds as _execution_step_item_node_seeds,
    execution_step_item_summaries as _execution_step_item_summaries,
    execution_step_node_seeds as _execution_step_node_seeds,
)
from crxzipple.app.integration.context_workspace_session_item_nodes import (
    consumed_tool_history_message_node_seeds as _consumed_tool_history_message_node_seeds,
    current_item_message_node_seeds as _current_item_message_node_seeds,
    current_items_range_seed as _current_items_range_seed,
)
from crxzipple.app.integration.context_workspace_session_segment_ranges import (
    historical_segment_range_seeds as _historical_segment_range_seeds,
    segment_range_item_seeds as _segment_range_item_seeds,
)
from crxzipple.app.integration.context_workspace_session_reader import (
    SessionContextService,
    active_transcript_items_or_messages as _active_transcript_items_or_messages,
    active_transcript_range_items_or_messages as _active_transcript_range_items_or_messages,
    find_session_instance as _find_session_instance,
    get_session_and_instances as _get_session_and_instances,
    transcript_items_or_messages as _transcript_items_or_messages,
)
from crxzipple.app.integration.context_workspace_session_segment_values import (
    historical_segment_kind as _historical_segment_kind,
    is_historical_segment_node_id as _is_historical_segment_node_id,
    is_session_instance_node_id as _is_session_instance_node_id,
    is_session_segment_node_id as _is_session_segment_node_id,
    is_session_segments_root_node_id as _is_session_segments_root_node_id,
)
from crxzipple.app.integration.context_workspace_session_segments import (
    current_turn_seed as _current_turn_seed,
    historical_segment_seed as _historical_segment_seed,
    session_instance_seed as _session_instance_seed,
    session_segments_root_seed as _session_segments_root_seed,
    session_segment_seed as _session_segment_seed,
)


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
            session, instances = _get_session_and_instances(
                self._session_service,
                session_key,
            )
            active_messages = _active_transcript_items_or_messages(
                self._session_service,
                session_key,
            )
        except SessionNotFoundError:
            return ()

        active_item_count = len(active_messages)
        active_instance = _find_session_instance(
            instances,
            session.active_session_id,
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
            session, instances = _get_session_and_instances(
                self._session_service,
                session_key,
            )
        except SessionNotFoundError:
            return ()
        instance_id = _optional_text(request.node.owner_ref.get("session_id"))
        instance = _find_session_instance(instances, instance_id)
        if instance is None:
            return ()
        active = instance.id == session.active_session_id
        return (
            _session_segments_root_seed(
                instance=instance,
                parent_id=request.node.id,
                active=active,
            ),
        )

    def _session_segments_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        session_key = request.workspace.session_key
        try:
            session, instances = _get_session_and_instances(
                self._session_service,
                session_key,
            )
            active_messages = _active_transcript_items_or_messages(
                self._session_service,
                session_key,
            )
        except SessionNotFoundError:
            return ()
        instance_id = _optional_text(request.node.owner_ref.get("session_id"))
        instance = _find_session_instance(instances, instance_id)
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
            active_messages = _active_transcript_items_or_messages(
                self._session_service,
                session_key,
            )
        except SessionNotFoundError:
            return ()
        if request.node.id != "session.segment.active":
            return self._historical_segment_range_children(request)
        if not active_messages:
            return ()
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
        seeds.append(
            _current_items_range_seed(
                tuple(active_messages),
                parent_id=request.node.id,
                session_key=session_key,
                session_id=session.active_session_id,
                segment_id=request.node.id,
                current_run_id=current_run_id,
                visible_tool_limit=self._active_consumed_tool_history_limit,
                actions=_BASIC_ACTIONS,
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
        return (
            _current_steps_root_seed(
                run_id=run_id,
                session_key=request.workspace.session_key,
                parent_id=request.node.id,
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

    def _current_item_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        session_key = request.workspace.session_key
        owner_ref = request.node.owner_ref
        after_sequence_no = _optional_int(owner_ref.get("from_sequence_no"))
        before_sequence_no = _optional_int(owner_ref.get("to_sequence_no"))
        try:
            messages = _active_transcript_range_items_or_messages(
                self._session_service,
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
        return _current_item_message_node_seeds(
            tuple(messages),
            parent_id=request.node.id,
            current_run_id=current_run_id,
            session_id=session_id,
            execution_summaries=execution_summaries,
            consumed_tool_history_visible_limit=self._active_consumed_tool_history_limit,
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
            messages = _transcript_items_or_messages(
                self._session_service,
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
        return _consumed_tool_history_message_node_seeds(
            range_messages,
            parent_id=request.node.id,
            current_run_id=current_run_id,
            session_id=session_id,
            execution_summaries=execution_summaries,
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
            messages = _transcript_items_or_messages(
                self._session_service,
                session_key,
                active_session_only=False,
            )
        except SessionNotFoundError:
            return ()
        return _historical_segment_range_seeds(
            parent_id=request.node.id,
            session_key=session_key,
            session_id=session_id,
            messages=tuple(messages),
            segment_kind=owner_ref.get("segment_kind"),
            message_scope=message_scope,
            recent_limit=self._recent_limit,
            historical_range_limit=self._historical_range_limit,
            range_token_soft_limit=self._range_token_soft_limit,
        )

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
            messages = _transcript_items_or_messages(
                self._session_service,
                session_key,
                active_session_only=False,
                after_sequence_no=from_sequence_no - 1,
                before_sequence_no=to_sequence_no + 1,
            )
        except SessionNotFoundError:
            return ()
        return _segment_range_item_seeds(
            parent_id=request.node.id,
            session_key=session_key,
            session_id=session_id,
            messages=tuple(messages),
            segment_kind=owner_ref.get("segment_kind"),
            message_scope=message_scope,
            from_sequence_no=from_sequence_no,
            to_sequence_no=to_sequence_no,
            current_run_id=_optional_text(request.workspace.metadata.get("last_run_id")),
            range_token_soft_limit=self._range_token_soft_limit,
        )


_BASIC_ACTIONS = (
    ContextAction.EXPAND,
    ContextAction.COLLAPSE,
    ContextAction.PIN,
    ContextAction.UNPIN,
    ContextAction.ESTIMATE,
)

__all__ = ["SessionContextNodeProvider"]
