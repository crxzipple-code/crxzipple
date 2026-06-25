from __future__ import annotations


RUNTIME_INSPECT_EXPRESSION = """
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
