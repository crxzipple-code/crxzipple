---
name: browser-investigation
description: Investigate live web pages with browser evidence, including DOM, forms, overlays, network, scripts, storage, and diagnostics.
version: 1
tags:
  - browser
  - web
  - investigation
  - evidence
when_to_use: When a task asks you to inspect, operate, debug, compare, or verify information from a live website or browser session.
required_tools:
  - browser.observe
  - browser.action.trace
suggested_tools:
  - browser.form.inspect
  - browser.overlay.observe
  - browser.dom.inspect
  - browser.dom.clickability
  - browser.network.inspect
  - browser.network.start_capture
  - browser.network.list_requests
  - browser.network.get_response_body
  - browser.script.find_request
  - browser.code.search
  - browser.script.inspect
  - browser.storage.indexeddb.list
  - browser.diagnostics.collect
  - browser.page.errors
surfaces:
  - interactive
---

# Browser Investigation

Use this skill when the answer depends on a live browser page, website behavior, web app state, or page-backed API evidence.

## Principle

Treat the browser as an evidence workbench. A DOM or interactive snapshot is a starting map, not proof that something is absent. When a control, price, calendar, request, error, or state is missing or ambiguous, continue through the specialized browser tools before concluding.

## Evidence Path

1. Start with `browser.observe` to identify the active tab, URL, visible controls, refs, forms, overlays, runtime hints, console/page errors, scripts, and suggested next tools.
2. Use `browser.action.trace` for meaningful clicks, typing, fills, or evaluations so the result includes before/after state, lifecycle, console/page-error, network, storage, and follow-up guidance.
3. If visible UI is incomplete, inspect `browser.form.inspect`, `browser.overlay.observe`, `browser.dom.inspect`, or `browser.dom.clickability` instead of guessing.
4. If the data is likely fetched asynchronously, use network capture/list/body tools and script search tools to identify the endpoint, request payload, and response evidence.
5. If page state or login/session behavior matters, inspect storage, service workers, diagnostics, and page errors.
6. Summarize conclusions with the evidence path used: URL/page state, tool observations, network/script facts, and remaining uncertainty.

## Rules

- Do not stop because a single snapshot lacks a ref or text. Try overlay/form/DOM/network/script diagnostics first.
- Prefer action trace over bare click/type when the effect matters.
- Prefer network/script evidence when the user asks to verify prices, availability, API-backed records, or rapidly changing data.
- Treat stale refs, ambiguous locators, and unchanged snapshots as diagnostic signals; refresh observation or inspect clickability rather than claiming the page is unusable.
- Do not expose secrets, cookies, tokens, or private page data unless the user explicitly needs that specific fact and it is safe to report.
- If the site blocks automation or the evidence remains inconclusive, explain exactly which path was attempted and what concrete signal blocked completion.
