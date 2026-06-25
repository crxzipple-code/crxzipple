"""Target, scrolling, and text-match browser-side JavaScript expressions."""

from __future__ import annotations

from .action_engine_script_markers import (
    _TARGET_INFO_MARKER,
    _TEXT_MATCH_ORDINAL_MARKER,
    _TEXT_MATCH_DETAILS_MARKER,
)

_TARGET_INFO_EXPRESSION = f"""
/*{_TARGET_INFO_MARKER}*/
(el) => {{
  const tag = el && el.tagName ? String(el.tagName).toLowerCase() : null;
  const explicitRole = el && el.getAttribute ? el.getAttribute("role") : null;
  const inputType = el && "type" in el && typeof el.type === "string" ? el.type.toLowerCase() : null;
  const contentEditable = !!(el && el.isContentEditable);
  const readOnly = !!(
    el
    && (
      (typeof el.readOnly === "boolean" && el.readOnly)
      || (el.getAttribute && el.getAttribute("readonly") !== null)
    )
  );
  const disabled = !!(
    el
    && (
      (typeof el.disabled === "boolean" && el.disabled)
      || (el.getAttribute && el.getAttribute("aria-disabled") === "true")
    )
  );
  const visible = !!(
    el
    && (
      !(el instanceof HTMLElement)
      || (
        !el.hidden
        && el.getAttribute("aria-hidden") !== "true"
        && (() => {{
          const style = window.getComputedStyle(el);
          if (!style) return true;
          if (style.display === "none") return false;
          if (style.visibility === "hidden" || style.visibility === "collapse") return false;
          if (style.pointerEvents === "none") return false;
          if (Number(style.opacity || "1") === 0) return false;
          const rect = el.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0;
        }})()
      )
    )
  );
  const focused = !!(el && document.activeElement === el);
  const value = el && "value" in el ? el.value : null;
  const checked = !!(
    el
    && (
      (typeof el.checked === "boolean" && el.checked)
      || (el.getAttribute && el.getAttribute("aria-checked") === "true")
    )
  );
  return {{
    tag,
    role: explicitRole ? String(explicitRole).toLowerCase() : null,
    type: inputType,
    contentEditable,
    readOnly,
    disabled,
    visible,
    focused,
    value,
    checked,
  }};
}}
""".strip()
_BROWSER_SCROLL_INTO_VIEW_EXPRESSION = """
(uid) => {
  const targetUid = String(uid || "").trim();
  if (!targetUid) {
    throw new Error("scroll-into-view requires uid");
  }
  const queue = [document.documentElement || document.body];
  const seen = new Set();
  while (queue.length) {
    const current = queue.shift();
    if (!(current instanceof Element) || seen.has(current)) continue;
    seen.add(current);
    if ((current.getAttribute("data-uid") || current.id || "").trim() === targetUid) {
      if (typeof current.scrollIntoView === "function") {
        current.scrollIntoView({ block: "center", inline: "nearest" });
      }
      return true;
    }
    queue.push(...Array.from(current.children));
  }
  return false;
}
""".strip()
_TEXT_MATCH_ORDINAL_EXPRESSION = f"""
/*{_TEXT_MATCH_ORDINAL_MARKER}*/
(root, options) => {{
  const scope = root instanceof Element ? root : document.body;
  const normalize = (value) => String(value || "").trim().replace(/\\s+/g, " ");
  const targetText = normalize(options?.text || "");
  const exact = !!options?.exact;
  const sourceSelector = typeof options?.sourceSelector === "string" ? options.sourceSelector.trim() : "";
  const sourceScopeSelector = typeof options?.sourceScopeSelector === "string" ? options.sourceScopeSelector.trim() : "";
  const source = sourceSelector ? document.querySelector(sourceSelector) : null;
  const sourceScope = sourceScopeSelector ? document.querySelector(sourceScopeSelector) : null;
  const sourceRect = source && typeof source.getBoundingClientRect === "function" ? source.getBoundingClientRect() : null;
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
  const interactiveScore = (element) => {{
    const explicitRole = normalize(element.getAttribute("role")).toLowerCase();
    const tag = normalize(element.tagName).toLowerCase();
    const highValueRoles = new Set(["button","checkbox","combobox","link","menuitem","option","radio","searchbox","switch","tab","textbox"]);
    const highValueTags = new Set(["a","button","input","select","textarea"]);
    let score = 0;
    if (highValueRoles.has(explicitRole)) score += 400;
    if (highValueTags.has(tag)) score += 250;
    if (element.getAttribute("contenteditable") === "true") score += 150;
    return score;
  }};
  const centerDistance = (rectA, rectB) => {{
    if (!rectA || !rectB) return 0;
    const ax = rectA.left + rectA.width / 2;
    const ay = rectA.top + rectA.height / 2;
    const bx = rectB.left + rectB.width / 2;
    const by = rectB.top + rectB.height / 2;
    return Math.hypot(ax - bx, ay - by);
  }};
  const candidates = [];
  const pushCandidate = (element) => {{
    if (!(element instanceof Element)) return;
    const candidateText = normalize(element.innerText || element.textContent || element.getAttribute("aria-label") || "");
    if (!candidateText) return;
    if (exact ? candidateText !== targetText : !candidateText.includes(targetText)) return;
    candidates.push(element);
  }};
  pushCandidate(scope);
  scope.querySelectorAll("*").forEach(pushCandidate);
  if (!candidates.length) return null;
  let bestOrdinal = 0;
  let bestScore = -Infinity;
  candidates.forEach((element, index) => {{
    let score = 0;
    if (isVisible(element)) score += 1000;
    if (!isDisabled(element)) score += 250;
    score += interactiveScore(element);
    if (
      sourceScope instanceof Element
      && (element === sourceScope || sourceScope.contains(element))
    ) {{
      score += 900;
    }}
    const rect = typeof element.getBoundingClientRect === "function" ? element.getBoundingClientRect() : null;
    if (sourceRect && rect) {{
      score += Math.max(0, 600 - centerDistance(sourceRect, rect));
    }}
    if (score > bestScore) {{
      bestScore = score;
      bestOrdinal = index;
    }}
  }});
  return bestOrdinal;
}}
""".strip()
_TEXT_MATCH_DETAILS_EXPRESSION = f"""
/*{_TEXT_MATCH_DETAILS_MARKER}*/
(root, options) => {{
  const scope = root instanceof Element ? root : document.body;
  const normalize = (value) => String(value || "").trim().replace(/\\s+/g, " ");
  const targetText = normalize(options?.text || "");
  const exact = !!options?.exact;
  const explicitOrdinal = Number.isInteger(options?.explicitOrdinal) ? Number(options.explicitOrdinal) : null;
  const sourceSelector = typeof options?.sourceSelector === "string" ? options.sourceSelector.trim() : "";
  const sourceScopeSelector = typeof options?.sourceScopeSelector === "string" ? options.sourceScopeSelector.trim() : "";
  const source = sourceSelector ? document.querySelector(sourceSelector) : null;
  const sourceScope = sourceScopeSelector ? document.querySelector(sourceScopeSelector) : null;
  const sourceRect = source && typeof source.getBoundingClientRect === "function" ? source.getBoundingClientRect() : null;
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
  const interactiveScore = (element) => {{
    const explicitRole = normalize(element.getAttribute("role")).toLowerCase();
    const tag = normalize(element.tagName).toLowerCase();
    const highValueRoles = new Set(["button","checkbox","combobox","link","menuitem","option","radio","searchbox","switch","tab","textbox"]);
    const highValueTags = new Set(["a","button","input","select","textarea"]);
    let score = 0;
    if (highValueRoles.has(explicitRole)) score += 400;
    if (highValueTags.has(tag)) score += 250;
    if (element.getAttribute("contenteditable") === "true") score += 150;
    return score;
  }};
  const centerDistance = (rectA, rectB) => {{
    if (!rectA || !rectB) return 0;
    const ax = rectA.left + rectA.width / 2;
    const ay = rectA.top + rectA.height / 2;
    const bx = rectB.left + rectB.width / 2;
    const by = rectB.top + rectB.height / 2;
    return Math.hypot(ax - bx, ay - by);
  }};
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
  const collectText = (element) => normalize(element.innerText || element.textContent || element.getAttribute("aria-label") || "");
  const candidates = [];
  const pushCandidate = (element) => {{
    if (!(element instanceof Element)) return;
    const candidateText = collectText(element);
    if (!candidateText) return;
    if (exact ? candidateText !== targetText : !candidateText.includes(targetText)) return;
    const rect = typeof element.getBoundingClientRect === "function" ? element.getBoundingClientRect() : null;
    const visible = isVisible(element);
    const disabled = isDisabled(element);
    const sameSourceScope = sourceScope instanceof Element && (element === sourceScope || sourceScope.contains(element));
    const distanceScore = sourceRect && rect ? Math.max(0, 600 - centerDistance(sourceRect, rect)) : 0;
    const iScore = interactiveScore(element);
    let score = 0;
    if (visible) score += 1000;
    if (!disabled) score += 250;
    if (sameSourceScope) score += 900;
    score += distanceScore;
    score += iScore;
    const reasonFlags = [];
    if (sameSourceScope) reasonFlags.push("same-source-scope");
    if (distanceScore > 0) reasonFlags.push("near-source");
    if (visible) reasonFlags.push("visible");
    if (!disabled) reasonFlags.push("enabled");
    if (iScore > 0) reasonFlags.push("interactive");
    candidates.push({{
      element,
      text: candidateText,
      selector: selectorFor(element),
      score,
      reasonFlags,
    }});
  }};
  pushCandidate(scope);
  scope.querySelectorAll("*").forEach(pushCandidate);
  if (!candidates.length) return null;
  const preview = candidates.slice(0, 5).map((candidate) => candidate.text || candidate.selector).filter(Boolean);
  let chosen = null;
  let chosenOrdinal = 0;
  if (explicitOrdinal !== null && explicitOrdinal >= 0 && explicitOrdinal < candidates.length) {{
    chosen = candidates[explicitOrdinal];
    chosenOrdinal = explicitOrdinal;
  }} else {{
    candidates.forEach((candidate, index) => {{
      if (chosen === null || candidate.score > chosen.score) {{
        chosen = candidate;
        chosenOrdinal = index;
      }}
    }});
  }}
  if (!chosen) return null;
  let reason = "text-match";
  if (explicitOrdinal !== null) reason = "explicit-ordinal";
  else if (chosen.reasonFlags.includes("same-source-scope")) reason = "same-source-scope";
  else if (chosen.reasonFlags.includes("near-source")) reason = "near-source";
  else if (chosen.reasonFlags.includes("interactive")) reason = "interactive";
  else if (chosen.reasonFlags.includes("visible")) reason = "visible";
  return {{
    ordinal: chosenOrdinal,
    candidateCount: candidates.length,
    chosenText: chosen.text || null,
    chosenSelector: chosen.selector || null,
    reason,
    reasonFlags: chosen.reasonFlags,
    candidatePreview: preview,
  }};
}}
""".strip()

__all__ = (
    "_TARGET_INFO_EXPRESSION",
    "_BROWSER_SCROLL_INTO_VIEW_EXPRESSION",
    "_TEXT_MATCH_ORDINAL_EXPRESSION",
    "_TEXT_MATCH_DETAILS_EXPRESSION",
)
