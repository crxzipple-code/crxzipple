from __future__ import annotations

import json
from typing import Any, Mapping

from crxzipple.modules.browser.domain import BrowserValidationError

from .network_capture import DefaultBrowserNetworkRedactor
from .network_page_fetch_common import (
    body_preview,
    header_value,
    int_or_none,
    string_mapping,
)

PAGE_FETCH_MARKER = "__crxzipple_browser_network_page_fetch__"
PAGE_FETCH_EXPRESSION = f"""
/*{PAGE_FETCH_MARKER}*/
async (raw) => {{
  const input = JSON.parse(String(raw || "{{}}"));
  const method = String(input.method || "GET").toUpperCase();
  const headers = input.headers && typeof input.headers === "object" ? input.headers : {{}};
  const maxBodyBytes = Number.isFinite(Number(input.max_body_bytes)) && Number(input.max_body_bytes) >= 0
    ? Math.floor(Number(input.max_body_bytes))
    : 262144;
  const timeoutMs = Number.isFinite(Number(input.timeout_ms)) && Number(input.timeout_ms) > 0
    ? Math.floor(Number(input.timeout_ms))
    : 30000;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  const options = {{
    method,
    headers,
    credentials: "include",
    redirect: "follow",
    signal: controller.signal,
  }};
  if (input.body !== null && input.body !== undefined && method !== "GET" && method !== "HEAD") {{
    options.body = String(input.body);
  }}
  try {{
    const response = await fetch(String(input.url), options);
    const responseHeaders = {{}};
    response.headers.forEach((value, key) => {{
      responseHeaders[key] = value;
    }});
    const bodyText = await response.text();
    const encodedSize = new TextEncoder().encode(bodyText).length;
    const truncated = encodedSize > maxBodyBytes;
    const body = truncated ? bodyText.slice(0, maxBodyBytes) : bodyText;
    return {{
      ok: true,
      url: response.url,
      status: response.status,
      status_text: response.statusText || "",
      redirected: response.redirected,
      headers: responseHeaders,
      body,
      size_bytes: encodedSize,
      stored_size_bytes: new TextEncoder().encode(body).length,
      truncated,
    }};
  }} catch (error) {{
    return {{
      ok: false,
      error: error && error.message ? String(error.message) : String(error),
      error_name: error && error.name ? String(error.name) : null,
    }};
  }} finally {{
    clearTimeout(timeoutId);
  }}
}}
""".strip()


def execute_page_network_fetch(
    *,
    page: Any,
    redactor: DefaultBrowserNetworkRedactor,
    request: Mapping[str, Any],
    kind: str,
) -> dict[str, Any]:
    raw_result = page.evaluate(PAGE_FETCH_EXPRESSION, json.dumps(dict(request)))
    if not isinstance(raw_result, Mapping):
        raise BrowserValidationError("Browser page fetch returned an invalid result.")
    if raw_result.get("ok") is not True:
        raise BrowserValidationError(
            f"Browser page fetch failed: {raw_result.get('error') or 'unknown error'}",
        )
    headers = string_mapping(raw_result.get("headers"))
    body = str(raw_result.get("body") or "")
    mime_type = header_value(headers, "content-type")
    redacted_body = redactor.redact_body(
        body=body,
        kind="response",
        mime_type=mime_type,
        headers=headers,
    )
    preview, preview_truncated = body_preview(
        redacted_body,
        max_bytes=int(request.get("body_preview_bytes") or 0),
    )
    include_body = bool(request.get("include_body"))
    result = {
        "kind": kind,
        "request": {
            "url": redactor.redact_url(str(request["url"])),
            "method": request["method"],
            "headers": redactor.redact_headers(request["headers"]),
            "source_kind": request["source_kind"],
            "allow_cross_origin": request["allow_cross_origin"],
            "allow_mutating": request["allow_mutating"],
            "include_body": include_body,
            "body_preview_bytes": request.get("body_preview_bytes"),
        },
        "url": redactor.redact_url(str(raw_result.get("url") or request["url"])),
        "status": int(raw_result.get("status") or 0),
        "status_text": str(raw_result.get("status_text") or ""),
        "redirected": bool(raw_result.get("redirected")),
        "headers": redactor.redact_headers(headers),
        "body_preview": preview,
        "body_available": bool(redacted_body),
        "body_omitted": bool(redacted_body) and not include_body,
        "body_preview_truncated": preview_truncated,
        "mime_type": mime_type,
        "body_kind": "response",
        "base64_encoded": False,
        "size_bytes": int_or_none(raw_result.get("size_bytes")),
        "stored_size_bytes": int_or_none(raw_result.get("stored_size_bytes")),
        "truncated": bool(raw_result.get("truncated")),
        "redacted": redacted_body != body,
    }
    if include_body:
        result["body"] = redacted_body
    return result


__all__ = ["PAGE_FETCH_MARKER", "execute_page_network_fetch"]
