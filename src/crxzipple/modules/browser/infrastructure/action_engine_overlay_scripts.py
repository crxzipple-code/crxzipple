"""Overlay and picker browser-side JavaScript expressions."""

from __future__ import annotations

from .action_engine_script_markers import (
    _ACTIVE_OVERLAY_MARKER,
    _ASSOCIATED_OVERLAY_MARKER,
    _AUTOCOMPLETE_OVERLAY_STATUS_MARKER,
    _DATEPICKER_PANEL_STATUS_MARKER,
    _DATEPICKER_DAY_ORDINAL_MARKER,
)

_ACTIVE_OVERLAY_SELECTOR_EXPRESSION = f"""
(() => {{
  const {_ACTIVE_OVERLAY_MARKER} = true;
  const selectorFor = (element) => {{
    if (!(element instanceof Element)) return null;
    if (element.id) return `#${{CSS.escape(element.id)}}`;
    const parts = [];
    let current = element;
    while (current && current.nodeType === Node.ELEMENT_NODE && current !== document.body) {{
      const tag = current.tagName.toLowerCase();
      let segment = tag;
      if (current.classList && current.classList.length) {{
        segment += "." + Array.from(current.classList).slice(0, 2).map((name) => CSS.escape(name)).join(".");
      }}
      const parent = current.parentElement;
      if (parent) {{
        const siblings = Array.from(parent.children).filter((candidate) => candidate.tagName === current.tagName);
        if (siblings.length > 1) {{
          segment += `:nth-of-type(${{siblings.indexOf(current) + 1}})`;
        }}
      }}
      parts.unshift(segment);
      current = parent;
    }}
    return parts.length ? `body > ${{parts.join(" > ")}}` : null;
  }};
  const isVisible = (element) => {{
    if (!(element instanceof HTMLElement)) return true;
    if (element.hidden) return false;
    if (element.getAttribute("aria-hidden") === "true") return false;
    const style = window.getComputedStyle(element);
    if (!style) return true;
    if (style.display === "none") return false;
    if (style.visibility === "hidden" || style.visibility === "collapse") return false;
    if (style.pointerEvents === "none") return false;
    if (Number(style.opacity || "1") === 0) return false;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }};
  const score = (element, index) => {{
    let total = index;
    const role = (element.getAttribute("role") || "").toLowerCase();
    if (role === "dialog" || role === "alertdialog") total += 2000;
    if (role === "listbox" || role === "menu") total += 1800;
    if (role === "tooltip" || role === "tree" || role === "grid") total += 1500;
    const cls = element.className || "";
    if (typeof cls === "string") {{
      if (/dropdown|popover|popup|modal|dialog|menu|autocomplete|picker|calendar-panel|datepicker|date-picker|time-picker|select/i.test(cls)) total += 1200;
      if (/\\bshow\\b|\\bopen\\b|\\bactive\\b/i.test(cls)) total += 500;
    }}
    const style = window.getComputedStyle(element);
    if (style) {{
      const zIndex = Number(style.zIndex || "0");
      if (!Number.isNaN(zIndex)) total += zIndex;
      if (style.position === "fixed") total += 400;
      if (style.position === "absolute") total += 200;
    }}
    return total;
  }};
  const candidates = Array.from(document.querySelectorAll(
    "[role='dialog'],[role='alertdialog'],[role='listbox'],[role='menu'],[role='tooltip'],[role='tree'],[role='grid'],.ant-select-dropdown,.ant-picker-dropdown,.ant-dropdown,.ant-popover,.ant-modal,.autocomplete,.city-autocomplete-list,.calendar-panel.show,.calendar-panel,[class*='calendar-panel'],[class*='picker-panel'],[class*='picker-dropdown'],[class*='datepicker'],[class*='date-picker'],[class*='time-picker'],.popup,.modal,.menu,.dropdown"
  )).filter(isVisible);
  if (!candidates.length) return null;
  let best = null;
  let bestScore = -Infinity;
  candidates.forEach((element, index) => {{
    const currentScore = score(element, index);
    if (currentScore > bestScore) {{
      best = element;
      bestScore = currentScore;
    }}
  }});
  return best ? selectorFor(best) : null;
}})()
""".strip()
_ASSOCIATED_OVERLAY_SELECTOR_EXPRESSION = f"""
/*{_ASSOCIATED_OVERLAY_MARKER}*/
(options) => {{
  const normalize = (value) => String(value || "").trim();
  const overlayKind = normalize(options?.overlayKind);
  const sourceSelector = normalize(options?.sourceSelector);
  const sourceScopeSelector = normalize(options?.sourceScopeSelector);
  const source = sourceSelector ? document.querySelector(sourceSelector) : null;
  const sourceScope = sourceScopeSelector ? document.querySelector(sourceScopeSelector) : null;
  const activeElement = document.activeElement instanceof Element ? document.activeElement : null;
  const selectorFor = (element) => {{
    if (!(element instanceof Element)) return null;
    if (element.id) return `#${{CSS.escape(element.id)}}`;
    const parts = [];
    let current = element;
    while (current && current.nodeType === Node.ELEMENT_NODE && current !== document.body) {{
      const tag = current.tagName.toLowerCase();
      let segment = tag;
      if (current.classList && current.classList.length) {{
        segment += "." + Array.from(current.classList).slice(0, 2).map((name) => CSS.escape(name)).join(".");
      }}
      const parent = current.parentElement;
      if (parent) {{
        const siblings = Array.from(parent.children).filter((candidate) => candidate.tagName === current.tagName);
        if (siblings.length > 1) {{
          segment += `:nth-of-type(${{siblings.indexOf(current) + 1}})`;
        }}
      }}
      parts.unshift(segment);
      current = parent;
    }}
    return parts.length ? `body > ${{parts.join(" > ")}}` : null;
  }};
  const isVisible = (element) => {{
    if (!(element instanceof HTMLElement)) return true;
    if (element.hidden) return false;
    if (element.getAttribute("aria-hidden") === "true") return false;
    const style = window.getComputedStyle(element);
    if (!style) return true;
    if (style.display === "none") return false;
    if (style.visibility === "hidden" || style.visibility === "collapse") return false;
    if (style.pointerEvents === "none") return false;
    if (Number(style.opacity || "1") === 0) return false;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }};
  const distance = (rectA, rectB) => {{
    if (!rectA || !rectB) return Infinity;
    const ax = rectA.left + rectA.width / 2;
    const ay = rectA.top + rectA.height / 2;
    const bx = rectB.left + rectB.width / 2;
    const by = rectB.top + rectB.height / 2;
    return Math.hypot(ax - bx, ay - by);
  }};
  const sourceRect = source && typeof source.getBoundingClientRect === "function" ? source.getBoundingClientRect() : null;
  const sourceScopeRect = sourceScope && typeof sourceScope.getBoundingClientRect === "function" ? sourceScope.getBoundingClientRect() : null;
  const controlledIds = new Set(
    [source?.getAttribute?.("aria-controls"), source?.getAttribute?.("aria-owns")]
      .filter((value) => typeof value === "string")
      .flatMap((value) => String(value).split(/\\s+/).map((item) => item.trim()).filter(Boolean))
  );
  const inferOverlayKind = (element) => {{
    if (!(element instanceof Element)) return null;
    const role = normalize(element.getAttribute("role")).toLowerCase();
    const cls = normalize(element.className).toLowerCase();
    if (
      role === "listbox"
      || /autocomplete|select|cascader|suggest|listbox/.test(cls)
      || element.querySelector("[role='option'], .ant-select-item-option, .ant-cascader-menu-item")
    ) return "autocomplete";
    if (
      /picker|calendar|datepicker/.test(cls)
      || element.querySelector(".ant-picker-cell, [role='gridcell'], .calendar-day, .date, .day")
    ) return "datepicker";
    if (
      role === "menu"
      || /menu|dropdown/.test(cls)
      || element.querySelector("[role='menuitem']")
    ) return "menu";
    return null;
  }};
  const candidates = Array.from(document.querySelectorAll(
    "[role='dialog'],[role='alertdialog'],[role='listbox'],[role='menu'],[role='tooltip'],[role='tree'],[role='grid'],.ant-select-dropdown,.ant-picker-dropdown,.ant-dropdown,.ant-popover,.ant-modal,.autocomplete,.city-autocomplete-list,.calendar-panel.show,.calendar-panel,[class*='calendar-panel'],[class*='picker-panel'],[class*='picker-dropdown'],[class*='datepicker'],[class*='date-picker'],[class*='time-picker'],.popup,.modal,.menu,.dropdown"
  )).filter(isVisible);
  if (!candidates.length) return null;
  let best = null;
  let bestScore = -Infinity;
  candidates.forEach((element, index) => {{
    let score = index;
    const rect = typeof element.getBoundingClientRect === "function" ? element.getBoundingClientRect() : null;
    const elementId = normalize(element.getAttribute("id"));
    if (elementId && controlledIds.has(elementId)) score += 6000;
    if (activeElement && element.contains(activeElement)) score += 2500;
    if (sourceScope && (sourceScope.contains(element) || element.contains(sourceScope))) score += 1200;
    if (sourceScopeRect && rect) score += Math.max(0, 450 - distance(sourceScopeRect, rect));
    if (sourceRect && rect) score += Math.max(0, 700 - distance(sourceRect, rect));
    const inferredKind = inferOverlayKind(element);
    if (overlayKind && inferredKind === overlayKind) score += 3500;
    else if (overlayKind && inferredKind && inferredKind !== overlayKind) score -= 1200;
    const cls = element.className || "";
    if (typeof cls === "string" && /autocomplete|picker|calendar-panel|datepicker|date-picker|time-picker|dropdown|popover|popup|modal|dialog|menu|select/i.test(cls)) {{
      score += 400;
    }}
    if (score > bestScore) {{
      best = element;
      bestScore = score;
    }}
  }});
  return best ? selectorFor(best) : null;
}}
""".strip()
_AUTOCOMPLETE_OVERLAY_STATUS_EXPRESSION = f"""
/*{_AUTOCOMPLETE_OVERLAY_STATUS_MARKER}*/
(options) => {{
  const normalize = (value) => String(value || "").trim().replace(/\\s+/g, " ");
  const overlayKind = normalize(options?.overlayKind);
  const sourceSelector = normalize(options?.sourceSelector);
  const sourceScopeSelector = normalize(options?.sourceScopeSelector);
  const explicitOverlaySelector = normalize(options?.overlaySelector);
  const explicitOptionSelector = normalize(options?.optionSelector);
  const optionText = normalize(options?.optionText);
  const exact = !!options?.exact;
  const activeOverlay = !!options?.activeOverlay;
  const requireReady = options?.requireReady !== false;
  const overlaySelectors = [
    "[role='dialog']",
    "[role='alertdialog']",
    "[role='listbox']",
    "[role='menu']",
    "[role='tooltip']",
    "[role='tree']",
    "[role='grid']",
    ".ant-select-dropdown",
    ".ant-picker-dropdown",
    ".ant-dropdown",
    ".ant-popover",
    ".ant-modal",
    ".autocomplete",
    ".city-autocomplete-list",
    ".calendar-panel.show",
    ".calendar-panel",
    "[class*='calendar-panel']",
    "[class*='picker-panel']",
    "[class*='picker-dropdown']",
    "[class*='datepicker']",
    "[class*='date-picker']",
    "[class*='time-picker']",
    ".popup",
    ".modal",
    ".menu",
    ".dropdown",
  ].join(",");
  const optionSelectors = explicitOptionSelector
    ? [explicitOptionSelector]
    : [
        "[role='option']",
        "[role='menuitem']",
        "[role='treeitem']",
        "[role='gridcell']",
        "[data-value]",
        "li",
        "button",
        "a[href]",
        ".ant-select-item-option",
        ".ant-select-item",
        ".ant-picker-cell",
        ".ant-cascader-menu-item",
      ];
  const selectorFor = (element) => {{
    if (!(element instanceof Element)) return null;
    if (element.id) return `#${{CSS.escape(element.id)}}`;
    const parts = [];
    let current = element;
    while (current && current.nodeType === Node.ELEMENT_NODE && current !== document.body) {{
      const tag = current.tagName.toLowerCase();
      let segment = tag;
      if (current.classList && current.classList.length) {{
        segment += "." + Array.from(current.classList).slice(0, 2).map((name) => CSS.escape(name)).join(".");
      }}
      const parent = current.parentElement;
      if (parent) {{
        const siblings = Array.from(parent.children).filter((candidate) => candidate.tagName === current.tagName);
        if (siblings.length > 1) {{
          segment += `:nth-of-type(${{siblings.indexOf(current) + 1}})`;
        }}
      }}
      parts.unshift(segment);
      current = parent;
    }}
    return parts.length ? `body > ${{parts.join(" > ")}}` : null;
  }};
  const isVisible = (element) => {{
    if (!(element instanceof HTMLElement)) return true;
    if (element.hidden) return false;
    if (element.getAttribute("aria-hidden") === "true") return false;
    const style = window.getComputedStyle(element);
    if (!style) return true;
    if (style.display === "none") return false;
    if (style.visibility === "hidden" || style.visibility === "collapse") return false;
    if (style.pointerEvents === "none") return false;
    if (Number(style.opacity || "1") === 0) return false;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }};
  const isDisabled = (element) => {{
    if (
      element instanceof HTMLButtonElement ||
      element instanceof HTMLInputElement ||
      element instanceof HTMLSelectElement ||
      element instanceof HTMLTextAreaElement ||
      element instanceof HTMLOptionElement
    ) {{
      if (element.disabled) return true;
    }}
    return element.getAttribute("aria-disabled") === "true";
  }};
  const textFor = (element) => {{
    const text = normalize(element.innerText || element.textContent || element.getAttribute("aria-label") || "");
    return text || null;
  }};
  const distance = (rectA, rectB) => {{
    if (!rectA || !rectB) return Infinity;
    const ax = rectA.left + rectA.width / 2;
    const ay = rectA.top + rectA.height / 2;
    const bx = rectB.left + rectB.width / 2;
    const by = rectB.top + rectB.height / 2;
    return Math.hypot(ax - bx, ay - by);
  }};
  const source = sourceSelector ? document.querySelector(sourceSelector) : null;
  const sourceScope = sourceScopeSelector ? document.querySelector(sourceScopeSelector) : null;
  const activeElement = document.activeElement instanceof Element ? document.activeElement : null;
  const sourceRect = source && typeof source.getBoundingClientRect === "function" ? source.getBoundingClientRect() : null;
  const sourceScopeRect = sourceScope && typeof sourceScope.getBoundingClientRect === "function" ? sourceScope.getBoundingClientRect() : null;
  const controlledIds = new Set(
    [source?.getAttribute?.("aria-controls"), source?.getAttribute?.("aria-owns")]
      .filter((value) => typeof value === "string")
      .flatMap((value) => String(value).split(/\\s+/).map((item) => item.trim()).filter(Boolean))
  );
  const collectCandidates = (overlay) => {{
    const seen = new Set();
    const resolved = [];
    optionSelectors.forEach((selector) => {{
      if (!selector) return;
      Array.from(overlay.querySelectorAll(selector)).forEach((element) => {{
        if (!(element instanceof Element)) return;
        if (!isVisible(element) || isDisabled(element)) return;
        const selectorValue = selectorFor(element);
        const text = textFor(element);
        const dedupeKey = selectorValue || `${{selector}}::${{text || ''}}`;
        if (seen.has(dedupeKey)) return;
        seen.add(dedupeKey);
        const matchesText = optionText
          ? (exact ? text === optionText : !!text && text.includes(optionText))
          : true;
        resolved.push({{
          selector: selectorValue,
          text,
          matchesText,
        }});
      }});
    }});
    return resolved;
  }};
  const inferOverlayKind = (overlay) => {{
    if (!(overlay instanceof Element)) return null;
    const role = normalize(overlay.getAttribute("role")).toLowerCase();
    const cls = normalize(overlay.className).toLowerCase();
    if (
      role === "listbox"
      || /autocomplete|select|cascader|suggest|listbox/.test(cls)
      || overlay.querySelector("[role='option'], .ant-select-item-option, .ant-cascader-menu-item")
    ) return "autocomplete";
    if (
      /picker|calendar|datepicker/.test(cls)
      || overlay.querySelector(".ant-picker-cell, [role='gridcell'], .calendar-day, .date, .day")
    ) return "datepicker";
    if (
      role === "menu"
      || /menu|dropdown/.test(cls)
      || overlay.querySelector("[role='menuitem']")
    ) return "menu";
    return null;
  }};
  const resolveOverlay = () => {{
    if (explicitOverlaySelector) {{
      const explicitOverlay = document.querySelector(explicitOverlaySelector);
      if (explicitOverlay instanceof Element && isVisible(explicitOverlay)) {{
        return {{ element: explicitOverlay, associationReason: "explicit-overlay-selector" }};
      }}
    }}
    const candidates = Array.from(document.querySelectorAll(overlaySelectors)).filter(isVisible);
    if (!candidates.length) return null;
    let best = null;
    let bestScore = -Infinity;
    let bestReason = "best-score";
    candidates.forEach((element, index) => {{
      let score = index;
      let reason = "best-score";
      const rect = typeof element.getBoundingClientRect === "function" ? element.getBoundingClientRect() : null;
      const elementId = normalize(element.getAttribute("id"));
      if (elementId && controlledIds.has(elementId)) {{
        score += 6000;
        reason = "aria-controls";
      }}
      if (activeElement && element.contains(activeElement)) {{
        score += 2500;
        if (reason === "best-score") reason = "active-element";
      }}
      if (sourceScope && (sourceScope.contains(element) || element.contains(sourceScope))) {{
        score += 1500;
        if (reason === "best-score") reason = "source-scope";
      }}
      if (sourceScopeRect && rect) {{
        score += Math.max(0, 550 - distance(sourceScopeRect, rect));
        if (reason === "best-score") reason = "source-scope-distance";
      }}
      if (sourceRect && rect) {{
        score += Math.max(0, 850 - distance(sourceRect, rect));
        if (reason === "best-score") reason = "source-distance";
      }}
      const candidateStats = collectCandidates(element);
      score += Math.min(candidateStats.length, 20) * 120;
      const matchedCount = candidateStats.filter((candidate) => candidate.matchesText).length;
      if (matchedCount) score += 1800 + matchedCount * 75;
      const inferredKind = inferOverlayKind(element);
      if (overlayKind && inferredKind === overlayKind) {{
        score += 3500;
        if (reason === "best-score") reason = "overlay-kind";
      }} else if (overlayKind && inferredKind && inferredKind !== overlayKind) {{
        score -= 1200;
      }}
      const cls = element.className || "";
      if (typeof cls === "string" && /autocomplete|picker|calendar-panel|datepicker|date-picker|time-picker|dropdown|popover|popup|modal|dialog|menu|select/i.test(cls)) {{
        score += 400;
      }}
      if (!activeOverlay && !explicitOverlaySelector && !sourceSelector && !sourceScopeSelector && matchedCount <= 0 && candidateStats.length <= 0) {{
        score -= 5000;
      }}
      if (score > bestScore) {{
        best = element;
        bestScore = score;
        bestReason = reason;
      }}
    }});
    if (!(best instanceof Element)) return null;
    if (activeOverlay && bestReason === "best-score") bestReason = "active-overlay";
    return {{ element: best, associationReason: bestReason }};
  }};
  const overlayResolution = resolveOverlay();
  if (!overlayResolution || !(overlayResolution.element instanceof Element) || !isVisible(overlayResolution.element)) {{
    return requireReady ? null : {{
      ready: false,
      overlaySelector: explicitOverlaySelector || null,
      candidateCount: 0,
      matchedCandidateCount: 0,
      candidatePreview: [],
      optionSelector: explicitOptionSelector || null,
      sourceBound: !!(sourceSelector || sourceScopeSelector),
      associationReason: overlayResolution?.associationReason || null,
      failureReason: "overlay-not-found",
    }};
  }}
  const overlay = overlayResolution.element;
  const candidates = collectCandidates(overlay);
  const matchedCandidates = candidates.filter((candidate) => candidate.matchesText);
  const candidatePreview = candidates
    .slice(0, 5)
    .map((candidate) => candidate.text || candidate.selector || null)
    .filter(Boolean);
  const diagnostics = {{
    ready: candidates.length > 0 && (!optionText || matchedCandidates.length > 0),
    overlaySelector: selectorFor(overlay) || explicitOverlaySelector || null,
    candidateCount: candidates.length,
    matchedCandidateCount: optionText ? matchedCandidates.length : candidates.length,
    readyVia: optionText ? "text-match" : "candidate-count",
    optionSelector: explicitOptionSelector || null,
    sourceBound: !!(sourceSelector || sourceScopeSelector),
    associationReason: overlayResolution.associationReason || null,
    candidatePreview,
    failureReason: null,
  }};
  if (!candidates.length) {{
    diagnostics.failureReason = "overlay-without-candidates";
    return requireReady ? null : diagnostics;
  }}
  if (optionText && !matchedCandidates.length) {{
    diagnostics.failureReason = "overlay-without-matching-candidates";
    return requireReady ? null : diagnostics;
  }}
  diagnostics.overlayKind = inferOverlayKind(overlay);
  return diagnostics;
}}
""".strip()
_DATEPICKER_PANEL_STATUS_EXPRESSION = f"""
/*{_DATEPICKER_PANEL_STATUS_MARKER}*/
(options) => {{
  const normalize = (value) => String(value || "").trim().replace(/\\s+/g, " ");
  const overlaySelector = normalize(options?.overlaySelector || "");
  if (!overlaySelector) return null;
  const overlay = document.querySelector(overlaySelector);
  if (!(overlay instanceof Element)) return null;
  const isVisible = (element) => {{
    if (!(element instanceof HTMLElement)) return true;
    if (element.hidden) return false;
    if (element.getAttribute("aria-hidden") === "true") return false;
    const style = window.getComputedStyle(element);
    if (!style) return true;
    if (style.display === "none") return false;
    if (style.visibility === "hidden" || style.visibility === "collapse") return false;
    if (Number(style.opacity || "1") === 0) return false;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }};
  const readText = (element) => normalize(
    element?.innerText || element?.textContent || element?.getAttribute?.("aria-label") || ""
  );
  let monthNode = null;
  const monthHeaderSelector = normalize(options?.monthHeaderSelector || "");
  if (monthHeaderSelector) {{
    monthNode = overlay.querySelector(monthHeaderSelector);
  }}
  if (!(monthNode instanceof Element)) {{
    monthNode = overlay.querySelector(
      "[role='heading'], .calendar-header, .month-header, .datepicker-header, .ui-datepicker-title, .ant-picker-header-view"
    );
  }}
  const limit = Math.max(1, Number(options?.limit || 7));
  const dayTexts = Array.from(
    overlay.querySelectorAll("button, [role='button'], [role='gridcell'], td, .calendar-day, .ant-picker-cell-inner, .day, .date")
  )
    .filter((candidate) => candidate instanceof Element && isVisible(candidate))
    .map((candidate) => readText(candidate))
    .filter((text) => /^\\d{{1,2}}$/.test(text));
  const dayPreview = dayTexts.slice(0, limit);
  const disabledDayCount = Array.from(
    overlay.querySelectorAll("button, [role='button'], [role='gridcell'], td, .calendar-day, .ant-picker-cell-inner, .day, .date")
  )
    .filter((candidate) => candidate instanceof Element && isVisible(candidate))
    .filter((candidate) => {{
      const cls = String(candidate.className || "");
      if (/disabled|unavailable|sold|outside|other-month|prev|next/i.test(cls)) return true;
      if (candidate instanceof HTMLButtonElement || candidate instanceof HTMLInputElement) {{
        if (candidate.disabled) return true;
      }}
      return candidate.getAttribute("aria-disabled") === "true";
    }})
    .length;
  return {{
    overlaySelector,
    currentMonthText: monthNode instanceof Element ? readText(monthNode) || null : null,
    dayPreview,
    dayCount: dayTexts.length,
    disabledDayCount,
  }};
}}
""".strip()
_DATEPICKER_DAY_ORDINAL_EXPRESSION = (
    f"/*{_DATEPICKER_DAY_ORDINAL_MARKER}*/\n"
    + """
(root, options) => {
  const scope = root instanceof Element ? root : document.body;
  const normalize = (value) => String(value || "").trim().replace(/\\s+/g, " ");
  const targetText = normalize(options?.text || "");
  const exact = !!options?.exact;
  const monthHeaderSelector = normalize(options?.monthHeaderSelector || "");
  const monthHeaderText = normalize(options?.monthHeaderText || "");
  const isVisible = (element) => {
    if (!(element instanceof HTMLElement)) return true;
    if (element.hidden) return false;
    if (element.getAttribute("aria-hidden") === "true") return false;
    const style = window.getComputedStyle(element);
    if (!style) return true;
    if (style.display === "none") return false;
    if (style.visibility === "hidden" || style.visibility === "collapse") return false;
    if (Number(style.opacity || "1") === 0) return false;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const readText = (element) => normalize(
    element?.innerText || element?.textContent || element?.getAttribute?.("aria-label") || ""
  );
  const isDisabled = (element) => {
    const cls = String(element.className || "");
    if (/disabled|unavailable|sold|outside|other-month|prev|next/i.test(cls)) return true;
    if (
      element instanceof HTMLButtonElement ||
      element instanceof HTMLInputElement ||
      element instanceof HTMLSelectElement ||
      element instanceof HTMLTextAreaElement
    ) {
      if (element.disabled) return true;
    }
    return element.getAttribute("aria-disabled") === "true";
  };
  const headerCandidates = [];
  if (monthHeaderSelector) {
    const bySelector = scope.querySelector(monthHeaderSelector);
    if (bySelector instanceof Element) headerCandidates.push(bySelector);
  }
  scope.querySelectorAll("[role='heading'], .calendar-header, .month-header, .datepicker-header, .ui-datepicker-title, .ant-picker-header-view")
    .forEach((candidate) => {
      if (!(candidate instanceof Element)) return;
      if (monthHeaderText && !readText(candidate).includes(monthHeaderText)) return;
      headerCandidates.push(candidate);
    });
  const header = headerCandidates[0] || null;
  const textCandidates = [];
  const pushCandidate = (element) => {
    if (!(element instanceof Element)) return;
    const candidateText = readText(element);
    if (!candidateText) return;
    if (exact ? candidateText !== targetText : !candidateText.includes(targetText)) return;
    textCandidates.push(element);
  };
  pushCandidate(scope);
  scope.querySelectorAll("*").forEach(pushCandidate);
  if (!textCandidates.length) return null;
  const containerScore = (candidate) => {
    if (!(header instanceof Element)) return 0;
    let score = 0;
    let current = header;
    let depthBoost = 1000;
    while (current && current !== scope && current instanceof Element) {
      if (current.contains(candidate)) {
        score = Math.max(score, depthBoost);
      }
      current = current.parentElement;
      depthBoost -= 120;
    }
    return score;
  };
  let bestOrdinal = 0;
  let bestScore = -Infinity;
  textCandidates.forEach((candidate, index) => {
    let score = 0;
    if (isVisible(candidate)) score += 1000;
    if (!isDisabled(candidate)) score += 800;
    score += containerScore(candidate);
    const role = normalize(candidate.getAttribute("role")).toLowerCase();
    const tag = normalize(candidate.tagName).toLowerCase();
    if (role === "button" || role === "gridcell") score += 200;
    if (tag === "button" || tag === "td") score += 100;
    if (score > bestScore) {
      bestScore = score;
      bestOrdinal = index;
    }
  });
  return bestOrdinal;
}
""".strip()
)

__all__ = (
    "_ACTIVE_OVERLAY_SELECTOR_EXPRESSION",
    "_ASSOCIATED_OVERLAY_SELECTOR_EXPRESSION",
    "_AUTOCOMPLETE_OVERLAY_STATUS_EXPRESSION",
    "_DATEPICKER_PANEL_STATUS_EXPRESSION",
    "_DATEPICKER_DAY_ORDINAL_EXPRESSION",
)
