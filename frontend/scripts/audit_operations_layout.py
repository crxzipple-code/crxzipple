#!/usr/bin/env python3
"""Audit Operations pages for monitor-screen layout regressions.

The script expects a running frontend server and checks the rendered pages for:
- card-level internal scrolling
- horizontal overflow outside table/raw/drawer surfaces
- visible cards pushed below the desktop viewport

It writes screenshots and a JSON report under tmp/operations-layout-audit by default.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


DEFAULT_MODULES = [
    "orchestration",
    "tool",
    "llm",
    "access",
    "channels",
    "memory",
    "skills",
    "events",
    "daemon",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit Operations page layout in a browser.")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OPERATIONS_AUDIT_BASE_URL", "http://127.0.0.1:4173"),
        help="Frontend base URL. Defaults to OPERATIONS_AUDIT_BASE_URL or http://127.0.0.1:4173.",
    )
    parser.add_argument(
        "--modules",
        default=",".join(DEFAULT_MODULES),
        help="Comma-separated Operations modules to audit.",
    )
    parser.add_argument(
        "--output-dir",
        default="../tmp/operations-layout-audit",
        help="Directory for screenshots and report, relative to frontend by default.",
    )
    parser.add_argument("--width", type=int, default=1440, help="Viewport width.")
    parser.add_argument("--height", type=int, default=900, help="Viewport height.")
    parser.add_argument("--wait-ms", type=int, default=2200, help="Wait after navigation before auditing.")
    parser.add_argument("--no-screenshots", action="store_true", help="Skip screenshots.")
    parser.add_argument("--warn-only", action="store_true", help="Do not exit non-zero on layout violations.")
    return parser.parse_args()


def page_script() -> str:
    return r"""
    () => {
      const root = document.querySelector("main.operations-module-console");
      if (!root) {
        return { missingRoot: true, cards: [], internalScroll: [], horizontalOverflow: [], partlyBelow: [] };
      }

      const shouldIgnore = (el) => {
        const cls = typeof el.className === "string" ? el.className : "";
        return Boolean(
          el.closest(".data-table")
          || el.closest("[class*='drawer']")
          || el.closest("[class*='overlay']")
          || el.tagName === "PRE"
          || cls.includes("drawer")
          || cls.includes("overlay")
          || cls.includes("scroll-area")
        );
      };

      const nodes = [
        ...root.querySelectorAll("article"),
        ...root.querySelectorAll("section[class$='panel'], section[class*='panel ']"),
        ...root.querySelectorAll("aside article"),
      ];

      const seen = new Set();
      const cards = nodes
        .filter((el) => {
          if (seen.has(el)) return false;
          seen.add(el);
          return !shouldIgnore(el);
        })
        .map((el) => {
          const rect = el.getBoundingClientRect();
          const style = getComputedStyle(el);
          return {
            cls: typeof el.className === "string" ? el.className : "",
            top: Math.round(rect.top),
            bottom: Math.round(rect.bottom),
            height: Math.round(rect.height),
            overflowY: style.overflowY,
            scrollX: Math.max(0, Math.round(el.scrollWidth - el.clientWidth)),
            scrollY: Math.max(0, Math.round(el.scrollHeight - el.clientHeight)),
            tableCount: el.querySelectorAll("table").length,
            text: (el.innerText || "").replace(/\s+/g, " ").trim().slice(0, 180),
          };
        })
        .filter((item) => item.height > 12 && item.bottom > 0 && item.top < window.innerHeight);

      return {
        missingRoot: false,
        cards,
        internalScroll: cards.filter((item) => item.scrollY > 2 && ["auto", "scroll"].includes(item.overflowY)),
        horizontalOverflow: cards.filter((item) => item.scrollX > 2),
        partlyBelow: cards.filter((item) => item.bottom > window.innerHeight + 2),
      };
    }
    """


def summarize_violations(report: dict[str, Any]) -> list[str]:
    messages: list[str] = []
    for module, item in report["modules"].items():
        if item.get("missingRoot"):
            messages.append(f"{module}: missing main.operations-module-console")
        for kind in ("internalScroll", "horizontalOverflow", "partlyBelow"):
            count = len(item.get(kind, []))
            if count:
                messages.append(f"{module}: {count} {kind} violation(s)")
    return messages


def main() -> int:
    args = parse_args()
    modules = [item.strip() for item in args.modules.split(",") if item.strip()]
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "baseUrl": args.base_url,
        "viewport": {"width": args.width, "height": args.height},
        "modules": {},
    }

    with sync_playwright() as playwright:
      browser = playwright.chromium.launch(headless=True)
      page = browser.new_page(
          viewport={"width": args.width, "height": args.height},
          device_scale_factor=1,
      )

      for module in modules:
          url = f"{args.base_url.rstrip('/')}/operations/{module}"
          page.goto(url, wait_until="domcontentloaded", timeout=30_000)
          page.wait_for_timeout(args.wait_ms)
          if not args.no_screenshots:
              page.screenshot(path=str(output_dir / f"{module}.png"), full_page=False)
          report["modules"][module] = page.evaluate(page_script())

      browser.close()

    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    violations = summarize_violations(report)
    if violations:
        print("Operations layout audit found violations:")
        for message in violations:
            print(f"- {message}")
        print(f"Report: {report_path}")
        return 0 if args.warn_only else 1

    print(f"Operations layout audit passed. Report: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
