"""Session context tree adapter.

This module lives in app integration because it maps Session-owned application
facts into Context Workspace node handles without making either module import
the other module's internals.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol

from crxzipple.modules.context_workspace.application import (
    ContextChildrenRequest,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextEstimate,
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
    SessionItemKind,
    SessionNotFoundError,
)
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
)
from crxzipple.shared.content_blocks import (
    FILE_BLOCK_TYPE,
    FILE_REF_BLOCK_TYPE,
    IMAGE_BLOCK_TYPE,
    IMAGE_REF_BLOCK_TYPE,
    TEXT_BLOCK_TYPE,
    content_blocks_from_payload,
    describe_content_for_text_fallback,
)
from crxzipple.shared.time import format_datetime_utc


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


def _evidence_facts(
    *,
    tool_name: str,
    payload: dict[str, object],
    details: object,
    metadata: object,
) -> dict[str, object]:
    facts: dict[str, object] = {}
    for source in (details, metadata):
        if not isinstance(source, dict):
            continue
        for fact_key, source_keys in (
            ("kind", ("kind", "action", "operation")),
            ("url", ("url", "page_url", "current_url", "href", "browser_target_url")),
            ("title", ("title", "page_title")),
            (
                "target_id",
                (
                    "target_id",
                    "targetId",
                    "browser_target_id",
                    "browser_observation_target_id",
                ),
            ),
            (
                "profile",
                (
                    "profile",
                    "profile_name",
                    "browser_profile",
                    "browser_context_profile",
                ),
            ),
            ("profile_source", ("profile_source", "browser_profile_source")),
            ("allocation_id", ("browser_allocation_id", "browser_context_lease_id")),
            ("host_service_key", ("browser_host_service_key",)),
            ("origin", ("browser_target_origin",)),
            ("endpoint", ("endpoint", "api_endpoint", "request_url", "path")),
            ("method", ("method", "request_method")),
            ("http_status", ("status_code", "http_status", "response_status")),
            ("request_id", ("request_id", "requestId")),
            ("body_ref", ("body_ref", "response_body_ref")),
            ("request_body_ref", ("request_body_ref",)),
            ("selector", ("verified_selector", "selector", "matched_selector")),
            ("ref", ("verified_ref", "ref", "target_ref", "element_ref")),
        ):
            if fact_key in facts:
                continue
            value = _find_first_text(source, source_keys)
            if value is not None:
                facts[fact_key] = _truncate(value, 180)
        _merge_artifact_evidence_facts(facts, source)
        _merge_structured_evidence_facts(facts, source)
    for fact_key, source_keys in (
        ("tool_run_id", ("tool_run_id",)),
        ("status", ("status",)),
    ):
        value = _find_first_text(payload, source_keys)
        if value is not None:
            facts[fact_key] = _truncate(value, 180)
    if tool_name.startswith("browser.") and "kind" not in facts:
        facts["kind"] = tool_name.removeprefix("browser.")
    return facts


def _merge_artifact_evidence_facts(
    facts: dict[str, object],
    source: dict[str, object],
) -> None:
    if "artifact_ids" in facts:
        return
    artifact_ids = source.get("artifact_ids")
    if not isinstance(artifact_ids, list):
        artifact_ids = source.get("browser_artifact_ids")
    if not isinstance(artifact_ids, list):
        return
    normalized: list[str] = []
    for item in artifact_ids:
        value = _optional_text(item)
        if value is not None:
            normalized.append(_truncate(value, 180))
        if len(normalized) >= 8:
            break
    if normalized:
        facts["artifact_ids"] = list(dict.fromkeys(normalized))


def _merge_structured_evidence_facts(
    facts: dict[str, object],
    source: dict[str, object],
) -> None:
    evidence = source.get("browser_evidence")
    if not isinstance(evidence, dict):
        return
    for key, alias in (
        ("payload_shape", None),
        ("result_shape", None),
        ("runtime_globals", None),
        ("verified_ref", "ref"),
        ("verified_selector", "selector"),
    ):
        if key in facts or (alias is not None and alias in facts):
            continue
        value = _small_structured_evidence_fact(evidence.get(key))
        if value is not None:
            facts[key] = value


def _small_structured_evidence_fact(value: object, *, depth: int = 0) -> object | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return _truncate(value, 240)
    if isinstance(value, list):
        items: list[object] = []
        for item in value[:12]:
            normalized = _small_structured_evidence_fact(item, depth=depth + 1)
            if normalized is not None:
                items.append(normalized)
        return items or None
    if isinstance(value, dict):
        if depth >= 4:
            return {"type": "object", "keys": len(value)}
        normalized: dict[str, object] = {}
        for index, (item_key, item_value) in enumerate(value.items()):
            if index >= 16:
                normalized["_truncated_keys"] = max(len(value) - 16, 0)
                break
            item = _small_structured_evidence_fact(item_value, depth=depth + 1)
            if item is not None:
                normalized[str(item_key)] = item
        return normalized or None
    return _truncate(str(value), 240)


def _evidence_type(
    *,
    tool_name: str,
    status: str,
    facts: dict[str, object],
) -> str:
    if status.lower() not in {"succeeded", "completed", "success"}:
        return "failed_attempt"
    kind = _optional_text(facts.get("kind")) or ""
    if "hypothesis" in facts:
        return "hypothesis"
    if "endpoint" in facts or kind.startswith("network"):
        return "api_endpoint"
    if "result_shape" in facts:
        return "result_shape"
    if "payload_shape" in facts:
        return "payload_shape"
    if tool_name.startswith("browser.") and (
        "selector" in facts or "ref" in facts
    ):
        return "observation"
    if tool_name.startswith("browser."):
        return "observation"
    return "user_visible_result"


def _is_failed_tool_status(status: str) -> bool:
    return status.strip().lower() not in {"succeeded", "completed", "success"}


def _tool_interaction_observed(
    *,
    tool_name: str,
    status: str,
    result_message: SessionItem,
) -> bool:
    if _is_failed_tool_status(status):
        return False
    payload = result_message.content_payload
    details = payload.get("details")
    metadata = payload.get("metadata")
    facts = _evidence_facts(
        tool_name=tool_name,
        payload=payload,
        details=details,
        metadata=metadata,
    )
    evidence_type = _evidence_type(
        tool_name=tool_name,
        status=status,
        facts=facts,
    )
    return evidence_type in {
        "api_endpoint",
        "result_shape",
        "payload_shape",
        "user_visible_result",
        "observation",
    }


def _tool_interaction_superseded(
    result_message: SessionItem,
    lifecycle_facts: dict[str, object] | None = None,
) -> bool:
    for source in _tool_interaction_fact_sources(
        result_message,
        lifecycle_facts=lifecycle_facts,
    ):
        if _truthy(source.get("superseded")):
            return True
        lifecycle_status = _optional_text(source.get("lifecycle_status"))
        if lifecycle_status == "superseded":
            return True
    return False


def _tool_interaction_superseded_by_tool_call_id(
    result_message: SessionItem,
    lifecycle_facts: dict[str, object] | None = None,
) -> str | None:
    for source in _tool_interaction_fact_sources(
        result_message,
        lifecycle_facts=lifecycle_facts,
    ):
        for key in (
            "superseded_by_tool_call_id",
            "replaced_by_tool_call_id",
            "replacement_tool_call_id",
        ):
            value = _optional_text(source.get(key))
            if value is not None:
                return _truncate(value, 180)
    return None


def _tool_interaction_fact_sources(
    result_message: SessionItem,
    lifecycle_facts: dict[str, object] | None = None,
) -> tuple[dict[str, object], ...]:
    sources: list[dict[str, object]] = []
    if lifecycle_facts:
        sources.append(lifecycle_facts)
    for candidate in (
        result_message.metadata,
        result_message.content_payload,
        result_message.content_payload.get("metadata"),
        result_message.content_payload.get("details"),
    ):
        if isinstance(candidate, dict):
            sources.append(candidate)
    return tuple(sources)


def _find_first_text(value: object, keys: tuple[str, ...]) -> str | None:
    if isinstance(value, dict):
        normalized = {str(key): item for key, item in value.items()}
        for key in keys:
            if key in normalized:
                candidate = _scalar_text(normalized[key])
                if candidate is not None:
                    return candidate
        for item in normalized.values():
            found = _find_first_text(item, keys)
            if found is not None:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_first_text(item, keys)
            if found is not None:
                return found
    return None


def _scalar_text(value: object) -> str | None:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None


def _session_instance_seed(
    *,
    instance: SessionInstance,
    item_count: int | None,
    parent_id: str,
    active: bool,
    display_order: int,
) -> ContextNodeSeed:
    if active:
        summary = (
            f"Active {instance.kind.value} instance #{instance.sequence_no} has "
            f"{item_count or 0} visible items."
        )
        node_id = "session.instance.active"
        title = "Active Instance"
    else:
        summary = f"Closed {instance.kind.value} instance #{instance.sequence_no}."
        node_id = f"session.instance.closed.{_node_part(instance.id)}"
        title = f"Closed Instance #{instance.sequence_no}"
    return ContextNodeSeed(
        node_id=node_id,
        parent_id=parent_id,
        owner="session",
        kind="session_instance",
        title=title,
        summary=summary,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=_BASIC_ACTIONS,
        owner_ref={
            "session_key": instance.session_key,
            "session_id": instance.id,
            "sequence_no": instance.sequence_no,
            "status": instance.status,
            "active": active,
            "item_count": item_count or 0,
        },
        estimate=_text_estimate(summary),
        display_order=display_order,
        metadata={
            "opened_at": format_datetime_utc(instance.opened_at),
            "closed_at": (
                format_datetime_utc(instance.closed_at)
                if instance.closed_at is not None
                else None
            ),
            "item_count": item_count,
        },
    )


def _session_segment_seed(
    *,
    instance: SessionInstance,
    item_count: int,
    parent_id: str,
    active: bool,
    display_order: int,
) -> ContextNodeSeed:
    segment_kind = "active" if active else _historical_segment_kind(instance)
    summary = (
        f"{segment_kind.title()} segment for instance #{instance.sequence_no} has "
        f"{item_count} visible items."
    )
    return ContextNodeSeed(
        node_id=(
            "session.segment.active"
            if active
            else f"session.segment.{segment_kind}.{_node_part(instance.id)}"
        ),
        parent_id=parent_id,
        owner="session",
        kind="session_segment",
        title=f"{segment_kind.title()} Segment",
        summary=summary,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=_BASIC_ACTIONS,
        owner_ref={
            "session_key": instance.session_key,
            "session_id": instance.id,
            "sequence_no": instance.sequence_no,
            "status": instance.status,
            "segment_kind": segment_kind,
            "item_count": item_count,
        },
        estimate=_text_estimate(summary),
        display_order=display_order,
        metadata={
            "opened_at": format_datetime_utc(instance.opened_at),
            "closed_at": (
                format_datetime_utc(instance.closed_at)
                if instance.closed_at is not None
                else None
            ),
            "item_count": item_count,
        },
    )


def _current_turn_seed(
    *,
    run_id: str,
    session_key: str,
    session_id: str | None,
    parent_id: str,
    display_order: int,
) -> ContextNodeSeed:
    summary = f"Current turn runtime facts are owned by orchestration run {run_id}."
    return ContextNodeSeed(
        node_id="session.turn.current",
        parent_id=parent_id,
        owner="session",
        kind="session_turn",
        title="Current Turn",
        summary=summary,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=_BASIC_ACTIONS,
        owner_ref={
            "session_key": session_key,
            "session_id": session_id or "",
            "run_id": run_id,
            "turn_id": run_id,
        },
        estimate=_text_estimate(summary),
        display_order=display_order,
        metadata={"run_id": run_id},
    )


def _historical_segment_seed(
    *,
    instance: SessionInstance,
    messages: tuple[SessionItem, ...] | None,
    parent_id: str,
    segment_kind: str,
    message_scope: str,
    fallback_summary: str | None,
    display_order: int,
) -> ContextNodeSeed:
    summary_text = _segment_summary_text(instance.metadata) or fallback_summary
    item_count = len(messages) if messages is not None else None
    archived_count = sum(
        1
        for message in messages or ()
        if _is_archived_transcript_entry(message)
    )
    fallback = f"{segment_kind.title()} segment #{instance.sequence_no} is available."
    if item_count is not None:
        fallback = (
            f"{segment_kind.title()} segment #{instance.sequence_no} has "
            f"{item_count} messages."
        )
    if archived_count > 0:
        fallback = (
            f"{segment_kind.title()} segment #{instance.sequence_no} has "
            f"{archived_count} archived messages."
        )
    summary = _truncate(summary_text or fallback, 320)
    owner_ref: dict[str, object] = {
        "session_key": instance.session_key,
        "session_id": instance.id,
        "sequence_no": instance.sequence_no,
        "status": instance.status,
        "segment_kind": segment_kind,
        "message_scope": message_scope,
        "archived_count": archived_count,
        "has_summary": bool(summary_text),
    }
    metadata: dict[str, object] = {
        "opened_at": format_datetime_utc(instance.opened_at),
        "closed_at": (
            format_datetime_utc(instance.closed_at)
            if instance.closed_at is not None
            else ""
        ),
        "reset_reason": instance.reset_reason or "",
        "archived_count": archived_count,
        "message_scope": message_scope,
        "has_summary": bool(summary_text),
    }
    if item_count is not None:
        owner_ref["item_count"] = item_count
        metadata["item_count"] = item_count
    return ContextNodeSeed(
        node_id=f"session.segment.{segment_kind}.{_node_part(instance.id)}",
        parent_id=parent_id,
        owner="session",
        kind="session_segment",
        title=f"{segment_kind.title()} Segment #{instance.sequence_no}",
        summary=summary,
        content=summary_text or "",
        state=ContextNodeState(collapsed=True, loaded=False),
        actions=_BASIC_ACTIONS,
        owner_ref=owner_ref,
        estimate=_text_estimate(summary),
        display_order=display_order,
        metadata=metadata,
    )


def _segment_message_range_seed(
    *,
    parent_id: str,
    session_key: str,
    session_id: str,
    messages: tuple[SessionItem, ...],
    segment_kind: object,
    message_scope: str,
    range_token_soft_limit: int,
    display_order: int,
) -> ContextNodeSeed:
    first_sequence_no = messages[0].sequence_no
    last_sequence_no = messages[-1].sequence_no
    estimate = _items_estimate(messages, current_run_id=None)
    archived = all(_is_archived_transcript_entry(message) for message in messages)
    budget_status = _range_budget_status(
        estimate=estimate,
        item_count=len(messages),
        soft_limit=range_token_soft_limit,
    )
    summary = (
        f"{len(messages)} messages in this segment, sequences "
        f"{first_sequence_no}-{last_sequence_no}."
    )
    if budget_status == "split_required":
        summary = f"{summary} Expanding this range will reveal smaller ranges first."
    elif budget_status == "blocked":
        summary = f"{summary} Expanding this range is blocked by the session budget."
    return ContextNodeSeed(
        node_id=(
            f"session.segment.items.{_node_part(session_id)}."
            f"{first_sequence_no}.{last_sequence_no}"
        ),
        parent_id=parent_id,
        owner="session",
        kind="session_item_range",
        title=f"Messages {first_sequence_no}-{last_sequence_no}",
        summary=summary,
        state=ContextNodeState(
            collapsed=True,
            loaded=False,
            archived=archived,
            status="archived" if archived else "available",
            render_reason="archived_by_compaction" if archived else "",
        ),
        actions=_BASIC_ACTIONS,
        owner_ref={
            "session_key": session_key,
            "session_id": session_id,
            "from_sequence_no": first_sequence_no,
            "to_sequence_no": last_sequence_no,
            "item_count": len(messages),
            "segment_kind": segment_kind,
            "message_scope": message_scope,
            "archived": archived,
        },
        estimate=ContextEstimate(text_chars=80, text_tokens=20),
        display_order=display_order,
        metadata={
            "item_count": len(messages),
            "segment_kind": segment_kind,
            "message_scope": message_scope,
            "archived": archived,
            "archived_count": sum(
                1
                for message in messages
                if _is_archived_transcript_entry(message)
            ),
            "range_budget_status": budget_status,
            "range_reason_code": _range_reason_code(budget_status),
            "range_budget_soft_limit": range_token_soft_limit,
            "estimated_expanded_text_tokens": estimate.text_tokens,
            "estimated_expanded_text_chars": estimate.text_chars,
        },
    )


def _split_segment_message_range_seeds(
    *,
    parent_id: str,
    session_key: str,
    session_id: str,
    messages: tuple[SessionItem, ...],
    segment_kind: object,
    message_scope: str,
    range_token_soft_limit: int,
) -> tuple[ContextNodeSeed, ...]:
    midpoint = max(len(messages) // 2, 1)
    split_chunks = tuple(chunk for chunk in (messages[:midpoint], messages[midpoint:]) if chunk)
    seeds: list[ContextNodeSeed] = []
    display_order = 10
    for chunk in split_chunks:
        seeds.append(
            _segment_message_range_seed(
                parent_id=parent_id,
                session_key=session_key,
                session_id=session_id,
                messages=chunk,
                segment_kind=segment_kind,
                message_scope=message_scope,
                range_token_soft_limit=range_token_soft_limit,
                display_order=display_order,
            ),
        )
        display_order += 10
    return tuple(seeds)


def _range_notice_seed(
    *,
    node_id: str,
    parent_id: str,
    title: str,
    summary: str,
    display_order: int,
    metadata: dict[str, object],
) -> ContextNodeSeed:
    return ContextNodeSeed(
        node_id=node_id,
        parent_id=parent_id,
        owner="session",
        kind="session_range_notice",
        title=title,
        summary=summary,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=_BASIC_ACTIONS,
        estimate=_text_estimate(summary),
        display_order=display_order,
        metadata=metadata,
    )


def _range_budget_status(
    *,
    estimate: ContextEstimate,
    item_count: int,
    soft_limit: int,
) -> str:
    if estimate.text_tokens <= soft_limit:
        return "ok"
    if item_count > 1:
        return "split_required"
    return "blocked"


def _range_reason_code(budget_status: str) -> str:
    if budget_status == "split_required":
        return "split_required"
    if budget_status == "blocked":
        return "over_budget"
    return "within_budget"


def _message_node_seeds(
    messages: tuple[SessionItem, ...],
    *,
    parent_id: str,
    current_run_id: str | None = None,
    consumed_through_sequence_no: int | None = None,
    tool_lifecycle_facts: dict[str, dict[str, object]] | None = None,
    collapse_consumed_tool_history: bool = False,
    consumed_tool_history_visible_limit: int = 8,
    only_tool_interactions: bool = False,
) -> tuple[ContextNodeSeed, ...]:
    sorted_messages = tuple(sorted(messages, key=lambda item: item.sequence_no))
    current_inbound_sequence_no = _current_inbound_sequence_no(
        sorted_messages,
        current_run_id=current_run_id,
    )
    tool_results_by_call_id = {
        tool_call_id: message
        for message in sorted_messages
        if message.role == "tool"
        for tool_call_id in (_tool_call_id(message),)
        if tool_call_id is not None
    }
    paired_message_ids: set[str] = set()
    seeds: list[ContextNodeSeed] = []
    for message in sorted_messages:
        if message.id in paired_message_ids:
            continue
        tool_call_id = _tool_call_id(message)
        if _is_function_call_message(message) and tool_call_id is not None:
            result = tool_results_by_call_id.get(tool_call_id)
            if result is not None:
                seeds.append(
                    _tool_interaction_node_seed(
                        call_message=message,
                        result_message=result,
                        parent_id=parent_id,
                        frontier=_is_tool_interaction_frontier(
                            call_message=message,
                            result_message=result,
                            current_inbound_sequence_no=current_inbound_sequence_no,
                            consumed_through_sequence_no=consumed_through_sequence_no,
                        ),
                        consumed_through_sequence_no=consumed_through_sequence_no,
                        current_run_id=current_run_id,
                        current_inbound_sequence_no=current_inbound_sequence_no,
                        lifecycle_facts=_tool_lifecycle_facts_for_result(
                            result,
                            tool_lifecycle_facts or {},
                        ),
                    ),
                )
                paired_message_ids.add(message.id)
                paired_message_ids.add(result.id)
                continue
        if only_tool_interactions:
            continue
        seeds.append(
            _message_node_seed(
                message,
                parent_id=parent_id,
                current_run_id=current_run_id,
            ),
        )
    if not collapse_consumed_tool_history:
        return tuple(seeds)
    return _collapse_consumed_tool_history_seeds(
        tuple(seeds),
        parent_id=parent_id,
        visible_limit=consumed_tool_history_visible_limit,
    )


def _current_items_range_prompt_content(
    messages: tuple[SessionItem, ...],
    *,
    current_run_id: str | None,
    visible_tool_limit: int,
) -> str:
    if not messages:
        return ""
    first_sequence_no = messages[0].sequence_no
    last_sequence_no = messages[-1].sequence_no
    lines = [
        (
            f"active_segment: {len(messages)} items, "
            f"sequences {first_sequence_no}-{last_sequence_no}."
        ),
    ]
    tool_seeds = tuple(
        seed
        for seed in _message_node_seeds(
            messages,
            parent_id="session.items.current.preview",
            current_run_id=current_run_id,
            consumed_through_sequence_no=None,
            collapse_consumed_tool_history=True,
            consumed_tool_history_visible_limit=visible_tool_limit,
            only_tool_interactions=True,
        )
        if seed.kind == "tool_interaction" and seed.content
    )
    if not tool_seeds:
        return "\n".join(lines)
    lines.append("recent_tool_interactions:")
    for seed in tool_seeds:
        lines.extend(
            f"  {line}"
            for line in _tool_interaction_range_preview(seed).splitlines()
        )
    return "\n".join(lines)


def _tool_interaction_range_preview(seed: ContextNodeSeed) -> str:
    if bool(seed.metadata.get("frontier")) and not seed.state.collapsed and seed.content:
        return seed.content
    if seed.summary:
        return f"tool_interaction: {seed.summary}"
    content_digest = _optional_text(seed.metadata.get("content_digest"))
    if content_digest is not None:
        return f"tool_interaction: collapsed; content_sha256={content_digest[:12]}."
    return "tool_interaction: collapsed; expand for refs."


def _collapse_consumed_tool_history_seeds(
    seeds: tuple[ContextNodeSeed, ...],
    *,
    parent_id: str,
    visible_limit: int,
) -> tuple[ContextNodeSeed, ...]:
    consumed_tool_seeds = tuple(
        seed
        for seed in seeds
        if seed.kind == "tool_interaction"
        and bool(seed.metadata.get("consumed"))
        and not bool(seed.metadata.get("frontier"))
    )
    if not consumed_tool_seeds:
        return seeds
    visible_count = max(int(visible_limit), 0)
    hidden_count = max(len(consumed_tool_seeds) - visible_count, 0)
    if hidden_count <= 0:
        return seeds
    visible_ids = {
        seed.node_id
        for seed in sorted(
            consumed_tool_seeds,
            key=lambda item: int(item.metadata.get("result_sequence_no") or 0),
        )[-visible_count:]
    }
    hidden_seeds = tuple(
        seed for seed in consumed_tool_seeds if seed.node_id not in visible_ids
    )
    hidden_ids = {seed.node_id for seed in hidden_seeds}
    range_seed = _consumed_tool_history_range_seed(
        hidden_seeds,
        parent_id=parent_id,
    )
    if range_seed is None:
        return seeds
    output: list[ContextNodeSeed] = []
    inserted = False
    for seed in seeds:
        if seed.node_id not in hidden_ids:
            output.append(seed)
            continue
        if not inserted:
            output.append(range_seed)
            inserted = True
    return tuple(output)


def _consumed_tool_history_range_seed(
    hidden_seeds: tuple[ContextNodeSeed, ...],
    *,
    parent_id: str,
) -> ContextNodeSeed | None:
    if not hidden_seeds:
        return None
    ordered = tuple(sorted(hidden_seeds, key=lambda seed: seed.display_order))
    first = ordered[0]
    last = ordered[-1]
    session_key = _optional_text(first.owner_ref.get("session_key"))
    session_id = _optional_text(first.owner_ref.get("session_id"))
    first_sequence = _optional_int(first.owner_ref.get("call_sequence_no"))
    last_sequence = _optional_int(last.owner_ref.get("result_sequence_no"))
    if session_key is None or session_id is None:
        return None
    if first_sequence is None or last_sequence is None:
        return None
    status_counts: dict[str, int] = {}
    tool_counts: dict[str, int] = {}
    for seed in ordered:
        status = str(
            seed.metadata.get("lifecycle_status")
            or seed.metadata.get("status")
            or "unknown",
        )
        tool_name = str(seed.metadata.get("tool_name") or "tool")
        status_counts[status] = status_counts.get(status, 0) + 1
        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
    status_label = _count_label(status_counts)
    tool_label = _count_label(tool_counts, limit=6)
    summary = (
        f"{len(ordered)} consumed tool interactions are folded into this active "
        f"session history range, sequences {first_sequence}-{last_sequence}."
    )
    if status_label:
        summary = f"{summary} Status: {status_label}."
    if tool_label:
        summary = f"{summary} Tools: {tool_label}."
    return ContextNodeSeed(
        node_id=(
            f"session.tool_interactions.consumed.{_node_part(session_id)}."
            f"{first_sequence}.{last_sequence}"
        ),
        parent_id=parent_id,
        owner="session",
        kind="session_tool_interaction_range",
        title=f"Consumed Tool History {first_sequence}-{last_sequence}",
        summary=summary,
        state=ContextNodeState(collapsed=True, loaded=True),
        actions=_BASIC_ACTIONS,
        owner_ref={
            "session_key": session_key,
            "session_id": session_id,
            "from_sequence_no": first_sequence,
            "to_sequence_no": last_sequence,
            "hidden_tool_interaction_count": len(ordered),
        },
        estimate=_text_estimate(summary),
        display_order=first.display_order,
        metadata={
            "hidden_tool_interaction_count": len(ordered),
            "status_counts": status_counts,
            "tool_counts": tool_counts,
            "from_sequence_no": first_sequence,
            "to_sequence_no": last_sequence,
            "range_reason_code": "active_consumed_tool_history_fold",
        },
    )


def _count_label(counts: dict[str, int], *, limit: int = 4) -> str:
    if not counts:
        return ""
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    visible = ordered[: max(limit, 1)]
    label = ", ".join(f"{key}={count}" for key, count in visible)
    omitted = len(ordered) - len(visible)
    if omitted > 0:
        label = f"{label}, +{omitted} more"
    return label


def _message_node_seed(
    message: SessionItem,
    *,
    parent_id: str,
    current_run_id: str | None = None,
) -> ContextNodeSeed:
    archived = _is_archived_transcript_entry(message)
    current_inbound = _is_current_inbound_message(
        message,
        current_run_id=current_run_id,
    )
    preview = (
        "Delivered as provider user message for this turn."
        if current_inbound
        else _message_preview(message)
    )
    content = "" if current_inbound else _message_prompt_content(message)
    owner_ref: dict[str, object] = {
        "session_key": message.session_key,
        "session_id": message.session_id,
        "session_item_id": message.id,
        "sequence_no": message.sequence_no,
        "role": message.role,
        "kind": _kind_label(message),
        "visibility": _visibility_label(message),
        "source_module": getattr(message, "source_module", "") or "",
        "source_kind": message.source_kind or "",
        "source_id": message.source_id or "",
    }
    for key in (
        "archived_reason",
        "archived_by_compaction_run_id",
        "compacted_segment_id",
        "archived_through_item_sequence_no",
        "summary_item_id",
    ):
        value = message.metadata.get(key)
        if value not in (None, "", {}, []):
            owner_ref[key] = value
    metadata: dict[str, object] = {
        "created_at": format_datetime_utc(message.created_at),
        "source_kind": message.source_kind,
        "source_id": message.source_id,
        "role": message.role,
        "kind": _kind_label(message),
        "sequence_no": message.sequence_no,
        "visibility": _visibility_label(message),
        "current_inbound": current_inbound,
        "content_block_types": _content_block_types(message),
        "content_digest": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "archived": archived,
    }
    for key in (
        "archived_reason",
        "archived_by_compaction_run_id",
        "compacted_segment_id",
        "archived_through_item_sequence_no",
        "summary_item_id",
    ):
        value = message.metadata.get(key)
        if value not in (None, "", {}, []):
            metadata[key] = value
    return ContextNodeSeed(
        node_id=f"session.item.{message.session_id}.{message.sequence_no}",
        parent_id=parent_id,
        owner="session",
        kind="session_item",
        title=f"{message.sequence_no}. {message.role}",
        summary=preview,
        content=content,
        state=ContextNodeState(
            collapsed=False,
            loaded=True,
            archived=archived,
            status="archived" if archived else "available",
            render_reason="archived_by_compaction" if archived else "",
        ),
        actions=_BASIC_ACTIONS,
        owner_ref=owner_ref,
        estimate=_message_estimate(message, content),
        display_order=message.sequence_no,
        metadata=metadata,
    )


def _tool_interaction_node_seed(
    *,
    call_message: SessionItem,
    result_message: SessionItem,
    parent_id: str,
    frontier: bool = False,
    consumed_through_sequence_no: int | None = None,
    current_run_id: str | None = None,
    current_inbound_sequence_no: int | None = None,
    lifecycle_facts: dict[str, object] | None = None,
) -> ContextNodeSeed:
    tool_call_id = _tool_call_id(call_message) or _tool_call_id(result_message) or ""
    tool_name = _tool_name(call_message) or _tool_name(result_message) or "tool"
    status = _tool_result_status(result_message) or "unknown"
    arguments_json = _json_fragment(call_message.content_payload.get("arguments") or {})
    result_content = _tool_result_content(result_message)
    result_envelope = _tool_result_envelope_metadata(result_message)
    result_browser_evidence = _tool_result_browser_evidence_metadata(result_message)
    error_json = _tool_result_error_json(result_message)
    frontier = bool(frontier)
    current_turn = (
        current_inbound_sequence_no is not None
        and call_message.sequence_no >= current_inbound_sequence_no
    )
    archived = _is_archived_transcript_entry(
        call_message,
    ) or _is_archived_transcript_entry(result_message)
    consumed = not frontier
    opened_by_default = False
    collapsed_by_default = not frontier and not opened_by_default
    failed = _is_failed_tool_status(status)
    observed = _tool_interaction_observed(
        tool_name=tool_name,
        status=status,
        result_message=result_message,
    )
    superseded = _tool_interaction_superseded(
        result_message,
        lifecycle_facts=lifecycle_facts,
    )
    superseded_by_tool_call_id = _tool_interaction_superseded_by_tool_call_id(
        result_message,
        lifecycle_facts=lifecycle_facts,
    )
    lifecycle_status = (
        "frontier_failed"
        if frontier and failed
        else "frontier"
        if frontier
        else "failed"
        if failed
        else "superseded"
        if superseded
        else "observed"
        if observed
        else "consumed"
    )
    content = _tool_interaction_prompt_content(
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        status=status,
        arguments_json=arguments_json,
        result_content=result_content,
        error_json=error_json,
    )
    summary = _tool_interaction_summary(
        tool_name=tool_name,
        status=status,
        frontier=frontier,
        current_turn=current_turn,
        arguments_json=arguments_json,
        result_content=result_content,
        error_json=error_json,
    )
    visibility_status = (
        "frontier_protocol_tail" if frontier else "folded_consumed_history"
    )
    return ContextNodeSeed(
        node_id=(
            f"session.tool_interaction.{call_message.session_id}."
            f"{_node_part(tool_call_id or str(call_message.sequence_no))}"
        ),
        parent_id=parent_id,
        owner="session",
        kind="tool_interaction",
        title=f"{call_message.sequence_no}-{result_message.sequence_no}. {tool_name}",
        summary=_truncate(summary, 320),
        content=content,
        state=ContextNodeState(
            collapsed=collapsed_by_default,
            loaded=True,
            opened=opened_by_default,
            consumed=consumed,
            archived=archived,
            status="archived" if archived else "available",
            render_reason="archived_by_compaction" if archived else "",
        ),
        actions=_BASIC_ACTIONS,
        owner_ref={
            "session_key": call_message.session_key,
            "session_id": call_message.session_id,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "status": status,
            "lifecycle_status": lifecycle_status,
            "frontier": frontier,
            "current_turn": current_turn,
            "consumed": consumed,
            "failed": failed,
            "observed": observed,
            "superseded": superseded,
            "superseded_by_tool_call_id": superseded_by_tool_call_id or "",
            "call_session_item_id": call_message.id,
            "result_session_item_id": result_message.id,
            "call_sequence_no": call_message.sequence_no,
            "result_sequence_no": result_message.sequence_no,
            "consumed_through_sequence_no": consumed_through_sequence_no,
            "visibility": _visibility_label(result_message),
            "archived": archived,
        },
        estimate=_text_estimate(content if not collapsed_by_default else summary),
        revision=_TOOL_INTERACTION_NODE_REVISION,
        display_order=call_message.sequence_no,
        metadata={
            "created_at": format_datetime_utc(call_message.created_at),
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "status": status,
            "arguments_json": arguments_json,
            "result_content": result_content,
            "artifact_content_candidates": (
                _tool_result_artifact_content_candidates(result_message)
            ),
            "tool_result_envelope": result_envelope,
            "tool_result_browser_evidence": result_browser_evidence,
            "error_json": error_json,
            "call_source_kind": call_message.source_kind,
            "call_source_id": call_message.source_id,
            "result_source_kind": result_message.source_kind,
            "result_source_id": result_message.source_id,
            "call_sequence_no": call_message.sequence_no,
            "result_sequence_no": result_message.sequence_no,
            "archived": archived,
            "consumed_through_sequence_no": consumed_through_sequence_no,
            "snapshot_visibility_status": visibility_status,
            "lifecycle_status": lifecycle_status,
            "frontier": frontier,
            "current_turn": current_turn,
            "consumed": consumed,
            "failed": failed,
            "observed": observed,
            "superseded": superseded,
            "superseded_by_tool_call_id": superseded_by_tool_call_id or "",
            "collapsed_by_default": collapsed_by_default,
            "opened_by_default": opened_by_default,
            "content_digest": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        },
    )


def _tool_interaction_summary(
    *,
    tool_name: str,
    status: str,
    frontier: bool,
    current_turn: bool,
    arguments_json: str,
    result_content: str,
    error_json: str | None,
) -> str:
    base = f"{tool_name} tool call {status}."
    if frontier:
        if error_json:
            return f"{base} error={_truncate(error_json, 180)}"
        if result_content:
            result_summary = _truncate(result_content.replace("\n", " "), 200)
            return f"{base} {result_summary}"
        return base
    if current_turn:
        if error_json:
            return f"{base} current-turn error available."
        if result_content:
            result_digest = _short_digest(result_content)
            if result_digest is not None:
                return f"{base} current-turn result_sha256={result_digest}."
        return f"{base} current-turn result available."
    digest_parts = []
    args_digest = _short_digest(arguments_json)
    if args_digest is not None:
        digest_parts.append(f"args_sha256={args_digest}")
    result_digest = _short_digest(result_content or error_json or "")
    if result_digest is not None:
        digest_parts.append(f"result_sha256={result_digest}")
    if error_json:
        digest_parts.append(f"error={_truncate(error_json, 120)}")
    digest = "; ".join(digest_parts)
    if digest:
        return f"{status} consumed; {digest}; expand for refs."
    return f"{status} consumed; expand for refs."


def _short_digest(value: str) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _is_tool_interaction_frontier(
    *,
    call_message: SessionItem,
    result_message: SessionItem,
    current_inbound_sequence_no: int | None,
    consumed_through_sequence_no: int | None,
) -> bool:
    if current_inbound_sequence_no is None:
        return False
    if call_message.sequence_no < current_inbound_sequence_no:
        return False
    if consumed_through_sequence_no is None:
        return False
    return result_message.sequence_no > consumed_through_sequence_no


def _message_preview(message: SessionItem) -> str:
    if message.role == "tool":
        return _tool_result_message_preview(message)
    text = describe_content_for_text_fallback(message.content_payload)
    return _truncate(text.replace("\n", " "), 320)


def _tool_result_message_preview(message: SessionItem) -> str:
    payload = message.content_payload
    tool_name = _optional_text(message.metadata.get("tool_name")) or _optional_text(
        payload.get("tool_name"),
    )
    tool_call_id = _optional_text(message.metadata.get("tool_call_id")) or _optional_text(
        payload.get("tool_call_id"),
    )
    status = _optional_text(payload.get("status"))
    content = _blocks_prompt_content(content_blocks_from_payload(payload))
    parts = ["tool_result"]
    if tool_name is not None:
        parts.append(tool_name)
    if status is not None:
        parts.append(f"status={status}")
    if tool_call_id is not None:
        parts.append(f"call_id={tool_call_id}")
    digest = _short_digest(content)
    if digest is not None:
        parts.append(f"content_sha256={digest}")
    return _truncate("; ".join(parts), 320)


def _current_inbound_sequence_no(
    messages: tuple[SessionItem, ...],
    *,
    current_run_id: str | None,
) -> int | None:
    if current_run_id is None:
        return None
    sequences = [
        message.sequence_no
        for message in messages
        if _is_current_inbound_message(message, current_run_id=current_run_id)
    ]
    return min(sequences) if sequences else None


def _message_prompt_content(message: SessionItem) -> str:
    if (
        message.role == "assistant"
        and message.content_payload.get("type") == "function_call"
    ):
        return _function_call_prompt_content(message)
    if message.role == "tool":
        return _tool_result_prompt_content(message)
    return _blocks_prompt_content(content_blocks_from_payload(message.content_payload))


def _function_call_prompt_content(message: SessionItem) -> str:
    payload = message.content_payload
    tool_call_id = _optional_text(message.metadata.get("tool_call_id")) or _optional_text(
        payload.get("call_id"),
    )
    tool_name = _optional_text(message.metadata.get("tool_name")) or _optional_text(
        payload.get("name"),
    )
    lines = ["tool_call:"]
    if tool_name is not None:
        lines.append(f"  name: {tool_name}")
    if tool_call_id is not None:
        lines.append(f"  call_id: {tool_call_id}")
    arguments = payload.get("arguments")
    if arguments is not None:
        lines.append(f"  arguments: {_json_fragment(arguments)}")
    return "\n".join(lines)


def _tool_result_prompt_content(message: SessionItem) -> str:
    payload = message.content_payload
    tool_call_id = _optional_text(message.metadata.get("tool_call_id")) or _optional_text(
        payload.get("tool_call_id"),
    )
    tool_name = _optional_text(message.metadata.get("tool_name")) or _optional_text(
        payload.get("tool_name"),
    )
    status = _optional_text(payload.get("status"))
    lines = ["tool_result:"]
    if tool_name is not None:
        lines.append(f"  tool_name: {tool_name}")
    if tool_call_id is not None:
        lines.append(f"  tool_call_id: {tool_call_id}")
    if status is not None:
        lines.append(f"  status: {status}")
    error = payload.get("error")
    if error is not None:
        lines.append(f"  error: {_json_fragment(error)}")
    content = _blocks_prompt_content(content_blocks_from_payload(payload))
    if content:
        lines.append(f"  content_sha256: {_short_digest(content)}")
        lines.append(f"  content_chars: {len(content)}")
    return "\n".join(lines)


def _tool_interaction_prompt_content(
    *,
    tool_name: str,
    tool_call_id: str,
    status: str,
    arguments_json: str,
    result_content: str,
    error_json: str | None,
) -> str:
    lines = [
        "tool_interaction:",
        f"  tool_name: {tool_name}",
    ]
    if tool_call_id:
        lines.append(f"  tool_call_id: {tool_call_id}")
    lines.append(f"  status: {status}")
    if arguments_json:
        lines.append(f"  arguments: {arguments_json}")
    if error_json is not None:
        lines.append(f"  error: {error_json}")
    if result_content:
        lines.append("  result:")
        lines.extend(f"    {line}" for line in result_content.splitlines())
    return "\n".join(lines)


def _is_function_call_message(message: SessionItem) -> bool:
    return message.role == "assistant" and (
        message.kind is SessionItemKind.TOOL_CALL
        or message.content_payload.get("type") == "function_call"
    )


def _tool_call_id(message: SessionItem) -> str | None:
    return (
        _optional_text(message.metadata.get("tool_call_id"))
        or _optional_text(message.content_payload.get("call_id"))
        or _optional_text(message.content_payload.get("tool_call_id"))
    )


def _tool_name(message: SessionItem) -> str | None:
    return (
        _optional_text(message.metadata.get("tool_name"))
        or _optional_text(message.content_payload.get("name"))
        or _optional_text(message.content_payload.get("tool_name"))
    )


def _tool_result_status(message: SessionItem) -> str | None:
    return _optional_text(message.content_payload.get("status"))


def _tool_result_content(message: SessionItem) -> str:
    compact_content = _large_tool_result_ref_content(message)
    if compact_content is not None:
        return compact_content
    return _blocks_prompt_content(content_blocks_from_payload(message.content_payload))


def _tool_result_envelope_metadata(message: SessionItem) -> dict[str, object] | None:
    metadata = message.content_payload.get("metadata")
    if not isinstance(metadata, dict):
        return None
    envelope = metadata.get(TOOL_RESULT_ENVELOPE_METADATA_KEY)
    if not isinstance(envelope, dict):
        return None
    return dict(envelope)


def _tool_result_browser_evidence_metadata(
    message: SessionItem,
) -> dict[str, object] | None:
    metadata = message.content_payload.get("metadata")
    if not isinstance(metadata, dict):
        return None
    evidence = metadata.get("browser_evidence")
    if not isinstance(evidence, dict):
        return None
    return dict(evidence)


def _large_tool_result_ref_content(message: SessionItem) -> str | None:
    payload = message.content_payload
    details = payload.get("details")
    metadata = payload.get("metadata")
    if not isinstance(details, dict):
        details = {}
    if not isinstance(metadata, dict):
        metadata = {}
    artifact_ids = _metadata_artifact_ids(metadata)
    body_removed = details.get("body_removed_from_details") is True
    evidence = metadata.get("browser_evidence")
    if not isinstance(evidence, dict):
        evidence = {}
    envelope = metadata.get(TOOL_RESULT_ENVELOPE_METADATA_KEY)
    if isinstance(envelope, dict):
        envelope_content = _tool_result_envelope_ref_content(
            envelope,
            artifact_ids=artifact_ids,
            body_removed=body_removed,
            browser_evidence=evidence,
        )
        if envelope_content is not None:
            return envelope_content
    if not artifact_ids and not body_removed:
        return None
    lines = ["tool_result_ref:"]
    lines.append("body_storage: externalized")
    endpoint = _optional_text(details.get("endpoint"))
    method = _optional_text(details.get("method"))
    request_id = _optional_text(evidence.get("request_id")) or _optional_text(
        details.get("request_id"),
    )
    if endpoint is not None:
        lines.append(f"endpoint: {endpoint}")
    if method is not None:
        lines.append(f"method: {method}")
    if request_id is not None:
        lines.append(f"request_id: {request_id}")
    if artifact_ids:
        lines.append(f"artifact_refs: {', '.join(artifact_ids)}")
    payload_shape = _small_structured_evidence_fact(evidence.get("payload_shape"))
    if payload_shape is not None:
        lines.append(f"payload_shape: {_json_fragment(payload_shape)}")
    result_shape = _small_structured_evidence_fact(evidence.get("result_shape"))
    if result_shape is not None:
        lines.append(f"result_shape: {_json_fragment(result_shape)}")
    lines.append("full_result_refs: artifact refs or read handles are available when needed")
    return "\n".join(lines)


def _tool_result_envelope_ref_content(
    envelope: dict[str, object],
    *,
    artifact_ids: tuple[str, ...],
    body_removed: bool,
    browser_evidence: dict[str, object],
) -> str | None:
    truncated = envelope.get("truncated") is True
    if not truncated and not artifact_ids and not body_removed:
        return None
    lines = ["tool_result_ref:"]
    lines.append("body_storage: externalized")
    status = _optional_text(envelope.get("status"))
    summary = _optional_text(envelope.get("summary"))
    if status is not None:
        lines.append(f"status: {status}")
    if summary is not None:
        lines.append(f"summary: {summary}")
    key_facts = envelope.get("key_facts")
    if isinstance(key_facts, dict) and key_facts:
        lines.append(f"key_facts: {_json_fragment(key_facts)}")
    refs = _envelope_text_list(envelope.get("evidence_refs"))
    if artifact_ids:
        refs = tuple(dict.fromkeys((*refs, *artifact_ids)))
    if refs:
        lines.append(f"artifact_refs: {', '.join(refs)}")
    omitted_count = _optional_int(envelope.get("omitted_count"))
    omitted_chars = _optional_int(envelope.get("omitted_chars"))
    if omitted_count is not None:
        lines.append(f"omitted_count: {omitted_count}")
    if omitted_chars is not None:
        lines.append(f"omitted_chars: {omitted_chars}")
    read_handles = _small_structured_evidence_fact(envelope.get("read_handles"))
    if read_handles is not None:
        lines.append(f"read_handles: {_json_fragment(read_handles)}")
    warnings = _envelope_text_list(envelope.get("warnings"))
    if warnings:
        lines.append(f"warnings: {'; '.join(warnings)}")
    lines.append("full_result_refs: artifact refs or read handles are available when needed")
    return "\n".join(lines)


def _metadata_artifact_ids(metadata: dict[str, object]) -> tuple[str, ...]:
    raw = metadata.get("artifact_ids")
    if not isinstance(raw, list):
        raw = metadata.get("browser_artifact_ids")
    if not isinstance(raw, list):
        return ()
    values = [_optional_text(item) for item in raw]
    return tuple(dict.fromkeys(item for item in values if item is not None))


def _tool_result_artifact_content_candidates(
    message: SessionItem,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for index, block in enumerate(content_blocks_from_payload(message.content_payload)):
        artifact_id = _optional_text(block.get("artifact_id"))
        mime_type = _optional_text(block.get("mime_type"))
        if artifact_id is None or mime_type is None:
            continue
        block_type = str(block.get("type") or "").strip()
        if block_type in {IMAGE_BLOCK_TYPE, IMAGE_REF_BLOCK_TYPE}:
            kind = "artifact_image"
        elif block_type in {FILE_BLOCK_TYPE, FILE_REF_BLOCK_TYPE}:
            kind = "artifact_file"
        elif mime_type.lower().startswith("image/"):
            kind = "artifact_image"
        else:
            kind = "artifact_file"
        candidate: dict[str, object] = {
            "node_id": f"{message.id}.artifact.{index}",
            "artifact_id": artifact_id,
            "kind": kind,
            "mime_type": mime_type,
        }
        name = _optional_text(block.get("name"))
        if name is not None:
            candidate["name"] = name
        candidates.append(candidate)
    return candidates


def _envelope_text_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    normalized = [_optional_text(item) for item in value]
    return tuple(dict.fromkeys(item for item in normalized if item is not None))


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _tool_result_error_json(message: SessionItem) -> str | None:
    error = message.content_payload.get("error")
    if error is None:
        return None
    return _json_fragment(error)


def _blocks_prompt_content(blocks: list[dict[str, object]]) -> str:
    if not blocks:
        return ""
    lines = []
    for block in blocks:
        line = _block_prompt_line(block)
        if line:
            lines.append(line)
    return "\n".join(lines)


def _block_prompt_line(block: dict[str, object]) -> str:
    block_type = str(block.get("type") or "").strip()
    if block_type == TEXT_BLOCK_TYPE:
        text = block.get("text")
        return text if isinstance(text, str) else ""
    if block_type in {IMAGE_BLOCK_TYPE, IMAGE_REF_BLOCK_TYPE}:
        return _attachment_prompt_line("image", block)
    if block_type in {FILE_BLOCK_TYPE, FILE_REF_BLOCK_TYPE}:
        return _attachment_prompt_line("file", block)
    if block_type:
        return f"[{block_type}]"
    return ""


def _attachment_prompt_line(label: str, block: dict[str, object]) -> str:
    name = _optional_text(block.get("name"))
    artifact_id = _optional_text(block.get("artifact_id"))
    if name is not None:
        return f"[{label}:{name}]"
    if artifact_id is not None:
        return f"[{label}:{artifact_id}]"
    return f"[{label}]"


def _content_block_types(message: SessionItem) -> list[str]:
    return [
        str(block.get("type") or "").strip()
        for block in content_blocks_from_payload(message.content_payload)
        if str(block.get("type") or "").strip()
    ]


def _kind_label(message: Any) -> str:
    value = getattr(message, "kind", "")
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        if enum_value in {"user_message", "assistant_message", "tool_call"}:
            return "message"
        return str(enum_value)
    return str(value)


def _visibility_label(message: Any) -> str:
    if _is_archived_transcript_entry(message):
        return "archived"
    return "default"


def _message_estimate(message: SessionItem, content: str) -> ContextEstimate:
    base = _text_estimate(content or _message_preview(message))
    block_types = set(_content_block_types(message))
    return ContextEstimate(
        text_chars=base.text_chars,
        text_tokens=base.text_tokens,
        image_count=1 if block_types & {IMAGE_BLOCK_TYPE, IMAGE_REF_BLOCK_TYPE} else 0,
        file_count=1 if block_types & {FILE_BLOCK_TYPE, FILE_REF_BLOCK_TYPE} else 0,
    )


def _json_fragment(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _items_estimate(
    messages: tuple[SessionItem, ...],
    *,
    current_run_id: str | None = None,
) -> ContextEstimate:
    total = ContextEstimate()
    for message in messages:
        content = (
            ""
            if _is_current_inbound_message(message, current_run_id=current_run_id)
            else _message_prompt_content(message)
        )
        total = total.plus(_message_estimate(message, content))
    return total


def _is_current_inbound_message(
    message: SessionItem,
    *,
    current_run_id: str | None,
) -> bool:
    if current_run_id is None:
        return False
    return (
        message.role == "user"
        and message.source_kind == "orchestration_run"
        and message.source_id == current_run_id
    )


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


def _tool_lifecycle_facts_from_execution_query(
    execution_query: Any | None,
    turn_id: str | None,
) -> dict[str, dict[str, object]]:
    if execution_query is None or turn_id is None:
        return {}
    return _tool_lifecycle_facts_from_execution_summaries(
        _execution_step_item_summaries(execution_query, turn_id),
    )


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
    sources = [summary]
    for key in ("tool_lifecycle", "evidence_lifecycle", "metadata"):
        value = summary.get(key)
        if isinstance(value, dict):
            sources.append(value)
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


def _tool_lifecycle_facts_for_result(
    result_message: SessionItem,
    facts_by_ref: dict[str, dict[str, object]],
) -> dict[str, object] | None:
    if not facts_by_ref:
        return None
    refs = (
        _tool_call_id(result_message),
        result_message.id,
        _optional_text(result_message.content_payload.get("tool_run_id")),
    )
    merged: dict[str, object] = {}
    for ref in refs:
        if ref is None:
            continue
        facts = facts_by_ref.get(ref)
        if facts:
            merged.update(facts)
    return merged or None


def _execution_step_item_summaries(
    execution_query: Any,
    turn_id: str,
) -> tuple[dict[str, object], ...]:
    summaries: list[dict[str, object]] = []
    for chain in execution_query.list_execution_chains(turn_id):
        chain_id = getattr(chain, "id", None)
        if not isinstance(chain_id, str) or not chain_id.strip():
            continue
        for step in execution_query.list_execution_steps(chain_id):
            step_id = getattr(step, "id", None)
            if not isinstance(step_id, str) or not step_id.strip():
                continue
            for item in execution_query.list_execution_step_items(step_id):
                summary = getattr(item, "summary_payload", None)
                if isinstance(summary, dict):
                    summaries.append(summary)
    return tuple(summaries)


def _execution_step_node_seeds(
    execution_query: Any,
    turn_id: str,
    *,
    parent_id: str,
) -> tuple[ContextNodeSeed, ...]:
    seeds: list[ContextNodeSeed] = []
    display_order = 10
    for chain in execution_query.list_execution_chains(turn_id):
        chain_id = _entity_id(chain)
        if chain_id is None:
            continue
        for step in execution_query.list_execution_steps(chain_id):
            step_id = _entity_id(step)
            if step_id is None:
                continue
            kind = _value_label(getattr(step, "kind", None)) or "step"
            status = _value_label(getattr(step, "status", None)) or "unknown"
            step_index = _optional_int(getattr(step, "step_index", None)) or 0
            item_count = len(execution_query.list_execution_step_items(step_id))
            summary = (
                f"Execution step {step_index}: {kind}; status={status}; "
                f"items={item_count}."
            )
            seeds.append(
                ContextNodeSeed(
                    node_id=f"session.step.{_node_part(step_id)}",
                    parent_id=parent_id,
                    owner="session",
                    kind="session_step",
                    title=f"{step_index}. {kind}",
                    summary=summary,
                    state=ContextNodeState(collapsed=False, loaded=True),
                    actions=_BASIC_ACTIONS,
                    owner_ref={
                        "turn_id": turn_id,
                        "run_id": turn_id,
                        "chain_id": chain_id,
                        "step_id": step_id,
                        "step_index": step_index,
                        "kind": kind,
                        "status": status,
                    },
                    estimate=_text_estimate(summary),
                    display_order=display_order + step_index,
                    metadata={
                        "item_count": item_count,
                        "chain_status": _value_label(getattr(chain, "status", None))
                        or "",
                    },
                ),
            )
            display_order += 10
    return tuple(seeds)


def _execution_step_item_node_seeds(
    execution_query: Any,
    step_id: str,
    *,
    parent_id: str,
) -> tuple[ContextNodeSeed, ...]:
    seeds: list[ContextNodeSeed] = []
    for index, item in enumerate(execution_query.list_execution_step_items(step_id), start=1):
        item_id = _entity_id(item)
        if item_id is None:
            continue
        item_kind = _value_label(getattr(item, "kind", None)) or "execution_item"
        status = _value_label(getattr(item, "status", None)) or "unknown"
        summary_payload = getattr(item, "summary_payload", None)
        runtime_semantic_kind = _runtime_semantic_kind(summary_payload)
        runtime_kind = _runtime_node_kind_for_execution_item(
            item_kind,
            runtime_semantic_kind=runtime_semantic_kind,
        )
        summary = _execution_item_summary(
            item_kind=item_kind,
            status=status,
            summary_payload=summary_payload,
        )
        owner_ref = _execution_item_owner_ref(item)
        owner_ref.update(
            {
                "step_id": step_id,
                "execution_step_item_id": item_id,
                "kind": item_kind,
                "status": status,
            },
        )
        seeds.append(
            ContextNodeSeed(
                node_id=f"session.step.item.{_node_part(item_id)}",
                parent_id=parent_id,
                owner="session",
                kind=runtime_kind,
                title=f"{index}. {item_kind}",
                summary=summary,
                state=ContextNodeState(collapsed=True, loaded=True),
                actions=_BASIC_ACTIONS,
                owner_ref=owner_ref,
                estimate=_text_estimate(summary),
                display_order=index * 10,
                metadata={
                    **(
                        {"runtime_semantic_kind": runtime_semantic_kind}
                        if runtime_semantic_kind is not None
                        else {}
                    ),
                    "summary_payload_keys": sorted(str(key) for key in summary_payload)
                    if isinstance(summary_payload, dict)
                    else [],
                },
            ),
        )
    return tuple(seeds)


def _entity_id(entity: object) -> str | None:
    return _optional_text(getattr(entity, "id", None))


def _value_label(value: object) -> str | None:
    raw_value = getattr(value, "value", value)
    return _optional_text(raw_value)


def _runtime_node_kind_for_execution_item(
    item_kind: str,
    *,
    runtime_semantic_kind: str | None = None,
) -> str:
    semantic_kind = _runtime_node_kind_for_semantic_kind(runtime_semantic_kind)
    if semantic_kind is not None:
        return semantic_kind
    return {
        "llm_invocation": "runtime_llm_invocation",
        "continuation_decision": "runtime_continuation_decision",
        "tool_call": "runtime_assistant_tool_call",
        "tool_run": "runtime_tool_run",
        "tool_result": "runtime_tool_result",
        "approval_request": "runtime_approval_request",
        "session_message": "runtime_session_message",
        "context_snapshot": "runtime_context_snapshot",
    }.get(item_kind, "runtime_execution_item")


def _runtime_node_kind_for_semantic_kind(runtime_semantic_kind: str | None) -> str | None:
    if runtime_semantic_kind is None:
        return None
    return {
        "runtime.assistant_progress": "runtime_assistant_progress",
        "runtime.assistant_message": "runtime_assistant_message",
        "runtime.assistant_tool_call": "runtime_assistant_tool_call",
        "runtime.final_answer": "runtime_final_answer",
        "runtime.reasoning": "runtime_reasoning",
        "runtime.tool_result": "runtime_tool_result",
        "runtime.provider_external_activity": "runtime_provider_external_activity",
        "runtime.context_compaction": "runtime_context_compaction",
        "runtime.structured_output": "runtime_structured_output",
        "runtime.blocked_state": "runtime_blocked_state",
    }.get(runtime_semantic_kind)


def _runtime_semantic_kind(summary_payload: object) -> str | None:
    if not isinstance(summary_payload, dict):
        return None
    return _optional_text(summary_payload.get("runtime_semantic_kind"))


def _execution_item_summary(
    *,
    item_kind: str,
    status: str,
    summary_payload: object,
) -> str:
    facts: list[str] = [f"{item_kind}; status={status}"]
    if isinstance(summary_payload, dict):
        for key in (
            "assistant_progress_item_ids",
            "assistant_message_item_ids",
            "tool_call_names",
            "tool_call_id",
            "tool_run_id",
            "llm_invocation_id",
            "llm_response_item_id",
            "runtime_semantic_kind",
            "session_item_id",
        ):
            value = summary_payload.get(key)
            if value in (None, "", (), [], {}):
                continue
            facts.append(f"{key}={_json_fragment(value)}")
    return _truncate("; ".join(facts), 320)


def _execution_item_owner_ref(item: object) -> dict[str, object]:
    owner = getattr(item, "owner", None)
    owner_ref: dict[str, object] = {}
    if owner is not None:
        owner_kind = _optional_text(getattr(owner, "owner_kind", None))
        owner_id = _optional_text(getattr(owner, "owner_id", None))
        if owner_kind is not None:
            owner_ref["owner_kind"] = owner_kind
        if owner_id is not None:
            owner_ref["owner_id"] = owner_id
    summary_payload = getattr(item, "summary_payload", None)
    if isinstance(summary_payload, dict):
        for key in (
            "llm_invocation_id",
            "llm_response_item_id",
            "runtime_semantic_kind",
            "session_item_id",
            "tool_call_id",
            "tool_run_id",
            "request_render_snapshot_id",
            "approval_request_id",
        ):
            value = _optional_text(summary_payload.get(key))
            if value is not None:
                owner_ref[key] = value
    return owner_ref


def _text_estimate(text: str) -> ContextEstimate:
    normalized = text or ""
    return ContextEstimate(
        text_chars=len(normalized),
        text_tokens=max((len(normalized) + 3) // 4, 1) if normalized else 0,
    )


def _truncate(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + "..."


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _segment_messages(
    messages: tuple[SessionItem, ...],
    *,
    session_id: str,
    message_scope: str,
) -> tuple[SessionItem, ...]:
    return tuple(
        message
        for message in messages
        if message.session_id == session_id
        and _matches_message_scope(
            message,
            message_scope=message_scope,
        )
    )


def _matches_message_scope(
    message: Any,
    *,
    message_scope: str,
) -> bool:
    if message_scope == "archived":
        return _is_archived_transcript_entry(message)
    return True


def _is_archived_transcript_entry(message: Any) -> bool:
    metadata = getattr(message, "metadata", None)
    if not isinstance(metadata, dict):
        return False
    return (
        metadata.get("archived_reason") is not None
        or metadata.get("compacted_segment_id") is not None
    )


def _is_session_instance_node_id(node_id: str) -> bool:
    return node_id == "session.instance.active" or node_id.startswith(
        "session.instance.closed.",
    )


def _is_session_segments_root_node_id(node_id: str) -> bool:
    return node_id == "session.segments.active" or node_id.startswith(
        "session.segments.closed.",
    )


def _is_session_segment_node_id(node_id: str) -> bool:
    return node_id == "session.segment.active" or node_id.startswith(
        "session.segment.compacted.",
    ) or node_id.startswith("session.segment.closed.")


def _is_historical_segment_node_id(node_id: str) -> bool:
    return node_id.startswith("session.segment.compacted.") or node_id.startswith(
        "session.segment.closed.",
    )


def _session_segments_root_id(instance: SessionInstance, *, active: bool) -> str:
    if active:
        return "session.segments.active"
    return f"session.segments.closed.{_node_part(instance.id)}"


def _historical_segment_kind(instance: SessionInstance) -> str:
    if _segment_summary_text(instance.metadata) is not None:
        return "compacted"
    # Session persists compaction metadata as a segment owner fact; Context
    # Workspace exposes the same fact as a session segment node.
    segment = instance.metadata.get("segment")
    if isinstance(segment, dict):
        kind = _optional_text(segment.get("kind")) or _optional_text(segment.get("status"))
        if kind == "compacted":
            return "compacted"
    return "closed"


def _segment_summary_text(metadata: dict[str, object]) -> str | None:
    # See _historical_segment_kind: this is a Session-owned metadata field.
    segment = metadata.get("segment")
    if not isinstance(segment, dict):
        return None
    return _optional_text(segment.get("summary_text"))


def _chunks(
    messages: tuple[SessionItem, ...],
    size: int,
) -> tuple[tuple[SessionItem, ...], ...]:
    chunk_size = max(int(size), 1)
    return tuple(
        messages[index : index + chunk_size]
        for index in range(0, len(messages), chunk_size)
    )


def _node_part(value: str) -> str:
    return "".join(
        char if char.isalnum() or char in {"-", "_"} else "_"
        for char in value
    )


def _short_node_part(value: str) -> str:
    normalized = _node_part(value)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]


__all__ = ["SessionContextNodeProvider"]
