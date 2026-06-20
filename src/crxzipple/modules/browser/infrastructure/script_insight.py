from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping
from urllib.parse import urlsplit

from crxzipple.modules.browser.domain import BrowserValidationError

from .devtools import BrowserDevToolsAdapter

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
_RUNTIME_INSPECT_EXPRESSION = """
/*__crxzipple_browser_runtime_inspect__*/
(raw) => {
  const input = raw && typeof raw === "object" ? raw : {};
  const limit = Math.max(1, Math.min(Number(input.limit || 40), 100));
  const includeStorage = input.include_storage !== false && input.includeStorage !== false;
  const includePerformance = input.include_performance !== false && input.includePerformance !== false;
  const safeString = (value, max = 160) => {
    try {
      const text = String(value ?? "");
      return text.length > max ? `${text.slice(0, max - 3)}...` : text;
    } catch {
      return "";
    }
  };
  const safeKeys = (value, max = 12) => {
    try {
      if (!value || (typeof value !== "object" && typeof value !== "function")) return [];
      return Object.keys(value).slice(0, max);
    } catch {
      return [];
    }
  };
  const methodRelevanceTerms = [
    "api",
    "client",
    "endpoint",
    "fetch",
    "load",
    "request",
    "response",
    "search",
    "query",
    "list",
    "result",
    "data",
    "detail",
    "info",
    "submit",
    "route",
    "router",
    "path",
    "calendar",
    "schedule",
    "availability",
  ];
  const relevanceScore = (name) => {
    const lowered = String(name || "").toLowerCase();
    let score = 0;
    for (const term of methodRelevanceTerms) {
      if (lowered.includes(term)) score += term.length;
    }
    if (/^(get|query|search|list|find|fetch|load)/i.test(String(name || ""))) score += 3;
    return score;
  };
  const rankedKeys = (value, max = 24) => {
    try {
      if (!value || (typeof value !== "object" && typeof value !== "function")) return [];
      return Object.keys(value)
        .map((key, index) => ({ key, index, score: relevanceScore(key) }))
        .sort((left, right) => right.score - left.score || left.index - right.index)
        .slice(0, max)
        .map((item) => item.key);
    } catch {
      return [];
    }
  };
  const routeHintFromValue = (name, value) => {
    if (!value || typeof value !== "object") return null;
    const keys = ["route", "router", "path", "pathname", "asPath", "currentRoute", "fullPath"];
    const out = { source: String(name), keys: [] };
    for (const key of keys) {
      try {
        const nested = value[key];
        if (typeof nested === "string" && nested) {
          out.keys.push({ key, value: safeString(nested, 240) });
        } else if (nested && typeof nested === "object") {
          const nestedKeys = {};
          for (const nestedKey of ["path", "fullPath", "name", "params", "query"]) {
            try {
              const nestedValue = nested[nestedKey];
              if (typeof nestedValue === "string") {
                nestedKeys[nestedKey] = safeString(nestedValue, 240);
              } else if (nestedValue && typeof nestedValue === "object") {
                nestedKeys[nestedKey] = safeString(JSON.stringify(nestedValue), 240);
              }
            } catch {}
          }
          if (Object.keys(nestedKeys).length) out.keys.push({ key, value: nestedKeys });
        }
      } catch {}
    }
    return out.keys.length ? out : null;
  };
  const describeGlobal = (name) => {
    const item = { name: String(name), exists: false };
    try {
      const value = window[name];
      if (typeof value === "undefined") return item;
      item.exists = true;
      item.type = typeof value;
      item.constructor_name = value && value.constructor && value.constructor.name
        ? String(value.constructor.name)
        : null;
      item.keys = safeKeys(value);
      if (["string", "number", "boolean"].includes(typeof value)) {
        item.preview = safeString(value);
      }
      const routeHint = routeHintFromValue(name, value);
      if (routeHint) item.route_hint = routeHint;
      return item;
    } catch (error) {
      item.error = error && error.message ? String(error.message) : String(error);
      return item;
    }
  };
  const storageKeys = (store) => {
    const keys = [];
    try {
      for (let index = 0; index < store.length && keys.length < limit; index += 1) {
        const key = store.key(index);
        if (key) keys.push(String(key));
      }
      return { count: store.length, keys };
    } catch (error) {
      return {
        count: null,
        keys: [],
        error: error && error.message ? String(error.message) : String(error),
      };
    }
  };
  const requestedGlobals = Array.isArray(input.global_names)
    ? input.global_names.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  const knownGlobals = [
    "__REACT_DEVTOOLS_GLOBAL_HOOK__",
    "__NEXT_DATA__",
    "__NUXT__",
    "$nuxt",
    "nuxtApp",
    "$fetch",
    "$axios",
    "Vue",
    "__VUE__",
    "ng",
    "angular",
    "Svelte",
    "__REDUX_DEVTOOLS_EXTENSION__",
    "__APOLLO_CLIENT__",
  ];
  const globalNames = Array.from(new Set([...knownGlobals, ...requestedGlobals])).slice(0, limit);
  const globals = globalNames.map(describeGlobal);
  const globalExists = (name) => globals.some((item) => item.name === name && item.exists);
  const reactHook = globalExists("__REACT_DEVTOOLS_GLOBAL_HOOK__");
  const nextData = globalExists("__NEXT_DATA__");
  const vueGlobal = globalExists("Vue") || globalExists("__VUE__");
  const nuxtGlobal = globalExists("__NUXT__") || globalExists("$nuxt") || globalExists("nuxtApp");
  const angularGlobal = globalExists("ng") || globalExists("angular");
  const svelteGlobal = globalExists("Svelte");
  const frameworks = [
    { key: "react", label: "React", detected: reactHook },
    { key: "next", label: "Next.js", detected: nextData },
    { key: "vue", label: "Vue", detected: vueGlobal },
    { key: "nuxt", label: "Nuxt", detected: nuxtGlobal },
    { key: "angular", label: "Angular", detected: angularGlobal },
    { key: "svelte", label: "Svelte", detected: svelteGlobal },
  ];
  const routeHints = [
    {
      source: "location",
      path: String(window.location.pathname || ""),
      search: String(window.location.search || ""),
      hash: String(window.location.hash || ""),
    },
  ];
  try {
    if (history && history.state != null) {
      routeHints.push({
        source: "history.state",
        preview: safeString(JSON.stringify(history.state), 300),
      });
    }
  } catch {}
  try {
    const nextData = window.__NEXT_DATA__;
    if (nextData && typeof nextData === "object") {
      routeHints.push({
        source: "__NEXT_DATA__",
        page: typeof nextData.page === "string" ? safeString(nextData.page, 240) : null,
        query: nextData.query && typeof nextData.query === "object"
          ? safeString(JSON.stringify(nextData.query), 240)
          : null,
      });
    }
  } catch {}
  const performanceSummary = {};
  if (includePerformance && performance && performance.getEntriesByType) {
    const resourceEntries = performance.getEntriesByType("resource");
    const byInitiator = {};
    for (const entry of resourceEntries) {
      const key = String(entry.initiatorType || "other");
      byInitiator[key] = (byInitiator[key] || 0) + 1;
    }
    performanceSummary.resource_count = resourceEntries.length;
    performanceSummary.navigation_count = performance.getEntriesByType("navigation").length;
    performanceSummary.by_initiator = byInitiator;
  }
  const clientModules = [];
  const pushModule = (path, value, methodLimit = 24) => {
    try {
      if (!value || (typeof value !== "object" && typeof value !== "function")) return;
      const allKeys = Object.keys(value);
      const keys = rankedKeys(value, methodLimit);
      if (!keys.length) return;
      const methods = allKeys
        .map((key, index) => {
          try {
            const child = value[key];
            if (typeof child !== "function") return null;
            return {
              name: key,
              path: `${path}.${key}`,
              arity: Number(child.length || 0),
              score: relevanceScore(key),
              index,
            };
          } catch {
            return null;
          }
        })
        .filter(Boolean)
        .sort((left, right) => right.score - left.score || left.index - right.index)
        .slice(0, methodLimit)
        .map(({ score, index, ...item }) => item);
      clientModules.push({
        path,
        type: typeof value,
        constructor_name: value && value.constructor && value.constructor.name
          ? String(value.constructor.name)
          : null,
        keys,
        key_count: allKeys.length,
        methods,
        method_count: allKeys.filter((key) => {
          try {
            return typeof value[key] === "function";
          } catch {
            return false;
          }
        }).length,
      });
    } catch {}
  };
  try {
    const nuxt = window.$nuxt;
    if (nuxt && typeof nuxt === "object") {
      pushModule("$nuxt", nuxt, 16);
      if (nuxt.$http) {
        pushModule("$nuxt.$http", nuxt.$http, 40);
        const httpKeys = safeKeys(nuxt.$http, 12);
        for (const key of httpKeys) {
          const value = nuxt.$http[key];
          if (value && (typeof value === "object" || typeof value === "function")) {
            pushModule(`$nuxt.$http.${key}`, value, 32);
          }
        }
      }
      if (nuxt.$api) pushModule("$nuxt.$api", nuxt.$api, 40);
      if (nuxt.$axios) pushModule("$nuxt.$axios", nuxt.$axios, 24);
      if (nuxt.$store) pushModule("$nuxt.$store", nuxt.$store, 24);
    }
  } catch {}
  const out = {
    url: String(window.location.href || ""),
    title: String(document.title || ""),
    page_state: {
      ready_state: String(document.readyState || ""),
      visibility_state: String(document.visibilityState || ""),
      focused: Boolean(document.hasFocus && document.hasFocus()),
      online: Boolean(navigator.onLine),
      history_length: Number.isFinite(Number(history.length)) ? Number(history.length) : null,
    },
    location: {
      origin: String(window.location.origin || ""),
      pathname: String(window.location.pathname || ""),
      search: String(window.location.search || ""),
      hash: String(window.location.hash || ""),
    },
    navigator: {
      user_agent: safeString(navigator.userAgent || "", 240),
      language: safeString(navigator.language || ""),
      platform: safeString(navigator.platform || ""),
      webdriver: Boolean(navigator.webdriver),
    },
    frameworks: {
      detected: frameworks.filter((item) => item.detected).map((item) => item.key),
      items: frameworks,
    },
    globals,
    client_modules: clientModules.slice(0, limit),
    route_hints: [
      ...routeHints,
      ...globals.map((item) => item.route_hint).filter(Boolean),
    ],
    performance: performanceSummary,
  };
  if (includeStorage) {
    out.storage = {
      local: storageKeys(window.localStorage),
      session: storageKeys(window.sessionStorage),
    };
  }
  return out;
}
""".strip()


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
            errors.append({"script_id": script_id, "message": str(exc)})
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
            errors.append({"script_id": script_id, "message": str(exc)})
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
        if projected > _MAX_REQUEST_EXTRACTION_WINDOW:
            truncated = True
            if not window_lines:
                window_lines.append(line[:_MAX_REQUEST_EXTRACTION_WINDOW])
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


def _payload_text_list(payload: Mapping[str, Any], *keys: str) -> list[str]:
    raw_value = _payload_value_any(payload, *keys)
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        return [item.strip() for item in raw_value.split(",") if item.strip()]
    if isinstance(raw_value, (list, tuple)):
        return [str(item).strip() for item in raw_value if str(item).strip()]
    raise BrowserValidationError("Browser script insight text lists must be a string or list.")


def _payload_text_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _payload_bool_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> bool | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            return value
    return None


def _payload_value_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def _payload_int_any(
    payload: Mapping[str, Any],
    *keys: str,
    minimum: int = 0,
) -> int | None:
    value = _payload_value_any(payload, *keys)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BrowserValidationError(f"payload.{keys[0]} must be an integer.")
    resolved = int(value)
    if resolved < minimum:
        raise BrowserValidationError(
            f"payload.{keys[0]} must be greater than or equal to {minimum}.",
        )
    return resolved


def _json_safe_payload(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_payload(item) for item in value]
    return str(value)
