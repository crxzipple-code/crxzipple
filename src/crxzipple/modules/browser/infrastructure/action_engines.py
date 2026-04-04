from __future__ import annotations

import base64
import calendar
from dataclasses import replace
from dataclasses import dataclass
from fnmatch import fnmatch
import json
import re
import time
from typing import Any, Mapping

from crxzipple.modules.browser.domain import (
    BrowserActionFamily,
    BrowserActionResult,
    BrowserActionTarget,
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserProfileRuntimeState,
    BrowserStoredRef,
    BrowserTab,
    BrowserValidationError,
)
from crxzipple.modules.browser.domain.value_objects import _normalize_optional_text

from ..application.ports import BrowserActionEngine, BrowserRefStore
from .cdp_urls import browser_ref_to_cdp_http_base
from .chrome_mcp import ChromeMcpClientPool
from .playwright import PlaywrightCdpSessionPool
from .role_snapshot import (
    build_role_snapshot,
    describe_role_locator,
)

_LOCATOR_ACTION_KINDS = frozenset(
    {
        "click",
        "type",
        "press",
        "hover",
        "drag",
        "scroll-into-view",
        "select",
        "fill",
    }
)
_SUPPORTED_KINDS = frozenset(
    _LOCATOR_ACTION_KINDS
    | {
        "batch",
        "resize",
        "wait",
        "snapshot",
        "screenshot",
        "pdf",
        "evaluate",
    }
)
_MCP_SUPPORTED_KINDS = frozenset(
    {
        "click",
        "type",
        "press",
        "hover",
        "drag",
        "resize",
        "select",
        "fill",
        "wait",
        "snapshot",
        "screenshot",
        "evaluate",
    }
)
_MCP_TARGETED_KINDS = frozenset(
    {
        "click",
        "type",
        "hover",
        "drag",
        "select",
        "fill",
    }
)
_MCP_INTERACTIVE_ROLES = frozenset(
    {
        "button",
        "checkbox",
        "combobox",
        "link",
        "listbox",
        "menuitem",
        "option",
        "radio",
        "searchbox",
        "slider",
        "spinbutton",
        "switch",
        "tab",
        "textbox",
        "treeitem",
    }
)
_DEFAULT_INTERACTIVE_REF_LIMIT = 40
_DEFAULT_EFFICIENT_SNAPSHOT_DEPTH = 6
_DEFAULT_FOCUSED_LOCATOR_LIMIT = 80
_DEFAULT_BULK_SELECT_LIMIT = 50
_MAX_BATCH_ACTIONS = 100
_MAX_BATCH_DEPTH = 5
_RETRYABLE_TRANSIENT_ACTION_KINDS = frozenset(
    {
        "click",
        "type",
        "fill",
        "press",
        "hover",
        "scroll-into-view",
        "select",
        "wait",
        "snapshot",
        "evaluate",
    }
)
_HIGH_VALUE_INTERACTIVE_ROLES = frozenset(
    {
        "button",
        "checkbox",
        "combobox",
        "link",
        "menuitem",
        "option",
        "radio",
        "searchbox",
        "switch",
        "tab",
        "textbox",
    }
)
_HIGH_VALUE_INTERACTIVE_TAGS = frozenset(
    {
        "a",
        "button",
        "input",
        "select",
        "textarea",
    }
)
_INTERACTIVE_SNAPSHOT_MARKER = "__crxzipple_collect_interactive_refs__"
_ACTIVE_OVERLAY_MARKER = "__crxzipple_find_active_overlay__"
_ASSOCIATED_OVERLAY_MARKER = "__crxzipple_find_associated_overlay__"
_AUTOCOMPLETE_OVERLAY_STATUS_MARKER = "__crxzipple_collect_autocomplete_overlay_status__"
_DATEPICKER_PANEL_STATUS_MARKER = "__crxzipple_collect_datepicker_panel_status__"
_DATEPICKER_DAY_ORDINAL_MARKER = "__crxzipple_collect_datepicker_day_ordinal__"
_TARGET_INFO_MARKER = "__crxzipple_widget_target_info__"
_BULK_SELECTION_MARKER = "__crxzipple_collect_bulk_selection_candidates__"
_TEXT_MATCH_ORDINAL_MARKER = "__crxzipple_find_preferred_text_ordinal__"
_TEXT_MATCH_DETAILS_MARKER = "__crxzipple_collect_text_match_details__"
_INTERACTIVE_SNAPSHOT_EXPRESSION = f"""
(() => {{
  const {_INTERACTIVE_SNAPSHOT_MARKER} = true;
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
  const textFor = (element) => {{
    const text = (element.innerText || element.textContent || "").trim().replace(/\\s+/g, " ");
    return text || null;
  }};
  const labelFor = (element) => {{
    const aria = element.getAttribute("aria-label");
    if (aria && aria.trim()) return aria.trim();
    const labelledBy = element.getAttribute("aria-labelledby");
    if (labelledBy) {{
      const labels = labelledBy
        .split(/\\s+/)
        .map((id) => document.getElementById(id))
        .filter(Boolean)
        .map((node) => (node.innerText || node.textContent || "").trim())
        .filter(Boolean);
      if (labels.length) return labels.join(" ");
    }}
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement) {{
      if (element.labels && element.labels.length) {{
        const labels = Array.from(element.labels)
          .map((node) => (node.innerText || node.textContent || "").trim())
          .filter(Boolean);
        if (labels.length) return labels.join(" ");
      }}
      const placeholder = element.getAttribute("placeholder");
      if (placeholder && placeholder.trim()) return placeholder.trim();
      const name = element.getAttribute("name");
      if (name && name.trim()) return name.trim();
    }}
    return textFor(element);
  }};
  const roleFor = (element) => {{
    const explicit = element.getAttribute("role");
    if (explicit && explicit.trim()) return explicit.trim().toLowerCase();
    const tag = element.tagName.toLowerCase();
    if (tag === "button") return "button";
    if (tag === "a" && element.hasAttribute("href")) return "link";
    if (tag === "select") return "combobox";
    if (tag === "textarea") return "textbox";
    if (tag === "input") {{
      const type = (element.getAttribute("type") || "text").toLowerCase();
      if (type === "checkbox") return "checkbox";
      if (type === "radio") return "radio";
      if (type === "search") return "searchbox";
      if (type === "number") return "spinbutton";
      return "textbox";
    }}
    return null;
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
  const selector = [
    "a[href]",
    "button",
    "input",
    "select",
    "textarea",
    "[role='button']",
    "[role='link']",
    "[role='textbox']",
    "[role='checkbox']",
    "[role='radio']",
    "[tabindex]:not([tabindex='-1'])"
  ].join(",");
  const seen = new Set();
  return Array.from(document.querySelectorAll(selector)).map((element) => {{
    const css = selectorFor(element);
    if (!css || seen.has(css)) return null;
    seen.add(css);
    return {{
      selector: css,
      label: labelFor(element),
      role: roleFor(element),
      text: textFor(element),
      tag: element.tagName.toLowerCase(),
      visible: isVisible(element),
      disabled: isDisabled(element),
      checked: !!(
        (element instanceof HTMLInputElement && ["checkbox", "radio"].includes((element.type || "").toLowerCase()) && element.checked)
        || element.getAttribute("aria-checked") === "true"
      ),
    }};
  }}).filter(Boolean);
}})()
""".strip()
_BULK_SELECTION_EXPRESSION = f"""
/*{_BULK_SELECTION_MARKER}*/
(options) => {{
  const itemSelector = typeof options?.itemSelector === "string" && options.itemSelector.trim()
    ? options.itemSelector.trim()
    : "input[type='checkbox'],[role='checkbox']";
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
  const textFor = (element) => {{
    const text = (element.innerText || element.textContent || "").trim().replace(/\\s+/g, " ");
    return text || null;
  }};
  const labelFor = (element) => {{
    const aria = element.getAttribute("aria-label");
    if (aria && aria.trim()) return aria.trim();
    const labelledBy = element.getAttribute("aria-labelledby");
    if (labelledBy) {{
      const labels = labelledBy
        .split(/\\s+/)
        .map((id) => document.getElementById(id))
        .filter(Boolean)
        .map((node) => (node.innerText || node.textContent || "").trim())
        .filter(Boolean);
      if (labels.length) return labels.join(" ");
    }}
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement) {{
      if (element.labels && element.labels.length) {{
        const labels = Array.from(element.labels)
          .map((node) => (node.innerText || node.textContent || "").trim())
          .filter(Boolean);
        if (labels.length) return labels.join(" ");
      }}
      const placeholder = element.getAttribute("placeholder");
      if (placeholder && placeholder.trim()) return placeholder.trim();
      const name = element.getAttribute("name");
      if (name && name.trim()) return name.trim();
    }}
    return textFor(element);
  }};
  const roleFor = (element) => {{
    const explicit = element.getAttribute("role");
    if (explicit && explicit.trim()) return explicit.trim().toLowerCase();
    const tag = element.tagName.toLowerCase();
    if (tag === "button") return "button";
    if (tag === "a" && element.hasAttribute("href")) return "link";
    if (tag === "select") return "combobox";
    if (tag === "textarea") return "textbox";
    if (tag === "input") {{
      const type = (element.getAttribute("type") || "text").toLowerCase();
      if (type === "checkbox") return "checkbox";
      if (type === "radio") return "radio";
      if (type === "search") return "searchbox";
      if (type === "number") return "spinbutton";
      return "textbox";
    }}
    return null;
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
  const isChecked = (element) => {{
    if (element instanceof HTMLInputElement) {{
      const type = (element.type || "").toLowerCase();
      if (type === "checkbox" || type === "radio") {{
        return !!element.checked;
      }}
    }}
    return element.getAttribute("aria-checked") === "true";
  }};
  const seen = new Set();
  return Array.from(document.querySelectorAll(itemSelector)).map((element) => {{
    const css = selectorFor(element);
    if (!css || seen.has(css)) return null;
    seen.add(css);
    return {{
      selector: css,
      label: labelFor(element),
      role: roleFor(element),
      text: textFor(element),
      tag: element.tagName.toLowerCase(),
      visible: isVisible(element),
      disabled: isDisabled(element),
      checked: isChecked(element),
    }};
  }}).filter(Boolean);
}}
""".strip()
_BULK_SELECTION_DESCENDANTS_EXPRESSION = f"""
/*{_BULK_SELECTION_MARKER}*/
(root, options) => {{
  const itemSelector = typeof options?.itemSelector === "string" && options.itemSelector.trim()
    ? options.itemSelector.trim()
    : "input[type='checkbox'],[role='checkbox']";
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
  const textFor = (element) => {{
    const text = (element.innerText || element.textContent || "").trim().replace(/\\s+/g, " ");
    return text || null;
  }};
  const labelFor = (element) => {{
    const aria = element.getAttribute("aria-label");
    if (aria && aria.trim()) return aria.trim();
    const labelledBy = element.getAttribute("aria-labelledby");
    if (labelledBy) {{
      const labels = labelledBy
        .split(/\\s+/)
        .map((id) => document.getElementById(id))
        .filter(Boolean)
        .map((node) => (node.innerText || node.textContent || "").trim())
        .filter(Boolean);
      if (labels.length) return labels.join(" ");
    }}
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement) {{
      if (element.labels && element.labels.length) {{
        const labels = Array.from(element.labels)
          .map((node) => (node.innerText || node.textContent || "").trim())
          .filter(Boolean);
        if (labels.length) return labels.join(" ");
      }}
      const placeholder = element.getAttribute("placeholder");
      if (placeholder && placeholder.trim()) return placeholder.trim();
      const name = element.getAttribute("name");
      if (name && name.trim()) return name.trim();
    }}
    return textFor(element);
  }};
  const roleFor = (element) => {{
    const explicit = element.getAttribute("role");
    if (explicit && explicit.trim()) return explicit.trim().toLowerCase();
    const tag = element.tagName.toLowerCase();
    if (tag === "button") return "button";
    if (tag === "a" && element.hasAttribute("href")) return "link";
    if (tag === "select") return "combobox";
    if (tag === "textarea") return "textbox";
    if (tag === "input") {{
      const type = (element.getAttribute("type") || "text").toLowerCase();
      if (type === "checkbox") return "checkbox";
      if (type === "radio") return "radio";
      if (type === "search") return "searchbox";
      if (type === "number") return "spinbutton";
      return "textbox";
    }}
    return null;
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
  const isChecked = (element) => {{
    if (element instanceof HTMLInputElement) {{
      const type = (element.type || "").toLowerCase();
      if (type === "checkbox" || type === "radio") {{
        return !!element.checked;
      }}
    }}
    return element.getAttribute("aria-checked") === "true";
  }};
  const seen = new Set();
  const elements = [];
  if (root instanceof Element) {{
    if (root.matches(itemSelector)) {{
      elements.push(root);
    }}
    elements.push(...Array.from(root.querySelectorAll(itemSelector)));
  }}
  return elements.map((element) => {{
    const css = selectorFor(element);
    if (!css || seen.has(css)) return null;
    seen.add(css);
    return {{
      selector: css,
      label: labelFor(element),
      role: roleFor(element),
      text: textFor(element),
      tag: element.tagName.toLowerCase(),
      visible: isVisible(element),
      disabled: isDisabled(element),
      checked: isChecked(element),
    }};
  }}).filter(Boolean);
}}
""".strip()
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
      if (/dropdown|popover|popup|modal|dialog|menu|autocomplete|picker|select/i.test(cls)) total += 1200;
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
    "[role='dialog'],[role='alertdialog'],[role='listbox'],[role='menu'],[role='tooltip'],[role='tree'],[role='grid'],.ant-select-dropdown,.ant-picker-dropdown,.ant-dropdown,.ant-popover,.ant-modal,.autocomplete,.city-autocomplete-list,.popup,.modal,.menu,.dropdown"
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
    "[role='dialog'],[role='alertdialog'],[role='listbox'],[role='menu'],[role='tooltip'],[role='tree'],[role='grid'],.ant-select-dropdown,.ant-picker-dropdown,.ant-dropdown,.ant-popover,.ant-modal,.autocomplete,.city-autocomplete-list,.popup,.modal,.menu,.dropdown"
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
    if (typeof cls === "string" && /autocomplete|picker|dropdown|popover|popup|modal|dialog|menu|select/i.test(cls)) {{
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
      if (typeof cls === "string" && /autocomplete|picker|dropdown|popover|popup|modal|dialog|menu|select/i.test(cls)) {{
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


def _timeout_ms(command: BrowserPageActionCommand) -> float | None:
    if command.timeout_ms is None:
        return None
    return float(command.timeout_ms)


def _timeout_kwargs(timeout: float | None) -> dict[str, float]:
    if timeout is None:
        return {}
    return {"timeout": timeout}


def _probe_timeout(timeout: float | None, *, ceiling_ms: float = 2_000.0) -> float:
    if timeout is None:
        return ceiling_ms
    return min(timeout, ceiling_ms)


def _is_pointer_interception_error(exc: Exception) -> bool:
    message = str(exc).lower()
    markers = (
        "intercepts pointer events",
        "subtree intercepts pointer events",
        "receives pointer events",
        "would receive pointer events",
        "would receive the click",
        "another element",
    )
    return any(marker in message for marker in markers)


def _payload_text(
    payload: Mapping[str, Any],
    *,
    key: str,
    required: bool = True,
) -> str | None:
    value = payload.get(key)
    if value is None:
        if required:
            raise BrowserValidationError(f"payload.{key} is required.")
        return None
    if not isinstance(value, str) or not value.strip():
        if required:
            raise BrowserValidationError(f"payload.{key} is required.")
        return None
    return value.strip()


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


def _payload_number_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> float | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
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


def _normalize_batch_kind(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BrowserValidationError("batch actions require kind.")
    normalized = value.strip().lower()
    if normalized == "scrollintoview":
        return "scroll-into-view"
    return normalized


def _coerce_batch_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _batch_action_timeout_ms(raw: Mapping[str, Any], inherited_timeout_ms: int | None) -> int | None:
    value = _payload_value_any(raw, "timeout_ms", "timeoutMs")
    if value is None:
        return inherited_timeout_ms
    if isinstance(value, bool):
        raise BrowserValidationError("batch action timeout_ms must be an integer.")
    if not isinstance(value, (int, float)):
        raise BrowserValidationError("batch action timeout_ms must be an integer.")
    resolved = int(value)
    if resolved < 1:
        raise BrowserValidationError("batch action timeout_ms must be greater than or equal to 1.")
    return resolved


def _count_batch_actions(actions: Any) -> int:
    if not isinstance(actions, (list, tuple)):
        return 0
    count = 0
    for raw_action in actions:
        if not isinstance(raw_action, Mapping):
            continue
        count += 1
        if _normalize_batch_kind(raw_action.get("kind")) == "batch":
            count += _count_batch_actions(raw_action.get("actions"))
    return count


def _normalize_batch_action(
    *,
    raw_action: Mapping[str, Any],
    profile_name: str,
    inherited_target_id: str | None,
    inherited_timeout_ms: int | None,
    depth: int,
) -> BrowserPageActionCommand:
    if depth > _MAX_BATCH_DEPTH:
        raise BrowserValidationError(
            f"Batch nesting depth exceeds maximum of {_MAX_BATCH_DEPTH}.",
        )
    kind = _normalize_batch_kind(raw_action.get("kind"))
    if kind not in _SUPPORTED_KINDS:
        raise BrowserValidationError(f"Unsupported batch action kind '{kind}'.")

    target_id = _payload_text_any(raw_action, "target_id", "targetId")
    if inherited_target_id is not None and target_id is not None and target_id != inherited_target_id:
        raise BrowserValidationError("batched action target_id must match request target_id.")
    effective_target_id = target_id or inherited_target_id
    payload = _coerce_batch_payload(raw_action.get("payload"))

    if kind == "batch":
        nested_actions = raw_action.get("actions")
        if not isinstance(nested_actions, (list, tuple)) or not nested_actions:
            raise BrowserValidationError("batch requires actions.")
        payload.setdefault("actions", list(nested_actions))
        stop_on_error = _payload_value_any(raw_action, "stop_on_error", "stopOnError")
        if isinstance(stop_on_error, bool):
            payload.setdefault("stop_on_error", stop_on_error)
        return BrowserPageActionCommand(
            profile_name=profile_name,
            kind="batch",
            target=BrowserActionTarget(target_id=effective_target_id),
            payload=payload,
            timeout_ms=_batch_action_timeout_ms(raw_action, inherited_timeout_ms),
        )

    ref = _payload_text_any(raw_action, "ref")
    selector = _payload_text_any(raw_action, "selector")

    for key, payload_keys in (
        ("text", ("text",)),
        ("date", ("date",)),
        ("query", ("query",)),
        ("command_text", ("command_text", "commandText")),
        ("command_ref", ("command_ref", "commandRef")),
        ("command_selector", ("command_selector", "commandSelector")),
        ("toolbar_ref", ("toolbar_ref", "toolbarRef")),
        ("toolbar_selector", ("toolbar_selector", "toolbarSelector")),
        ("option_text", ("option_text", "optionText")),
        ("option_ref", ("option_ref", "optionRef")),
        ("option_selector", ("option_selector", "optionSelector")),
        ("overlay_selector", ("overlay_selector", "overlaySelector")),
        ("overlay_text", ("overlay_text", "overlayText")),
        ("input_mode", ("input_mode", "inputMode")),
        ("select_via", ("select_via", "selectVia")),
        ("navigate_key", ("navigate_key", "navigateKey")),
        ("confirm_key", ("confirm_key", "confirmKey")),
        ("month_direction", ("month_direction", "monthDirection")),
        ("next_month_ref", ("next_month_ref", "nextMonthRef")),
        ("next_month_selector", ("next_month_selector", "nextMonthSelector")),
        ("prev_month_ref", ("prev_month_ref", "prevMonthRef")),
        ("prev_month_selector", ("prev_month_selector", "prevMonthSelector")),
        ("trigger", ("trigger",)),
        ("key", ("key",)),
        ("button", ("button",)),
        ("value", ("value",)),
        ("expression", ("expression",)),
        ("fn", ("fn",)),
        ("url", ("url",)),
        ("state", ("state",)),
        ("load_state", ("load_state", "loadState")),
        ("text_gone", ("text_gone", "textGone")),
        ("frame_selector", ("frame_selector", "frameSelector")),
        ("refs_mode", ("refs_mode", "refsMode")),
        ("mode", ("mode",)),
        ("type", ("type",)),
        ("start_ref", ("start_ref", "startRef")),
        ("start_selector", ("start_selector", "startSelector")),
        ("end_ref", ("end_ref", "endRef")),
        ("end_selector", ("end_selector", "endSelector")),
        ("target_ref", ("target_ref",)),
        ("target_selector", ("target_selector",)),
        ("scope_ref", ("scope_ref", "scopeRef")),
        ("scope_selector", ("scope_selector", "scopeSelector")),
        ("to_ref", ("to_ref",)),
        ("to_selector", ("to_selector",)),
    ):
        value = _payload_value_any(raw_action, *payload_keys)
        if value is not None:
            payload.setdefault(key, value)

    for key, payload_keys in (
        ("double_click", ("double_click", "doubleClick")),
        ("compact", ("compact",)),
        ("full_page", ("full_page", "fullPage")),
        ("print_background", ("print_background", "printBackground")),
        ("active_overlay", ("active_overlay", "activeOverlay")),
        ("exact", ("exact",)),
        ("clear_existing", ("clear_existing", "clearExisting")),
        ("open_first", ("open_first", "openFirst")),
        ("open_picker", ("open_picker", "openPicker")),
    ):
        value = _payload_value_any(raw_action, *payload_keys)
        if isinstance(value, bool):
            payload.setdefault(key, value)

    for key, payload_keys in (
        ("delay_ms", ("delay_ms", "delayMs")),
        ("time_ms", ("time_ms", "timeMs")),
        ("depth", ("depth",)),
        ("limit", ("limit",)),
        ("width", ("width",)),
        ("height", ("height",)),
        ("option_steps", ("option_steps", "optionSteps")),
        ("advance_months", ("advance_months", "advanceMonths")),
    ):
        value = _payload_value_any(raw_action, *payload_keys)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            payload.setdefault(key, int(value))

    if "arg" in raw_action:
        payload.setdefault("arg", raw_action.get("arg"))
    if isinstance(raw_action.get("args"), list):
        payload.setdefault("args", list(raw_action["args"]))
    if isinstance(raw_action.get("values"), (list, tuple)):
        payload.setdefault("values", list(raw_action["values"]))
    if isinstance(raw_action.get("fields"), (list, tuple)):
        payload.setdefault("fields", list(raw_action["fields"]))

    return BrowserPageActionCommand(
        profile_name=profile_name,
        kind=kind,
        target=BrowserActionTarget(
            target_id=effective_target_id,
            ref=ref,
            selector=selector,
        ),
        payload=payload,
        timeout_ms=_batch_action_timeout_ms(raw_action, inherited_timeout_ms),
    )


def _drag_source_ref(command: BrowserPageActionCommand) -> str | None:
    return command.target.ref or _payload_text_any(
        command.payload,
        "start_ref",
        "startRef",
    )


def _drag_source_selector(command: BrowserPageActionCommand) -> str | None:
    return command.target.selector or _payload_text_any(
        command.payload,
        "start_selector",
        "startSelector",
    )


def _drag_target_ref(payload: Mapping[str, Any]) -> str | None:
    return _payload_text_any(
        payload,
        "end_ref",
        "endRef",
        "target_ref",
        "to_ref",
    )


def _drag_target_selector(payload: Mapping[str, Any]) -> str | None:
    return _payload_text_any(
        payload,
        "end_selector",
        "endSelector",
        "target_selector",
        "to_selector",
    )


def _serialize_tab(tab: BrowserTab) -> dict[str, Any]:
    return {
        "target_id": tab.target_id,
        "url": tab.url,
        "title": tab.title,
        "type": tab.type,
        "ws_url": tab.ws_url,
        "json_endpoints": dict(tab.json_endpoints) if tab.json_endpoints else None,
    }


def _serialize_frame_path(frame_path: tuple[int, ...] | None) -> list[int] | None:
    if frame_path is None:
        return None
    return list(frame_path)


def _combine_frame_snapshots(
    frames: list[dict[str, Any]],
    *,
    key: str = "snapshot",
) -> str:
    if not frames:
        return "(empty)"
    if len(frames) == 1:
        value = frames[0].get(key)
        return str(value or "(empty)")
    chunks: list[str] = []
    for frame in frames:
        frame_path = frame.get("frame_path")
        snapshot = str(frame.get(key) or "(empty)")
        if isinstance(frame_path, list) and frame_path:
            label = f"frame {frame_path}"
        else:
            label = "main frame"
        chunks.append(f"[{label}]\n{snapshot}")
    return "\n\n".join(chunks)


def _role_snapshot_stats(
    *,
    snapshot: str,
    refs: tuple[BrowserStoredRef, ...],
) -> dict[str, int]:
    interactive_refs = sum(
        1
        for ref in refs
        if str(ref.role or "").strip().lower() in _HIGH_VALUE_INTERACTIVE_ROLES | _MCP_INTERACTIVE_ROLES
    )
    return {
        "lines": len(str(snapshot).splitlines()),
        "chars": len(str(snapshot)),
        "refs": len(refs),
        "interactive": interactive_refs,
    }


def _normalize_snapshot_node(node: Any) -> dict[str, Any] | None:
    if not isinstance(node, dict):
        return None
    return dict(node)


def _normalize_text_payload(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, (list, tuple)):
        resolved: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                resolved.append(item.strip())
        return resolved
    return []


def _normalize_form_fields(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        ref = _payload_text_any(item, "ref")
        if ref is None:
            continue
        field_type = _payload_text_any(item, "type") or "text"
        raw_value = _payload_value_any(item, "value")
        if isinstance(raw_value, (str, int, float, bool)) and not isinstance(raw_value, bool):
            value_payload: Any = str(raw_value)
        elif isinstance(raw_value, bool):
            value_payload = raw_value
        elif raw_value is None:
            value_payload = ""
        else:
            continue
        normalized.append(
            {
                "ref": ref,
                "type": field_type.strip().lower() or "text",
                "value": value_payload,
            }
        )
    return tuple(normalized)


def _interactive_snapshot_limit(
    payload: Mapping[str, Any],
    snapshot_format: str,
    limit: Any,
) -> int | None:
    if isinstance(limit, int) and limit > 0:
        return limit
    if snapshot_format == "interactive":
        mode = _snapshot_mode(payload, snapshot_format=snapshot_format)
        if mode == "focused":
            return _DEFAULT_FOCUSED_LOCATOR_LIMIT
        if mode == "wide":
            return None
        return _DEFAULT_INTERACTIVE_REF_LIMIT
    return None


def _interactive_role_snapshot_is_too_sparse(
    *,
    snapshot_mode: str | None,
    root_selector: str | None,
    ref_count: int,
) -> bool:
    if ref_count > 1:
        return False
    if _normalize_optional_text(root_selector) is not None:
        return True
    return snapshot_mode == "focused"


def _is_frame_detached_error(exc: Exception) -> bool:
    message = str(exc).strip().lower()
    return "frame was detached" in message


def _is_transient_page_context_error(exc: Exception) -> bool:
    message = str(exc).strip().lower()
    return (
        "frame was detached" in message
        or "execution context was destroyed" in message
        or "cannot find context with specified id" in message
        or "most likely because of a navigation" in message
    )


def _requested_snapshot_mode(payload: Mapping[str, Any]) -> str | None:
    mode = payload.get("mode")
    if not isinstance(mode, str):
        return None
    normalized = mode.strip().lower()
    return normalized or None


def _snapshot_refs_mode(payload: Mapping[str, Any]) -> str | None:
    refs_mode = payload.get("refs_mode")
    if refs_mode is None:
        refs_mode = payload.get("refsMode")
    if not isinstance(refs_mode, str):
        return None
    normalized = refs_mode.strip().lower()
    if not normalized:
        return None
    if normalized not in {"role", "aria"}:
        raise BrowserValidationError("payload.refs_mode must be either 'role' or 'aria'.")
    return normalized


def _snapshot_frame_selector(payload: Mapping[str, Any]) -> str | None:
    frame_selector = payload.get("frame_selector")
    if frame_selector is None:
        frame_selector = payload.get("frameSelector")
    if not isinstance(frame_selector, str):
        return None
    normalized = frame_selector.strip()
    return normalized or None


def _requested_snapshot_format(payload: Mapping[str, Any]) -> str | None:
    requested = payload.get("format")
    if not isinstance(requested, str):
        return None
    normalized = requested.strip().lower()
    return normalized or None


def _resolve_snapshot_format(payload: Mapping[str, Any]) -> str:
    requested_format = _requested_snapshot_format(payload)
    refs_mode = _snapshot_refs_mode(payload)
    if refs_mode is None:
        return requested_format or "html"
    if requested_format is None:
        return refs_mode
    if requested_format in {"role", "aria"}:
        if requested_format != refs_mode:
            raise BrowserValidationError(
                "payload.refs_mode must match payload.format when using role or aria snapshots.",
            )
        return requested_format
    raise BrowserValidationError(
        "payload.refs_mode can only be used when payload.format is omitted or set to 'role'/'aria'.",
    )


def _snapshot_mode(payload: Mapping[str, Any], *, snapshot_format: str) -> str | None:
    requested = _requested_snapshot_mode(payload)
    if requested is not None:
        if snapshot_format == "interactive" and requested not in {"efficient", "focused", "wide"}:
            raise BrowserValidationError(
                "payload.mode for interactive snapshots must be 'efficient', 'focused', or 'wide'.",
            )
        return requested
    if snapshot_format == "interactive" and "compact" not in payload and "depth" not in payload:
        return "efficient"
    return None

def _snapshot_compact(payload: Mapping[str, Any], *, snapshot_format: str) -> bool:
    compact = payload.get("compact")
    if isinstance(compact, bool):
        return compact
    return _snapshot_mode(payload, snapshot_format=snapshot_format) == "efficient"


def _snapshot_depth(payload: Mapping[str, Any], *, snapshot_format: str) -> int | None:
    depth = payload.get("depth")
    if isinstance(depth, int) and depth >= 0:
        return depth
    if _snapshot_mode(payload, snapshot_format=snapshot_format) == "efficient":
        return _DEFAULT_EFFICIENT_SNAPSHOT_DEPTH
    return None


def _snapshot_item_visible(item: Mapping[str, Any]) -> bool:
    visible = item.get("visible")
    if isinstance(visible, bool):
        return visible
    return True


def _snapshot_item_disabled(item: Mapping[str, Any]) -> bool:
    disabled = item.get("disabled")
    if isinstance(disabled, bool):
        return disabled
    return False


def _snapshot_item_priority(item: Mapping[str, Any]) -> int:
    score = 0
    role = str(item.get("role") or "").strip().lower()
    tag = str(item.get("tag") or "").strip().lower()
    label = str(item.get("label") or "").strip()
    text = str(item.get("text") or "").strip()
    selector = str(item.get("selector") or "").strip()
    if role in _HIGH_VALUE_INTERACTIVE_ROLES:
        score += 3
    if tag in _HIGH_VALUE_INTERACTIVE_TAGS:
        score += 2
    if label:
        score += 2
    if text:
        score += 1
    if selector.startswith("#"):
        score += 1
    return score


def _is_low_value_interactive_name(name: str | None) -> bool:
    normalized = _normalize_optional_text(name)
    if normalized is None:
        return False
    lowered = normalized.lower()
    return lowered in {
        "skip to content",
        "skip to main content",
        "skip navigation",
        "skip to navigation",
    }


def _snapshot_item_is_low_value_boilerplate(item: Mapping[str, Any]) -> bool:
    role = str(item.get("role") or "").strip().lower()
    if role != "link":
        return False
    return _is_low_value_interactive_name(
        str(item.get("label") or item.get("text") or "").strip() or None,
    )


def _snapshot_item_semantic_key(item: Mapping[str, Any]) -> tuple[str, str] | None:
    role = str(item.get("role") or "").strip().lower()
    name = str(item.get("label") or item.get("text") or "").strip()
    if not role or not name:
        return None
    return role, name


def _main_frame(page):  # noqa: ANN001
    return getattr(page, "main_frame", page)


def _child_frames(frame) -> tuple[Any, ...]:  # noqa: ANN001
    frames = getattr(frame, "child_frames", ())
    if not frames:
        return ()
    return tuple(frames)


def _iter_frame_contexts(page) -> tuple[tuple[Any, tuple[int, ...]], ...]:  # noqa: ANN001
    resolved: list[tuple[Any, tuple[int, ...]]] = []

    def _visit(frame, frame_path: tuple[int, ...]) -> None:  # noqa: ANN001
        resolved.append((frame, frame_path))
        for child_index, child in enumerate(_child_frames(frame)):
            _visit(child, frame_path + (child_index,))

    _visit(_main_frame(page), ())
    return tuple(resolved)


def _resolve_frame_context(page, frame_path: tuple[int, ...]):  # noqa: ANN001
    frame = _main_frame(page)
    for index in frame_path:
        children = _child_frames(frame)
        if index >= len(children):
            raise BrowserValidationError(
                f"Browser ref frame path {list(frame_path)} is no longer available.",
            )
        frame = children[index]
    return frame


def _resolve_frame_from_selector(page, frame_selector: str):  # noqa: ANN001
    resolver = getattr(page, "resolve_frame_selector", None)
    if callable(resolver):
        frame = resolver(frame_selector)
        if frame is None:
            raise BrowserValidationError(
                f"Browser snapshot frame selector '{frame_selector}' did not resolve to a frame.",
            )
        return frame

    locator = page.locator(frame_selector)
    element_handle = locator.element_handle(**_timeout_kwargs(_probe_timeout(None)))
    if element_handle is None:
        raise BrowserValidationError(
            f"Browser snapshot frame selector '{frame_selector}' did not resolve to an iframe or frame element.",
        )
    content_frame = getattr(element_handle, "content_frame", None)
    if not callable(content_frame):
        raise BrowserValidationError(
            f"Browser snapshot frame selector '{frame_selector}' did not resolve to an iframe or frame element.",
        )
    frame = content_frame()
    if frame is None:
        raise BrowserValidationError(
            f"Browser snapshot frame selector '{frame_selector}' did not resolve to a frame.",
        )
    return frame


def _snapshot_frame_contexts(
    page,
    *,
    frame_selector: str | None,
) -> tuple[tuple[Any, tuple[int, ...]], ...]:  # noqa: ANN001
    resolved = _iter_frame_contexts(page)
    if frame_selector is None:
        return resolved
    selected_frame = _resolve_frame_from_selector(page, frame_selector)
    selected_path: tuple[int, ...] | None = None
    for frame, frame_path in resolved:
        if frame is selected_frame:
            selected_path = frame_path
            break
    if selected_path is None:
        raise BrowserValidationError(
            f"Browser snapshot frame selector '{frame_selector}' did not match a reachable frame.",
        )
    return tuple(
        (frame, frame_path)
        for frame, frame_path in resolved
        if frame_path[: len(selected_path)] == selected_path
    )


def _snapshot_root_contexts(
    page,
    *,
    frame_selector: str | None,
    root_selector: str | None,
) -> tuple[tuple[Any, tuple[int, ...]], ...]:  # noqa: ANN001
    if root_selector is None:
        return _snapshot_frame_contexts(page, frame_selector=frame_selector)
    if frame_selector is not None:
        scoped = _snapshot_frame_contexts(page, frame_selector=frame_selector)
        if not scoped:
            return ()
        return (scoped[0],)
    return ((_main_frame(page), ()),)


def _snapshot_root_locator(context, *, root_selector: str | None):  # noqa: ANN001
    return context.locator(root_selector or "body")


def _active_overlay_selector(page) -> str | None:  # noqa: ANN001
    resolver = getattr(page, "resolve_active_overlay_selector", None)
    if callable(resolver):
        resolved = resolver()
        if isinstance(resolved, str) and resolved.strip():
            return resolved.strip()
        return None
    evaluate = getattr(page, "evaluate", None)
    if not callable(evaluate):
        return None
    try:
        resolved = evaluate(_ACTIVE_OVERLAY_SELECTOR_EXPRESSION)
    except Exception:  # noqa: BLE001
        return None
    if isinstance(resolved, str) and resolved.strip():
        return resolved.strip()
    return None


def _associated_overlay_selector(  # noqa: ANN001
    page,
    *,
    overlay_kind: str | None = None,
    source_selector: str | None = None,
    source_scope_selector: str | None = None,
) -> str | None:
    resolver = getattr(page, "resolve_associated_overlay_selector", None)
    if callable(resolver):
        resolved = resolver(
            overlay_kind=overlay_kind,
            source_selector=source_selector,
            source_scope_selector=source_scope_selector,
        )
        if isinstance(resolved, str) and resolved.strip():
            return resolved.strip()
        return None
    evaluate = getattr(page, "evaluate", None)
    if not callable(evaluate):
        return None
    try:
        resolved = evaluate(
            _ASSOCIATED_OVERLAY_SELECTOR_EXPRESSION,
            {
                "overlayKind": _normalize_optional_text(overlay_kind),
                "sourceSelector": _normalize_optional_text(source_selector),
                "sourceScopeSelector": _normalize_optional_text(source_scope_selector),
            },
        )
    except Exception:  # noqa: BLE001
        return None
    if isinstance(resolved, str) and resolved.strip():
        return resolved.strip()
    return None


def _command_overlay_source_refs(command: BrowserPageActionCommand) -> tuple[str, ...]:
    candidates: list[str] = []
    overlay_source_ref = _payload_text_any(
        command.payload,
        "overlay_source_ref",
        "overlaySourceRef",
    )
    if overlay_source_ref is not None:
        candidates.append(overlay_source_ref)
    if command.target.ref is not None:
        candidates.append(command.target.ref)
    scope_ref = _scope_ref_id(command.payload)
    if scope_ref is not None:
        candidates.append(scope_ref)
    seen: set[str] = set()
    resolved: list[str] = []
    for candidate in candidates:
        normalized = str(candidate).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        resolved.append(normalized)
    return tuple(resolved)


def _command_overlay_source_selectors(
    command: BrowserPageActionCommand,
    *,
    resolved_selector: str | None = None,
) -> tuple[str, ...]:
    candidates: list[str] = []
    overlay_source_selector = _payload_text_any(
        command.payload,
        "overlay_source_selector",
        "overlaySourceSelector",
    )
    if overlay_source_selector is not None:
        candidates.append(overlay_source_selector)
    if resolved_selector is not None and ">>" not in resolved_selector:
        candidates.append(resolved_selector)
    if command.target.selector is not None:
        candidates.append(command.target.selector)
    scope_selector = _scope_selector(command.payload)
    if scope_selector is not None:
        candidates.append(scope_selector)
    seen: set[str] = set()
    resolved: list[str] = []
    for candidate in candidates:
        normalized = str(candidate).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        resolved.append(normalized)
    return tuple(resolved)


def _command_overlay_source_scope_selectors(
    command: BrowserPageActionCommand,
) -> tuple[str, ...]:
    candidates: list[str] = []
    explicit_scope_selector = _payload_text_any(
        command.payload,
        "overlay_source_scope_selector",
        "overlaySourceScopeSelector",
    )
    if explicit_scope_selector is not None:
        candidates.append(explicit_scope_selector)
    scope_selector = _scope_selector(command.payload)
    if scope_selector is not None:
        candidates.append(scope_selector)
    seen: set[str] = set()
    resolved: list[str] = []
    for candidate in candidates:
        normalized = str(candidate).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        resolved.append(normalized)
    return tuple(resolved)


def _effective_root_selector(
    *,
    page,
    runtime_state: BrowserProfileRuntimeState,
    tab: BrowserTab,
    payload: Mapping[str, Any],
    root_selector: str | None,
) -> str | None:  # noqa: ANN001
    if root_selector is not None:
        return root_selector
    if not _active_overlay(payload):
        return None
    return runtime_state.active_overlay_selector(
        target_id=tab.target_id,
        source_refs=tuple(
            normalized
            for normalized in (
                _payload_text_any(payload, "overlay_source_ref", "overlaySourceRef"),
            )
            if normalized is not None
        ),
        source_selectors=tuple(
            normalized
            for normalized in (
                _payload_text_any(payload, "overlay_source_selector", "overlaySourceSelector"),
            )
            if normalized is not None
        ),
        source_scope_selectors=tuple(
            normalized
            for normalized in (
                _payload_text_any(
                    payload,
                    "overlay_source_scope_selector",
                    "overlaySourceScopeSelector",
                ),
                _scope_selector(payload),
            )
            if normalized is not None
        ),
    ) or _active_overlay_selector(page)


def _stored_ref_name(item: BrowserStoredRef) -> str | None:
    return item.label or item.text


def _scope_ref_id(payload: Mapping[str, Any]) -> str | None:
    return _payload_text_any(payload, "scope_ref", "scopeRef")


def _scope_selector(payload: Mapping[str, Any]) -> str | None:
    return _payload_text_any(payload, "scope_selector", "scopeSelector")


def _locator_ordinal(payload: Mapping[str, Any]) -> int | None:
    return _payload_int_any(payload, "ordinal", minimum=0)


def _locator_exact(payload: Mapping[str, Any]) -> bool:
    exact = _payload_bool_any(payload, "exact")
    return bool(exact)


def _active_overlay(payload: Mapping[str, Any]) -> bool:
    active_overlay = _payload_bool_any(payload, "active_overlay", "activeOverlay")
    return bool(active_overlay)


def _allows_implicit_selector_ordinal(command: BrowserPageActionCommand) -> bool:
    return command.kind in {"fill", "type", "wait", "select", "press"}


def _explicit_overlay_kind(payload: Mapping[str, Any]) -> str | None:
    return _payload_text_any(payload, "overlay_kind", "overlayKind")


def _wait_prefers_active_overlay(command: BrowserPageActionCommand) -> bool:
    if command.kind != "wait":
        return False
    if command.target.ref is not None or command.target.selector is not None:
        return False
    if _scope_ref_id(command.payload) is not None or _scope_selector(command.payload) is not None:
        return False
    return bool(
        _payload_value_any(command.payload, "text", "text_gone", "textGone") is not None,
    )


def _bulk_select_limit(payload: Mapping[str, Any]) -> int:
    limit = _payload_int_any(payload, "limit", minimum=1)
    if limit is None:
        return _DEFAULT_BULK_SELECT_LIMIT
    return limit


def _bulk_select_checked(payload: Mapping[str, Any]) -> bool:
    checked = _payload_bool_any(payload, "checked")
    if checked is None:
        return True
    return checked


def _bulk_skip_already_selected(payload: Mapping[str, Any]) -> bool:
    skip_already = _payload_bool_any(
        payload,
        "skip_already_selected",
        "skipAlreadySelected",
    )
    if skip_already is None:
        return True
    return skip_already


def _bulk_allow_zero_selection(payload: Mapping[str, Any]) -> bool:
    allow_zero = _payload_bool_any(
        payload,
        "allow_zero_selection",
        "allowZeroSelection",
    )
    return bool(allow_zero)


@dataclass(slots=True)
class CdpBackedPlaywrightActionEngine(BrowserActionEngine):
    session_pool: PlaywrightCdpSessionPool
    ref_store: BrowserRefStore
    family: BrowserActionFamily = "cdp-backed-playwright"

    def supports(
        self,
        *,
        command: BrowserPageActionCommand,
    ) -> bool:
        return command.kind in _SUPPORTED_KINDS

    def execute(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab | None,
        command: BrowserPageActionCommand,
    ) -> BrowserActionResult:
        if tab is None:
            raise BrowserValidationError("cdp-backed-playwright actions require a tab.")
        cdp_url = self._runtime_cdp_url(plan=plan, runtime_state=runtime_state)
        max_attempts = (
            2
            if command.kind in _RETRYABLE_TRANSIENT_ACTION_KINDS
            else 1
        )
        last_error: Exception | None = None
        for attempt in range(max_attempts):
            page = self.session_pool.resolve_page(
                profile=plan.profile,
                target_id=tab.target_id,
                timeout_ms=command.timeout_ms,
                cdp_url=cdp_url,
            )
            try:
                result_value, resolved_selector, resolved_frame_path = self._execute_on_page(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    command=command,
                )
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt + 1 < max_attempts and _is_transient_page_context_error(exc):
                    continue
                raise
        else:
            assert last_error is not None
            raise last_error
        if command.kind == "snapshot" and isinstance(result_value, dict):
            runtime_state.remember_page_snapshot(
                target_id=tab.target_id,
                generation=int(result_value.get("generation") or 1),
                snapshot_format=str(result_value.get("format") or "snapshot"),
                ref_count=int(result_value.get("ref_count") or 0),
                frame_count=int(result_value.get("frame_count") or 0),
            )
        else:
            runtime_state.remember_page_action(
                target_id=tab.target_id,
                action_kind=command.kind,
            )
        return BrowserActionResult(
            command=command,
            ok=True,
            target_id=tab.target_id,
            value={
                "engine": self.family,
                "control_family": plan.control_family,
                "profile": plan.profile.name,
                "tab": _serialize_tab(tab),
                "ref": command.target.ref,
                "selector": resolved_selector,
                "frame_path": _serialize_frame_path(resolved_frame_path),
                "payload": dict(command.payload),
                "result": result_value,
            },
            message=f"Executed {command.kind} via cdp-backed-playwright.",
        )

    def clear_profile(
        self,
        *,
        profile_name: str,
    ) -> None:
        self.session_pool.clear_profile(profile_name=profile_name)

    def _execute_on_page(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
        batch_depth: int = 0,
    ) -> tuple[Any, str | None, tuple[int, ...] | None]:
        timeout = _timeout_ms(command)
        fill_fields = _normalize_form_fields(command.payload.get("fields")) if command.kind == "fill" else ()
        effective_command = command
        if command.kind == "drag" and command.target.ref is None and command.target.selector is None:
            source_ref = _drag_source_ref(command)
            source_selector = _drag_source_selector(command)
            if source_ref is not None or source_selector is not None:
                effective_command = replace(
                    command,
                    target=replace(
                        command.target,
                        ref=source_ref,
                        selector=source_selector,
                    ),
                )
        context, locator, resolved_selector, resolved_frame_path = self._locator(
            plan=plan,
            tab=tab,
            page=page,
            runtime_state=runtime_state,
            command=effective_command,
            required=(
                command.kind in _LOCATOR_ACTION_KINDS
                and not bool(fill_fields)
            ),
        )

        if command.kind == "batch":
            return (
                self._batch(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    command=command,
                    batch_depth=batch_depth,
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "click":
            button = command.payload.get("button")
            click_mode = self._click(
                locator=locator,
                timeout=timeout,
                button=button,
                force=bool(command.payload.get("force", False)),
                double_click=bool(command.payload.get("double_click", False)),
            )
            return {"kind": "click", "mode": click_mode}, resolved_selector, resolved_frame_path

        if command.kind == "type":
            text = _payload_text(command.payload, key="text")
            input_mode = self._input_text(
                locator=locator,
                text=text,
                payload={**dict(command.payload), "input_mode": "type"},
                timeout=timeout,
                action_kind="type",
                default_mode="type",
            )
            return {"kind": "type", "text": text, "input_mode": input_mode}, resolved_selector, resolved_frame_path

        if command.kind == "press":
            key = _payload_text(command.payload, key="key")
            if locator is None:
                page.keyboard.press(key, **_timeout_kwargs(timeout))
            else:
                locator.press(key, **_timeout_kwargs(timeout))
            return {"kind": "press", "key": key}, resolved_selector, resolved_frame_path

        if command.kind == "hover":
            locator.hover(**_timeout_kwargs(timeout))
            return {"kind": "hover"}, resolved_selector, resolved_frame_path

        if command.kind == "drag":
            target_ref = _drag_target_ref(command.payload)
            target_selector = _drag_target_selector(command.payload)
            if target_ref is not None:
                (
                    _target_context,
                    target_locator,
                    _resolved_target_selector,
                    _resolved_target_frame_path,
                ) = self._locator_from_ref(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    ref_id=target_ref,
                )
            else:
                if target_selector is None:
                    raise BrowserValidationError(
                        "drag requires end_ref/end_selector or target_ref/target_selector.",
                    )
                target_locator = context.locator(target_selector)
            locator.drag_to(target_locator, **_timeout_kwargs(timeout))
            return (
                {
                    "kind": "drag",
                    "start_ref": effective_command.target.ref,
                    "start_selector": effective_command.target.selector,
                    "end_ref": target_ref,
                    "end_selector": target_selector,
                },
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "resize":
            width = int(_payload_number_any(command.payload, "width") or 0)
            height = int(_payload_number_any(command.payload, "height") or 0)
            if width < 1 or height < 1:
                raise BrowserValidationError("payload.width and payload.height are required.")
            set_viewport_size = getattr(page, "set_viewport_size", None)
            if not callable(set_viewport_size):
                raise BrowserValidationError(
                    "Playwright page does not support set_viewport_size().",
                )
            set_viewport_size({"width": width, "height": height})
            return (
                {
                    "kind": "resize",
                    "width": width,
                    "height": height,
                },
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "scroll-into-view":
            locator.scroll_into_view_if_needed(**_timeout_kwargs(timeout))
            return {"kind": "scroll-into-view"}, resolved_selector, resolved_frame_path

        if command.kind == "select":
            values = command.payload.get("values")
            if values is None:
                value = _payload_text(command.payload, key="value")
                selection: Any = value
            elif isinstance(values, (list, tuple)):
                selection = list(values)
            else:
                selection = values
            selected = locator.select_option(selection, **_timeout_kwargs(timeout))
            return (
                {"kind": "select", "selected": selected},
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "fill":
            if fill_fields:
                filled: list[dict[str, Any]] = []
                for field in fill_fields:
                    (
                        _field_context,
                        field_locator,
                        field_selector,
                        field_frame_path,
                    ) = self._locator_from_ref(
                        plan=plan,
                        tab=tab,
                        page=page,
                        runtime_state=runtime_state,
                        ref_id=str(field["ref"]),
                    )
                    field_type = str(field["type"])
                    raw_value = field["value"]
                    if field_type in {"checkbox", "radio"}:
                        checked = bool(raw_value)
                        set_checked = getattr(field_locator, "set_checked", None)
                        if not callable(set_checked):
                            raise BrowserValidationError(
                                f"Playwright locator for ref '{field['ref']}' does not support set_checked().",
                            )
                        set_checked(checked, **_timeout_kwargs(timeout))
                        value_repr: Any = checked
                    else:
                        value_repr = (
                            raw_value
                            if isinstance(raw_value, str)
                            else str(raw_value)
                        )
                        self._ensure_editable_text_target(locator=field_locator, action_kind="fill")
                        field_locator.fill(str(value_repr), **_timeout_kwargs(timeout))
                    filled.append(
                        {
                            "ref": field["ref"],
                            "type": field_type,
                            "value": value_repr,
                            "selector": field_selector,
                            "frame_path": _serialize_frame_path(field_frame_path),
                        }
                    )
                return {"kind": "fill", "fields": filled}, resolved_selector, resolved_frame_path

            text = _payload_text(command.payload, key="text")
            self._ensure_editable_text_target(locator=locator, action_kind="fill")
            locator.fill(text, **_timeout_kwargs(timeout))
            return {"kind": "fill", "text": text}, resolved_selector, resolved_frame_path

        if command.kind == "wait":
            return (
                self._wait(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    locator=locator,
                    command=command,
                    timeout=timeout,
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "snapshot":
            return (
                self._snapshot(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    command=command,
                ),
                resolved_selector,
                resolved_frame_path,
            )

        if command.kind == "screenshot":
            image_type = _payload_text(command.payload, key="type", required=False) or "png"
            screenshot_kwargs: dict[str, Any] = {
                "full_page": bool(command.payload.get("full_page", False)),
                "type": image_type,
            }
            screenshot_kwargs.update(_timeout_kwargs(timeout))
            screenshot = page.screenshot(**screenshot_kwargs)
            return {
                "kind": "screenshot",
                "content_type": f"image/{image_type}",
                "encoding": "base64",
                "data": base64.b64encode(screenshot).decode("ascii"),
            }, resolved_selector, resolved_frame_path

        if command.kind == "pdf":
            pdf = page.pdf(print_background=bool(command.payload.get("print_background", True)))
            return {
                "kind": "pdf",
                "content_type": "application/pdf",
                "encoding": "base64",
                "data": base64.b64encode(pdf).decode("ascii"),
            }, resolved_selector, resolved_frame_path

        if command.kind == "evaluate":
            expression = _payload_text_any(command.payload, "expression", "fn")
            if expression is None:
                raise BrowserValidationError("payload.expression or payload.fn is required.")
            evaluate_target = locator
            if evaluate_target is not None:
                if "arg" in command.payload:
                    return (
                        evaluate_target.evaluate(expression, command.payload.get("arg")),
                        resolved_selector,
                        resolved_frame_path,
                    )
                return (
                    evaluate_target.evaluate(expression),
                    resolved_selector,
                    resolved_frame_path,
                )
            if "arg" in command.payload:
                return (
                    page.evaluate(expression, command.payload.get("arg")),
                    resolved_selector,
                    resolved_frame_path,
                )
            return page.evaluate(expression), resolved_selector, resolved_frame_path

        raise BrowserValidationError(
            f"Action engine '{self.family}' does not support '{command.kind}'.",
        )











    def _batch(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
        batch_depth: int,
    ) -> dict[str, Any]:
        if batch_depth > _MAX_BATCH_DEPTH:
            raise BrowserValidationError(
                f"Batch nesting depth exceeds maximum of {_MAX_BATCH_DEPTH}.",
            )
        raw_actions = command.payload.get("actions")
        if not isinstance(raw_actions, (list, tuple)) or not raw_actions:
            raise BrowserValidationError("batch requires actions.")
        if _count_batch_actions(raw_actions) > _MAX_BATCH_ACTIONS:
            raise BrowserValidationError(f"Batch exceeds maximum of {_MAX_BATCH_ACTIONS} actions.")

        actions: list[BrowserPageActionCommand] = []
        for raw_action in raw_actions:
            if not isinstance(raw_action, Mapping):
                raise BrowserValidationError("batch actions must be objects.")
            actions.append(
                _normalize_batch_action(
                    raw_action=raw_action,
                    profile_name=plan.profile.name,
                    inherited_target_id=tab.target_id,
                    inherited_timeout_ms=command.timeout_ms,
                    depth=batch_depth + 1,
                )
            )
        if not actions:
            raise BrowserValidationError("batch requires actions.")
        stop_on_error = command.payload.get("stop_on_error")
        if not isinstance(stop_on_error, bool):
            stop_on_error = True

        results: list[dict[str, Any]] = []
        for action in actions:
            try:
                result_value, _selector, _frame_path = self._execute_on_page(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    command=action,
                    batch_depth=batch_depth + 1,
                )
                if action.kind == "snapshot" and isinstance(result_value, dict):
                    runtime_state.remember_page_snapshot(
                        target_id=tab.target_id,
                        generation=int(result_value.get("generation") or 1),
                        snapshot_format=str(result_value.get("format") or "snapshot"),
                        ref_count=int(result_value.get("ref_count") or 0),
                        frame_count=int(result_value.get("frame_count") or 0),
                    )
                else:
                    runtime_state.remember_page_action(
                        target_id=tab.target_id,
                        action_kind=action.kind,
                    )
                results.append(
                    {
                        "ok": True,
                        "kind": action.kind,
                        "result": result_value,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                results.append(
                    {
                        "ok": False,
                        "kind": action.kind,
                        "error": str(exc),
                    }
                )
                if stop_on_error:
                    break
        return {
            "kind": "batch",
            "stop_on_error": stop_on_error,
            "results": results,
        }

    def _runtime_cdp_url(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> str | None:
        cached = runtime_state.metadata.get("cdp_base_url")
        if isinstance(cached, str) and cached.strip():
            return cached.strip()
        derived = browser_ref_to_cdp_http_base(runtime_state.browser_ref)
        if derived is not None:
            return derived
        return plan.profile.cdp_url

    def _trigger_locator(
        self,
        *,
        locator,
        payload: Mapping[str, Any],
        timeout: float | None,
    ) -> dict[str, Any]:
        trigger = (_payload_text_any(payload, "trigger") or "click").strip().lower()
        if trigger == "click":
            return {
                "trigger": "click",
                "mode": self._click(
                    locator=locator,
                    timeout=timeout,
                    button="left",
                    force=bool(payload.get("force", False)),
                    double_click=False,
                ),
            }
        if trigger == "hover":
            locator.hover(**_timeout_kwargs(timeout))
            return {"trigger": "hover"}
        if trigger == "press":
            key = _payload_text_any(payload, "key") or "ArrowDown"
            locator.press(key, **_timeout_kwargs(timeout))
            return {"trigger": "press", "key": key}
        raise BrowserValidationError("trigger must be click, hover, or press.")

    def _toolbar_command_locator(
        self,
        *,
        root,
        payload: Mapping[str, Any],
    ):
        command_text = _payload_text_any(payload, "command_text", "commandText", "text")
        if command_text is None:
            raise BrowserValidationError("toolbar-action requires command_text, command_ref, or command_selector.")
        exact = _locator_exact(payload)
        ordinal = _locator_ordinal(payload)
        for role in ("button", "menuitem", "tab", "link", "checkbox", "radio"):
            get_by_role = getattr(root, "get_by_role", None)
            if callable(get_by_role):
                locator = get_by_role(role, name=command_text, exact=exact)
                if ordinal is not None:
                    nth_method = getattr(locator, "nth", None)
                    if callable(nth_method):
                        locator = nth_method(ordinal)
                return locator, describe_role_locator(role=role, name=command_text, nth=ordinal)
        locator = self._text_locator(
            root=root,
            text=command_text,
            exact=exact,
            ordinal=ordinal,
        )
        description = f"text={command_text}"
        if ordinal is not None:
            description = f"{description}[ordinal={ordinal}]"
        return locator, description

    def _input_text(
        self,
        *,
        locator,
        text: str,
        payload: Mapping[str, Any],
        timeout: float | None,
        action_kind: str,
        default_mode: str = "fill",
    ) -> str:
        input_mode = (_payload_text_any(payload, "input_mode", "inputMode") or default_mode).strip().lower()
        if input_mode not in {"fill", "type"}:
            raise BrowserValidationError("input_mode must be fill or type.")
        self._ensure_editable_text_target(locator=locator, action_kind=action_kind)
        if input_mode == "type":
            type_kwargs: dict[str, Any] = _timeout_kwargs(timeout)
            delay = _payload_number_any(payload, "delay_ms", "delayMs")
            if delay is not None:
                type_kwargs["delay"] = float(delay)
            type_method = getattr(locator, "type", None)
            if callable(type_method):
                type_method(text, **type_kwargs)
            else:
                locator.fill(text, **_timeout_kwargs(timeout))
                input_mode = "fill"
        else:
            locator.fill(text, **_timeout_kwargs(timeout))
        return input_mode

    def _ensure_editable_text_target(self, *, locator, action_kind: str) -> None:
        info = self._target_info(locator=locator)
        tag = str(info.get("tag") or "").strip().lower()
        role = str(info.get("role") or "").strip().lower()
        content_editable = bool(info.get("content_editable"))
        read_only = bool(info.get("read_only"))
        disabled = bool(info.get("disabled"))
        editable = (
            content_editable
            or tag in {"input", "textarea"}
            or role in {"textbox", "combobox", "searchbox", "spinbutton"}
        )
        if editable and not read_only and not disabled:
            return
        target_bits = [part for part in (f"tag={tag}" if tag else None, f"role={role}" if role else None) if part]
        target_desc = ", ".join(target_bits) if target_bits else "unknown target"
        raise BrowserValidationError(
            f"Browser action '{action_kind}' targeted a non-editable element ({target_desc}). Choose an input/textbox/contenteditable ref or selector.",
        )

    def _target_info(self, *, locator) -> dict[str, Any]:
        evaluate = getattr(locator, "evaluate", None)
        if not callable(evaluate):
            return {}
        try:
            value = evaluate(_TARGET_INFO_EXPRESSION)
        except Exception:  # noqa: BLE001
            return {}
        if not isinstance(value, Mapping):
            return {}
        return {
            "tag": str(value.get("tag") or "").strip().lower() or None,
            "role": str(value.get("role") or "").strip().lower() or None,
            "type": str(value.get("type") or "").strip().lower() or None,
            "content_editable": bool(value.get("contentEditable") or value.get("content_editable")),
            "read_only": bool(value.get("readOnly") or value.get("read_only")),
            "disabled": bool(value.get("disabled")),
            "checked": bool(value.get("checked")),
            "value": value.get("value"),
        }

    def _derive_date_option_text(self, *, date_value: str) -> str:
        for separator in ("-", "/", "."):
            parts = [segment.strip() for segment in date_value.split(separator)]
            if len(parts) == 3 and all(parts):
                tail = parts[-1]
                if tail.isdigit():
                    return str(int(tail))
        digits = "".join(character for character in date_value if character.isdigit())
        if len(digits) >= 1 and date_value.strip().isdigit():
            return str(int(digits))
        return date_value


    def _derive_date_target_month(
        self,
        *,
        date_value: str | None,
        month_header_text: str | None,
    ) -> dict[str, Any] | None:
        resolved_text = _normalize_optional_text(month_header_text)
        month_key: str | None = None
        if date_value is not None:
            for separator in ("-", "/", "."):
                parts = [segment.strip() for segment in date_value.split(separator)]
                if len(parts) != 3 or not all(parts):
                    continue
                year_text, month_text, _day_text = parts
                if not (year_text.isdigit() and len(year_text) == 4 and month_text.isdigit()):
                    continue
                year = int(year_text)
                month = int(month_text)
                if not 1 <= month <= 12:
                    continue
                month_key = f"{year:04d}-{month:02d}"
                if resolved_text is None:
                    resolved_text = f"{calendar.month_name[month]} {year:04d}"
                break
        if resolved_text is None and month_key is None:
            return None
        result: dict[str, Any] = {}
        if resolved_text is not None:
            result["text"] = resolved_text
        if month_key is not None:
            result["key"] = month_key
        return result

    def _month_key_from_text(self, text: str | None) -> str | None:
        normalized = _normalize_optional_text(text)
        if normalized is None:
            return None
        direct_match = re.search(r"(?P<year>\d{4})\D+(?P<month>\d{1,2})", normalized)
        if direct_match:
            year = int(direct_match.group("year"))
            month = int(direct_match.group("month"))
            if 1 <= month <= 12:
                return f"{year:04d}-{month:02d}"
        lowered = normalized.lower()
        year_match = re.search(r"(?P<year>\d{4})", lowered)
        if year_match is None:
            return None
        year = int(year_match.group("year"))
        for month in range(1, 13):
            names = {
                calendar.month_name[month].lower(),
                calendar.month_abbr[month].lower(),
            }
            if any(name and name in lowered for name in names):
                return f"{year:04d}-{month:02d}"
        return None

    def _month_delta(self, *, current_key: str | None, target_key: str | None) -> int | None:
        if current_key is None or target_key is None:
            return None
        try:
            current_year, current_month = (int(part) for part in current_key.split("-", 1))
            target_year, target_month = (int(part) for part in target_key.split("-", 1))
        except (TypeError, ValueError):
            return None
        return (target_year - current_year) * 12 + (target_month - current_month)



    def _locator_display_text(self, locator) -> str | None:  # noqa: ANN001
        evaluate = getattr(locator, "evaluate", None)
        if not callable(evaluate):
            return None
        try:
            resolved = evaluate(
                "(element) => (element.innerText || element.textContent || element.getAttribute('aria-label') || '').trim()",
            )
        except Exception:  # noqa: BLE001
            return None
        return _normalize_optional_text(resolved)

    def _target_locator_from_payload(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        payload: Mapping[str, Any],
        ref_keys: tuple[str, ...],
        selector_keys: tuple[str, ...],
    ) -> tuple[Any, Any, str | None, tuple[int, ...]] | None:
        ref_id = _payload_text_any(payload, *ref_keys)
        if ref_id is not None:
            return self._locator_from_ref(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                ref_id=ref_id,
            )
        selector = _payload_text_any(payload, *selector_keys)
        if selector is None:
            return None
        scope_payload = dict(payload)
        temp_command = BrowserPageActionCommand(
            profile_name=plan.profile.name,
            kind="click",
            target=BrowserActionTarget(
                target_id=tab.target_id,
                selector=selector,
            ),
            payload=scope_payload,
        )
        return self._locator(
            plan=plan,
            tab=tab,
            page=page,
            runtime_state=runtime_state,
            command=temp_command,
            required=True,
        )

    def _bulk_selection_root(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
    ) -> tuple[Any, bool, str | None, tuple[int, ...]]:
        scope_ref = _scope_ref_id(command.payload)
        scope_selector = _scope_selector(command.payload)
        if scope_ref is not None and scope_selector is not None:
            raise BrowserValidationError(
                "payload.scope_ref and payload.scope_selector are mutually exclusive.",
            )
        if scope_ref is not None:
            _context, locator, description, frame_path = self._locator_from_ref(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                ref_id=scope_ref,
            )
            return locator, True, description, frame_path
        if scope_selector is not None:
            return _main_frame(page).locator(scope_selector), True, scope_selector, ()
        if command.target.ref is not None:
            _context, locator, description, frame_path = self._locator_from_ref(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                ref_id=command.target.ref,
            )
            return locator, True, description, frame_path
        if command.target.selector is not None:
            return _main_frame(page).locator(command.target.selector), True, command.target.selector, ()
        if _active_overlay(command.payload):
            overlay_selector = self._resolved_active_overlay_selector(
                page=page,
                runtime_state=runtime_state,
                tab=tab,
                command=command,
            )
            if overlay_selector is not None:
                return _main_frame(page).locator(overlay_selector), True, overlay_selector, ()
        return _main_frame(page), False, None, ()


    def _set_locator_checked(
        self,
        *,
        locator,
        checked: bool,
        timeout: float | None,
        force: bool,
    ) -> str:
        set_checked = getattr(locator, "set_checked", None)
        if callable(set_checked):
            set_checked(checked, **_timeout_kwargs(timeout))
            return "set_checked"
        method = getattr(locator, "check" if checked else "uncheck", None)
        if callable(method):
            method(**_timeout_kwargs(timeout))
            return "check" if checked else "uncheck"
        return self._click(
            locator=locator,
            timeout=timeout,
            button="left",
            force=force,
            double_click=False,
        )

    def _click(
        self,
        *,
        locator,
        timeout: float | None,
        button: Any,
        force: bool,
        double_click: bool,
    ) -> str:
        method_name = "dblclick" if double_click else "click"
        method = getattr(locator, method_name, None)
        if not callable(method):
            raise BrowserValidationError(
                f"Playwright locator does not support '{method_name}'.",
            )

        kwargs: dict[str, Any] = {}
        if isinstance(button, str) and button.strip():
            kwargs["button"] = button.strip()

        if force:
            method(**kwargs, **_timeout_kwargs(timeout), force=True)
            return "force"

        try:
            method(**kwargs, **_timeout_kwargs(_probe_timeout(timeout)))
            return "direct"
        except Exception as exc:  # noqa: BLE001
            if not _is_pointer_interception_error(exc):
                raise

        method(**kwargs, **_timeout_kwargs(timeout), force=True)
        return "force"

    def _locator(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
        required: bool,
    ) -> tuple[Any, Any | None, str | None, tuple[int, ...] | None]:
        if command.target.ref is not None:
            return self._locator_from_ref(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                ref_id=command.target.ref,
            )
        if command.target.selector is None:
            if required:
                raise BrowserValidationError(
                    f"Browser action '{command.kind}' requires ref or selector targeting.",
                )
            return page, None, None, None
        root = self._scoped_root(
            plan=plan,
            tab=tab,
            page=page,
            runtime_state=runtime_state,
            command=command,
        )
        locator_factory = getattr(root, "locator", None)
        if not callable(locator_factory):
            raise BrowserValidationError(
                f"Browser action '{command.kind}' does not support scoped selector resolution.",
            )
        locator = locator_factory(command.target.selector)
        ordinal = _locator_ordinal(command.payload)
        if ordinal is None and _allows_implicit_selector_ordinal(command):
            ordinal = self._preferred_selector_ordinal(
                locator=locator,
                command=command,
            )
        if ordinal is not None:
            nth_method = getattr(locator, "nth", None)
            if not callable(nth_method):
                raise BrowserValidationError(
                    f"Browser action '{command.kind}' does not support ordinal selector resolution.",
                )
            locator = nth_method(ordinal)
        description = command.target.selector
        scope_selector = _scope_selector(command.payload)
        scope_ref = _scope_ref_id(command.payload)
        if scope_selector is not None:
            description = f"{scope_selector} >> {description}"
        elif scope_ref is not None:
            description = f"{scope_ref} >> {description}"
        if ordinal is not None:
            ordinal_label = "auto-ordinal" if _locator_ordinal(command.payload) is None else "ordinal"
            description = f"{description}[{ordinal_label}={ordinal}]"
        return _main_frame(page), locator, description, ()

    def _preferred_selector_ordinal(
        self,
        *,
        locator,
        command: BrowserPageActionCommand,
    ) -> int | None:
        count = getattr(locator, "count", None)
        nth = getattr(locator, "nth", None)
        if not callable(count) or not callable(nth):
            return None
        try:
            candidate_count = int(count())
        except Exception:  # noqa: BLE001
            return None
        if candidate_count <= 1:
            return None
        best_ordinal: int | None = None
        best_score: int | None = None
        for index in range(candidate_count):
            candidate = nth(index)
            info = self._locator_target_info(candidate)
            score = self._score_selector_candidate(info=info, command=command)
            if best_score is None or score > best_score:
                best_score = score
                best_ordinal = index
        return best_ordinal

    def _locator_target_info(
        self,
        locator,
    ) -> Mapping[str, Any]:
        evaluate = getattr(locator, "evaluate", None)
        if not callable(evaluate):
            return {}
        try:
            value = evaluate(_TARGET_INFO_EXPRESSION)
        except Exception:  # noqa: BLE001
            return {}
        if isinstance(value, Mapping):
            return value
        return {}

    def _score_selector_candidate(
        self,
        *,
        info: Mapping[str, Any],
        command: BrowserPageActionCommand,
    ) -> int:
        tag = str(info.get("tag") or "").strip().lower()
        role = str(info.get("role") or "").strip().lower()
        score = 0
        if bool(info.get("focused")):
            score += 10_000
        if bool(info.get("visible", True)):
            score += 5_000
        if not bool(info.get("disabled", False)):
            score += 2_000
        if command.kind in {"fill", "type", "wait", "press"}:
            if tag in {"input", "textarea", "select"}:
                score += 700
            if role in {"textbox", "combobox", "searchbox", "spinbutton"}:
                score += 800
            if bool(info.get("contentEditable")):
                score += 650
            if not bool(info.get("readOnly", False)):
                score += 250
        if command.kind == "select" and tag == "select":
            score += 900
        return score

    def _locator_from_ref(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        ref_id: str,
    ) -> tuple[Any, Any, str | None, tuple[int, ...]]:
        stored_refs = self.ref_store.get_tab_refs(
            profile_name=plan.profile.name,
            target_id=tab.target_id,
        )
        page_state = runtime_state.page_state(target_id=tab.target_id) or {}
        current_generation = int(page_state.get("current_ref_generation") or 0)
        for item in stored_refs:
            if item.ref != ref_id:
                continue
            if item.selector is None and item.role is None:
                raise BrowserValidationError(
                    f"Browser ref '{ref_id}' does not expose a supported locator.",
                )
            context = _resolve_frame_context(page, item.frame_path)
            generation_mismatch = current_generation and item.generation != current_generation
            anchored_locator, anchored_description = self._anchored_locator_from_ref_item(
                context=context,
                item=item,
            )
            role_locator = self._semantic_locator_from_ref_item(context=context, item=item)
            prefer_semantic = (
                anchored_locator is not None
                or role_locator is not None
                and (
                    item.snapshot_format in {"interactive", "role", "aria"}
                    or item.selector is None
                    or item.nth is not None
                )
            )
            if generation_mismatch:
                if anchored_locator is not None:
                    return (
                        context,
                        anchored_locator,
                        anchored_description,
                        item.frame_path,
                    )
                if role_locator is not None:
                    return (
                        context,
                        role_locator,
                        describe_role_locator(
                            role=item.role or "generic",
                            name=_stored_ref_name(item),
                            nth=item.nth,
                        ),
                        item.frame_path,
                    )
                raise BrowserValidationError(
                    f"Browser ref '{ref_id}' is stale for tab '{tab.target_id}'.",
                )
            if prefer_semantic and anchored_locator is not None:
                return (
                    context,
                    anchored_locator,
                    anchored_description,
                    item.frame_path,
                )
            if prefer_semantic and item.role is not None:
                return (
                    context,
                    role_locator,
                    describe_role_locator(
                        role=item.role,
                        name=_stored_ref_name(item),
                        nth=item.nth,
                    ),
                    item.frame_path,
                )
            if item.selector is not None:
                return (
                    context,
                    context.locator(item.selector),
                    item.selector,
                    item.frame_path,
                )
            if role_locator is not None and item.role is not None:
                return (
                    context,
                    role_locator,
                    describe_role_locator(
                        role=item.role,
                        name=_stored_ref_name(item),
                        nth=item.nth,
                    ),
                    item.frame_path,
                )
            raise BrowserValidationError(
                f"Browser ref '{ref_id}' does not expose a supported locator.",
            )
        raise BrowserValidationError(
            f"Browser ref '{ref_id}' was not found for tab '{tab.target_id}'.",
        )

    def _anchored_locator_from_ref_item(
        self,
        *,
        context,
        item: BrowserStoredRef,
    ) -> tuple[Any, str] | tuple[None, None]:
        scope_selector = _normalize_optional_text(item.scope_selector)
        if scope_selector is None:
            return None, None
        scoped_root = context.locator(scope_selector)

        role_locator = self._semantic_locator_from_ref_item(context=scoped_root, item=item)
        if role_locator is not None:
            return (
                role_locator,
                f"{scope_selector} >> {describe_role_locator(role=item.role or 'generic', name=_stored_ref_name(item), nth=item.nth)}",
            )

        name = _stored_ref_name(item)
        if name is None:
            return None, None
        text_factory = getattr(scoped_root, "get_by_text", None)
        if not callable(text_factory):
            return None, None
        text_locator = text_factory(name, exact=True)
        if item.nth is not None:
            nth_method = getattr(text_locator, "nth", None)
            if not callable(nth_method):
                raise BrowserValidationError(
                    f"Browser ref '{item.ref}' requires nth text resolution, but the Playwright locator does not support nth().",
                )
            text_locator = nth_method(item.nth)
        description = f'{scope_selector} >> text="{name}"'
        if item.nth is not None:
            description = f"{description}[nth={item.nth}]"
        return text_locator, description

    def _semantic_locator_from_ref_item(self, *, context, item: BrowserStoredRef):  # noqa: ANN001
        locator_factory = getattr(context, "get_by_role", None)
        if not callable(locator_factory) or item.role is None:
            return None
        role_kwargs: dict[str, Any] = {}
        name = _stored_ref_name(item)
        if name is not None:
            role_kwargs["name"] = name
            role_kwargs["exact"] = True
        role_locator = locator_factory(item.role, **role_kwargs)
        if item.nth is not None:
            nth_method = getattr(role_locator, "nth", None)
            if not callable(nth_method):
                raise BrowserValidationError(
                    f"Browser ref '{item.ref}' requires nth role resolution, but the Playwright locator does not support nth().",
                )
            role_locator = nth_method(item.nth)
        return role_locator

    def _resolved_active_overlay_selector(
        self,
        *,
        page,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab,
        command: BrowserPageActionCommand | None = None,
        overlay_kind: str | None = None,
        source_refs: tuple[str, ...] = (),
        source_selectors: tuple[str, ...] = (),
        source_scope_selectors: tuple[str, ...] = (),
    ) -> str | None:
        candidate_refs = source_refs
        candidate_selectors = source_selectors
        candidate_scope_selectors = source_scope_selectors
        if command is not None:
            candidate_refs = candidate_refs + _command_overlay_source_refs(command)
            candidate_selectors = candidate_selectors + _command_overlay_source_selectors(
                command,
            )
            candidate_scope_selectors = (
                candidate_scope_selectors
                + _command_overlay_source_scope_selectors(command)
                + self._overlay_source_scope_selectors_for_command(
                    plan=None,
                    tab=tab,
                    runtime_state=runtime_state,
                    command=command,
                )
            )
            if overlay_kind is None:
                overlay_kind = self._overlay_kind_for_command(
                    runtime_state=runtime_state,
                    tab=tab,
                    command=command,
                )
        stored = runtime_state.active_overlay_selector(
            target_id=tab.target_id,
            overlay_kind=overlay_kind,
            source_refs=candidate_refs,
            source_selectors=candidate_selectors,
            source_scope_selectors=candidate_scope_selectors,
        )
        if stored is not None:
            return stored
        return _active_overlay_selector(page)

    def _overlay_source_selector_for_command(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
    ) -> str | None:
        explicit_selector = _payload_text_any(
            command.payload,
            "overlay_source_selector",
            "overlaySourceSelector",
        )
        if explicit_selector is not None:
            return explicit_selector

        source_ref = _payload_text_any(
            command.payload,
            "overlay_source_ref",
            "overlaySourceRef",
        )
        if source_ref is not None:
            try:
                _context, _locator, description, _frame_path = self._locator_from_ref(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    ref_id=source_ref,
                )
            except BrowserValidationError:
                description = None
            if isinstance(description, str) and description.strip().startswith(("#", ".", "body ", "body>", "input", "button", "select", "textarea", "[")):
                return description.strip()

        overlay_context = runtime_state.active_overlay_context(target_id=tab.target_id)
        if isinstance(overlay_context, dict):
            return _normalize_optional_text(overlay_context.get("source_selector"))
        return None

    def _overlay_source_scope_selectors_for_command(
        self,
        *,
        plan: BrowserExecutionPlan | None,
        tab: BrowserTab,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
    ) -> tuple[str, ...]:
        candidates: list[str] = list(_command_overlay_source_scope_selectors(command))
        for ref_id in _command_overlay_source_refs(command):
            resolved_scope = self._stored_ref_scope_selector(
                plan=plan,
                tab=tab,
                ref_id=ref_id,
            )
            if resolved_scope is not None:
                candidates.append(resolved_scope)
        overlay_context = runtime_state.active_overlay_context(target_id=tab.target_id)
        if isinstance(overlay_context, dict):
            runtime_scope = _normalize_optional_text(
                overlay_context.get("source_scope_selector"),
            )
            if runtime_scope is not None:
                candidates.append(runtime_scope)
        seen: set[str] = set()
        resolved: list[str] = []
        for candidate in candidates:
            normalized = _normalize_optional_text(candidate)
            if normalized is None or normalized in seen:
                continue
            seen.add(normalized)
            resolved.append(normalized)
        return tuple(resolved)

    def _stored_ref_scope_selector(
        self,
        *,
        plan: BrowserExecutionPlan | None,
        tab: BrowserTab,
        ref_id: str,
    ) -> str | None:
        if plan is None:
            return None
        for item in self.ref_store.get_tab_refs(
            profile_name=plan.profile.name,
            target_id=tab.target_id,
        ):
            if item.ref == ref_id:
                return _normalize_optional_text(item.scope_selector)
        return None

    def _remember_overlay_binding(
        self,
        *,
        plan: BrowserExecutionPlan,
        page,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab,
        command: BrowserPageActionCommand,
        payload: Mapping[str, Any],
        resolved_selector: str | None = None,
        overlay_selector: str | None = None,
    ) -> str | None:
        resolved_overlay = overlay_selector
        if resolved_overlay is None:
            resolved_overlay = _payload_text_any(
                payload,
                "overlay_selector",
                "overlaySelector",
            )
        if resolved_overlay is None:
            resolved_overlay = _active_overlay_selector(page)
        if resolved_overlay is None:
            return None
        runtime_state.remember_active_overlay(
            target_id=tab.target_id,
            overlay_selector=resolved_overlay,
            overlay_kind=self._overlay_kind_for_command(
                runtime_state=runtime_state,
                tab=tab,
                command=command,
            ),
            source_ref=next(iter(_command_overlay_source_refs(command)), None),
            source_selector=next(
                iter(
                    _command_overlay_source_selectors(
                        command,
                        resolved_selector=resolved_selector,
                    )
                ),
                None,
            ),
            source_scope_selector=next(
                iter(
                    self._overlay_source_scope_selectors_for_command(
                        plan=plan,
                        tab=tab,
                        runtime_state=runtime_state,
                        command=command,
                    )
                ),
                None,
            ),
        )
        return resolved_overlay

    def _overlay_kind_for_command(
        self,
        *,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab,
        command: BrowserPageActionCommand,
    ) -> str | None:
        explicit = _explicit_overlay_kind(command.payload)
        if explicit is not None:
            return explicit
        overlay_context = runtime_state.active_overlay_context(target_id=tab.target_id)
        if isinstance(overlay_context, dict):
            return _normalize_optional_text(overlay_context.get("kind"))
        return None

    def _clear_overlay_binding(
        self,
        *,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab,
    ) -> None:
        runtime_state.clear_active_overlay(target_id=tab.target_id)

    def _scoped_root(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
    ):
        scope_ref = _scope_ref_id(command.payload)
        scope_selector = _scope_selector(command.payload)
        if scope_ref is not None and scope_selector is not None:
            raise BrowserValidationError(
                "payload.scope_ref and payload.scope_selector are mutually exclusive.",
            )
        if scope_ref is not None:
            _context, scope_locator, _description, _frame_path = self._locator_from_ref(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                ref_id=scope_ref,
            )
            return scope_locator
        context = _main_frame(page)
        if scope_selector is not None:
            return context.locator(scope_selector)
        if _active_overlay(command.payload) or _wait_prefers_active_overlay(command):
            overlay_selector = self._resolved_active_overlay_selector(
                page=page,
                runtime_state=runtime_state,
                tab=tab,
                command=command,
            )
            if overlay_selector is not None:
                return context.locator(overlay_selector)
        return context

    def _text_locator(
        self,
        *,
        root,
        text: str,
        exact: bool,
        ordinal: int | None,
        source_selector: str | None = None,
        source_scope_selector: str | None = None,
    ):
        search_root = root
        if not callable(getattr(search_root, "get_by_text", None)):
            locator_factory = getattr(root, "locator", None)
            if callable(locator_factory):
                search_root = locator_factory("body")

        text_factory = getattr(search_root, "get_by_text", None)
        if callable(text_factory):
            locator = text_factory(text, exact=exact)
        else:
            locator_factory = getattr(search_root, "locator", None)
            if not callable(locator_factory):
                raise BrowserValidationError("Browser text wait could not construct a locator.")
            locator = locator_factory("text=" + text)
        resolved_ordinal = ordinal
        if resolved_ordinal is None:
            resolved_ordinal = self._preferred_text_ordinal(
                root=search_root,
                text=text,
                exact=exact,
                source_selector=source_selector,
                source_scope_selector=source_scope_selector,
            )
        if resolved_ordinal is not None:
            nth_method = getattr(locator, "nth", None)
            if not callable(nth_method):
                raise BrowserValidationError("Browser text wait does not support ordinal selection.")
            locator = nth_method(resolved_ordinal)
        return locator

    def _preferred_text_ordinal(
        self,
        *,
        root,
        text: str,
        exact: bool,
        source_selector: str | None,
        source_scope_selector: str | None,
    ) -> int | None:
        normalized_source = _normalize_optional_text(source_selector)
        normalized_source_scope = _normalize_optional_text(source_scope_selector)
        if normalized_source is None and normalized_source_scope is None:
            return None
        evaluate = getattr(root, "evaluate", None)
        if not callable(evaluate):
            return None
        try:
            resolved = evaluate(
                _TEXT_MATCH_ORDINAL_EXPRESSION,
                {
                    "text": text,
                    "exact": exact,
                    "sourceSelector": normalized_source,
                    "sourceScopeSelector": normalized_source_scope,
                },
            )
        except Exception:  # noqa: BLE001
            return None
        try:
            numeric = int(resolved)
        except (TypeError, ValueError):
            return None
        return numeric if numeric >= 0 else None


    def _wait_for_overlay_surface(
        self,
        *,
        plan: BrowserExecutionPlan,
        page,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab,
        command: BrowserPageActionCommand,
        payload: Mapping[str, Any],
        timeout: float | None,
    ) -> dict[str, Any]:
        overlay_selector = _payload_text_any(payload, "overlay_selector", "overlaySelector")
        if overlay_selector is not None:
            page.locator(overlay_selector).wait_for(
                state="visible",
                **_timeout_kwargs(timeout),
            )
            return {
                "waited_for_overlay": True,
                "overlay_selector": overlay_selector,
            }

        overlay_text = _payload_text_any(payload, "overlay_text", "overlayText")
        if overlay_text is not None:
            overlay_locator = self._text_locator(
                root=_main_frame(page),
                text=overlay_text,
                exact=_locator_exact(payload),
                ordinal=_locator_ordinal(payload),
                source_selector=_payload_text_any(
                    payload,
                    "overlay_source_selector",
                    "overlaySourceSelector",
                ),
                source_scope_selector=_payload_text_any(
                    payload,
                    "overlay_source_scope_selector",
                    "overlaySourceScopeSelector",
                )
                or _scope_selector(payload),
            )
            overlay_locator.wait_for(**_timeout_kwargs(timeout))
            resolved_overlay_selector = _active_overlay_selector(page) or self._resolved_active_overlay_selector(
                page=page,
                runtime_state=runtime_state,
                tab=tab,
                command=command,
            )
            return {
                "waited_for_overlay": True,
                "overlay_text": overlay_text,
                "exact": _locator_exact(payload),
                "ordinal": _locator_ordinal(payload),
                "overlay_selector": resolved_overlay_selector,
            }

        if _active_overlay(payload):
            overlay_kind = self._overlay_kind_for_command(
                runtime_state=runtime_state,
                tab=tab,
                command=command,
            )
            source_selector = self._overlay_source_selector_for_command(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                command=command,
            )
            source_scope_selector = next(
                iter(
                    self._overlay_source_scope_selectors_for_command(
                        plan=plan,
                        tab=tab,
                        runtime_state=runtime_state,
                        command=command,
                    )
                ),
                None,
            )
            if source_selector is not None or source_scope_selector is not None:
                page.wait_for_function(
                    _ASSOCIATED_OVERLAY_SELECTOR_EXPRESSION,
                    {
                        "overlayKind": _normalize_optional_text(overlay_kind),
                        "sourceSelector": source_selector,
                        "sourceScopeSelector": source_scope_selector,
                    },
                    **_timeout_kwargs(timeout),
                )
            else:
                page.wait_for_function(
                    _ACTIVE_OVERLAY_SELECTOR_EXPRESSION,
                    **_timeout_kwargs(timeout),
                )
            resolved_overlay_selector = (
                _associated_overlay_selector(
                    page,
                    overlay_kind=overlay_kind,
                    source_selector=source_selector,
                    source_scope_selector=source_scope_selector,
                )
                or _active_overlay_selector(page)
                or self._resolved_active_overlay_selector(
                    page=page,
                    runtime_state=runtime_state,
                    tab=tab,
                    command=command,
                    overlay_kind=overlay_kind,
                    source_scope_selectors=(
                        (source_scope_selector,) if source_scope_selector is not None else ()
                    ),
                )
            )
            return {
                "waited_for_overlay": True,
                "active_overlay": True,
                "overlay_source_bound": bool(source_selector or source_scope_selector),
                "overlay_selector": resolved_overlay_selector,
            }

        return {"waited_for_overlay": False}



    def _overlay_association_reason(
        self,
        *,
        payload: Mapping[str, Any],
        resolved_overlay_selector: str | None,
        source_selector: str | None,
        source_scope_selector: str | None,
    ) -> str | None:
        if _payload_text_any(payload, "overlay_selector", "overlaySelector") is not None:
            return "explicit-overlay-selector"
        if source_scope_selector is not None and resolved_overlay_selector is not None:
            return "source-scope"
        if source_selector is not None and resolved_overlay_selector is not None:
            return "source-selector"
        if _active_overlay(payload) and resolved_overlay_selector is not None:
            return "active-overlay"
        if resolved_overlay_selector is not None:
            return "overlay-detected"
        return None





    def _wait(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        locator,
        command: BrowserPageActionCommand,
        timeout: float | None,
    ) -> dict[str, Any]:
        if locator is not None:
            state = _payload_text_any(command.payload, "state") or "visible"
            wait_kwargs: dict[str, Any] = {"state": state}
            wait_kwargs.update(_timeout_kwargs(timeout))
            locator.wait_for(**wait_kwargs)
            return {"kind": "wait", "state": state}

        text_values = _normalize_text_payload(_payload_value_any(command.payload, "text"))
        if text_values:
            root = self._scoped_root(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                command=command,
            )
            exact = _locator_exact(command.payload)
            ordinal = _locator_ordinal(command.payload)
            text_locator = self._text_locator(
                root=root,
                text=text_values[0],
                exact=exact,
                ordinal=ordinal,
                source_selector=self._overlay_source_selector_for_command(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    command=command,
                ),
                source_scope_selector=next(
                    iter(
                        self._overlay_source_scope_selectors_for_command(
                            plan=plan,
                            tab=tab,
                            runtime_state=runtime_state,
                            command=command,
                        )
                    ),
                    None,
                ),
            )
            text_locator.wait_for(**_timeout_kwargs(timeout))
            return {
                "kind": "wait",
                "text": text_values,
                "exact": exact,
                "ordinal": ordinal,
            }

        text_gone_values = _normalize_text_payload(
            _payload_value_any(command.payload, "text_gone", "textGone"),
        )
        if text_gone_values:
            root = self._scoped_root(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                command=command,
            )
            exact = _locator_exact(command.payload)
            ordinal = _locator_ordinal(command.payload)
            text_locator = self._text_locator(
                root=root,
                text=text_gone_values[0],
                exact=exact,
                ordinal=ordinal,
                source_selector=self._overlay_source_selector_for_command(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    command=command,
                ),
                source_scope_selector=next(
                    iter(
                        self._overlay_source_scope_selectors_for_command(
                            plan=plan,
                            tab=tab,
                            runtime_state=runtime_state,
                            command=command,
                        )
                    ),
                    None,
                ),
            )
            text_locator.wait_for(
                state="hidden",
                **_timeout_kwargs(timeout),
            )
            return {
                "kind": "wait",
                "text_gone": text_gone_values,
                "exact": exact,
                "ordinal": ordinal,
            }

        url = _payload_text_any(command.payload, "url")
        if url is not None:
            page.wait_for_url(url, **_timeout_kwargs(timeout))
            return {"kind": "wait", "url": url}

        load_state = _payload_text_any(command.payload, "load_state", "loadState")
        if load_state is not None:
            page.wait_for_load_state(load_state, **_timeout_kwargs(timeout))
            return {"kind": "wait", "load_state": load_state}

        expression = _payload_text_any(command.payload, "expression", "fn")
        if expression is not None:
            page.wait_for_function(expression, **_timeout_kwargs(timeout))
            return {"kind": "wait", "expression": expression}

        delay_ms = _payload_number_any(command.payload, "delay_ms", "time_ms", "timeMs")
        if delay_ms is not None:
            page.wait_for_timeout(float(delay_ms))
            return {"kind": "wait", "delay_ms": float(delay_ms)}

        raise BrowserValidationError(
            "wait requires selector, payload.text, payload.text_gone, payload.url, payload.load_state, payload.expression/payload.fn, or payload.delay_ms.",
        )

    def _snapshot(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
    ) -> dict[str, Any]:
        snapshot_format = _resolve_snapshot_format(command.payload)
        snapshot_mode = _snapshot_mode(command.payload, snapshot_format=snapshot_format)
        snapshot_compact = _snapshot_compact(command.payload, snapshot_format=snapshot_format)
        snapshot_depth = _snapshot_depth(command.payload, snapshot_format=snapshot_format)
        refs_mode = _snapshot_refs_mode(command.payload)
        frame_selector = _snapshot_frame_selector(command.payload)
        root_selector = _effective_root_selector(
            page=page,
            runtime_state=runtime_state,
            tab=tab,
            payload=command.payload,
            root_selector=command.target.selector,
        )
        ref_count = 0
        frame_count = 0
        generation = 0
        if snapshot_format == "html":
            value = page.content()
        elif snapshot_format == "text":
            value = page.locator("body").inner_text()
        elif snapshot_format == "title":
            value = page.title()
        elif snapshot_format == "url":
            value = page.url
        elif snapshot_format == "aria":
            value, frame_count = self._aria_snapshot(
                page=page,
                frame_selector=frame_selector,
                root_selector=root_selector,
            )
        elif snapshot_format == "role":
            value, ref_count, frame_count, generation = self._role_snapshot(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                snapshot_format=snapshot_format,
                compact=snapshot_compact,
                depth=snapshot_depth,
                frame_selector=frame_selector,
                root_selector=root_selector,
            )
        elif snapshot_format == "interactive":
            value, ref_count, frame_count, generation = self._interactive_snapshot(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                snapshot_format=snapshot_format,
                snapshot_mode=snapshot_mode,
                limit=command.payload.get("limit"),
                compact=snapshot_compact,
                depth=snapshot_depth,
                payload=command.payload,
                frame_selector=frame_selector,
                root_selector=root_selector,
            )
        else:
            raise BrowserValidationError(
                f"Unsupported snapshot format '{snapshot_format}'.",
            )
        return {
            "kind": "snapshot",
            "format": snapshot_format,
            "generation": generation,
            "value": value,
            "ref_count": ref_count,
            "frame_count": frame_count,
            "mode": snapshot_mode,
            "compact": snapshot_compact,
            "depth": snapshot_depth,
            "refs_mode": refs_mode,
            "frame_selector": frame_selector,
            "root_selector": root_selector,
            "active_overlay": _active_overlay(command.payload),
        }

    def _aria_snapshot(
        self,
        *,
        page,
        frame_selector: str | None,
        root_selector: str | None,
    ) -> tuple[dict[str, Any], int]:
        frames: list[dict[str, Any]] = []
        for frame, frame_path in _snapshot_root_contexts(
            page,
            frame_selector=frame_selector,
            root_selector=root_selector,
        ):
            snapshot = _snapshot_root_locator(
                frame,
                root_selector=root_selector,
            ).aria_snapshot(**_timeout_kwargs(_probe_timeout(None)))
            frames.append(
                {
                    "frame_path": list(frame_path),
                    "snapshot": str(snapshot or "(empty)"),
                }
            )
        return {
            "snapshot": _combine_frame_snapshots(frames),
            "frames": frames,
        }, len(frames)

    def _role_snapshot(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        snapshot_format: str,
        compact: bool,
        depth: int | None,
        frame_selector: str | None,
        root_selector: str | None,
    ) -> tuple[dict[str, Any], int, int, int]:
        generation = runtime_state.next_ref_generation(target_id=tab.target_id)
        stored_refs: list[BrowserStoredRef] = []
        frames: list[dict[str, Any]] = []
        for frame, frame_path in _snapshot_root_contexts(
            page,
            frame_selector=frame_selector,
            root_selector=root_selector,
        ):
            aria_snapshot = _snapshot_root_locator(
                frame,
                root_selector=root_selector,
            ).aria_snapshot(**_timeout_kwargs(_probe_timeout(None)))
            built = build_role_snapshot(
                str(aria_snapshot or ""),
                compact=compact,
                max_depth=depth,
            )
            frame_refs: list[dict[str, Any]] = []
            for ref in built.refs:
                stored = BrowserStoredRef(
                    ref=f"r{len(stored_refs) + 1}",
                    scope_selector=root_selector,
                    nth=ref.nth,
                    generation=generation,
                    snapshot_format=snapshot_format,
                    frame_path=frame_path,
                    label=ref.name,
                    role=ref.role,
                    text=ref.name,
                    tag=ref.role,
                )
                stored_refs.append(stored)
                frame_refs.append(
                    {
                        "ref": stored.ref,
                        "selector": stored.selector,
                        "scope_selector": stored.scope_selector,
                        "uid": stored.uid,
                        "nth": stored.nth,
                        "generation": stored.generation,
                        "frame_path": list(stored.frame_path),
                        "label": stored.label,
                        "role": stored.role,
                        "text": stored.text,
                        "tag": stored.tag,
                        "format": snapshot_format,
                    }
                )
            frames.append(
                {
                    "frame_path": list(frame_path),
                    "snapshot": built.snapshot,
                    "refs": frame_refs,
                    "ref_count": len(frame_refs),
                }
            )
        refs_tuple = tuple(stored_refs)
        self.ref_store.save_tab_refs(
            profile_name=plan.profile.name,
            target_id=tab.target_id,
            refs=refs_tuple,
        )
        combined_snapshot = _combine_frame_snapshots(frames)
        return {
            "snapshot": combined_snapshot,
            "frames": frames,
            "refs": [frame_ref for frame in frames for frame_ref in frame["refs"]],
            "stats": _role_snapshot_stats(snapshot=combined_snapshot, refs=refs_tuple),
        }, len(refs_tuple), len(frames), generation

    def _interactive_snapshot(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        snapshot_format: str,
        snapshot_mode: str | None,
        limit: Any,
        compact: bool,
        depth: int | None,
        payload: Mapping[str, Any],
        frame_selector: str | None,
        root_selector: str | None,
    ) -> tuple[dict[str, Any], int, int, int]:
        effective_limit = _interactive_snapshot_limit(payload, snapshot_format, limit)
        role_snapshot = self._interactive_role_snapshot(
            plan=plan,
            tab=tab,
            page=page,
            runtime_state=runtime_state,
            snapshot_format=snapshot_format,
            snapshot_mode=snapshot_mode,
            limit=effective_limit,
            compact=compact,
            depth=depth,
            frame_selector=frame_selector,
            root_selector=root_selector,
        )
        if role_snapshot is not None:
            return role_snapshot

        return self._dom_interactive_snapshot(
            plan=plan,
            tab=tab,
            page=page,
            runtime_state=runtime_state,
            snapshot_format=snapshot_format,
            snapshot_mode=snapshot_mode,
            limit=effective_limit,
            frame_selector=frame_selector,
            root_selector=root_selector,
        )

    def _interactive_role_snapshot(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        snapshot_format: str,
        snapshot_mode: str | None,
        limit: Any,
        compact: bool,
        depth: int | None,
        frame_selector: str | None,
        root_selector: str | None,
    ) -> tuple[dict[str, Any], int, int, int] | None:
        stored_refs: list[BrowserStoredRef] = []
        generation = runtime_state.next_ref_generation(target_id=tab.target_id)
        max_items = limit
        effective_compact = compact
        if snapshot_mode == "focused":
            effective_compact = True
        frames: list[dict[str, Any]] = []
        for frame, frame_path in _snapshot_root_contexts(
            page,
            frame_selector=frame_selector,
            root_selector=root_selector,
        ):
            try:
                aria_snapshot = _snapshot_root_locator(
                    frame,
                    root_selector=root_selector,
                ).aria_snapshot(
                    **_timeout_kwargs(_probe_timeout(None))
                )
            except Exception:  # noqa: BLE001
                return None
            remaining_refs = None
            if max_items is not None:
                remaining_refs = max(0, max_items - len(stored_refs))
                if remaining_refs == 0:
                    break
            built = build_role_snapshot(
                str(aria_snapshot or ""),
                compact=effective_compact,
                max_depth=depth,
                interactive_only=True,
                max_refs=remaining_refs,
            )
            candidate_refs = list(built.refs)
            if snapshot_mode != "wide":
                candidate_refs = [
                    ref
                    for ref in candidate_refs
                    if not (
                        ref.role == "link"
                        and _is_low_value_interactive_name(ref.name)
                    )
                ]
            frame_refs: list[BrowserStoredRef] = []
            for ref in candidate_refs:
                stored = BrowserStoredRef(
                    ref=f"r{len(stored_refs) + 1}",
                    scope_selector=root_selector,
                    nth=ref.nth,
                    generation=generation,
                    snapshot_format=snapshot_format,
                    frame_path=frame_path,
                    label=ref.name,
                    role=ref.role,
                    text=ref.name,
                    tag=ref.role,
                )
                stored_refs.append(stored)
                frame_refs.append(stored)
            if frame_refs:
                frames.append(
                    {
                        "frame_path": list(frame_path),
                        "snapshot": built.snapshot,
                        "refs": self._interactive_refs_payload(
                            refs=tuple(frame_refs),
                            snapshot_format=snapshot_format,
                        ),
                        "ref_count": len(frame_refs),
                    }
                )
            if max_items is not None and len(stored_refs) >= max_items:
                break

        if not stored_refs:
            return None
        if _interactive_role_snapshot_is_too_sparse(
            snapshot_mode=snapshot_mode,
            root_selector=root_selector,
            ref_count=len(stored_refs),
        ):
            return None
        refs_tuple = tuple(stored_refs)
        self.ref_store.save_tab_refs(
            profile_name=plan.profile.name,
            target_id=tab.target_id,
            refs=refs_tuple,
        )
        combined_snapshot = _combine_frame_snapshots(frames)
        return {
            "snapshot": combined_snapshot,
            "frames": frames,
            "refs": self._interactive_refs_payload(
                refs=refs_tuple,
                snapshot_format=snapshot_format,
            ),
            "stats": _role_snapshot_stats(snapshot=combined_snapshot, refs=refs_tuple),
        }, len(refs_tuple), len(frames), generation

    def _interactive_ref_line(self, *, item: BrowserStoredRef, indent: int = 0) -> str:
        role = str(item.role or "generic").strip() or "generic"
        line = f"- {role}"
        name = _normalize_optional_text(item.label or item.text)
        if name is not None:
            line += f' "{name}"'
        line += f" [ref={item.ref}]"
        if item.nth is not None:
            line += f" [nth={item.nth}]"
        return f'{"  " * indent}{line}'

    def _interactive_frame_snapshot(
        self,
        *,
        refs: tuple[BrowserStoredRef, ...],
        root_selector: str | None = None,
    ) -> str:
        if not refs:
            return "(no interactive elements)"
        default_scope = _normalize_optional_text(root_selector)
        grouped_refs: dict[str, list[BrowserStoredRef]] = {}
        scope_order: list[str] = []
        ungrouped_refs: list[BrowserStoredRef] = []
        for item in refs:
            scope_selector = _normalize_optional_text(item.scope_selector)
            if scope_selector is None or scope_selector == default_scope:
                ungrouped_refs.append(item)
                continue
            if scope_selector not in grouped_refs:
                grouped_refs[scope_selector] = []
                scope_order.append(scope_selector)
            grouped_refs[scope_selector].append(item)

        lines: list[str] = []
        for item in ungrouped_refs:
            lines.append(self._interactive_ref_line(item=item))
        for scope_selector in scope_order:
            lines.append(f'- scope "{scope_selector}":')
            for item in grouped_refs[scope_selector]:
                lines.append(self._interactive_ref_line(item=item, indent=1))
        return "\n".join(lines)

    def _interactive_refs_payload(
        self,
        *,
        refs: tuple[BrowserStoredRef, ...],
        snapshot_format: str,
    ) -> list[dict[str, Any]]:
        return [
            {
                "ref": item.ref,
                "selector": item.selector,
                "scope_selector": item.scope_selector,
                "uid": item.uid,
                "nth": item.nth,
                "generation": item.generation,
                "frame_path": list(item.frame_path),
                "label": item.label,
                "role": item.role,
                "text": item.text,
                "tag": item.tag,
                "format": snapshot_format,
            }
            for item in refs
        ]

    def _dom_interactive_snapshot(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        snapshot_format: str,
        snapshot_mode: str | None,
        limit: Any,
        frame_selector: str | None,
        root_selector: str | None,
    ) -> tuple[dict[str, Any], int, int, int]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                return self._dom_interactive_snapshot_once(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    snapshot_format=snapshot_format,
                    snapshot_mode=snapshot_mode,
                    limit=limit,
                    frame_selector=frame_selector,
                    root_selector=root_selector,
                )
            except Exception as exc:  # noqa: BLE001
                if attempt == 0 and _is_frame_detached_error(exc):
                    last_error = exc
                    continue
                raise
        assert last_error is not None
        raise last_error

    def _dom_interactive_snapshot_once(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        snapshot_format: str,
        snapshot_mode: str | None,
        limit: Any,
        frame_selector: str | None,
        root_selector: str | None,
    ) -> tuple[dict[str, Any], int, int, int]:
        snapshot_candidates: list[tuple[tuple[int, ...], dict[str, Any]]] = []
        generation = runtime_state.next_ref_generation(target_id=tab.target_id)
        max_items = limit
        for frame, frame_path in _snapshot_root_contexts(
            page,
            frame_selector=frame_selector,
            root_selector=root_selector,
        ):
            raw_items = frame.evaluate(_INTERACTIVE_SNAPSHOT_EXPRESSION, root_selector)
            if not isinstance(raw_items, list):
                raise BrowserValidationError(
                    "Interactive snapshot did not return a list of elements.",
                )
            candidate_items = [item for item in raw_items if isinstance(item, dict)]
            if snapshot_mode != "wide":
                candidate_items = [
                    item
                    for item in candidate_items
                    if (
                        _snapshot_item_visible(item)
                        and not _snapshot_item_disabled(item)
                        and not _snapshot_item_is_low_value_boilerplate(item)
                    )
                ]
                candidate_items = [
                    item
                    for _index, item in sorted(
                        enumerate(candidate_items),
                        key=lambda entry: (-_snapshot_item_priority(entry[1]), entry[0]),
                    )
                ]
            for item in candidate_items:
                if not isinstance(item, dict):
                    continue
                selector = item.get("selector")
                if not isinstance(selector, str) or not selector.strip():
                    continue
                snapshot_candidates.append((frame_path, dict(item)))
                if max_items is not None and len(snapshot_candidates) >= max_items:
                    break
            if max_items is not None and len(snapshot_candidates) >= max_items:
                break

        semantic_counts: dict[tuple[str, str], int] = {}
        for _frame_path, item in snapshot_candidates:
            semantic_key = _snapshot_item_semantic_key(item)
            if semantic_key is None:
                continue
            semantic_counts[semantic_key] = semantic_counts.get(semantic_key, 0) + 1

        semantic_seen: dict[tuple[str, str], int] = {}
        resolved_items: list[BrowserStoredRef] = []
        for frame_path, item in snapshot_candidates:
            semantic_key = _snapshot_item_semantic_key(item)
            nth: int | None = None
            if semantic_key is not None and semantic_counts.get(semantic_key, 0) > 1:
                nth = semantic_seen.get(semantic_key, 0)
                semantic_seen[semantic_key] = nth + 1
            resolved_items.append(
                BrowserStoredRef(
                    ref=f"r{len(resolved_items) + 1}",
                    selector=str(item["selector"]),
                    scope_selector=(
                        str(item["scope_selector"]).strip()
                        if item.get("scope_selector") is not None
                        and str(item["scope_selector"]).strip()
                        else root_selector
                    ),
                    nth=nth,
                    generation=generation,
                    snapshot_format=snapshot_format,
                    frame_path=frame_path,
                    label=(
                        str(item["label"]) if item.get("label") is not None else None
                    ),
                    role=(
                        str(item["role"]) if item.get("role") is not None else None
                    ),
                    text=(
                        str(item["text"]) if item.get("text") is not None else None
                    ),
                    tag=str(item["tag"]) if item.get("tag") is not None else None,
                )
            )

        refs_tuple = tuple(resolved_items)
        self.ref_store.save_tab_refs(
            profile_name=plan.profile.name,
            target_id=tab.target_id,
            refs=refs_tuple,
        )
        grouped_frames: dict[tuple[int, ...], list[BrowserStoredRef]] = {}
        for item in refs_tuple:
            grouped_frames.setdefault(item.frame_path, []).append(item)
        frames = [
            {
                "frame_path": list(frame_path),
                "snapshot": self._interactive_frame_snapshot(
                    refs=tuple(items),
                    root_selector=root_selector,
                ),
                "refs": self._interactive_refs_payload(
                    refs=tuple(items),
                    snapshot_format=snapshot_format,
                ),
                "ref_count": len(items),
            }
            for frame_path, items in grouped_frames.items()
        ]
        combined_snapshot = _combine_frame_snapshots(frames)
        return {
            "snapshot": combined_snapshot,
            "frames": frames,
            "refs": self._interactive_refs_payload(
                refs=refs_tuple,
                snapshot_format=snapshot_format,
            ),
            "stats": _role_snapshot_stats(snapshot=combined_snapshot, refs=refs_tuple),
        }, len(refs_tuple), len(grouped_frames), generation


@dataclass(slots=True)
class McpBackedActionEngine(BrowserActionEngine):
    mcp_pool: ChromeMcpClientPool
    ref_store: BrowserRefStore
    family: BrowserActionFamily = "mcp-backed"
    wait_poll_interval_s: float = 0.1
    monotonic: Any = time.monotonic
    sleep: Any = time.sleep

    def supports(
        self,
        *,
        command: BrowserPageActionCommand,
    ) -> bool:
        return command.kind in _MCP_SUPPORTED_KINDS

    def execute(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab | None,
        command: BrowserPageActionCommand,
    ) -> BrowserActionResult:
        if tab is None:
            raise BrowserValidationError("mcp-backed actions require a tab.")

        result_value, resolved_uid = self._execute_on_tab(
            plan=plan,
            tab=tab,
            runtime_state=runtime_state,
            command=command,
        )
        if command.kind == "snapshot" and isinstance(result_value, dict):
            runtime_state.remember_page_snapshot(
                target_id=tab.target_id,
                generation=int(result_value.get("generation") or 1),
                snapshot_format=str(result_value.get("format") or "snapshot"),
                ref_count=int(result_value.get("ref_count") or 0),
                frame_count=int(result_value.get("frame_count") or 0),
            )
        else:
            runtime_state.remember_page_action(
                target_id=tab.target_id,
                action_kind=command.kind,
            )
        return BrowserActionResult(
            command=command,
            ok=True,
            target_id=tab.target_id,
            value={
                "engine": self.family,
                "control_family": plan.control_family,
                "profile": plan.profile.name,
                "tab": _serialize_tab(tab),
                "ref": command.target.ref,
                "selector": command.target.selector,
                "uid": resolved_uid,
                "payload": dict(command.payload),
                "result": result_value,
            },
            message=f"Executed {command.kind} via mcp-backed.",
        )

    def clear_profile(
        self,
        *,
        profile_name: str,
    ) -> None:
        del profile_name

    def _execute_on_tab(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
    ) -> tuple[Any, str | None]:
        timeout_ms = command.timeout_ms
        uid = self._resolve_uid(
            plan=plan,
            tab=tab,
            runtime_state=runtime_state,
            command=command,
        )

        if command.kind == "click":
            self.mcp_pool.click_element(
                profile_name=plan.profile.name,
                system=plan.system,
                target_id=tab.target_id,
                uid=uid or self._require_ref(command),
                user_data_dir=plan.profile.user_data_dir,
                double_click=bool(command.payload.get("double_click", False)),
            )
            return {"kind": "click"}, uid

        if command.kind in {"type", "fill"}:
            if command.kind == "fill":
                fields = _normalize_form_fields(command.payload.get("fields"))
                if fields:
                    filled: list[dict[str, Any]] = []
                    for field in fields:
                        resolved_uid = self._resolve_secondary_uid(
                            plan=plan,
                            tab=tab,
                            runtime_state=runtime_state,
                            raw_ref=str(field["ref"]),
                        )
                        value_repr = (
                            field["value"]
                            if isinstance(field["value"], str)
                            else str(field["value"]).lower()
                            if isinstance(field["value"], bool)
                            else str(field["value"])
                        )
                        self.mcp_pool.fill_element(
                            profile_name=plan.profile.name,
                            system=plan.system,
                            target_id=tab.target_id,
                            uid=resolved_uid,
                            value=value_repr,
                            user_data_dir=plan.profile.user_data_dir,
                        )
                        filled.append(
                            {
                                "ref": field["ref"],
                                "uid": resolved_uid,
                                "type": field["type"],
                                "value": value_repr,
                            }
                        )
                    return {"kind": "fill", "fields": filled}, uid

            text = _payload_text(command.payload, key="text")
            self.mcp_pool.fill_element(
                profile_name=plan.profile.name,
                system=plan.system,
                target_id=tab.target_id,
                uid=uid or self._require_ref(command),
                value=text,
                user_data_dir=plan.profile.user_data_dir,
            )
            return {"kind": command.kind, "text": text}, uid

        if command.kind == "press":
            key = _payload_text(command.payload, key="key")
            self.mcp_pool.press_key(
                profile_name=plan.profile.name,
                system=plan.system,
                target_id=tab.target_id,
                key=key,
                user_data_dir=plan.profile.user_data_dir,
            )
            return {"kind": "press", "key": key}, uid

        if command.kind == "hover":
            self.mcp_pool.hover_element(
                profile_name=plan.profile.name,
                system=plan.system,
                target_id=tab.target_id,
                uid=uid or self._require_ref(command),
                user_data_dir=plan.profile.user_data_dir,
            )
            return {"kind": "hover"}, uid

        if command.kind == "drag":
            source_ref = _drag_source_ref(command)
            if source_ref is None:
                raise BrowserValidationError(
                    "mcp-backed drag requires start_ref/end_ref style ref targeting.",
                )
            target_uid = self._resolve_secondary_uid(
                plan=plan,
                tab=tab,
                runtime_state=runtime_state,
                raw_ref=_drag_target_ref(command.payload) or _payload_text(command.payload, key="target_ref", required=False)
                or _payload_text(command.payload, key="to_ref", required=True),
            )
            self.mcp_pool.drag_element(
                profile_name=plan.profile.name,
                system=plan.system,
                target_id=tab.target_id,
                from_uid=self._resolve_secondary_uid(
                    plan=plan,
                    tab=tab,
                    runtime_state=runtime_state,
                    raw_ref=source_ref,
                ),
                to_uid=target_uid,
                user_data_dir=plan.profile.user_data_dir,
            )
            return {
                "kind": "drag",
                "start_ref": source_ref,
                "target_uid": target_uid,
            }, uid

        if command.kind == "resize":
            width = int(_payload_number_any(command.payload, "width") or 0)
            height = int(_payload_number_any(command.payload, "height") or 0)
            if width < 1 or height < 1:
                raise BrowserValidationError("payload.width and payload.height are required.")
            self.mcp_pool.resize_page(
                profile_name=plan.profile.name,
                system=plan.system,
                target_id=tab.target_id,
                width=width,
                height=height,
                user_data_dir=plan.profile.user_data_dir,
            )
            return {
                "kind": "resize",
                "width": width,
                "height": height,
            }, uid

        if command.kind == "select":
            values = command.payload.get("values")
            if isinstance(values, (list, tuple)):
                normalized_values = [str(item).strip() for item in values if str(item).strip()]
                if len(normalized_values) != 1:
                    raise BrowserValidationError(
                        "mcp-backed select currently supports exactly one value.",
                    )
                value = normalized_values[0]
            else:
                value = _payload_text(command.payload, key="value")
            self.mcp_pool.fill_element(
                profile_name=plan.profile.name,
                system=plan.system,
                target_id=tab.target_id,
                uid=uid or self._require_ref(command),
                value=value,
                user_data_dir=plan.profile.user_data_dir,
            )
            return {"kind": "select", "selected": [value]}, uid

        if command.kind == "wait":
            return self._wait(plan=plan, tab=tab, command=command, timeout_ms=timeout_ms), uid

        if command.kind == "snapshot":
            return self._snapshot(
                plan=plan,
                tab=tab,
                runtime_state=runtime_state,
                command=command,
            ), uid

        if command.kind == "screenshot":
            image_type = _payload_text(command.payload, key="type", required=False) or "png"
            screenshot = self.mcp_pool.take_screenshot(
                profile_name=plan.profile.name,
                system=plan.system,
                target_id=tab.target_id,
                user_data_dir=plan.profile.user_data_dir,
                uid=uid,
                full_page=bool(command.payload.get("full_page", False)),
                image_format=image_type,
            )
            return {
                "kind": "screenshot",
                "content_type": f"image/{image_type}",
                "encoding": "base64",
                "data": base64.b64encode(screenshot).decode("ascii"),
            }, uid

        if command.kind == "evaluate":
            expression = _payload_text_any(command.payload, "expression", "fn")
            if expression is None:
                raise BrowserValidationError("payload.expression or payload.fn is required.")
            args = command.payload.get("args")
            normalized_args = [str(item) for item in args] if isinstance(args, list) else None
            if "arg" in command.payload:
                normalized_args = [json.dumps(command.payload.get("arg"))]
            if command.target.ref is not None:
                resolved_uid = uid or self._require_ref(command)
                normalized_args = [resolved_uid, *(normalized_args or [])]
            result = self.mcp_pool.evaluate_script(
                profile_name=plan.profile.name,
                system=plan.system,
                target_id=tab.target_id,
                fn=expression,
                user_data_dir=plan.profile.user_data_dir,
                args=normalized_args,
            )
            return {
                "kind": "evaluate",
                "expression": expression,
                "value": result,
            }, uid

        raise BrowserValidationError(
            f"Action engine '{self.family}' does not support '{command.kind}'.",
        )

    def _resolve_uid(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
    ) -> str | None:
        if command.target.ref is None:
            if command.target.selector is not None and command.kind in _MCP_TARGETED_KINDS:
                raise BrowserValidationError(
                    f"mcp-backed action '{command.kind}' requires ref targeting; selectors are not supported.",
                )
            return None
        for item in self.ref_store.get_tab_refs(
            profile_name=plan.profile.name,
            target_id=tab.target_id,
        ):
            if item.ref == command.target.ref:
                page_state = runtime_state.page_state(target_id=tab.target_id) or {}
                current_generation = int(page_state.get("current_ref_generation") or 0)
                if current_generation and item.generation != current_generation:
                    raise BrowserValidationError(
                        f"Browser ref '{command.target.ref}' is stale for tab '{tab.target_id}'.",
                    )
                return item.uid or item.ref
        return command.target.ref

    @staticmethod
    def _require_ref(command: BrowserPageActionCommand) -> str:
        if command.target.ref is None:
            raise BrowserValidationError(
                f"mcp-backed action '{command.kind}' requires ref targeting.",
            )
        return command.target.ref

    def _resolve_secondary_uid(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        runtime_state: BrowserProfileRuntimeState,
        raw_ref: str,
    ) -> str:
        for item in self.ref_store.get_tab_refs(
            profile_name=plan.profile.name,
            target_id=tab.target_id,
        ):
            if item.ref == raw_ref:
                page_state = runtime_state.page_state(target_id=tab.target_id) or {}
                current_generation = int(page_state.get("current_ref_generation") or 0)
                if current_generation and item.generation != current_generation:
                    raise BrowserValidationError(
                        f"Browser ref '{raw_ref}' is stale for tab '{tab.target_id}'.",
                    )
                return item.uid or item.ref
        return raw_ref

    def _wait(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        command: BrowserPageActionCommand,
        timeout_ms: int | None,
    ) -> dict[str, Any]:
        selector = command.target.selector
        if selector is not None:
            state = _payload_text_any(command.payload, "state") or "visible"
            self._poll_until(
                timeout_ms=timeout_ms,
                predicate=lambda: self.mcp_pool.evaluate_script(
                    profile_name=plan.profile.name,
                    system=plan.system,
                    target_id=tab.target_id,
                    fn=self._selector_wait_expression(selector=selector, state=state),
                    user_data_dir=plan.profile.user_data_dir,
                ),
                satisfied=lambda value: bool(value),
                label=f"selector '{selector}' in state '{state}'",
            )
            return {"kind": "wait", "selector": selector, "state": state}

        text_values = _normalize_text_payload(_payload_value_any(command.payload, "text"))
        if text_values:
            self.mcp_pool.wait_for_text(
                profile_name=plan.profile.name,
                system=plan.system,
                target_id=tab.target_id,
                text=text_values,
                user_data_dir=plan.profile.user_data_dir,
                timeout_ms=timeout_ms,
            )
            return {"kind": "wait", "text": text_values}

        text_gone_values = _normalize_text_payload(
            _payload_value_any(command.payload, "text_gone", "textGone"),
        )
        if text_gone_values:
            target_text = text_gone_values[0]
            self._poll_until(
                timeout_ms=timeout_ms,
                predicate=lambda: self.mcp_pool.evaluate_script(
                    profile_name=plan.profile.name,
                    system=plan.system,
                    target_id=tab.target_id,
                    fn="() => document.body.innerText || ''",
                    user_data_dir=plan.profile.user_data_dir,
                ),
                satisfied=lambda value: isinstance(value, str) and target_text not in value,
                label=f"text '{target_text}' to disappear",
            )
            return {"kind": "wait", "text_gone": text_gone_values}

        url_pattern = _payload_text_any(command.payload, "url")
        if url_pattern is not None:
            self._poll_until(
                timeout_ms=timeout_ms,
                predicate=lambda: self._current_url(
                    plan=plan,
                    tab=tab,
                ),
                satisfied=lambda value: isinstance(value, str)
                and (
                    fnmatch(value, url_pattern)
                    if any(char in url_pattern for char in "*?[]")
                    else value == url_pattern
                ),
                label=f"url '{url_pattern}'",
            )
            return {"kind": "wait", "url": url_pattern}

        load_state = _payload_text_any(command.payload, "load_state", "loadState")
        if load_state is not None:
            normalized_state = load_state.strip().lower()
            if normalized_state == "networkidle":
                raise BrowserValidationError(
                    "mcp-backed wait does not support load_state=networkidle yet.",
                )
            self._poll_until(
                timeout_ms=timeout_ms,
                predicate=lambda: self.mcp_pool.evaluate_script(
                    profile_name=plan.profile.name,
                    system=plan.system,
                    target_id=tab.target_id,
                    fn="() => document.readyState",
                    user_data_dir=plan.profile.user_data_dir,
                ),
                satisfied=lambda value: self._ready_state_satisfied(
                    ready_state=value,
                    load_state=normalized_state,
                ),
                label=f"load_state '{normalized_state}'",
            )
            return {"kind": "wait", "load_state": normalized_state}

        expression = _payload_text_any(command.payload, "expression", "fn")
        if expression is not None:
            self._poll_until(
                timeout_ms=timeout_ms,
                predicate=lambda: self.mcp_pool.evaluate_script(
                    profile_name=plan.profile.name,
                    system=plan.system,
                    target_id=tab.target_id,
                    fn=expression,
                    user_data_dir=plan.profile.user_data_dir,
                ),
                satisfied=lambda value: bool(value),
                label="expression",
            )
            return {"kind": "wait", "expression": expression}

        delay_ms = _payload_number_any(command.payload, "delay_ms", "time_ms", "timeMs")
        if delay_ms is not None:
            self.sleep(float(delay_ms) / 1000.0)
            return {"kind": "wait", "delay_ms": float(delay_ms)}

        raise BrowserValidationError(
            "wait requires selector, payload.text, payload.text_gone, payload.url, payload.load_state, payload.expression/payload.fn, or payload.delay_ms.",
        )

    @staticmethod
    def _selector_wait_expression(*, selector: str, state: str) -> str:
        selector_json = json.dumps(selector)
        normalized_state = state.strip().lower()
        if normalized_state == "attached":
            return f"() => Boolean(document.querySelector({selector_json}))"
        if normalized_state in {"hidden", "detached"}:
            return (
                "() => {"
                f" const el = document.querySelector({selector_json});"
                " if (!el) return true;"
                " const style = window.getComputedStyle(el);"
                " if (!style) return false;"
                " const rect = el.getBoundingClientRect();"
                " return el.hidden || el.getAttribute('aria-hidden') === 'true' || "
                "style.display === 'none' || style.visibility === 'hidden' || "
                "style.visibility === 'collapse' || Number(style.opacity || '1') === 0 || "
                "(rect.width === 0 && rect.height === 0);"
                " }"
            )
        return (
            "() => {"
            f" const el = document.querySelector({selector_json});"
            " if (!el) return false;"
            " const style = window.getComputedStyle(el);"
            " if (!style) return true;"
            " const rect = el.getBoundingClientRect();"
            " return !el.hidden && el.getAttribute('aria-hidden') !== 'true' && "
            "style.display !== 'none' && style.visibility !== 'hidden' && "
            "style.visibility !== 'collapse' && Number(style.opacity || '1') !== 0 && "
            "(rect.width > 0 || rect.height > 0);"
            " }"
        )

    @staticmethod
    def _ready_state_satisfied(*, ready_state: Any, load_state: str) -> bool:
        normalized = str(ready_state or "").strip().lower()
        if load_state == "domcontentloaded":
            return normalized in {"interactive", "complete"}
        if load_state == "load":
            return normalized == "complete"
        return False

    def _snapshot(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
    ) -> dict[str, Any]:
        snapshot_format = (
            _payload_text(command.payload, key="format", required=False) or "interactive"
        ).lower()
        if command.target.selector is not None or _snapshot_frame_selector(command.payload) is not None:
            raise BrowserValidationError(
                "mcp-backed snapshots do not support selector/frame scoped snapshots yet; snapshot the whole page and use refs.",
            )
        ref_count = 0
        frame_count = 0
        generation = 0
        if snapshot_format == "html":
            value = self.mcp_pool.evaluate_script(
                profile_name=plan.profile.name,
                system=plan.system,
                target_id=tab.target_id,
                fn="() => document.documentElement?.outerHTML ?? ''",
                user_data_dir=plan.profile.user_data_dir,
            )
        elif snapshot_format == "text":
            value = self.mcp_pool.evaluate_script(
                profile_name=plan.profile.name,
                system=plan.system,
                target_id=tab.target_id,
                fn="() => document.body?.innerText ?? ''",
                user_data_dir=plan.profile.user_data_dir,
            )
        elif snapshot_format == "title":
            value = self.mcp_pool.evaluate_script(
                profile_name=plan.profile.name,
                system=plan.system,
                target_id=tab.target_id,
                fn="() => document.title",
                user_data_dir=plan.profile.user_data_dir,
            )
        elif snapshot_format == "url":
            value = self._current_url(plan=plan, tab=tab)
        elif snapshot_format == "interactive":
            value, ref_count, frame_count, generation = self._interactive_snapshot(
                plan=plan,
                tab=tab,
                runtime_state=runtime_state,
                snapshot_format=snapshot_format,
                payload=command.payload,
                limit=command.payload.get("limit"),
            )
        else:
            raise BrowserValidationError(
                f"Unsupported mcp-backed snapshot format '{snapshot_format}'.",
            )
        return {
            "kind": "snapshot",
            "format": snapshot_format,
            "generation": generation,
            "value": value,
            "ref_count": ref_count,
            "frame_count": frame_count,
        }

    def _interactive_snapshot(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        runtime_state: BrowserProfileRuntimeState,
        snapshot_format: str,
        payload: Mapping[str, Any],
        limit: Any,
    ) -> tuple[list[dict[str, Any]], int, int, int]:
        root = self.mcp_pool.take_snapshot(
            profile_name=plan.profile.name,
            system=plan.system,
            target_id=tab.target_id,
            user_data_dir=plan.profile.user_data_dir,
        )
        max_items = _interactive_snapshot_limit(payload, snapshot_format, limit)
        generation = runtime_state.next_ref_generation(target_id=tab.target_id)
        refs = self._build_refs_from_snapshot(
            root=root,
            limit=max_items,
            generation=generation,
            snapshot_format=snapshot_format,
        )
        self.ref_store.save_tab_refs(
            profile_name=plan.profile.name,
            target_id=tab.target_id,
            refs=refs,
        )
        return [
            {
                "ref": item.ref,
                "selector": item.selector,
                "scope_selector": item.scope_selector,
                "uid": item.uid,
                "nth": item.nth,
                "generation": item.generation,
                "frame_path": list(item.frame_path),
                "label": item.label,
                "role": item.role,
                "text": item.text,
                "tag": item.tag,
                "format": snapshot_format,
            }
            for item in refs
        ], len(refs), len({item.frame_path for item in refs}) if refs else 0, generation

    def _build_refs_from_snapshot(
        self,
        *,
        root: dict[str, Any],
        limit: int | None,
        generation: int,
        snapshot_format: str,
    ) -> tuple[BrowserStoredRef, ...]:
        resolved: list[BrowserStoredRef] = []

        def _visit(node: dict[str, Any]) -> None:
            if limit is not None and len(resolved) >= limit:
                return
            normalized = _normalize_snapshot_node(node)
            if normalized is None:
                return
            uid = normalized.get("id")
            role_raw = normalized.get("role")
            role = str(role_raw).strip().lower() if role_raw is not None else ""
            name = (
                str(normalized.get("name")).strip()
                if normalized.get("name") is not None
                else None
            )
            value = (
                str(normalized.get("value")).strip()
                if normalized.get("value") is not None
                else None
            )
            description = (
                str(normalized.get("description")).strip()
                if normalized.get("description") is not None
                else None
            )
            if isinstance(uid, str) and uid.strip() and role in _MCP_INTERACTIVE_ROLES:
                resolved.append(
                    BrowserStoredRef(
                        ref=f"r{len(resolved) + 1}",
                        uid=uid.strip(),
                        scope_selector=None,
                        generation=generation,
                        snapshot_format=snapshot_format,
                        label=name,
                        role=role,
                        text=value or description or name,
                        tag=role,
                    )
                )
                if limit is not None and len(resolved) >= limit:
                    return

            children = normalized.get("children")
            if isinstance(children, list):
                for child in children:
                    if not isinstance(child, dict):
                        continue
                    _visit(child)
                    if limit is not None and len(resolved) >= limit:
                        return

        _visit(root)
        return tuple(resolved)

    def _current_url(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
    ) -> Any:
        return self.mcp_pool.evaluate_script(
            profile_name=plan.profile.name,
            system=plan.system,
            target_id=tab.target_id,
            fn="() => window.location.href",
            user_data_dir=plan.profile.user_data_dir,
        )

    def _poll_until(
        self,
        *,
        timeout_ms: int | None,
        predicate,
        satisfied,
        label: str,
    ) -> Any:
        deadline = None
        if timeout_ms is not None:
            deadline = self.monotonic() + (float(timeout_ms) / 1000.0)
        while True:
            value = predicate()
            if satisfied(value):
                return value
            if deadline is not None and self.monotonic() >= deadline:
                raise BrowserValidationError(f"Timed out while waiting for {label}.")
            self.sleep(self.wait_poll_interval_s)
