from __future__ import annotations

import re
from typing import Any, Mapping
from urllib.parse import urlsplit

from crxzipple.modules.browser.domain import BrowserValidationError

from .script_insight_payloads import (
    json_safe_payload as _json_safe_payload,
    payload_bool_any as _payload_bool_any,
    payload_int_any as _payload_int_any,
    payload_text_any as _payload_text_any,
)

_REQUEST_ENDPOINT_RE = re.compile(
    r"""(?P<quote>['"`])(?P<value>(?:https?://[^'"`\s<>{}|\\]+|/[A-Za-z0-9_./~:%?&=#,+-]{2,}|[A-Za-z0-9_-]+(?:/[A-Za-z0-9_.~:%?&=#,+-]+){1,}))(?P=quote)""",
)
_REQUEST_METHOD_RE = re.compile(
    r"""(?i)(?:method\s*[:=]\s*['"]|\.)(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)(?:['"]|\b)""",
)
_CLIENT_METHOD_RE = re.compile(
    r"""\b([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*){1,})\s*\(""",
)
_NAMED_FUNCTION_RE = re.compile(
    r"""\b([A-Za-z_$][\w$]*)\s*(?:[:=]\s*(?:async\s*)?function|\([^)]{0,160}\)\s*=>|\([^)]{0,160}\)\s*\{)""",
)
_PAYLOAD_KEY_RE = re.compile(
    r"""(?<![\w$])['"]?([A-Za-z_$][\w$]{1,48})['"]?\s*:""",
)


def _collect_script_metadata(raw_scripts: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    scripts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_script in raw_scripts:
        script_id = _payload_text_any(raw_script, "scriptId", "script_id")
        if script_id is None or script_id in seen:
            continue
        seen.add(script_id)
        metadata = {
            "script_id": script_id,
            "url": _payload_text_any(raw_script, "url"),
            "start_line": _payload_int_any(raw_script, "startLine", "start_line", minimum=0),
            "start_column": _payload_int_any(
                raw_script,
                "startColumn",
                "start_column",
                minimum=0,
            ),
            "end_line": _payload_int_any(raw_script, "endLine", "end_line", minimum=0),
            "end_column": _payload_int_any(raw_script, "endColumn", "end_column", minimum=0),
            "execution_context_id": _payload_int_any(
                raw_script,
                "executionContextId",
                "execution_context_id",
                minimum=0,
            ),
            "hash": _payload_text_any(raw_script, "hash"),
            "source_map_url": _payload_text_any(raw_script, "sourceMapURL", "source_map_url"),
            "is_module": bool(_payload_bool_any(raw_script, "isModule", "is_module") or False),
        }
        scripts.append({key: value for key, value in metadata.items() if value is not None})
    return scripts


def _script_list_item(script: Mapping[str, Any]) -> dict[str, Any]:
    start_line = _payload_int_any(script, "start_line", minimum=0)
    end_line = _payload_int_any(script, "end_line", minimum=0)
    line_count = None
    if start_line is not None and end_line is not None and end_line >= start_line:
        line_count = end_line - start_line + 1
    item = {
        "script_id": _payload_text_any(script, "script_id"),
        "url": _payload_text_any(script, "url"),
        "start_line": start_line,
        "end_line": end_line,
        "line_count": line_count,
        "execution_context_id": _payload_int_any(script, "execution_context_id", minimum=0),
        "source_map_url": _payload_text_any(script, "source_map_url"),
        "is_module": bool(_payload_bool_any(script, "is_module") or False),
        "hash": _payload_text_any(script, "hash"),
    }
    return {key: value for key, value in item.items() if value is not None}


def _request_search_terms(
    *,
    request_url: str | None,
    explicit_path: str | None,
    explicit_query: str | None,
) -> tuple[str, ...]:
    terms: list[str] = []
    if request_url is not None:
        terms.append(request_url)
        try:
            parsed = urlsplit(request_url)
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.path:
                terms.append(parsed.path)
                stripped_path = parsed.path.lstrip("/")
                if stripped_path:
                    terms.append(stripped_path)
            if parsed.query and parsed.path:
                terms.append(f"{parsed.path}?{parsed.query}")
    if explicit_path is not None:
        terms.append(explicit_path)
        stripped_path = explicit_path.lstrip("/")
        if stripped_path:
            terms.append(stripped_path)
    if explicit_query is not None:
        terms.append(explicit_query)
    return tuple(
        dict.fromkeys(
            term
            for term in (_normalize_search_term(item) for item in terms)
            if term is not None
        )
    )


def _normalize_search_term(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if len(normalized) < 3:
        return None
    return normalized


def _request_search_payload(*, request_url: str | None, terms: tuple[str, ...]) -> dict[str, Any]:
    payload: dict[str, Any] = {"search_terms": list(terms)}
    if request_url is None:
        return payload
    payload["url"] = request_url
    try:
        parsed = urlsplit(request_url)
    except ValueError:
        return payload
    if parsed.netloc:
        payload["origin"] = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme else parsed.netloc
    if parsed.path:
        payload["path"] = parsed.path
    if parsed.query:
        payload["has_query"] = True
    return payload


def _script_find_request_metadata_matches(
    script: Mapping[str, Any],
    *,
    terms: tuple[str, ...],
    case_sensitive: bool,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for metadata_field in ("url", "source_map_url"):
        value = _payload_text_any(script, metadata_field)
        if value is None:
            continue
        for term in terms:
            if not _text_matches(
                value,
                pattern=None,
                query=term,
                case_sensitive=case_sensitive,
                use_regex=False,
            ):
                continue
            matches.append(
                {
                    "field": metadata_field,
                    "term": term,
                    "line_number": None,
                    "column": None,
                    "snippet": _bounded_code_snippet(value, limit=500),
                }
            )
            break
    return matches


def _script_find_request_source_matches(
    source: str,
    *,
    terms: tuple[str, ...],
    case_sensitive: bool,
    context_lines: int,
    limit: int,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    seen_locations: set[tuple[int | None, int | None, str]] = set()
    for term in terms:
        remaining = max(0, limit - len(matches))
        if not remaining:
            break
        term_matches = _code_search_source_matches(
            source,
            pattern=None,
            query=term,
            case_sensitive=case_sensitive,
            use_regex=False,
            context_lines=context_lines,
            limit=remaining,
        )
        for match in term_matches:
            line_number = _payload_int_any(match, "line_number", minimum=1)
            column = _payload_int_any(match, "column", minimum=1)
            dedupe_key = (line_number, column, term)
            if dedupe_key in seen_locations:
                continue
            seen_locations.add(dedupe_key)
            matches.append({**match, "term": term})
            if len(matches) >= limit:
                break
    return matches


def _filter_scripts(
    scripts: list[dict[str, Any]],
    *,
    script_id: str | None,
    url_contains: str | None,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    normalized_url_contains = url_contains.lower() if url_contains is not None else None
    for script in scripts:
        if script_id is not None and _payload_text_any(script, "script_id") != script_id:
            continue
        if normalized_url_contains is not None:
            url = (_payload_text_any(script, "url") or "").lower()
            if normalized_url_contains not in url:
                continue
        filtered.append(script)
    return filtered


def _find_script_metadata(
    scripts: list[dict[str, Any]],
    *,
    script_id: str | None,
    url_contains: str | None,
) -> dict[str, Any] | None:
    filtered = _filter_scripts(
        scripts,
        script_id=script_id,
        url_contains=url_contains,
    )
    return filtered[0] if filtered else None


def _looks_like_script_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _compile_code_search_pattern(
    *,
    query: str,
    case_sensitive: bool,
    use_regex: bool,
) -> re.Pattern[str] | None:
    if not use_regex:
        return None
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        return re.compile(query, flags)
    except re.error as exc:
        raise BrowserValidationError(f"payload.query is not a valid regex: {exc}") from exc


def _code_search_metadata_matches(
    script: Mapping[str, Any],
    *,
    pattern: re.Pattern[str] | None,
    query: str,
    case_sensitive: bool,
    use_regex: bool,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for metadata_field in ("url", "source_map_url"):
        value = _payload_text_any(script, metadata_field)
        if value is None:
            continue
        if not _text_matches(
            value,
            pattern=pattern,
            query=query,
            case_sensitive=case_sensitive,
            use_regex=use_regex,
        ):
            continue
        matches.append(
            {
                "field": metadata_field,
                "line_number": None,
                "column": None,
                "snippet": _bounded_code_snippet(value, limit=500),
            }
        )
    return matches


def _code_search_source_matches(
    source: str,
    *,
    pattern: re.Pattern[str] | None,
    query: str,
    case_sensitive: bool,
    use_regex: bool,
    context_lines: int,
    limit: int,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    lines = source.splitlines()
    for index, line in enumerate(lines):
        column = _text_match_column(
            line,
            pattern=pattern,
            query=query,
            case_sensitive=case_sensitive,
            use_regex=use_regex,
        )
        if column is None:
            continue
        start_index = max(0, index - context_lines)
        end_index = min(len(lines), index + context_lines + 1)
        snippet_lines = [
            f"{line_number + 1}: {lines[line_number]}"
            for line_number in range(start_index, end_index)
        ]
        matches.append(
            {
                "field": "source",
                "line_number": index + 1,
                "column": column,
                "snippet": _bounded_code_snippet("\n".join(snippet_lines), limit=320),
            }
        )
        if len(matches) >= limit:
            break
    return matches


def _script_source_preview(
    source: str,
    *,
    start_line: int | None,
    line_count: int | None,
    start_column: int | None,
    match_column: int | None,
    column_window: int,
    max_chars: int,
) -> dict[str, Any]:
    lines = source.splitlines()
    start_index = max(0, (start_line or 1) - 1)
    if start_index >= len(lines):
        return {
            "start_line": start_index + 1,
            "end_line": start_index + 1,
            "source_preview": "",
            "truncated": bool(source),
        }
    if start_column is not None or match_column is not None:
        return _script_source_column_preview(
            lines[start_index],
            line_number=start_index + 1,
            start_column=start_column,
            match_column=match_column,
            column_window=column_window,
            max_chars=max_chars,
        )
    end_index = len(lines) if line_count is None else min(len(lines), start_index + line_count)
    preview_lines: list[str] = []
    char_count = 0
    truncated = end_index < len(lines) or start_index > 0
    for line_number in range(start_index, end_index):
        line_text = f"{line_number + 1}: {lines[line_number]}"
        projected = char_count + len(line_text) + (1 if preview_lines else 0)
        if projected > max_chars:
            truncated = True
            if not preview_lines:
                preview_lines.append(_bounded_code_snippet(line_text, limit=max_chars))
            break
        preview_lines.append(line_text)
        char_count = projected
    return {
        "start_line": start_index + 1,
        "end_line": start_index + len(preview_lines),
        "source_preview": "\n".join(preview_lines),
        "truncated": truncated,
    }


def _script_source_column_preview(
    line: str,
    *,
    line_number: int,
    start_column: int | None,
    match_column: int | None,
    column_window: int,
    max_chars: int,
) -> dict[str, Any]:
    max_window = max(80, min(column_window, max_chars))
    if match_column is not None and start_column is None:
        start_index = max(0, match_column - 1 - max_window // 3)
    else:
        start_index = max(0, (start_column or match_column or 1) - 1)
    end_index = min(len(line), start_index + max_window)
    segment = line[start_index:end_index]
    prefix = "..." if start_index > 0 else ""
    suffix = "..." if end_index < len(line) else ""
    preview = (
        f"{line_number} [columns {start_index + 1}-{max(start_index + 1, end_index)}]: "
        f"{prefix}{segment}{suffix}"
    )
    return {
        "start_line": line_number,
        "end_line": line_number,
        "start_column": start_index + 1,
        "end_column": max(start_index + 1, end_index),
        "source_preview": preview,
        "truncated": start_index > 0 or end_index < len(line),
    }


def _script_source_extraction_window(
    source: str,
    *,
    start_line: int | None,
    line_count: int,
    start_column: int | None,
    match_column: int | None,
    column_window: int,
    max_source_chars: int,
) -> dict[str, Any]:
    lines = source.splitlines()
    start_index = max(0, (start_line or 1) - 1)
    if start_index >= len(lines):
        return {
            "start_line": start_index + 1,
            "end_line": start_index + 1,
            "source_window": "",
            "truncated": bool(source),
        }
    if start_column is not None or match_column is not None:
        max_window = max(160, column_window)
        line = lines[start_index]
        if match_column is not None and start_column is None:
            column_start_index = max(0, match_column - 1 - max_window // 3)
        else:
            column_start_index = max(0, (start_column or match_column or 1) - 1)
        column_end_index = min(len(line), column_start_index + max_window)
        return {
            "start_line": start_index + 1,
            "end_line": start_index + 1,
            "start_column": column_start_index + 1,
            "end_column": max(column_start_index + 1, column_end_index),
            "source_window": line[column_start_index:column_end_index],
            "truncated": column_start_index > 0 or column_end_index < len(line),
        }
    requested_end_index = min(len(lines), start_index + max(1, line_count))
    window_lines: list[str] = []
    char_count = 0
    truncated = start_index > 0 or requested_end_index < len(lines)
    for line_number in range(start_index, requested_end_index):
        line = lines[line_number]
        projected = char_count + len(line) + (1 if window_lines else 0)
        if projected > max_source_chars:
            truncated = True
            if not window_lines:
                window_lines.append(line[:max_source_chars])
            break
        window_lines.append(line)
        char_count = projected
    return {
        "start_line": start_index + 1,
        "end_line": start_index + max(1, len(window_lines)),
        "source_window": "\n".join(window_lines),
        "truncated": truncated,
    }


def _extract_request_candidates_from_window(
    source_window: str,
    *,
    base_line: int,
    base_column: int,
    single_line: bool,
    focus_terms: tuple[str, ...],
    limit: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, match in enumerate(_REQUEST_ENDPOINT_RE.finditer(source_window)):
        endpoint = match.group("value")
        if endpoint in seen:
            continue
        seen.add(endpoint)
        neighborhood = _source_neighborhood(source_window, match.start(), match.end())
        location = _window_location(
            source_window,
            offset=match.start("value"),
            base_line=base_line,
            base_column=base_column,
            single_line=single_line,
        )
        candidate = {
            "kind": "endpoint_candidate",
            "endpoint": endpoint,
            "endpoint_kind": _endpoint_kind(endpoint),
            "line_number": location["line_number"],
            "column": location["column"],
            "method_candidates": _extract_method_candidates(neighborhood),
            "client_method_candidates": _extract_client_method_candidates(
                neighborhood,
                limit=8,
            ),
            "payload_key_candidates": _extract_payload_key_candidates(
                neighborhood,
                limit=16,
            ),
            "focus_match": _candidate_matches_focus(endpoint, neighborhood, focus_terms),
            "endpoint_focus_match": _candidate_endpoint_matches_focus(
                endpoint,
                focus_terms,
            ),
            "confidence": "medium",
            "evidence_preview": _bounded_code_snippet(neighborhood, limit=700),
            "_focus_score": _candidate_focus_score(endpoint, neighborhood, focus_terms),
            "_source_index": index,
        }
        if candidate["method_candidates"] or candidate["payload_key_candidates"]:
            candidate["confidence"] = "high"
        if candidate["endpoint_focus_match"]:
            candidate["confidence"] = "high"
        candidates.append(_json_safe_payload(candidate))
    candidates.sort(
        key=lambda item: (
            -int(item.get("_focus_score") or 0),
            0 if item.get("confidence") == "high" else 1,
            int(item.get("_source_index") or 0),
        ),
    )
    return [
        {
            key: value
            for key, value in candidate.items()
            if key not in {"_focus_score", "_source_index"}
        }
        for candidate in candidates[:limit]
    ]


def _source_neighborhood(source: str, start: int, end: int) -> str:
    window_start = max(0, start - 900)
    window_end = min(len(source), end + 1200)
    return source[window_start:window_end]


def _window_location(
    source_window: str,
    *,
    offset: int,
    base_line: int,
    base_column: int,
    single_line: bool,
) -> dict[str, int]:
    if single_line:
        return {"line_number": base_line, "column": base_column + offset}
    prefix = source_window[:offset]
    line_delta = prefix.count("\n")
    if line_delta == 0:
        return {"line_number": base_line, "column": base_column + offset}
    last_newline = prefix.rfind("\n")
    return {
        "line_number": base_line + line_delta,
        "column": offset - last_newline,
    }


def _endpoint_kind(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme and parsed.netloc:
        return "absolute_url"
    if value.startswith("/"):
        return "absolute_path"
    return "relative_path"


def _extract_method_candidates(source: str) -> list[str]:
    values: list[str] = []
    for match in _REQUEST_METHOD_RE.finditer(source):
        values.append(match.group(1).upper())
    return list(dict.fromkeys(values))


def _extract_client_method_candidates(source: str, *, limit: int) -> list[str]:
    values: list[str] = []
    for regex in (_CLIENT_METHOD_RE, _NAMED_FUNCTION_RE):
        for match in regex.finditer(source):
            value = match.group(1)
            if value in {"if", "for", "while", "switch", "function", "return"}:
                continue
            values.append(value)
            if len(dict.fromkeys(values)) >= limit:
                return list(dict.fromkeys(values))
    return list(dict.fromkeys(values))[:limit]


def _extract_payload_key_candidates(source: str, *, limit: int) -> list[str]:
    values: list[str] = []
    for match in _PAYLOAD_KEY_RE.finditer(source):
        value = match.group(1)
        if value in {"http", "https", "function", "return", "var", "let", "const"}:
            continue
        values.append(value)
        if len(dict.fromkeys(values)) >= limit:
            break
    return list(dict.fromkeys(values))[:limit]


def _candidate_matches_focus(
    endpoint: str,
    neighborhood: str,
    focus_terms: tuple[str, ...],
) -> bool:
    return _candidate_focus_score(endpoint, neighborhood, focus_terms) > 0


def _candidate_endpoint_matches_focus(
    endpoint: str,
    focus_terms: tuple[str, ...],
) -> bool:
    endpoint_lower = endpoint.lower()
    return any(
        term_lower == endpoint_lower or term_lower in endpoint_lower
        for term_lower in (term.lower() for term in focus_terms)
    )


def _candidate_focus_score(
    endpoint: str,
    neighborhood: str,
    focus_terms: tuple[str, ...],
) -> int:
    if not focus_terms:
        return 0
    haystack = f"{endpoint}\n{neighborhood}".lower()
    endpoint_lower = endpoint.lower()
    score = 0
    for term in focus_terms:
        term_lower = term.lower()
        if term_lower == endpoint_lower:
            score = max(score, 100)
            continue
        if term_lower in endpoint_lower:
            score = max(score, 80)
            continue
        if term_lower in haystack:
            score = max(score, 20)
    return score


def _text_matches(
    value: str,
    *,
    pattern: re.Pattern[str] | None,
    query: str,
    case_sensitive: bool,
    use_regex: bool,
) -> bool:
    if use_regex:
        return pattern is not None and pattern.search(value) is not None
    if case_sensitive:
        return query in value
    return query.lower() in value.lower()


def _text_match_column(
    value: str,
    *,
    pattern: re.Pattern[str] | None,
    query: str,
    case_sensitive: bool,
    use_regex: bool,
) -> int | None:
    if use_regex:
        match = pattern.search(value) if pattern is not None else None
        return match.start() + 1 if match is not None else None
    haystack = value if case_sensitive else value.lower()
    needle = query if case_sensitive else query.lower()
    index = haystack.find(needle)
    return index + 1 if index >= 0 else None


def _bounded_code_snippet(value: str, *, limit: int) -> str:
    normalized = value.strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3].rstrip()}..."

