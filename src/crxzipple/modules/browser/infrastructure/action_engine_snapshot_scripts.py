"""Interactive snapshot browser-side JavaScript expression."""

from __future__ import annotations

from .action_engine_script_markers import (
    _INTERACTIVE_SNAPSHOT_MARKER,
)

_INTERACTIVE_SNAPSHOT_EXPRESSION = f"""
(rootSelector) => {{
  const {_INTERACTIVE_SNAPSHOT_MARKER} = true;
  const normalizedRootSelector = typeof rootSelector === "string" ? rootSelector.trim() : "";
  const rootsFor = (selector) => {{
    if (!selector) return [document];
    try {{
      const root = document.querySelector(selector);
      return root ? [root] : [document];
    }} catch (_error) {{
      return [document];
    }}
  }};
  const queryAllDeep = (root, selector) => {{
    const resolved = [];
    const visit = (scope) => {{
      if (!scope) return;
      if (scope instanceof Element && scope.matches(selector)) {{
        resolved.push(scope);
      }}
      if (typeof scope.querySelectorAll !== "function") return;
      const matches = Array.from(scope.querySelectorAll(selector));
      resolved.push(...matches);
      const descendants = Array.from(scope.querySelectorAll("*"));
      for (const descendant of descendants) {{
        if (descendant.shadowRoot) visit(descendant.shadowRoot);
      }}
    }};
    visit(root);
    return resolved;
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
  const textFor = (element) => {{
    const text = (element.innerText || element.textContent || "").trim().replace(/\\s+/g, " ");
    return text || null;
  }};
  const ownTextFor = (element) => {{
    if (!(element instanceof Element)) return textFor(element);
    const text = Array.from(element.childNodes || [])
      .filter((node) => node.nodeType === Node.TEXT_NODE)
      .map((node) => (node.textContent || "").trim())
      .filter(Boolean)
      .join(" ")
      .replace(/\\s+/g, " ")
      .trim();
    return text || textFor(element);
  }};
  const classTextFor = (element) => {{
    if (!(element instanceof Element)) return "";
    return String(element.className || "").toLowerCase();
  }};
  const ancestorClassTextFor = (element, maxDepth = 3) => {{
    if (!(element instanceof Element)) return "";
    const parts = [];
    let current = element.parentElement;
    let depth = 0;
    while (current && current !== document.body && depth < maxDepth) {{
      parts.push(classTextFor(current));
      current = current.parentElement;
      depth += 1;
    }}
    return parts.join(" ");
  }};
  const actionableClassFor = (element) => {{
    const classes = `${{classTextFor(element)}} ${{ancestorClassTextFor(element)}}`;
    return /(^|[-_\\s])(btn|button|link|tab|nav|option|select|picker|calendar|date|city|search|seg|segment|route|from|to|origin|destination|choice|toggle)([-_\\s]|$)/i.test(classes);
  }};
  const hasPickerAncestor = (element) => {{
    if (!(element instanceof Element)) return false;
    try {{
      return !!element.closest(
        "[class*='picker'],[class*='calendar'],[class*='datepicker'],[class*='date-picker'],[class*='time-picker']"
      );
    }} catch (_error) {{
      return false;
    }}
  }};
  const looksLikePickerChoice = (element) => {{
    if (!(element instanceof Element)) return false;
    const role = (element.getAttribute("role") || "").toLowerCase();
    if (["gridcell", "option", "menuitem"].includes(role)) return true;
    if (element.hasAttribute("aria-selected")) return true;
    const tag = element.tagName.toLowerCase();
    const cls = classTextFor(element);
    const pickerClass = /picker|calendar|datepicker|date-picker|time-picker|time-panel/.test(cls);
    const cellClass = /cell|day|date|time|hour|minute|month|year/.test(cls);
    if (pickerClass && cellClass) return true;
    if (hasPickerAncestor(element) && ["td", "li", "span", "div", "button"].includes(tag)) {{
      const ownText = ownTextFor(element);
      const childCount = element.children ? element.children.length : 0;
      return !!ownText && ownText.length <= 80 && (tag === "td" || tag === "li" || childCount <= 3 || cellClass);
    }}
    return false;
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
    if (looksLikePickerChoice(element)) return "option";
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
    if (element.hasAttribute("onclick")) return "button";
    if (element.hasAttribute("tabindex")) return "button";
    if (looksLikeVisualControl(element)) return "button";
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
  const rectFor = (element) => {{
    if (!(element instanceof Element)) return null;
    const rect = element.getBoundingClientRect();
    if (!rect) return null;
    const round = (value) => Math.round(Number(value || 0) * 100) / 100;
    return {{
      x: round(rect.x),
      y: round(rect.y),
      width: round(rect.width),
      height: round(rect.height)
    }};
  }};
  const hitTestMatches = (element) => {{
    if (!(element instanceof Element)) return false;
    const rect = element.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return false;
    const x = Math.max(0, Math.min(window.innerWidth - 1, rect.left + rect.width / 2));
    const y = Math.max(0, Math.min(window.innerHeight - 1, rect.top + rect.height / 2));
    let hit = document.elementFromPoint(x, y);
    let depth = 0;
    while (hit && depth < 6) {{
      if (hit === element) return true;
      hit = hit.parentElement;
      depth += 1;
    }}
    return false;
  }};
  const evidenceFor = (element, role, label, rootScopedFallback) => {{
    const evidence = [];
    const tag = element.tagName.toLowerCase();
    if (["button", "input", "select", "textarea", "option"].includes(tag)) evidence.push("native-control");
    if (element.getAttribute("role")) evidence.push("aria-role");
    if (label || textFor(element)) evidence.push("visible-text");
    if (element.hasAttribute("onclick")) evidence.push("self-listener");
    if (element.hasAttribute("tabindex")) evidence.push("tabindex");
    if (looksLikePickerChoice(element)) evidence.push("picker-choice");
    if (hitTestMatches(element)) evidence.push("hit-test");
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element.isContentEditable) evidence.push("editable");
    if (looksLikeVisualControl(element) || rootScopedFallback) evidence.push("visual-fallback");
    return Array.from(new Set(evidence));
  }};
  const confidenceFor = (evidence) => {{
    const values = new Set(evidence || []);
    let score = 0.22;
    if (values.has("native-control")) score += 0.28;
    if (values.has("aria-role")) score += 0.18;
    if (values.has("self-listener")) score += 0.18;
    if (values.has("hit-test")) score += 0.14;
    if (values.has("editable")) score += 0.08;
    if (values.has("picker-choice")) score += 0.08;
    if (values.has("visible-text")) score += 0.06;
    if (values.has("visual-fallback")) score += 0.03;
    return Math.round(Math.min(score, 0.99) * 100) / 100;
  }};
  const looksLikeVisualControl = (element) => {{
    if (!(element instanceof HTMLElement)) return false;
    const tag = element.tagName.toLowerCase();
    if (!["div", "span", "p", "li", "td"].includes(tag)) return false;
    const label = (ownTextFor(element) || textFor(element) || "").trim();
    if (!label || label.length > 80) return false;
    const rect = element.getBoundingClientRect();
    if (!rect || rect.width < 8 || rect.height < 8 || rect.height > 160) return false;
    const childCount = element.children ? element.children.length : 0;
    if (childCount > 4) return false;
    const style = window.getComputedStyle(element);
    if (style && style.cursor === "pointer") return true;
    return actionableClassFor(element);
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
    "[role='option']",
    "[role='menuitem']",
    "[role='gridcell']",
    "[role='tab']",
    "[role='switch']",
    "[role='slider']",
    "[role='spinbutton']",
    "[aria-selected]",
    "[onclick]",
    "[tabindex]:not([tabindex='-1'])",
    "[class*='btn']",
    "[class*='btn'] *",
    "[class*='button']",
    "[class*='button'] *",
    "[class*='search']",
    "[class*='search'] *",
    "[class*='city']",
    "[class*='city'] *",
    "[class*='calendar']",
    "[class*='calendar'] *",
    "[class*='date']",
    "[class*='date'] *",
    "[class*='picker']",
    "[class*='picker'] *",
    "[class*='seg']",
    "[class*='seg'] *",
    "[class*='tab']",
    "[class*='tab'] *",
    "[class*='nav']",
    "[class*='nav'] *",
    ".ant-picker-cell",
    ".ant-picker-cell-inner",
    ".ant-picker-time-panel-cell",
    ".ant-picker-time-panel-cell-inner",
    ".calendar-day",
    ".datepicker-day",
    ".date-picker td",
    ".datepicker td",
    ".calendar td",
    ".el-date-table td",
    ".el-picker-panel td",
    "[class*='picker'] td",
    "[class*='picker'] li",
    "[class*='calendar'] td",
    "[class*='datepicker'] td"
  ].join(",");
  const scopedFallbackSelector = "td,li,button,a,input,select,textarea,[role],span,div";
  const seen = new Set();
  const roots = rootsFor(normalizedRootSelector);
  const elements = [];
  for (const root of roots) {{
    elements.push(...queryAllDeep(root, selector));
    if (normalizedRootSelector) {{
      elements.push(...queryAllDeep(root, scopedFallbackSelector));
    }}
  }}
  return elements.map((element) => {{
    const css = selectorFor(element);
    if (!css || seen.has(css)) return null;
    const tag = element.tagName.toLowerCase();
    const label = labelFor(element);
    const text = textFor(element);
    const role = roleFor(element);
    const ownText = ownTextFor(element);
    const style = element instanceof HTMLElement ? window.getComputedStyle(element) : null;
    const rootScopedFallback = !!normalizedRootSelector
      && ["td", "li", "span", "div"].includes(tag)
      && !!ownText
      && ownText.length <= 80
      && (
        looksLikePickerChoice(element)
        || element.hasAttribute("onclick")
        || element.hasAttribute("aria-selected")
        || (style && style.cursor === "pointer")
      );
    if (!role && !rootScopedFallback) return null;
    seen.add(css);
    const evidence = evidenceFor(element, role || "button", label || text, rootScopedFallback);
    return {{
      selector: css,
      scope_selector: normalizedRootSelector || null,
      label,
      role: role || "button",
      text,
      tag: element.tagName.toLowerCase(),
      bbox: rectFor(element),
      evidence,
      confidence: confidenceFor(evidence),
      backend_node_id: null,
      visible: isVisible(element),
      disabled: isDisabled(element),
      checked: !!(
        (element instanceof HTMLInputElement && ["checkbox", "radio"].includes((element.type || "").toLowerCase()) && element.checked)
        || element.getAttribute("aria-checked") === "true"
      ),
    }};
  }}).filter(Boolean);
}}
""".strip()

__all__ = (
    "_INTERACTIVE_SNAPSHOT_EXPRESSION",
)
