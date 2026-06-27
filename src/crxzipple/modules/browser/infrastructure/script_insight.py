from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from crxzipple.modules.browser.domain import BrowserValidationError

from .devtools import BrowserDevToolsAdapter
from .error_projection import display_safe_exception_message
from .script_insight_payloads import (
    json_safe_payload as _json_safe_payload,
    payload_bool_any as _payload_bool_any,
    payload_int_any as _payload_int_any,
    payload_text_any as _payload_text_any,
    payload_text_list as _payload_text_list,
)
from .script_insight_runtime_expression import (
    RUNTIME_INSPECT_EXPRESSION as _RUNTIME_INSPECT_EXPRESSION,
)
from .script_insight_source_analysis import (
    _code_search_metadata_matches,
    _code_search_source_matches,
    _collect_script_metadata,
    _compile_code_search_pattern,
    _extract_client_method_candidates,
    _extract_payload_key_candidates,
    _extract_request_candidates_from_window,
    _filter_scripts,
    _find_script_metadata,
    _looks_like_script_url,
    _normalize_search_term,
    _request_search_payload,
    _request_search_terms,
    _script_find_request_metadata_matches,
    _script_find_request_source_matches,
    _script_list_item,
    _script_source_extraction_window,
    _script_source_preview,
)

SCRIPT_INSIGHT_KINDS = frozenset(
    {
        "runtime-inspect",
        "script-list",
        "script-find-request",
        "code-search",
        "script-inspect",
        "script-extract-request",
    }
)
_MAX_RUNTIME_INSPECT_LIMIT = 100
_MAX_SCRIPT_LIST_LIMIT = 100
_DEFAULT_SCRIPT_FIND_REQUEST_LIMIT = 12
_MAX_SCRIPT_FIND_REQUEST_LIMIT = 20
_DEFAULT_SCRIPT_FIND_REQUEST_MAX_SCRIPTS = 24
_MAX_SCRIPT_FIND_REQUEST_MAX_SCRIPTS = 32
_DEFAULT_CODE_SEARCH_LIMIT = 8
_MAX_CODE_SEARCH_LIMIT = 12
_DEFAULT_CODE_SEARCH_MAX_SCRIPTS = 16
_MAX_CODE_SEARCH_MAX_SCRIPTS = 24
_MAX_CODE_SEARCH_CONTEXT_LINES = 2
_MAX_SCRIPT_INSPECT_PREVIEW_CHARS = 20000
_DEFAULT_SCRIPT_INSPECT_PREVIEW_CHARS = 4000
_DEFAULT_SCRIPT_INSPECT_COLUMN_WINDOW = 2400
_MAX_SCRIPT_INSPECT_COLUMN_WINDOW = 8000
_DEFAULT_REQUEST_EXTRACTION_WINDOW = 6000
_MAX_REQUEST_EXTRACTION_WINDOW = 16000


@dataclass(slots=True)
class BrowserScriptInsightService:
    devtools_adapter: BrowserDevToolsAdapter

    def execute(
        self,
        *,
        page: Any,
        kind: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        if kind == "runtime-inspect":
            return _runtime_inspect_action(page=page, payload=payload)
        if kind == "script-list":
            return _script_list_action(
                devtools_adapter=self.devtools_adapter,
                page=page,
                payload=payload,
            )
        if kind == "script-find-request":
            return _script_find_request_action(
                devtools_adapter=self.devtools_adapter,
                page=page,
                payload=payload,
            )
        if kind == "code-search":
            return _code_search_action(
                devtools_adapter=self.devtools_adapter,
                page=page,
                payload=payload,
            )
        if kind == "script-inspect":
            return _script_inspect_action(
                devtools_adapter=self.devtools_adapter,
                page=page,
                payload=payload,
            )
        if kind == "script-extract-request":
            return _script_extract_request_action(
                devtools_adapter=self.devtools_adapter,
                page=page,
                payload=payload,
            )
        raise BrowserValidationError(f"Unsupported browser code insight kind '{kind}'.")


def _runtime_inspect_action(
    *,
    page: Any,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    limit = min(_payload_int_any(payload, "limit", minimum=1) or 40, _MAX_RUNTIME_INSPECT_LIMIT)
    global_names = _payload_text_list(payload, "global_names", "globalNames")
    include_storage = _payload_bool_any(payload, "include_storage", "includeStorage")
    include_performance = _payload_bool_any(
        payload,
        "include_performance",
        "includePerformance",
    )
    raw_result = page.evaluate(
        _RUNTIME_INSPECT_EXPRESSION,
        {
            "limit": limit,
            "global_names": global_names,
            "include_storage": True if include_storage is None else include_storage,
            "include_performance": (
                True if include_performance is None else include_performance
            ),
        },
    )
    if not isinstance(raw_result, Mapping):
        raise BrowserValidationError("Browser runtime inspect returned an invalid result.")
    return {
        "kind": "runtime-inspect",
        "limit": limit,
        **_json_safe_payload(raw_result),
    }


def _script_list_action(
    *,
    devtools_adapter: BrowserDevToolsAdapter,
    page: Any,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    limit = min(
        _payload_int_any(payload, "limit", minimum=1) or 50,
        _MAX_SCRIPT_LIST_LIMIT,
    )
    wait_ms = _payload_int_any(payload, "wait_ms", "waitMs", minimum=0) or 50
    script_id_filter = _payload_text_any(payload, "script_id", "scriptId")
    url_contains = _payload_text_any(payload, "url_contains", "urlContains", "url")
    scripts = _collect_script_metadata(
        devtools_adapter.collect_debugger_scripts(page, wait_ms=wait_ms),
    )
    filtered_scripts = _filter_scripts(
        scripts,
        script_id=script_id_filter,
        url_contains=url_contains,
    )
    items = [_script_list_item(script) for script in filtered_scripts[:limit]]
    return {
        "kind": "script-list",
        "scripts_count": len(scripts),
        "matched_scripts": len(filtered_scripts),
        "returned_scripts": len(items),
        "limit": limit,
        "filters": {
            "script_id": script_id_filter,
            "url_contains": url_contains,
        },
        "scripts": items,
        "errors": [],
    }


def _script_find_request_action(
    *,
    devtools_adapter: BrowserDevToolsAdapter,
    page: Any,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    request_url = _payload_text_any(payload, "request_url", "requestUrl")
    explicit_path = _payload_text_any(payload, "path", "request_path", "requestPath")
    explicit_query = _payload_text_any(payload, "query", "endpoint", "text", "keyword")
    terms = _request_search_terms(
        request_url=request_url,
        explicit_path=explicit_path,
        explicit_query=explicit_query,
    )
    if not terms:
        raise BrowserValidationError(
            "payload.request_url, payload.path, or payload.query is required for script-find-request.",
        )
    limit = min(
        _payload_int_any(payload, "limit", minimum=1) or _DEFAULT_SCRIPT_FIND_REQUEST_LIMIT,
        _MAX_SCRIPT_FIND_REQUEST_LIMIT,
    )
    max_scripts = min(
        _payload_int_any(payload, "max_scripts", "maxScripts", minimum=1)
        or _DEFAULT_SCRIPT_FIND_REQUEST_MAX_SCRIPTS,
        _MAX_SCRIPT_FIND_REQUEST_MAX_SCRIPTS,
    )
    context_lines = min(
        _payload_int_any(payload, "context_lines", "contextLines", minimum=0) or 1,
        _MAX_CODE_SEARCH_CONTEXT_LINES,
    )
    wait_ms = _payload_int_any(payload, "wait_ms", "waitMs", minimum=0) or 50
    case_sensitive = bool(
        _payload_bool_any(payload, "case_sensitive", "caseSensitive") or False,
    )
    script_id_filter = _payload_text_any(payload, "script_id", "scriptId")
    url_contains = _payload_text_any(payload, "url_contains", "urlContains")
    scripts = _collect_script_metadata(
        devtools_adapter.collect_debugger_scripts(page, wait_ms=wait_ms),
    )
    filtered_scripts = _filter_scripts(
        scripts,
        script_id=script_id_filter,
        url_contains=url_contains,
    )
    candidates: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    total_matches = 0
    searched_scripts = 0
    for script in filtered_scripts[:max_scripts]:
        script_id = _payload_text_any(script, "script_id")
        if script_id is None:
            continue
        searched_scripts += 1
        matches: list[dict[str, Any]] = []
        matches.extend(
            _script_find_request_metadata_matches(
                script,
                terms=terms,
                case_sensitive=case_sensitive,
            )
        )
        source_available = False
        source_chars: int | None = None
        try:
            source_payload = devtools_adapter.read_script_source(page, script_id=script_id)
            source = str(source_payload.get("scriptSource") or "")
            source_available = True
            source_chars = len(source)
            remaining = max(0, limit - total_matches - len(matches))
            if remaining:
                matches.extend(
                    _script_find_request_source_matches(
                        source,
                        terms=terms,
                        case_sensitive=case_sensitive,
                        context_lines=context_lines,
                        limit=remaining,
                    )
                )
        except BrowserValidationError as exc:
            errors.append(
                {
                    "script_id": script_id,
                    "message": display_safe_exception_message(exc),
                }
            )
        if not matches:
            continue
        total_matches += len(matches)
        matched_terms = tuple(
            dict.fromkeys(
                term
                for match in matches
                for term in (_payload_text_any(match, "term"),)
                if term is not None
            )
        )
        candidates.append(
            _json_safe_payload(
                {
                    "script": script,
                    "script_id": script_id,
                    "url": script.get("url"),
                    "source_available": source_available,
                    "source_chars": source_chars,
                    "matched_terms": list(matched_terms),
                    "score": len(matched_terms) * 10 + len(matches),
                    "matches": matches,
                }
            )
        )
        if total_matches >= limit:
            break
    candidates.sort(key=lambda item: int(item.get("score") or 0), reverse=True)
    return {
        "kind": "script-find-request",
        "request": _request_search_payload(request_url=request_url, terms=terms),
        "case_sensitive": case_sensitive,
        "scripts_count": len(scripts),
        "searched_scripts": searched_scripts,
        "candidate_count": len(candidates),
        "match_count": total_matches,
        "limit": limit,
        "candidates": candidates,
        "errors": errors,
    }


def _code_search_action(
    *,
    devtools_adapter: BrowserDevToolsAdapter,
    page: Any,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    query = _payload_text_any(payload, "query", "text", "keyword")
    if query is None:
        raise BrowserValidationError("payload.query is required for code-search.")
    limit = min(
        _payload_int_any(payload, "limit", minimum=1) or _DEFAULT_CODE_SEARCH_LIMIT,
        _MAX_CODE_SEARCH_LIMIT,
    )
    max_scripts = min(
        _payload_int_any(payload, "max_scripts", "maxScripts", minimum=1)
        or _DEFAULT_CODE_SEARCH_MAX_SCRIPTS,
        _MAX_CODE_SEARCH_MAX_SCRIPTS,
    )
    context_lines = min(
        _payload_int_any(payload, "context_lines", "contextLines", minimum=0) or 1,
        _MAX_CODE_SEARCH_CONTEXT_LINES,
    )
    wait_ms = _payload_int_any(payload, "wait_ms", "waitMs", minimum=0) or 50
    case_sensitive = bool(
        _payload_bool_any(payload, "case_sensitive", "caseSensitive") or False,
    )
    use_regex = bool(_payload_bool_any(payload, "regex", "use_regex", "useRegex") or False)
    script_id_filter = _payload_text_any(payload, "script_id", "scriptId")
    url_contains = _payload_text_any(payload, "url_contains", "urlContains", "url")
    pattern = _compile_code_search_pattern(
        query=query,
        case_sensitive=case_sensitive,
        use_regex=use_regex,
    )
    scripts = _collect_script_metadata(
        devtools_adapter.collect_debugger_scripts(page, wait_ms=wait_ms),
    )
    filtered_scripts = _filter_scripts(
        scripts,
        script_id=script_id_filter,
        url_contains=url_contains,
    )
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    total_matches = 0
    searched_scripts = 0
    for script in filtered_scripts[:max_scripts]:
        script_id = _payload_text_any(script, "script_id")
        if script_id is None:
            continue
        searched_scripts += 1
        matches = _code_search_metadata_matches(
            script,
            pattern=pattern,
            query=query,
            case_sensitive=case_sensitive,
            use_regex=use_regex,
        )
        source_available = False
        source_chars: int | None = None
        try:
            source_payload = devtools_adapter.read_script_source(
                page,
                script_id=script_id,
            )
            source = str(source_payload.get("scriptSource") or "")
            source_available = True
            source_chars = len(source)
            remaining = max(0, limit - total_matches - len(matches))
            if remaining:
                matches.extend(
                    _code_search_source_matches(
                        source,
                        pattern=pattern,
                        query=query,
                        case_sensitive=case_sensitive,
                        use_regex=use_regex,
                        context_lines=context_lines,
                        limit=remaining,
                    )
                )
        except BrowserValidationError as exc:
            errors.append(
                {
                    "script_id": script_id,
                    "message": display_safe_exception_message(exc),
                }
            )
        if not matches:
            continue
        total_matches += len(matches)
        result = {
            "script": script,
            "script_id": script_id,
            "url": script.get("url"),
            "source_available": source_available,
            "source_chars": source_chars,
            "matches": matches,
        }
        results.append(_json_safe_payload(result))
        if total_matches >= limit:
            break
    return {
        "kind": "code-search",
        "query": query,
        "regex": use_regex,
        "case_sensitive": case_sensitive,
        "scripts_count": len(scripts),
        "searched_scripts": searched_scripts,
        "matched_scripts": len(results),
        "match_count": total_matches,
        "limit": limit,
        "matches": results,
        "errors": errors,
    }


def _script_inspect_action(
    *,
    devtools_adapter: BrowserDevToolsAdapter,
    page: Any,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    script_id = _payload_text_any(payload, "script_id", "scriptId")
    url_contains = _payload_text_any(payload, "url_contains", "urlContains", "url")
    if script_id is not None and _looks_like_script_url(script_id) and url_contains is None:
        url_contains = script_id
        script_id = None
    if script_id is None and url_contains is None:
        raise BrowserValidationError(
            "payload.script_id or payload.url_contains is required for script-inspect.",
        )
    wait_ms = _payload_int_any(payload, "wait_ms", "waitMs", minimum=0) or 50
    max_chars = min(
        _payload_int_any(payload, "max_chars", "maxChars", minimum=1)
        or _DEFAULT_SCRIPT_INSPECT_PREVIEW_CHARS,
        _MAX_SCRIPT_INSPECT_PREVIEW_CHARS,
    )
    start_line = _payload_int_any(payload, "start_line", "startLine", minimum=1)
    line_count = _payload_int_any(payload, "line_count", "lineCount", minimum=1)
    start_column = _payload_int_any(payload, "start_column", "startColumn", minimum=1)
    match_column = _payload_int_any(
        payload,
        "column",
        "match_column",
        "matchColumn",
        minimum=1,
    )
    column_window = min(
        _payload_int_any(
            payload,
            "column_window",
            "columnWindow",
            minimum=80,
        )
        or _DEFAULT_SCRIPT_INSPECT_COLUMN_WINDOW,
        _MAX_SCRIPT_INSPECT_COLUMN_WINDOW,
    )
    scripts = _collect_script_metadata(
        devtools_adapter.collect_debugger_scripts(page, wait_ms=wait_ms),
    )
    script = _find_script_metadata(
        scripts,
        script_id=script_id,
        url_contains=url_contains,
    )
    effective_script_id = script_id or _payload_text_any(script or {}, "script_id")
    if effective_script_id is None:
        raise BrowserValidationError("No matching browser script was found.")
    source_payload = devtools_adapter.read_script_source(
        page,
        script_id=effective_script_id,
    )
    source = str(source_payload.get("scriptSource") or "")
    preview = _script_source_preview(
        source,
        start_line=start_line,
        line_count=line_count,
        start_column=start_column,
        match_column=match_column,
        column_window=column_window,
        max_chars=max_chars,
    )
    return {
        "kind": "script-inspect",
        "script_id": effective_script_id,
        "script": script
        or {
            "script_id": effective_script_id,
            "url": None,
        },
        "scripts_count": len(scripts),
        "source_chars": len(source),
        **preview,
    }


def _script_extract_request_action(
    *,
    devtools_adapter: BrowserDevToolsAdapter,
    page: Any,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    script_id = _payload_text_any(payload, "script_id", "scriptId")
    url_contains = _payload_text_any(payload, "url_contains", "urlContains", "url")
    if script_id is not None and _looks_like_script_url(script_id) and url_contains is None:
        url_contains = script_id
        script_id = None
    wait_ms = _payload_int_any(payload, "wait_ms", "waitMs", minimum=0) or 50
    start_line = _payload_int_any(payload, "start_line", "startLine", minimum=1)
    line_count = _payload_int_any(payload, "line_count", "lineCount", minimum=1) or 8
    start_column = _payload_int_any(payload, "start_column", "startColumn", minimum=1)
    match_column = _payload_int_any(
        payload,
        "column",
        "match_column",
        "matchColumn",
        minimum=1,
    )
    column_window = min(
        _payload_int_any(
            payload,
            "column_window",
            "columnWindow",
            minimum=160,
        )
        or _DEFAULT_REQUEST_EXTRACTION_WINDOW,
        _MAX_REQUEST_EXTRACTION_WINDOW,
    )
    focus_terms = tuple(
        dict.fromkeys(
            term
            for term in (
                _normalize_search_term(item)
                for item in (
                    _payload_text_any(payload, "query", "text", "keyword"),
                    _payload_text_any(payload, "endpoint"),
                    _payload_text_any(payload, "path", "request_path", "requestPath"),
                    _payload_text_any(payload, "request_url", "requestUrl"),
                )
            )
            if term is not None
        )
    )
    limit = min(_payload_int_any(payload, "limit", minimum=1) or 8, 20)
    scripts = _collect_script_metadata(
        devtools_adapter.collect_debugger_scripts(page, wait_ms=wait_ms),
    )
    inferred_target: dict[str, Any] | None = None
    if script_id is None and url_contains is None:
        inferred_target = _infer_script_extract_target(
            devtools_adapter=devtools_adapter,
            page=page,
            focus_terms=focus_terms,
            wait_ms=wait_ms,
        )
        if inferred_target is None:
            raise BrowserValidationError(
                "payload.script_id or payload.url_contains is required for "
                "script-extract-request when no query/path can infer a script.",
            )
        script_id = _payload_text_any(inferred_target, "script_id", "scriptId")
        if start_line is None:
            start_line = _payload_int_any(inferred_target, "line_number", minimum=1)
        if match_column is None:
            match_column = _payload_int_any(inferred_target, "column", minimum=1)
    script = _find_script_metadata(
        scripts,
        script_id=script_id,
        url_contains=url_contains,
    )
    effective_script_id = script_id or _payload_text_any(script or {}, "script_id")
    if effective_script_id is None:
        raise BrowserValidationError("No matching browser script was found.")
    source_payload = devtools_adapter.read_script_source(
        page,
        script_id=effective_script_id,
    )
    source = str(source_payload.get("scriptSource") or "")
    window = _script_source_extraction_window(
        source,
        start_line=start_line,
        line_count=line_count,
        start_column=start_column,
        match_column=match_column,
        column_window=column_window,
        max_source_chars=_MAX_REQUEST_EXTRACTION_WINDOW,
    )
    candidates = _extract_request_candidates_from_window(
        window.get("source_window") or "",
        base_line=_payload_int_any(window, "start_line", minimum=1) or 1,
        base_column=_payload_int_any(window, "start_column", minimum=1) or 1,
        single_line=(
            (_payload_int_any(window, "start_line", minimum=1) or 1)
            == (_payload_int_any(window, "end_line", minimum=1) or 1)
        ),
        focus_terms=focus_terms,
        limit=limit,
    )
    return {
        "kind": "script-extract-request",
        "script_id": effective_script_id,
        "script": script
        or {
            "script_id": effective_script_id,
            "url": None,
        },
        "scripts_count": len(scripts),
        "source_chars": len(source),
        "focus_terms": list(focus_terms),
        "inferred_target": _json_safe_payload(inferred_target),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "payload_key_candidates": _extract_payload_key_candidates(
            window.get("source_window") or "",
            limit=20,
        ),
        "client_method_candidates": _extract_client_method_candidates(
            window.get("source_window") or "",
            limit=20,
        ),
        **{key: value for key, value in window.items() if key != "source_window"},
    }


def _infer_script_extract_target(
    *,
    devtools_adapter: BrowserDevToolsAdapter,
    page: Any,
    focus_terms: tuple[str, ...],
    wait_ms: int,
) -> dict[str, Any] | None:
    if not focus_terms:
        return None
    found = _script_find_request_action(
        devtools_adapter=devtools_adapter,
        page=page,
        payload={
            "query": focus_terms[0],
            "limit": 1,
            "max_scripts": 24,
            "context_lines": 0,
            "wait_ms": wait_ms,
        },
    )
    candidates = found.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return None
    candidate = candidates[0]
    if not isinstance(candidate, Mapping):
        return None
    script_id = _payload_text_any(candidate, "script_id", "scriptId")
    if script_id is None:
        return None
    matches = candidate.get("matches")
    match = matches[0] if isinstance(matches, list) and matches else {}
    if not isinstance(match, Mapping):
        match = {}
    return {
        "script_id": script_id,
        "url": _payload_text_any(candidate, "url"),
        "line_number": _payload_int_any(match, "line_number", minimum=1),
        "column": _payload_int_any(match, "column", minimum=1),
        "term": _payload_text_any(match, "term"),
    }
