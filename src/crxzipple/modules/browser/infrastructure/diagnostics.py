from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
import tempfile
from typing import Any, Mapping
from uuid import uuid4

from crxzipple.modules.browser.application.events import (
    BROWSER_DIAGNOSTICS_COLLECTED_EVENT,
    BROWSER_TRACE_EXPORTED_EVENT,
    BROWSER_TRACE_STARTED_EVENT,
    BrowserEventEmitter,
    emit_browser_event,
)
from crxzipple.modules.browser.domain import BrowserValidationError
from crxzipple.modules.browser.domain.value_objects import _normalize_optional_text

from .cdp_sessions import BrowserCdpSessionBroker

_DIAGNOSTIC_KINDS = frozenset(
    {
        "diagnostics-collect",
        "performance-metrics",
        "trace-start",
        "trace-stop",
        "trace-export",
        "page-lifecycle",
        "page-errors",
    }
)
_PERFORMANCE_ENTRY_EXPRESSION = """
/*__crxzipple_browser_performance_entries__*/
() => {
  const entries = performance.getEntries().slice(-200).map((entry) => ({
    name: entry.name,
    entry_type: entry.entryType,
    initiator_type: entry.initiatorType || null,
    start_time: entry.startTime,
    duration: entry.duration,
    transfer_size: entry.transferSize || 0,
    encoded_body_size: entry.encodedBodySize || 0,
    decoded_body_size: entry.decodedBodySize || 0,
    next_hop_protocol: entry.nextHopProtocol || null,
    response_status: entry.responseStatus || 0,
  }));
  return {
    url: location.href,
    time_origin: performance.timeOrigin,
    entry_count: entries.length,
    entries,
  };
}
""".strip()
_PAGE_LIFECYCLE_EXPRESSION = """
() => ({
  url: location.href,
  title: document.title,
  ready_state: document.readyState,
  visibility_state: document.visibilityState,
  focused: document.hasFocus(),
  history_length: history.length,
  online: navigator.onLine,
})
""".strip()


@dataclass(slots=True)
class BrowserDiagnosticsService:
    event_emitter: BrowserEventEmitter | None = None
    _trace_artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)

    def execute(
        self,
        *,
        page: Any,
        kind: str,
        payload: Mapping[str, Any],
        console_messages: list[dict[str, Any]] | None = None,
        page_errors: list[dict[str, Any]] | None = None,
        profile_name: str | None = None,
        target_id: str | None = None,
        page_url: str | None = None,
    ) -> dict[str, Any]:
        normalized_kind = _normalize_kind(kind)
        raw_payload = dict(payload)
        if normalized_kind == "diagnostics-collect":
            result = self._collect_diagnostics(
                page=page,
                payload=raw_payload,
                console_messages=console_messages or [],
                page_errors=page_errors or [],
            )
        elif normalized_kind == "performance-metrics":
            result = self._performance_metrics(page=page, payload=raw_payload)
        elif normalized_kind == "page-lifecycle":
            result = self._page_lifecycle(page=page)
        elif normalized_kind == "page-errors":
            result = self._page_errors(
                payload=raw_payload,
                console_messages=console_messages or [],
                page_errors=page_errors or [],
            )
        elif normalized_kind == "trace-start":
            result = self._trace_start(page=page, payload=raw_payload, target_id=target_id)
        elif normalized_kind == "trace-stop":
            result = self._trace_stop(page=page, payload=raw_payload, target_id=target_id)
        elif normalized_kind == "trace-export":
            result = self._trace_export(payload=raw_payload, target_id=target_id)
        else:  # pragma: no cover - guarded by _normalize_kind
            raise BrowserValidationError(f"Unsupported browser diagnostic kind '{kind}'.")
        self._emit_diagnostic_event(
            kind=normalized_kind,
            result=result,
            profile_name=profile_name,
            target_id=target_id,
            page_url=page_url,
        )
        return {
            "kind": normalized_kind,
            "profile_name": profile_name,
            "target_id": target_id,
            "page_url": page_url,
            **result,
        }

    def _emit_diagnostic_event(
        self,
        *,
        kind: str,
        result: Mapping[str, Any],
        profile_name: str | None,
        target_id: str | None,
        page_url: str | None,
    ) -> None:
        if self.event_emitter is None:
            return
        if kind == "trace-start":
            event_name = BROWSER_TRACE_STARTED_EVENT
            status = "started"
            level = "info"
            entity_type = "browser.trace"
            entity_id = _payload_text(result, "trace_id") or target_id or "trace"
            display_label = "Browser trace started"
            display_summary = f"Trace {entity_id} started."
        elif kind in {"trace-stop", "trace-export"}:
            event_name = BROWSER_TRACE_EXPORTED_EVENT
            status = "exported"
            level = "info"
            entity_type = "browser.trace"
            entity_id = _payload_text(result, "trace_id") or target_id or "trace"
            display_label = "Browser trace exported"
            display_summary = f"Trace {entity_id} exported."
        else:
            event_name = BROWSER_DIAGNOSTICS_COLLECTED_EVENT
            issue_count = _safe_int(result.get("issue_count"))
            if issue_count is None:
                issue_count = _safe_int(result.get("error_count")) or 0
            status = "warning" if issue_count > 0 else "healthy"
            level = "warning" if issue_count > 0 else "info"
            entity_type = "browser.diagnostics"
            entity_id = target_id or kind
            display_label = "Browser diagnostics collected"
            display_summary = f"{kind} found {issue_count} issue(s)."
        payload = {
            "profile_name": profile_name,
            "target_id": target_id,
            "page_url": page_url,
            "diagnostic_kind": kind,
            "operation_kind": kind,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "display_label": display_label,
            "display_summary": display_summary,
            **_diagnostic_event_facts(result),
        }
        emit_browser_event(
            self.event_emitter,
            event_name,
            payload=payload,
            status=status,
            level=level,
        )

    def _collect_diagnostics(
        self,
        *,
        page: Any,
        payload: Mapping[str, Any],
        console_messages: list[dict[str, Any]],
        page_errors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        include_entries = _payload_bool(payload, "include_entries")
        if include_entries is None:
            include_entries = False
        performance = self._performance_metrics(
            page=page,
            payload={"include_entries": include_entries},
        )
        lifecycle = self._page_lifecycle(page=page)
        errors = _error_messages(console_messages, page_errors)
        return {
            "diagnostics": {
                "lifecycle": lifecycle,
                "performance": performance,
                "errors": errors,
                "console": _console_summary(console_messages),
            },
            "issue_count": len(errors),
            "summary": _diagnostics_summary(
                lifecycle=lifecycle,
                performance=performance,
                errors=errors,
                console_messages=console_messages,
            ),
        }

    def _performance_metrics(
        self,
        *,
        page: Any,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        include_entries = bool(_payload_bool(payload, "include_entries"))
        errors: list[dict[str, str]] = []
        metrics: dict[str, Any] = {}
        entries: dict[str, Any] = {}
        session = _new_page_cdp_session(page)
        try:
            try:
                _send_cdp_session_command(session, "Performance.enable", {})
                raw_metrics = _send_cdp_session_command(session, "Performance.getMetrics", {})
                metrics = _json_safe(raw_metrics) if isinstance(raw_metrics, dict) else {}
            except Exception as exc:  # noqa: BLE001
                errors.append({"source": "Performance.getMetrics", "message": str(exc)})
        finally:
            _detach_cdp_session(session)
        if include_entries:
            try:
                raw_entries = page.evaluate(_PERFORMANCE_ENTRY_EXPRESSION)
                entries = _json_safe(raw_entries) if isinstance(raw_entries, dict) else {}
            except Exception as exc:  # noqa: BLE001
                errors.append({"source": "performance.entries", "message": str(exc)})
        return {
            "metrics": metrics,
            "entries": entries,
            "errors": errors,
        }

    def _page_lifecycle(self, *, page: Any) -> dict[str, Any]:
        errors: list[dict[str, str]] = []
        lifecycle: dict[str, Any] = {}
        try:
            raw_lifecycle = page.evaluate(_PAGE_LIFECYCLE_EXPRESSION)
            lifecycle = _json_safe(raw_lifecycle) if isinstance(raw_lifecycle, dict) else {}
        except Exception as exc:  # noqa: BLE001
            errors.append({"source": "page.lifecycle", "message": str(exc)})
        session = _new_page_cdp_session(page)
        try:
            try:
                history = _send_cdp_session_command(session, "Page.getNavigationHistory", {})
                if isinstance(history, dict):
                    lifecycle["navigation_history"] = _json_safe(history)
            except Exception as exc:  # noqa: BLE001
                errors.append({"source": "Page.getNavigationHistory", "message": str(exc)})
        finally:
            _detach_cdp_session(session)
        return {
            **lifecycle,
            "errors": errors,
        }

    def _page_errors(
        self,
        *,
        payload: Mapping[str, Any],
        console_messages: list[dict[str, Any]],
        page_errors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        limit = _payload_int(payload, "limit", minimum=1) or 50
        errors = _error_messages(console_messages, page_errors)[-limit:]
        return {
            "errors": errors,
            "error_count": len(errors),
        }

    def _trace_start(
        self,
        *,
        page: Any,
        payload: Mapping[str, Any],
        target_id: str | None,
    ) -> dict[str, Any]:
        tracing = _context_tracing(page)
        trace_id = _payload_text(payload, "trace_id") or f"trace-{uuid4().hex}"
        screenshots = _payload_bool(payload, "screenshots")
        snapshots = _payload_bool(payload, "snapshots")
        sources = _payload_bool(payload, "sources")
        start_kwargs = {
            "screenshots": True if screenshots is None else screenshots,
            "snapshots": True if snapshots is None else snapshots,
            "sources": False if sources is None else sources,
        }
        title = _payload_text(payload, "title")
        if title is not None:
            start_kwargs["title"] = title
        tracing.start(**start_kwargs)
        self._trace_artifacts[_trace_key(target_id)] = {
            "trace_id": trace_id,
            "status": "active",
            "target_id": target_id,
            "start_options": dict(start_kwargs),
        }
        return {
            "trace_id": trace_id,
            "status": "active",
            "start_options": start_kwargs,
        }

    def _trace_stop(
        self,
        *,
        page: Any,
        payload: Mapping[str, Any],
        target_id: str | None,
    ) -> dict[str, Any]:
        tracing = _context_tracing(page)
        current = dict(self._trace_artifacts.get(_trace_key(target_id), {}))
        trace_id = _payload_text(payload, "trace_id") or _normalize_optional_text(
            current.get("trace_id"),
        ) or f"trace-{uuid4().hex}"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / f"{trace_id}.zip"
            tracing.stop(path=str(path))
            data = path.read_bytes()
        artifact = {
            "trace_id": trace_id,
            "status": "stopped",
            "content_type": "application/zip",
            "encoding": "base64",
            "data": base64.b64encode(data).decode("ascii"),
            "size_bytes": len(data),
        }
        self._trace_artifacts[_trace_key(target_id)] = artifact
        return dict(artifact)

    def _trace_export(
        self,
        *,
        payload: Mapping[str, Any],
        target_id: str | None,
    ) -> dict[str, Any]:
        trace_id = _payload_text(payload, "trace_id")
        candidates = (
            self._trace_artifacts.values()
            if trace_id is not None
            else (self._trace_artifacts.get(_trace_key(target_id)),)
        )
        for artifact in candidates:
            if not isinstance(artifact, dict):
                continue
            if trace_id is not None and artifact.get("trace_id") != trace_id:
                continue
            if artifact.get("status") == "stopped":
                return dict(artifact)
        raise BrowserValidationError("No stopped browser trace is available to export.")


def _normalize_kind(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in _DIAGNOSTIC_KINDS:
        supported = ", ".join(sorted(_DIAGNOSTIC_KINDS))
        raise BrowserValidationError(f"kind must be one of {supported}.")
    return normalized


def _page_context(page: Any) -> Any:
    page_context = getattr(page, "context", None)
    if callable(page_context):
        page_context = page_context()
    if page_context is None:
        raise BrowserValidationError("Playwright page does not expose a browser context.")
    return page_context


def _context_tracing(page: Any) -> Any:
    tracing = getattr(_page_context(page), "tracing", None)
    if tracing is None:
        raise BrowserValidationError(
            "Playwright browser context does not support tracing.",
        )
    return tracing


def _new_page_cdp_session(page: Any) -> Any:
    return BrowserCdpSessionBroker().open_command_session(page)


def _send_cdp_session_command(
    session: Any,
    method: str,
    params: Mapping[str, Any] | None = None,
) -> Any:
    return BrowserCdpSessionBroker().send_command(session, method, params)


def _detach_cdp_session(session: Any) -> None:
    BrowserCdpSessionBroker().detach(session)


def _payload_text(payload: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _normalize_optional_text(payload.get(key))
        if value is not None:
            return value
    return None


def _payload_bool(payload: Mapping[str, Any], *keys: str) -> bool | None:
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
        raise BrowserValidationError(f"{key} must be a boolean.")
    return None


def _payload_int(
    payload: Mapping[str, Any],
    *keys: str,
    minimum: int | None = None,
) -> int | None:
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, bool):
            raise BrowserValidationError(f"{key} must be an integer.")
        try:
            numeric = int(value)
        except (TypeError, ValueError) as exc:
            raise BrowserValidationError(f"{key} must be an integer.") from exc
        if minimum is not None and numeric < minimum:
            raise BrowserValidationError(
                f"{key} must be greater than or equal to {minimum}.",
            )
        return numeric
    return None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _diagnostic_event_facts(result: Mapping[str, Any]) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    summary = result.get("summary")
    if isinstance(summary, Mapping):
        facts.update(
            {
                "ready_state": summary.get("ready_state"),
                "visibility_state": summary.get("visibility_state"),
                "console_count": summary.get("console_count"),
                "error_count": summary.get("error_count"),
                "performance_error_count": summary.get("performance_error_count"),
            },
        )
    for key in ("issue_count", "error_count", "content_type"):
        if result.get(key) is not None:
            facts[key] = result.get(key)
    trace_id = _payload_text(result, "trace_id")
    if trace_id is not None:
        facts["trace_id"] = trace_id
    size_bytes = _safe_int(result.get("size_bytes"))
    if size_bytes is not None:
        facts["trace_size_bytes"] = size_bytes
    return {key: value for key, value in facts.items() if value is not None}


def _error_messages(
    messages: list[dict[str, Any]],
    page_errors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for message in messages:
        level = str(message.get("level") or "").strip().lower()
        if level not in {"error", "assert"}:
            continue
        item = dict(message)
        item.setdefault("source", "console")
        errors.append(item)
    for page_error in page_errors:
        item = dict(page_error)
        item.setdefault("level", "error")
        item.setdefault("source", "pageerror")
        errors.append(item)
    return errors


def _console_summary(messages: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for message in messages:
        level = str(message.get("level") or "log").strip().lower() or "log"
        counts[level] = counts.get(level, 0) + 1
    return counts


def _diagnostics_summary(
    *,
    lifecycle: Mapping[str, Any],
    performance: Mapping[str, Any],
    errors: list[dict[str, Any]],
    console_messages: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "ready_state": lifecycle.get("ready_state"),
        "visibility_state": lifecycle.get("visibility_state"),
        "console_count": len(console_messages),
        "error_count": len(errors),
        "performance_error_count": len(performance.get("errors", ()) or ()),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _trace_key(target_id: str | None) -> str:
    return _normalize_optional_text(target_id) or "default"


__all__ = ["BrowserDiagnosticsService"]
