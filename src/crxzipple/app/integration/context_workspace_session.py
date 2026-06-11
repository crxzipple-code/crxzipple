"""Session context tree adapter.

This module lives in app integration because it maps Session-owned application
facts into Context Workspace node handles without making either module import
the other module's internals.
"""

from __future__ import annotations

import hashlib
import json
import re
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
    ListSessionMessagesInput,
)
from crxzipple.modules.session.domain import (
    Session,
    SessionInstance,
    SessionMessage,
    SessionMessageVisibility,
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

    def list_messages(
        self,
        data: ListSessionMessagesInput,
    ) -> list[SessionMessage]:
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
        if request.node.id == "evidence.frontier":
            return self._current_evidence_frontier_children(request)
        if request.node.id == "session.segment.current":
            return self._current_segment_children(request)
        if request.node.id == "session.evidence.current":
            return self._current_evidence_children(request)
        if _is_historical_segment_node_id(request.node.id):
            return self._historical_segment_range_children(request)
        if request.node.id.startswith("session.segment.messages."):
            return self._segment_range_message_children(request)
        if request.node.id.startswith("session.tool_interactions.consumed."):
            return self._current_consumed_tool_history_children(request)
        if request.node.id == "session.messages.current":
            return self._current_message_children(request)
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
            active_messages = self._session_service.list_messages(
                ListSessionMessagesInput(
                    session_key=session_key,
                    active_session_only=True,
                    include_archived=False,
                ),
            )
        except SessionNotFoundError:
            return ()

        active_message_count = len(active_messages)
        active_instance = next(
            (item for item in instances if item.id == session.active_session_id),
            None,
        )
        seeds: list[ContextNodeSeed] = []
        if active_instance is not None:
            seeds.append(
                _current_segment_seed(
                    instance=active_instance,
                    message_count=active_message_count,
                    parent_id="session.current",
                    display_order=10,
                ),
            )

        display_order = 20
        for instance in instances:
            if instance.id == session.active_session_id:
                continue
            segment_kind = _historical_segment_kind(instance)
            seeds.append(
                _historical_segment_seed(
                    instance=instance,
                    messages=None,
                    parent_id="session.current",
                    segment_kind=segment_kind,
                    message_visibility=(
                        "archived" if segment_kind == "compacted" else "all"
                    ),
                    fallback_summary=None,
                    display_order=display_order,
                ),
            )
            display_order += 10
        return tuple(seeds)

    def _current_segment_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        session_key = request.workspace.session_key
        try:
            session = self._session_service.get_session(session_key)
            active_messages = self._session_service.list_messages(
                ListSessionMessagesInput(
                    session_key=session_key,
                    active_session_only=True,
                    include_archived=False,
                ),
            )
        except SessionNotFoundError:
            return ()
        if not active_messages:
            return ()
        first_sequence = active_messages[0].sequence_no
        last_sequence = active_messages[-1].sequence_no
        current_run_id = _optional_text(request.workspace.metadata.get("last_run_id"))
        tool_lifecycle_facts = _tool_lifecycle_facts_from_execution_query(
            self._execution_query,
            current_run_id,
        )
        evidence_items = _evidence_items_for_current_run(
            tuple(active_messages),
            current_run_id=current_run_id,
            tool_lifecycle_facts=tool_lifecycle_facts,
        )
        seeds = [
            ContextNodeSeed(
                node_id="session.messages.current",
                parent_id=request.node.id,
                owner="session",
                kind="session_message_range",
                title="Current Messages",
                summary=(
                    f"{len(active_messages)} visible messages in the active "
                    f"segment, sequences {first_sequence}-{last_sequence}."
                ),
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
                estimate=_messages_estimate(
                    tuple(active_messages),
                    current_run_id=current_run_id,
                ),
                revision=(
                    f"{_CURRENT_MESSAGES_RANGE_REVISION}.run"
                    if current_run_id is not None
                    else f"{_CURRENT_MESSAGES_RANGE_REVISION}.inspect"
                ),
                display_order=10,
                metadata={"message_count": len(active_messages)},
            ),
        ]
        if evidence_items:
            seeds.append(
                _current_evidence_ledger_seed(
                    session_key=session_key,
                    session_id=session.active_session_id,
                    current_run_id=current_run_id,
                    evidence_items=evidence_items,
                    parent_id=request.node.id,
                    display_order=20,
                ),
        )
        return tuple(seeds)

    def _current_evidence_frontier_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        session_key = request.workspace.session_key
        try:
            messages = tuple(
                self._session_service.list_messages(
                    ListSessionMessagesInput(
                        session_key=session_key,
                        active_session_only=True,
                        include_archived=False,
                    ),
                ),
            )
        except SessionNotFoundError:
            return ()
        current_run_id = _optional_text(request.workspace.metadata.get("last_run_id"))
        records = _browser_tool_records_for_current_run(
            messages,
            current_run_id=current_run_id,
        )
        warnings = _browser_investigation_warnings(records)
        return tuple(
            _browser_investigation_warning_seed(
                item,
                parent_id=request.node.id,
                display_order=(index + 1) * 10,
            )
            for index, item in enumerate(warnings)
        )

    def _current_evidence_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        session_key = request.workspace.session_key
        try:
            messages = tuple(
                self._session_service.list_messages(
                    ListSessionMessagesInput(
                        session_key=session_key,
                        active_session_only=True,
                        include_archived=False,
                    ),
                ),
            )
        except SessionNotFoundError:
            return ()
        current_run_id = _optional_text(request.workspace.metadata.get("last_run_id"))
        tool_lifecycle_facts = _tool_lifecycle_facts_from_execution_query(
            self._execution_query,
            current_run_id,
        )
        evidence_items = _evidence_items_for_current_run(
            messages,
            current_run_id=current_run_id,
            tool_lifecycle_facts=tool_lifecycle_facts,
        )
        return tuple(
            _evidence_item_seed(
                item,
                parent_id=request.node.id,
                display_order=(index + 1) * 10,
            )
            for index, item in enumerate(evidence_items)
        )

    def _current_message_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        session_key = request.workspace.session_key
        owner_ref = request.node.owner_ref
        after_sequence_no = _optional_int(owner_ref.get("from_sequence_no"))
        before_sequence_no = _optional_int(owner_ref.get("to_sequence_no"))
        try:
            messages = self._session_service.list_messages(
                ListSessionMessagesInput(
                    session_key=session_key,
                    active_session_only=True,
                    include_archived=False,
                    after_sequence_no=(
                        after_sequence_no - 1 if after_sequence_no is not None else None
                    ),
                    before_sequence_no=(
                        before_sequence_no + 1 if before_sequence_no is not None else None
                    ),
                ),
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
            _consumed_direct_transcript_through_sequence_no_from_summaries(
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
            messages = self._session_service.list_messages(
                ListSessionMessagesInput(
                    session_key=session_key,
                    active_session_only=True,
                    include_archived=False,
                    after_sequence_no=from_sequence_no - 1,
                    before_sequence_no=to_sequence_no + 1,
                ),
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
            _consumed_direct_transcript_through_sequence_no_from_summaries(
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
        message_visibility = _optional_text(owner_ref.get("message_visibility")) or "all"
        if session_id is None:
            return ()
        try:
            messages = self._session_service.list_messages(
                ListSessionMessagesInput(
                    session_key=session_key,
                    active_session_only=False,
                    include_archived=True,
                ),
            )
        except SessionNotFoundError:
            return ()
        segment_messages = _segment_messages(
            tuple(messages),
            session_id=session_id,
            message_visibility=message_visibility,
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
                    message_visibility=message_visibility,
                    range_token_soft_limit=self._range_token_soft_limit,
                    display_order=display_order,
                )
            )
            display_order += 10
        omitted_chunks = chunks[self._historical_range_limit :]
        if omitted_chunks:
            omitted_message_count = sum(len(chunk) for chunk in omitted_chunks)
            ranges.append(
                _range_notice_seed(
                    node_id=f"session.segment.ranges.more.{_node_part(session_id)}",
                    parent_id=request.node.id,
                    title="More Message Ranges",
                    summary=(
                        f"{len(omitted_chunks)} more range pages with "
                        f"{omitted_message_count} messages are hidden by the "
                        "session range page limit."
                    ),
                    display_order=display_order,
                    metadata={
                        "notice_kind": "range_limit",
                        "range_reason_code": "range_page_limit",
                        "segment_kind": owner_ref.get("segment_kind"),
                        "message_visibility": message_visibility,
                        "omitted_range_count": len(omitted_chunks),
                        "omitted_message_count": omitted_message_count,
                        "range_page_limit": self._historical_range_limit,
                    },
                ),
            )
        return tuple(ranges)

    def _segment_range_message_children(
        self,
        request: ContextChildrenRequest,
    ) -> tuple[ContextNodeSeed, ...]:
        session_key = request.workspace.session_key
        owner_ref = request.node.owner_ref
        session_id = _optional_text(owner_ref.get("session_id"))
        message_visibility = _optional_text(owner_ref.get("message_visibility")) or "all"
        from_sequence_no = _optional_int(owner_ref.get("from_sequence_no"))
        to_sequence_no = _optional_int(owner_ref.get("to_sequence_no"))
        if session_id is None or from_sequence_no is None or to_sequence_no is None:
            return ()
        try:
            messages = self._session_service.list_messages(
                ListSessionMessagesInput(
                    session_key=session_key,
                    active_session_only=False,
                    include_archived=True,
                    after_sequence_no=from_sequence_no - 1,
                    before_sequence_no=to_sequence_no + 1,
                ),
            )
        except SessionNotFoundError:
            return ()
        range_messages = tuple(
            message
            for message in messages
            if message.session_id == session_id
            and _matches_message_visibility(
                message,
                message_visibility=message_visibility,
            )
        )
        range_estimate = _messages_estimate(
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
                    message_visibility=message_visibility,
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
                        "message_count": len(range_messages),
                        "segment_kind": owner_ref.get("segment_kind"),
                        "message_visibility": message_visibility,
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
_BROWSER_INVESTIGATION_WARNING_REVISION = "2026-06-09.browser_investigation_warnings.v1"
_ENDPOINT_CANDIDATES_RE = re.compile(r"Endpoint candidates:\s*(\d+)")


def _current_evidence_ledger_seed(
    *,
    session_key: str,
    session_id: str,
    current_run_id: str | None,
    evidence_items: tuple[dict[str, object], ...],
    parent_id: str,
    display_order: int,
) -> ContextNodeSeed:
    evidence_types = tuple(
        dict.fromkeys(
            _optional_text(item.get("evidence_type")) or "observation"
            for item in evidence_items
        ),
    )
    summary = (
        f"{len(evidence_items)} current-run evidence items extracted from tool "
        "results. Items contain compact facts and refs; expand message/tool refs "
        "only when raw evidence is needed."
    )
    return ContextNodeSeed(
        node_id="session.evidence.current",
        parent_id=parent_id,
        owner="session",
        kind="evidence_ledger",
        title="Current Evidence Ledger",
        summary=summary,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=_BASIC_ACTIONS,
        owner_ref={
            "session_key": session_key,
            "session_id": session_id,
            "run_id": current_run_id or "",
            "evidence_count": len(evidence_items),
        },
        estimate=_text_estimate(summary),
        display_order=display_order,
        metadata={
            "evidence_count": len(evidence_items),
            "evidence_types": list(evidence_types),
            "run_id": current_run_id or "",
        },
    )


def _evidence_item_seed(
    item: dict[str, object],
    *,
    parent_id: str,
    display_order: int,
) -> ContextNodeSeed:
    tool_call_id = _optional_text(item.get("tool_call_id")) or str(display_order)
    tool_name = _optional_text(item.get("tool_name")) or "tool"
    evidence_type = _optional_text(item.get("evidence_type")) or "observation"
    status = _optional_text(item.get("status")) or "unknown"
    summary = _optional_text(item.get("summary")) or f"{tool_name} {status}."
    content = _evidence_item_content(item)
    return ContextNodeSeed(
        node_id=(
            f"session.evidence.{_short_node_part(_optional_text(item.get('session_id')) or 'active')}."
            f"{_short_node_part(tool_call_id)}"
        ),
        parent_id=parent_id,
        owner="session",
        kind="session_evidence",
        title=f"{evidence_type}: {tool_name}",
        summary=_truncate(summary, 320),
        content=content,
        state=ContextNodeState(collapsed=True, loaded=True, consumed=True),
        actions=_BASIC_ACTIONS,
        owner_ref={
            "session_key": _optional_text(item.get("session_key")) or "",
            "session_id": _optional_text(item.get("session_id")) or "",
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "tool_run_id": _optional_text(item.get("tool_run_id")) or "",
            "status": status,
            "evidence_type": evidence_type,
            "evidence_lifecycle_status": _optional_text(
                item.get("evidence_lifecycle_status"),
            )
            or "observed",
            "verified": bool(item.get("verified")),
            "failed": bool(item.get("failed")),
            "superseded": bool(item.get("superseded")),
            "hypothesis": bool(item.get("hypothesis")),
            "unresolved": bool(item.get("unresolved")),
            "call_message_id": _optional_text(item.get("call_message_id")) or "",
            "result_message_id": _optional_text(item.get("result_message_id")) or "",
            "call_sequence_no": item.get("call_sequence_no") or 0,
            "result_sequence_no": item.get("result_sequence_no") or 0,
        },
        estimate=_text_estimate(summary),
        display_order=display_order,
        metadata=dict(item),
    )


def _browser_investigation_warning_seed(
    item: dict[str, object],
    *,
    parent_id: str,
    display_order: int,
) -> ContextNodeSeed:
    code = _optional_text(item.get("code")) or "browser_investigation_warning"
    summary = _optional_text(item.get("summary")) or "Browser investigation needs attention."
    content = _browser_investigation_warning_content(item)
    warning_types = _browser_investigation_warning_types(
        code=code,
        latest_tool=_optional_text(item.get("latest_tool")) or "",
    )
    metadata = dict(item)
    metadata["warning_types"] = list(warning_types)
    metadata["warning_type"] = warning_types[0] if warning_types else "browser_investigation"
    return ContextNodeSeed(
        node_id=f"evidence.frontier.browser_warning.{_short_node_part(code)}",
        parent_id=parent_id,
        owner="session",
        kind="investigation_warning",
        title="Browser Investigation Warning",
        summary=summary,
        content=content,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=_BASIC_ACTIONS,
        owner_ref={
            "code": code,
            "warning_types": list(warning_types),
            "warning_type": warning_types[0] if warning_types else "browser_investigation",
            "severity": _optional_text(item.get("severity")) or "warning",
            "latest_tool": _optional_text(item.get("latest_tool")) or "",
            "latest_sequence_no": item.get("latest_sequence_no") or 0,
        },
        estimate=_text_estimate(f"{summary}\n{content}"),
        revision=_BROWSER_INVESTIGATION_WARNING_REVISION,
        display_order=display_order,
        metadata=metadata,
    )


def _browser_investigation_warning_content(item: dict[str, object]) -> str:
    lines = [
        "investigation_warning:",
        f"  code: {_optional_text(item.get('code')) or 'browser_investigation_warning'}",
    ]
    for key in ("latest_tool", "latest_sequence_no", "action_required", "reason"):
        value = item.get(key)
        if value is not None:
            lines.append(f"  {key}: {_json_fragment(value)}")
    return "\n".join(lines)


def _browser_investigation_warning_types(
    *,
    code: str,
    latest_tool: str,
) -> tuple[str, ...]:
    if code == "browser.endpoint_candidate_not_escalated":
        return ("candidate_not_escalated",)
    if code == "browser.network_capture_no_requests":
        return ("evidence_path_no_terminal_fact",)
    if code == "browser.same_probe_repeated":
        if latest_tool in {
            "browser.script.extract_request",
            "browser.script.find_request",
            "browser.code.search",
        }:
            return ("same_script_candidate_repetition", "same_tool_repetition")
        return ("same_tool_repetition",)
    return ("browser_investigation",)


def _evidence_items_for_current_run(
    messages: tuple[SessionMessage, ...],
    *,
    current_run_id: str | None,
    tool_lifecycle_facts: dict[str, dict[str, object]] | None = None,
    limit: int = 16,
) -> tuple[dict[str, object], ...]:
    sorted_messages = tuple(sorted(messages, key=lambda item: item.sequence_no))
    current_inbound_sequence_no = _current_inbound_sequence_no(
        sorted_messages,
        current_run_id=current_run_id,
    )
    current_messages = tuple(
        message
        for message in sorted_messages
        if current_inbound_sequence_no is None
        or message.sequence_no >= current_inbound_sequence_no
    )
    calls_by_id = {
        tool_call_id: message
        for message in current_messages
        if _is_function_call_message(message)
        for tool_call_id in (_tool_call_id(message),)
        if tool_call_id is not None
    }
    items: list[dict[str, object]] = []
    for result_message in current_messages:
        if result_message.role != "tool":
            continue
        tool_call_id = _tool_call_id(result_message)
        call_message = calls_by_id.get(tool_call_id or "")
        item = _tool_result_evidence_item(
            result_message=result_message,
            call_message=call_message,
            lifecycle_facts=_tool_lifecycle_facts_for_result(
                result_message,
                tool_lifecycle_facts or {},
            ),
        )
        if item is not None:
            items.append(item)
        if len(items) >= limit:
            break
    return tuple(items)


def _browser_tool_records_for_current_run(
    messages: tuple[SessionMessage, ...],
    *,
    current_run_id: str | None,
) -> tuple[dict[str, object], ...]:
    sorted_messages = tuple(sorted(messages, key=lambda item: item.sequence_no))
    current_inbound_sequence_no = _current_inbound_sequence_no(
        sorted_messages,
        current_run_id=current_run_id,
    )
    current_messages = tuple(
        message
        for message in sorted_messages
        if current_inbound_sequence_no is None
        or message.sequence_no >= current_inbound_sequence_no
    )
    calls_by_id = {
        tool_call_id: message
        for message in current_messages
        if _is_function_call_message(message)
        for tool_call_id in (_tool_call_id(message),)
        if tool_call_id is not None
    }
    records: list[dict[str, object]] = []
    for result_message in current_messages:
        if result_message.role != "tool":
            continue
        tool_call_id = _tool_call_id(result_message)
        call_message = calls_by_id.get(tool_call_id or "")
        tool_name = _tool_name(result_message) or (
            _tool_name(call_message) if call_message is not None else None
        )
        if tool_name is None or not tool_name.startswith("browser."):
            continue
        call_arguments = (
            call_message.content_payload.get("arguments")
            if call_message is not None
            and isinstance(call_message.content_payload.get("arguments"), dict)
            else {}
        )
        records.append(
            {
                "tool_name": tool_name,
                "tool_call_id": tool_call_id or "",
                "call_sequence_no": call_message.sequence_no if call_message else 0,
                "result_sequence_no": result_message.sequence_no,
                "arguments": call_arguments,
                "status": _tool_result_status(result_message) or "unknown",
                "result_content": _tool_result_content(result_message),
            },
        )
    return tuple(records)


def _browser_investigation_warnings(
    records: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    if not records:
        return ()
    warnings: list[dict[str, object]] = []
    for item in (
        _browser_network_capture_no_requests_warning(records),
        _browser_endpoint_candidate_not_escalated_warning(records),
        _browser_repeated_probe_warning(records),
    ):
        if item is not None:
            warnings.append(item)
    return tuple(warnings[:3])


def _browser_network_capture_no_requests_warning(
    records: tuple[dict[str, object], ...],
) -> dict[str, object] | None:
    zero_list_record = next(
        (
            record
            for record in reversed(records)
            if record.get("tool_name") == "browser.network.list_requests"
            and _network_list_returned_no_requests(record)
        ),
        None,
    )
    if zero_list_record is None:
        return None
    list_sequence = _optional_int(zero_list_record.get("result_sequence_no")) or 0
    start_records = tuple(
        record
        for record in records
        if record.get("tool_name") == "browser.network.start_capture"
        and (_optional_int(record.get("result_sequence_no")) or 0) <= list_sequence
    )
    if not start_records:
        return None
    latest_start_sequence = _optional_int(start_records[-1].get("result_sequence_no")) or 0
    triggered = any(
        record.get("tool_name")
        in {
            "browser.runtime.probe_client",
            "browser.runtime.call_client",
            "browser.evaluate",
            "browser.observe",
            "browser.action.trace",
            "browser.click",
            "browser.form.fill",
            "browser.overlay.select",
        }
        and latest_start_sequence
        <= (_optional_int(record.get("result_sequence_no")) or 0)
        <= list_sequence
        for record in records
    )
    if not triggered:
        return None
    return {
        "code": "browser.network_capture_no_requests",
        "severity": "warning",
        "latest_tool": "browser.network.list_requests",
        "latest_sequence_no": list_sequence,
        "summary": (
            "Network capture returned 0 requests after capture/probe. Trigger one "
            "concrete action or report a gap; do not repeat observe/runtime probes."
        ),
        "action_required": (
            "Choose one concrete trigger for the selected endpoint/client candidate, "
            "or stop and report verified facts/gaps."
        ),
        "reason": "network.list_requests produced no matching requests after capture was active.",
    }


def _browser_endpoint_candidate_not_escalated_warning(
    records: tuple[dict[str, object], ...],
) -> dict[str, object] | None:
    extract_record = next(
        (
            record
            for record in reversed(records)
            if record.get("tool_name") == "browser.script.extract_request"
            and _endpoint_candidate_count(record) > 0
        ),
        None,
    )
    if extract_record is None:
        return None
    extract_sequence = _optional_int(extract_record.get("result_sequence_no")) or 0
    after = tuple(
        record
        for record in records
        if (_optional_int(record.get("result_sequence_no")) or 0) > extract_sequence
    )
    if len(after) < 2:
        return None
    if any(
        record.get("tool_name")
        in {
            "browser.network.get_response_body",
            "browser.network.get_request_body",
            "browser.network.fetch_as_page",
            "browser.network.replay_request",
        }
        for record in after
    ):
        return None
    count = _endpoint_candidate_count(extract_record)
    return {
        "code": "browser.endpoint_candidate_not_escalated",
        "severity": "warning",
        "latest_tool": after[-1].get("tool_name") or "",
        "latest_sequence_no": after[-1].get("result_sequence_no") or 0,
        "summary": (
            f"script.extract_request found {count} endpoint candidate(s), but the "
            "run has not escalated to body read, page fetch, or replay."
        ),
        "action_required": (
            "Select one candidate and verify it with network body/fetch/replay, "
            "or stop and report why the candidate cannot be verified."
        ),
        "reason": "Endpoint candidates are partial evidence; more broad observe/search is no longer useful.",
    }


def _browser_repeated_probe_warning(
    records: tuple[dict[str, object], ...],
) -> dict[str, object] | None:
    signatures: dict[str, list[dict[str, object]]] = {}
    for record in records:
        signature = _browser_probe_signature(record)
        if signature is None:
            continue
        signatures.setdefault(signature, []).append(record)
    latest_sequence = _optional_int(records[-1].get("result_sequence_no")) or 0
    repeated = tuple(
        items
        for items in signatures.values()
        if len(items) >= 2
        and (_optional_int(items[-1].get("result_sequence_no")) or 0) >= latest_sequence - 4
    )
    if not repeated:
        return None
    latest_group = max(
        repeated,
        key=lambda items: _optional_int(items[-1].get("result_sequence_no")) or 0,
    )
    latest = latest_group[-1]
    return {
        "code": "browser.same_probe_repeated",
        "severity": "warning",
        "latest_tool": latest.get("tool_name") or "",
        "latest_sequence_no": latest.get("result_sequence_no") or 0,
        "summary": (
            "The same browser probe/search was repeated without a clear new fact. "
            "Switch evidence path or stop with verified facts/gaps."
        ),
        "action_required": (
            "Do not call the same probe again unless its arguments materially change."
        ),
        "reason": f"Repeated signature: {_browser_probe_signature(latest) or 'unknown'}",
    }


def _network_list_returned_no_requests(record: dict[str, object]) -> bool:
    content = _optional_text(record.get("result_content")) or ""
    return "0 shown of 0" in content or "No matching requests" in content


def _endpoint_candidate_count(record: dict[str, object]) -> int:
    content = _optional_text(record.get("result_content")) or ""
    match = _ENDPOINT_CANDIDATES_RE.search(content)
    if match is None:
        return 0
    try:
        return max(int(match.group(1)), 0)
    except ValueError:
        return 0


def _browser_probe_signature(record: dict[str, object]) -> str | None:
    tool_name = _optional_text(record.get("tool_name"))
    if tool_name not in {
        "browser.observe",
        "browser.runtime.inspect",
        "browser.runtime.probe_client",
        "browser.runtime.call_client",
        "browser.code.search",
        "browser.script.find_request",
        "browser.script.extract_request",
        "browser.network.list_requests",
    }:
        return None
    arguments = record.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}
    if tool_name == "browser.runtime.probe_client":
        return _signature_from_arguments(
            tool_name,
            arguments,
            ("target_id", "object_path", "method_name"),
        )
    if tool_name == "browser.runtime.call_client":
        return _signature_from_arguments(
            tool_name,
            arguments,
            ("target_id", "object_path", "method_name", "arguments", "argument"),
        )
    if tool_name == "browser.runtime.inspect":
        return _signature_from_arguments(
            tool_name,
            arguments,
            ("target_id", "global_names", "include_storage"),
        )
    if tool_name in {"browser.code.search", "browser.script.find_request"}:
        return _signature_from_arguments(
            tool_name,
            arguments,
            ("target_id", "query", "regex"),
        )
    if tool_name == "browser.script.extract_request":
        return _signature_from_arguments(
            tool_name,
            arguments,
            ("target_id", "script_id", "start_line", "start_column", "column"),
        )
    if tool_name == "browser.network.list_requests":
        return _signature_from_arguments(
            tool_name,
            arguments,
            ("target_id", "capture_id", "keyword", "domain", "path", "method"),
        )
    return _signature_from_arguments(tool_name, arguments, ("target_id", "mode"))


def _signature_from_arguments(
    tool_name: str,
    arguments: dict[str, object],
    keys: tuple[str, ...],
) -> str:
    parts = [tool_name]
    for key in keys:
        value = _optional_text(arguments.get(key))
        if value is not None:
            parts.append(f"{key}={value}")
    return "|".join(parts)


def _tool_result_evidence_item(
    *,
    result_message: SessionMessage,
    call_message: SessionMessage | None,
    lifecycle_facts: dict[str, object] | None = None,
) -> dict[str, object] | None:
    tool_call_id = _tool_call_id(result_message) or (
        _tool_call_id(call_message) if call_message is not None else None
    )
    tool_name = _tool_name(result_message) or (
        _tool_name(call_message) if call_message is not None else None
    )
    if tool_call_id is None or tool_name is None:
        return None
    if not _is_evidence_tool(tool_name):
        return None
    status = _tool_result_status(result_message) or "unknown"
    payload = result_message.content_payload
    details = payload.get("details")
    metadata = payload.get("metadata")
    facts = _evidence_facts(
        tool_name=tool_name,
        payload=payload,
        details=details,
        metadata=metadata,
    )
    evidence_type = _evidence_type(tool_name=tool_name, status=status, facts=facts)
    lifecycle_status = _evidence_lifecycle_status(
        evidence_type=evidence_type,
        status=status,
        facts=facts,
        result_message=result_message,
        lifecycle_facts=lifecycle_facts,
    )
    evidence_flags = _evidence_lifecycle_flags(lifecycle_status)
    summary = _evidence_summary(
        tool_name=tool_name,
        status=status,
        evidence_type=evidence_type,
        facts=facts,
        result_preview=_tool_result_content(result_message),
        error_json=_tool_result_error_json(result_message),
    )
    read_hints = _evidence_read_hints(
        session_key=result_message.session_key,
        tool_run_id=_optional_text(payload.get("tool_run_id")) or "",
        tool_name=tool_name,
        result_message_id=result_message.id,
        result_sequence_no=result_message.sequence_no,
        facts=facts,
    )
    return {
        "session_key": result_message.session_key,
        "session_id": result_message.session_id,
        "evidence_type": evidence_type,
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "tool_run_id": _optional_text(payload.get("tool_run_id")) or "",
        "status": status,
        "evidence_lifecycle_status": lifecycle_status,
        **evidence_flags,
        "summary": summary,
        "facts": facts,
        "call_message_id": call_message.id if call_message is not None else "",
        "result_message_id": result_message.id,
        "call_sequence_no": (
            call_message.sequence_no if call_message is not None else 0
        ),
        "result_sequence_no": result_message.sequence_no,
        "result_source_kind": result_message.source_kind,
        "result_source_id": result_message.source_id,
        "read_hints": [dict(item) for item in read_hints],
    }


def _is_evidence_tool(tool_name: str) -> bool:
    return not tool_name.startswith("context_tree.")


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
    path_key = _optional_text(evidence.get("evidence_path_key"))
    if path_key is not None and "evidence_path" not in facts:
        facts["evidence_path"] = _truncate(path_key, 80)
    path_title = _optional_text(evidence.get("evidence_path_title"))
    if path_title is not None and "evidence_path_title" not in facts:
        facts["evidence_path_title"] = _truncate(path_title, 120)
    path_tools = evidence.get("evidence_path_tools")
    if isinstance(path_tools, list) and "evidence_path_tools" not in facts:
        normalized_tools = [
            _truncate(value, 120)
            for value in (_optional_text(item) for item in path_tools)
            if value is not None
        ][:6]
        if normalized_tools:
            facts["evidence_path_tools"] = list(dict.fromkeys(normalized_tools))
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


def _evidence_read_hints(
    *,
    session_key: str,
    tool_run_id: str,
    tool_name: str,
    result_message_id: str,
    result_sequence_no: int,
    facts: dict[str, object],
) -> tuple[dict[str, object], ...]:
    hints: list[dict[str, object]] = []
    if tool_run_id:
        hints.append(
            {
                "owner": "tool",
                "label": "Read full tool run result",
                "ref": tool_run_id,
                "http": f"/tools/runs/{tool_run_id}",
                "cli": f"python -m crxzipple.main tool get-run {tool_run_id}",
            },
        )
    if session_key and result_message_id:
        before_sequence_no = max(result_sequence_no - 1, 1)
        hints.append(
            {
                "owner": "session",
                "label": "Read raw session result message",
                "ref": result_message_id,
                "http": (
                    f"/sessions/{session_key}/messages"
                    f"?after_sequence_no={before_sequence_no - 1}"
                    f"&before_sequence_no={result_sequence_no + 1}"
                ),
            },
        )
    for artifact_id in _evidence_artifact_ids(facts):
        hints.append(
            {
                "owner": "artifact",
                "label": "Download artifact content",
                "ref": artifact_id,
                "http": f"/artifacts/{artifact_id}/download",
            },
        )
    browser_hint = _browser_network_body_read_hint(tool_name=tool_name, facts=facts)
    if browser_hint is not None:
        hints.append(browser_hint)
    return tuple(hints)


def _evidence_artifact_ids(facts: dict[str, object]) -> tuple[str, ...]:
    raw = facts.get("artifact_ids")
    if isinstance(raw, list):
        values = [_optional_text(item) for item in raw]
        return tuple(dict.fromkeys(item for item in values if item is not None))
    value = _optional_text(raw)
    return (value,) if value is not None else ()


def _browser_network_body_read_hint(
    *,
    tool_name: str,
    facts: dict[str, object],
) -> dict[str, object] | None:
    if not tool_name.startswith("browser.") and not str(facts.get("kind") or "").startswith("network"):
        return None
    request_id = _optional_text(facts.get("request_id"))
    target_id = _optional_text(facts.get("target_id"))
    if request_id is None:
        return None
    arguments: dict[str, object] = {"request_id": request_id}
    profile = _optional_text(facts.get("profile"))
    if profile is not None:
        arguments["profile"] = profile
    if target_id is not None:
        arguments["target_id"] = target_id
    return {
        "owner": "browser",
        "label": "Read captured network response body",
        "ref": request_id,
        "tool": "browser.network.get_response_body",
        "arguments": arguments,
    }


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
        return "verified_fact"
    if tool_name.startswith("browser."):
        return "observation"
    return "user_visible_result"


def _is_failed_tool_status(status: str) -> bool:
    return status.strip().lower() not in {"succeeded", "completed", "success"}


def _tool_interaction_verified(
    *,
    tool_name: str,
    status: str,
    result_message: SessionMessage,
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
    return evidence_type == "verified_fact"


def _tool_interaction_superseded(
    result_message: SessionMessage,
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
    result_message: SessionMessage,
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


def _evidence_lifecycle_status(
    *,
    evidence_type: str,
    status: str,
    facts: dict[str, object],
    result_message: SessionMessage,
    lifecycle_facts: dict[str, object] | None = None,
) -> str:
    explicit = _explicit_evidence_lifecycle_status(
        result_message,
        lifecycle_facts=lifecycle_facts,
    )
    if explicit is not None:
        return explicit
    if _tool_interaction_superseded(
        result_message,
        lifecycle_facts=lifecycle_facts,
    ):
        return "superseded"
    if _is_failed_tool_status(status):
        return "failed"
    if evidence_type == "hypothesis":
        return "hypothesis"
    if evidence_type in {
        "api_endpoint",
        "result_shape",
        "payload_shape",
        "user_visible_result",
        "verified_fact",
    }:
        return "verified"
    if "endpoint" in facts or "result_shape" in facts or "payload_shape" in facts:
        return "verified"
    return "observed"


def _explicit_evidence_lifecycle_status(
    result_message: SessionMessage,
    lifecycle_facts: dict[str, object] | None = None,
) -> str | None:
    for source in _tool_interaction_fact_sources(
        result_message,
        lifecycle_facts=lifecycle_facts,
    ):
        for key in (
            "evidence_lifecycle_status",
            "evidence_lifecycle",
            "lifecycle_status",
        ):
            normalized = _normalize_evidence_lifecycle_status(source.get(key))
            if normalized is not None:
                return normalized
        browser_evidence = source.get("browser_evidence")
        if isinstance(browser_evidence, dict):
            for key in (
                "evidence_lifecycle_status",
                "evidence_lifecycle",
                "lifecycle_status",
            ):
                normalized = _normalize_evidence_lifecycle_status(
                    browser_evidence.get(key),
                )
                if normalized is not None:
                    return normalized
    return None


def _normalize_evidence_lifecycle_status(value: object) -> str | None:
    text = _optional_text(value)
    if text is None:
        return None
    normalized = text.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "complete": "verified",
        "completed": "verified",
        "success": "verified",
        "succeeded": "verified",
        "valid": "verified",
        "validated": "verified",
        "failure": "failed",
        "error": "failed",
        "invalid": "failed",
        "blocked": "failed",
        "replaced": "superseded",
        "obsolete": "superseded",
        "assumption": "hypothesis",
        "assumed": "hypothesis",
        "unknown": "unresolved",
        "pending": "unresolved",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in {
        "verified",
        "failed",
        "superseded",
        "hypothesis",
        "observed",
        "unresolved",
    }:
        return normalized
    return None


def _evidence_lifecycle_flags(lifecycle_status: str) -> dict[str, object]:
    return {
        "verified": lifecycle_status == "verified",
        "failed": lifecycle_status == "failed",
        "superseded": lifecycle_status == "superseded",
        "hypothesis": lifecycle_status == "hypothesis",
        "unresolved": lifecycle_status == "unresolved",
    }


def _tool_interaction_fact_sources(
    result_message: SessionMessage,
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


def _evidence_summary(
    *,
    tool_name: str,
    status: str,
    evidence_type: str,
    facts: dict[str, object],
    result_preview: str,
    error_json: str | None,
) -> str:
    ordered_fact_items = tuple(_ordered_evidence_summary_facts(facts))
    fact_bits = [
        f"{key}={value}"
        for key, value in ordered_fact_items
        if key not in {"tool_run_id", "status"} and str(value).strip()
    ]
    prefix = f"{tool_name} {evidence_type} ({status})."
    if fact_bits:
        return _truncate(f"{prefix} {'; '.join(fact_bits[:5])}.", 320)
    if error_json:
        return _truncate(f"{prefix} error={error_json}", 320)
    if result_preview:
        result_digest = _short_digest(result_preview)
        if result_digest is not None:
            return f"{prefix} result_sha256={result_digest}; read result handle if needed."
    return prefix


def _ordered_evidence_summary_facts(
    facts: dict[str, object],
) -> tuple[tuple[str, object], ...]:
    priority = (
        "endpoint",
        "method",
        "http_status",
        "evidence_path",
        "request_id",
        "target_id",
        "ref",
        "selector",
        "profile",
        "url",
        "kind",
    )
    remaining = tuple(
        (key, value)
        for key, value in facts.items()
        if key not in priority
    )
    prioritized = tuple(
        (key, facts[key])
        for key in priority
        if key in facts
    )
    return prioritized + remaining


def _evidence_item_content(item: dict[str, object]) -> str:
    facts = item.get("facts")
    if not isinstance(facts, dict):
        facts = {}
    lines = [
        f"evidence_type: {_optional_text(item.get('evidence_type')) or 'observation'}",
        f"evidence_lifecycle: {_optional_text(item.get('evidence_lifecycle_status')) or 'observed'}",
        f"tool: {_optional_text(item.get('tool_name')) or 'tool'}",
        f"status: {_optional_text(item.get('status')) or 'unknown'}",
    ]
    if facts:
        lines.append("facts:")
        for key, value in facts.items():
            if value is None or value == "":
                continue
            lines.append(f"  {key}: {_evidence_fact_text(value)}")
    lines.append("refs:")
    for key in (
        "tool_call_id",
        "tool_run_id",
        "call_message_id",
        "result_message_id",
        "call_sequence_no",
        "result_sequence_no",
    ):
        value = item.get(key)
        if value is not None and str(value).strip():
            lines.append(f"  {key}: {value}")
    read_hints = item.get("read_hints")
    if isinstance(read_hints, list) and read_hints:
        lines.append("owner_read_hints:")
        for hint in read_hints[:6]:
            if isinstance(hint, dict):
                lines.append(f"  - {_truncate(_json_fragment(hint), 280)}")
    return "\n".join(lines)


def _evidence_fact_text(value: object) -> str:
    if isinstance(value, (dict, list)):
        return _truncate(_json_fragment(value), 240)
    return _truncate(str(value), 240)


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


def _current_segment_seed(
    *,
    instance: SessionInstance,
    message_count: int,
    parent_id: str,
    display_order: int,
) -> ContextNodeSeed:
    summary = (
        f"Active {instance.kind.value} segment #{instance.sequence_no} has "
        f"{message_count} visible messages."
    )
    return ContextNodeSeed(
        node_id="session.segment.current",
        parent_id=parent_id,
        owner="session",
        kind="session_segment",
        title="Current Segment",
        summary=summary,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=_BASIC_ACTIONS,
        owner_ref={
            "session_key": instance.session_key,
            "session_id": instance.id,
            "sequence_no": instance.sequence_no,
            "status": instance.status,
            "segment_kind": "current",
            "message_count": message_count,
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
            "message_count": message_count,
        },
    )


def _historical_segment_seed(
    *,
    instance: SessionInstance,
    messages: tuple[SessionMessage, ...] | None,
    parent_id: str,
    segment_kind: str,
    message_visibility: str,
    fallback_summary: str | None,
    display_order: int,
) -> ContextNodeSeed:
    summary_text = _segment_summary_text(instance.metadata) or fallback_summary
    message_count = len(messages) if messages is not None else None
    archived_count = sum(
        1
        for message in messages or ()
        if message.visibility is SessionMessageVisibility.ARCHIVED
    )
    fallback = f"{segment_kind.title()} segment #{instance.sequence_no} is available."
    if message_count is not None:
        fallback = (
            f"{segment_kind.title()} segment #{instance.sequence_no} has "
            f"{message_count} messages."
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
        "message_visibility": message_visibility,
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
        "message_visibility": message_visibility,
        "has_summary": bool(summary_text),
    }
    if message_count is not None:
        owner_ref["message_count"] = message_count
        metadata["message_count"] = message_count
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
    messages: tuple[SessionMessage, ...],
    segment_kind: object,
    message_visibility: str,
    range_token_soft_limit: int,
    display_order: int,
) -> ContextNodeSeed:
    first_sequence_no = messages[0].sequence_no
    last_sequence_no = messages[-1].sequence_no
    estimate = _messages_estimate(messages, current_run_id=None)
    budget_status = _range_budget_status(
        estimate=estimate,
        message_count=len(messages),
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
            f"session.segment.messages.{_node_part(session_id)}."
            f"{first_sequence_no}.{last_sequence_no}"
        ),
        parent_id=parent_id,
        owner="session",
        kind="session_message_range",
        title=f"Messages {first_sequence_no}-{last_sequence_no}",
        summary=summary,
        actions=_BASIC_ACTIONS,
        owner_ref={
            "session_key": session_key,
            "session_id": session_id,
            "from_sequence_no": first_sequence_no,
            "to_sequence_no": last_sequence_no,
            "message_count": len(messages),
            "segment_kind": segment_kind,
            "message_visibility": message_visibility,
        },
        estimate=ContextEstimate(text_chars=80, text_tokens=20),
        display_order=display_order,
        metadata={
            "message_count": len(messages),
            "segment_kind": segment_kind,
            "message_visibility": message_visibility,
            "archived_count": sum(
                1
                for message in messages
                if message.visibility is SessionMessageVisibility.ARCHIVED
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
    messages: tuple[SessionMessage, ...],
    segment_kind: object,
    message_visibility: str,
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
                message_visibility=message_visibility,
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
    message_count: int,
    soft_limit: int,
) -> str:
    if estimate.text_tokens <= soft_limit:
        return "ok"
    if message_count > 1:
        return "split_required"
    return "blocked"


def _range_reason_code(budget_status: str) -> str:
    if budget_status == "split_required":
        return "split_required"
    if budget_status == "blocked":
        return "over_budget"
    return "within_budget"


def _message_node_seeds(
    messages: tuple[SessionMessage, ...],
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
    fallback_frontier_tool_call_ids = _fallback_frontier_tool_call_ids(
        sorted_messages,
        current_inbound_sequence_no=current_inbound_sequence_no,
        tool_results_by_call_id=tool_results_by_call_id,
    )
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
                            fallback_frontier_tool_call_ids=(
                                fallback_frontier_tool_call_ids
                            ),
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
    message: SessionMessage,
    *,
    parent_id: str,
    current_run_id: str | None = None,
) -> ContextNodeSeed:
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
    return ContextNodeSeed(
        node_id=f"session.message.{message.session_id}.{message.sequence_no}",
        parent_id=parent_id,
        owner="session",
        kind="session_message",
        title=f"{message.sequence_no}. {message.role}",
        summary=preview,
        content=content,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=_BASIC_ACTIONS,
        owner_ref={
            "session_key": message.session_key,
            "session_id": message.session_id,
            "message_id": message.id,
            "sequence_no": message.sequence_no,
            "role": message.role,
            "kind": message.kind.value,
            "visibility": message.visibility.value,
        },
        estimate=_message_estimate(message, content),
        display_order=message.sequence_no,
        metadata={
            "created_at": format_datetime_utc(message.created_at),
            "source_kind": message.source_kind,
            "source_id": message.source_id,
            "role": message.role,
            "kind": message.kind.value,
            "sequence_no": message.sequence_no,
            "visibility": message.visibility.value,
            "current_inbound": current_inbound,
            "content_block_types": _content_block_types(message),
            "content_digest": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        },
    )


def _tool_interaction_node_seed(
    *,
    call_message: SessionMessage,
    result_message: SessionMessage,
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
    consumed = not frontier
    opened_by_default = False
    collapsed_by_default = not frontier and not opened_by_default
    failed = _is_failed_tool_status(status)
    verified = _tool_interaction_verified(
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
        else "verified"
        if verified
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
            "verified": verified,
            "superseded": superseded,
            "superseded_by_tool_call_id": superseded_by_tool_call_id or "",
            "call_message_id": call_message.id,
            "result_message_id": result_message.id,
            "call_sequence_no": call_message.sequence_no,
            "result_sequence_no": result_message.sequence_no,
            "consumed_through_sequence_no": consumed_through_sequence_no,
            "visibility": result_message.visibility.value,
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
            "tool_result_envelope": result_envelope,
            "tool_result_browser_evidence": result_browser_evidence,
            "error_json": error_json,
            "call_source_kind": call_message.source_kind,
            "call_source_id": call_message.source_id,
            "result_source_kind": result_message.source_kind,
            "result_source_id": result_message.source_id,
            "call_sequence_no": call_message.sequence_no,
            "result_sequence_no": result_message.sequence_no,
            "consumed_through_sequence_no": consumed_through_sequence_no,
            "prompt_visibility_status": visibility_status,
            "lifecycle_status": lifecycle_status,
            "frontier": frontier,
            "current_turn": current_turn,
            "consumed": consumed,
            "failed": failed,
            "verified": verified,
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
    call_message: SessionMessage,
    result_message: SessionMessage,
    current_inbound_sequence_no: int | None,
    consumed_through_sequence_no: int | None,
    fallback_frontier_tool_call_ids: frozenset[str] = frozenset(),
) -> bool:
    if current_inbound_sequence_no is None:
        return False
    if call_message.sequence_no < current_inbound_sequence_no:
        return False
    if consumed_through_sequence_no is None:
        tool_call_id = _tool_call_id(call_message) or _tool_call_id(result_message)
        return tool_call_id in fallback_frontier_tool_call_ids
    return result_message.sequence_no > consumed_through_sequence_no


def _fallback_frontier_tool_call_ids(
    messages: tuple[SessionMessage, ...],
    *,
    current_inbound_sequence_no: int | None,
    tool_results_by_call_id: dict[str, SessionMessage],
) -> frozenset[str]:
    if current_inbound_sequence_no is None:
        return frozenset()
    pairs: list[tuple[int, str, str, str]] = []
    for message in messages:
        if message.sequence_no < current_inbound_sequence_no:
            continue
        tool_call_id = _tool_call_id(message)
        if not _is_function_call_message(message) or tool_call_id is None:
            continue
        result = tool_results_by_call_id.get(tool_call_id)
        if result is None:
            continue
        pairs.append(
            (
                result.sequence_no,
                message.source_kind,
                message.source_id,
                tool_call_id,
            ),
        )
    if not pairs:
        return frozenset()
    _latest_result_sequence, latest_source_kind, latest_source_id, latest_call_id = max(
        pairs,
        key=lambda item: item[0],
    )
    if latest_source_kind == "llm_invocation" and latest_source_id:
        return frozenset(
            tool_call_id
            for _result_sequence, source_kind, source_id, tool_call_id in pairs
            if source_kind == latest_source_kind and source_id == latest_source_id
        )
    return frozenset({latest_call_id})


def _message_preview(message: SessionMessage) -> str:
    if message.role == "tool":
        return _tool_result_message_preview(message)
    text = describe_content_for_text_fallback(message.content_payload)
    return _truncate(text.replace("\n", " "), 320)


def _tool_result_message_preview(message: SessionMessage) -> str:
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
    messages: tuple[SessionMessage, ...],
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


def _message_prompt_content(message: SessionMessage) -> str:
    if (
        message.role == "assistant"
        and message.content_payload.get("type") == "function_call"
    ):
        return _function_call_prompt_content(message)
    if message.role == "tool":
        return _tool_result_prompt_content(message)
    return _blocks_prompt_content(content_blocks_from_payload(message.content_payload))


def _function_call_prompt_content(message: SessionMessage) -> str:
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


def _tool_result_prompt_content(message: SessionMessage) -> str:
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


def _is_function_call_message(message: SessionMessage) -> bool:
    return (
        message.role == "assistant"
        and message.content_payload.get("type") == "function_call"
    )


def _tool_call_id(message: SessionMessage) -> str | None:
    return (
        _optional_text(message.metadata.get("tool_call_id"))
        or _optional_text(message.content_payload.get("call_id"))
        or _optional_text(message.content_payload.get("tool_call_id"))
    )


def _tool_name(message: SessionMessage) -> str | None:
    return (
        _optional_text(message.metadata.get("tool_name"))
        or _optional_text(message.content_payload.get("name"))
        or _optional_text(message.content_payload.get("tool_name"))
    )


def _tool_result_status(message: SessionMessage) -> str | None:
    return _optional_text(message.content_payload.get("status"))


def _tool_result_content(message: SessionMessage) -> str:
    compact_content = _large_tool_result_ref_content(message)
    if compact_content is not None:
        return compact_content
    return _blocks_prompt_content(content_blocks_from_payload(message.content_payload))


def _tool_result_envelope_metadata(message: SessionMessage) -> dict[str, object] | None:
    metadata = message.content_payload.get("metadata")
    if not isinstance(metadata, dict):
        return None
    envelope = metadata.get(TOOL_RESULT_ENVELOPE_METADATA_KEY)
    if not isinstance(envelope, dict):
        return None
    return dict(envelope)


def _tool_result_browser_evidence_metadata(
    message: SessionMessage,
) -> dict[str, object] | None:
    metadata = message.content_payload.get("metadata")
    if not isinstance(metadata, dict):
        return None
    evidence = metadata.get("browser_evidence")
    if not isinstance(evidence, dict):
        return None
    return dict(evidence)


def _large_tool_result_ref_content(message: SessionMessage) -> str | None:
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
    lines = ["result_body: omitted_from_prompt"]
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
    evidence_path = _browser_evidence_path_ref_line(evidence)
    if evidence_path is not None:
        lines.append(evidence_path)
    if artifact_ids:
        lines.append(f"artifact_refs: {', '.join(artifact_ids)}")
    payload_shape = _small_structured_evidence_fact(evidence.get("payload_shape"))
    if payload_shape is not None:
        lines.append(f"payload_shape: {_json_fragment(payload_shape)}")
    result_shape = _small_structured_evidence_fact(evidence.get("result_shape"))
    if result_shape is not None:
        lines.append(f"result_shape: {_json_fragment(result_shape)}")
    lines.append("read_full_result: use owner refs or evidence read_hints")
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
    lines = ["result_body: omitted_from_prompt"]
    status = _optional_text(envelope.get("status"))
    summary = _optional_text(envelope.get("summary"))
    if status is not None:
        lines.append(f"status: {status}")
    if summary is not None:
        lines.append(f"summary: {summary}")
    key_facts = envelope.get("key_facts")
    if isinstance(key_facts, dict) and key_facts:
        lines.append(f"key_facts: {_json_fragment(key_facts)}")
    evidence_path = _browser_evidence_path_ref_line(browser_evidence)
    if evidence_path is not None:
        lines.append(evidence_path)
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
    lines.append("read_full_result: use owner refs or evidence read_hints")
    return "\n".join(lines)


def _browser_evidence_path_ref_line(evidence: dict[str, object]) -> str | None:
    key = _optional_text(evidence.get("evidence_path_key"))
    title = _optional_text(evidence.get("evidence_path_title"))
    tools = _envelope_text_list(evidence.get("evidence_path_tools"))
    if key is None and title is None and not tools:
        return None
    label = key or title or "browser_evidence"
    if key is not None and title is not None:
        label = f"{key} ({title})"
    if tools:
        label += ": " + ", ".join(tools[:4])
    return f"evidence_path: {label}"


def _metadata_artifact_ids(metadata: dict[str, object]) -> tuple[str, ...]:
    raw = metadata.get("artifact_ids")
    if not isinstance(raw, list):
        raw = metadata.get("browser_artifact_ids")
    if not isinstance(raw, list):
        return ()
    values = [_optional_text(item) for item in raw]
    return tuple(dict.fromkeys(item for item in values if item is not None))


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


def _tool_result_error_json(message: SessionMessage) -> str | None:
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


def _content_block_types(message: SessionMessage) -> list[str]:
    return [
        str(block.get("type") or "").strip()
        for block in content_blocks_from_payload(message.content_payload)
        if str(block.get("type") or "").strip()
    ]


def _message_estimate(message: SessionMessage, content: str) -> ContextEstimate:
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


def _messages_estimate(
    messages: tuple[SessionMessage, ...],
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
    message: SessionMessage,
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


def _consumed_direct_transcript_through_sequence_no_from_summaries(
    summaries: tuple[dict[str, object], ...],
    *,
    session_id: str,
) -> int | None:
    consumed_through: int | None = None
    for summary in summaries:
        consumption = summary.get("llm_transcript_consumption")
        if not isinstance(consumption, dict):
            continue
        sequence_range = consumption.get("direct_transcript_sequence_range")
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
            "supersedes_result_message_id",
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
        for key in ("tool_call_id", "result_message_id", "tool_run_id"):
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
        "supersedes_result_message_id",
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
    result_message: SessionMessage,
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
    messages: tuple[SessionMessage, ...],
    *,
    session_id: str,
    message_visibility: str,
) -> tuple[SessionMessage, ...]:
    return tuple(
        message
        for message in messages
        if message.session_id == session_id
        and _matches_message_visibility(
            message,
            message_visibility=message_visibility,
        )
    )


def _matches_message_visibility(
    message: SessionMessage,
    *,
    message_visibility: str,
) -> bool:
    if message_visibility == "archived":
        return message.visibility is SessionMessageVisibility.ARCHIVED
    return True


def _is_historical_segment_node_id(node_id: str) -> bool:
    return node_id.startswith("session.segment.compacted.") or node_id.startswith(
        "session.segment.closed.",
    )


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
    messages: tuple[SessionMessage, ...],
    size: int,
) -> tuple[tuple[SessionMessage, ...], ...]:
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
