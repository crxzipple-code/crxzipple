"""Bulk selection browser-side JavaScript expressions."""

from __future__ import annotations

from .action_engine_script_markers import (
    _BULK_SELECTION_MARKER,
)

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

__all__ = (
    "_BULK_SELECTION_EXPRESSION",
    "_BULK_SELECTION_DESCENDANTS_EXPRESSION",
)
