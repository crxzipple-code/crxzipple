"""Browser-side JavaScript expressions used by the Playwright action engine."""

from __future__ import annotations

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
