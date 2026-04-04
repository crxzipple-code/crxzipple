from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import tempfile
from dataclasses import replace
from urllib.parse import parse_qs, unquote, urlparse

from crxzipple.bootstrap import AppContainer, build_container
from crxzipple.core.config import Settings, load_settings
from crxzipple.core.db import create_schema
from crxzipple.modules.browser.domain import (
    BrowserProfileConfig,
    BrowserSystemConfig,
    BrowserTab,
)
from crxzipple.modules.browser.infrastructure.state_root import initialize_browser_state_root


def _matches_fake_item_selector(item: dict[str, object], item_selector: str | None) -> bool:
    if item_selector is None or not item_selector.strip():
        return True
    selector = str(item.get("selector") or "").strip()
    role = str(item.get("role") or "").strip().lower()
    tag = str(item.get("tag") or "").strip().lower()
    input_type = str(item.get("input_type") or item.get("type") or "").strip().lower()
    for raw_part in item_selector.split(","):
        part = raw_part.strip().lower()
        if not part:
            continue
        if selector == raw_part.strip():
            return True
        if part in {"[role='checkbox']", '[role="checkbox"]'} and role == "checkbox":
            return True
        if part in {"[role='radio']", '[role="radio"]'} and role == "radio":
            return True
        if part.startswith("input[type='checkbox'") or part.startswith('input[type="checkbox"'):
            if tag == "input" and input_type == "checkbox":
                return True
        if part.startswith("input[type='radio'") or part.startswith('input[type="radio"'):
            if tag == "input" and input_type == "radio":
                return True
    return False


def _fake_text_match_details(
    items: list[dict[str, object]],
    *,
    text: str,
    exact: bool,
    explicit_ordinal: int | None = None,
    source_selector: str | None = None,
    source_scope_selector: str | None = None,
) -> dict[str, object] | None:
    normalized_text = str(text).strip()
    if not normalized_text:
        return None
    candidates: list[dict[str, object]] = []
    for index, raw_item in enumerate(items):
        item = dict(raw_item)
        item_text = str(item.get("text") or item.get("label") or "").strip()
        if exact:
            if item_text != normalized_text:
                continue
        elif normalized_text not in item_text:
            continue
        score = 0
        reason_flags: list[str] = []
        if bool(item.get("visible", True)):
            score += 1000
            reason_flags.append("visible")
        if not bool(item.get("disabled", False)):
            score += 250
            reason_flags.append("enabled")
        if (
            source_scope_selector is not None
            and str(item.get("scope_selector") or "").strip() == source_scope_selector
        ):
            score += 900
            reason_flags.append("same-source-scope")
        if source_selector is not None and str(item.get("source_selector") or "").strip() == source_selector:
            score += 600
            reason_flags.append("same-source-selector")
        role = str(item.get("role") or "").strip().lower()
        tag = str(item.get("tag") or "").strip().lower()
        if role in {"button", "checkbox", "combobox", "link", "menuitem", "option", "radio", "searchbox", "switch", "tab", "textbox"}:
            score += 400
            reason_flags.append("interactive")
        elif tag in {"a", "button", "input", "select", "textarea"}:
            score += 250
            reason_flags.append("interactive")
        candidates.append(
            {
                "index": index,
                "text": item_text,
                "selector": str(item.get("resolved_selector") or item.get("selector") or "").strip() or None,
                "score": score,
                "reason_flags": reason_flags,
            }
        )
    if not candidates:
        return None
    preview = [str(item["text"]) for item in candidates[:5] if str(item.get("text") or "").strip()]
    if explicit_ordinal is not None and 0 <= explicit_ordinal < len(candidates):
        chosen = candidates[explicit_ordinal]
        reason = "explicit-ordinal"
    else:
        chosen = sorted(candidates, key=lambda item: (-int(item["score"]), int(item["index"])))[0]
        flags = list(chosen.get("reason_flags") or [])
        if "same-source-scope" in flags:
            reason = "same-source-scope"
        elif "same-source-selector" in flags:
            reason = "same-source-selector"
        elif "interactive" in flags:
            reason = "interactive"
        elif "visible" in flags:
            reason = "visible"
        else:
            reason = "text-match"
    return {
        "ordinal": int(chosen["index"]),
        "candidateCount": len(candidates),
        "chosenText": chosen["text"],
        "chosenSelector": chosen["selector"],
        "reason": reason,
        "reasonFlags": list(chosen.get("reason_flags") or []),
        "candidatePreview": preview,
    }


class SqliteTestHarness:
    def __init__(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        database_path = Path(self._tempdir.name) / "test.db"
        self.authorization_runtime_policy_path = str(
            Path(self._tempdir.name) / "authorization_runtime.yaml",
        )
        self.database_url = f"sqlite:///{database_path}"
        self._containers: list[AppContainer] = []

    def initialize_schema(self, *, settings: Settings | None = None) -> None:
        resolved_settings = self._resolved_settings(settings)
        container = build_container(
            settings=resolved_settings,
            database_url=self.database_url,
        )
        create_schema(container.engine)
        container.close()

    def build_container(self, *, settings: Settings | None = None) -> AppContainer:
        resolved_settings = self._resolved_settings(settings)
        container = build_container(
            settings=resolved_settings,
            database_url=self.database_url,
        )
        create_schema(container.engine)
        self._containers.append(container)
        return container

    def _resolved_settings(self, settings: Settings | None) -> Settings:
        resolved = settings or load_settings()
        return replace(
            resolved,
            authorization_runtime_policy_path=self.authorization_runtime_policy_path,
            browser_state_dir=str(Path(self._tempdir.name) / "browser"),
        )

    def close(self) -> None:
        while self._containers:
            container = self._containers.pop()
            container.close()
        self._tempdir.cleanup()


def seed_browser_state_root(
    root_dir: str | Path,
    *,
    default_profile: str = "crxzipple",
    profiles: list[dict[str, object]] | tuple[dict[str, object], ...],
    headless: bool = False,
    executable_path: str | None = None,
    no_sandbox: bool = False,
    managed_tab_limit: int | None = None,
    cdp_host: str = "127.0.0.1",
    cdp_port_range_start: int = 18800,
    cdp_port_range_end: int = 18832,
) -> None:
    initialize_browser_state_root(
        root_dir,
        system_config=BrowserSystemConfig(
            default_profile=default_profile,
            profiles=tuple(
                BrowserProfileConfig(
                    name=str(item["name"]),
                    driver=str(item.get("driver") or "managed"),  # type: ignore[arg-type]
                    cdp_url=(
                        str(item["cdp_url"]) if item.get("cdp_url") is not None else None
                    ),
                    cdp_port=(
                        int(item["cdp_port"]) if item.get("cdp_port") is not None else None
                    ),
                    user_data_dir=(
                        str(item["user_data_dir"])
                        if item.get("user_data_dir") is not None
                        else None
                    ),
                    attach_only=bool(item.get("attach_only", False)),
                )
                for item in profiles
            ),
            headless=headless,
            executable_path=executable_path,
            no_sandbox=no_sandbox,
            managed_tab_limit=managed_tab_limit,
            cdp_host=cdp_host,
            cdp_port_range_start=cdp_port_range_start,
            cdp_port_range_end=cdp_port_range_end,
        ),
    )


def openapi_fixture_path(name: str) -> str:
    return str(Path(__file__).with_name("fixtures") / name)


def fixture_path(name: str) -> str:
    return str(Path(__file__).with_name("fixtures") / name)


class SampleApiServer:
    def __init__(self) -> None:
        self._server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            _build_sample_api_handler(),
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="sample-api-server",
            daemon=True,
        )

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


class FakeCdpServer:
    def __init__(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _build_fake_cdp_handler())
        server.tabs = {}  # type: ignore[attr-defined]
        server.next_tab_id = 1  # type: ignore[attr-defined]
        server.active_target_id = None  # type: ignore[attr-defined]
        self._server = server
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="fake-cdp-server",
            daemon=True,
        )

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    @property
    def browser_ws_url(self) -> str:
        host, port = self._server.server_address
        return f"ws://{host}:{port}/devtools/browser/fake-browser"

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)

    def navigate_tab(self, *, target_id: str, url: str) -> None:
        payload = self._server.tabs.get(target_id)  # type: ignore[attr-defined]
        if not isinstance(payload, dict):
            raise KeyError(target_id)
        payload["url"] = url
        payload["title"] = url

    def websocket_factory(self):
        server = self

        class _FakeWebSocket:
            def __init__(self, ws_url: str) -> None:
                parsed = urlparse(ws_url)
                self._target_id = parsed.path.rsplit("/", 1)[-1]
                self._pending_response = json.dumps({"id": 1, "result": {}})

            def send(self, payload: str) -> None:
                message = json.loads(payload)
                if message.get("method") == "Page.navigate":
                    params = message.get("params") or {}
                    server.navigate_tab(
                        target_id=self._target_id,
                        url=str(params.get("url") or ""),
                    )

            def recv(self) -> str:
                return self._pending_response

            def close(self) -> None:
                return None

        def _connect(ws_url: str, timeout: float | None = None):  # noqa: ANN202
            del timeout
            return _FakeWebSocket(ws_url)

        return _connect


class FakePlaywrightLocator:
    def __init__(
        self,
        context,
        selector: str,
        *,
        candidates: list[dict[str, object]] | None = None,
        nth_index: int | None = None,
        container_selector: str | None = None,
    ) -> None:  # noqa: ANN001
        self.context = context
        self.page = context.page
        self.selector = selector
        self.candidates = [dict(item) for item in (candidates or [])]
        self.nth_index = nth_index
        self.container_selector = container_selector

    def nth(self, index: int):  # noqa: ANN001
        return FakePlaywrightLocator(
            self.context,
            self.selector,
            candidates=self.candidates,
            nth_index=index,
            container_selector=self.container_selector,
        )

    def count(self) -> int:
        return len(self._items_in_scope())

    def _scoped_items(self) -> list[dict[str, object]]:
        resolver = getattr(self.context, "items_for_selector", None)
        if callable(resolver):
            return [dict(item) for item in resolver(self.selector)]
        return [dict(item) for item in self.context.interactive_items]

    def _items_in_scope(self) -> list[dict[str, object]]:
        if self.candidates:
            return [dict(item) for item in self.candidates]
        return [dict(item) for item in self._scoped_items()]

    def aria_snapshot(self, **kwargs) -> str:  # noqa: ANN003
        self.page.operations.append(
            ("aria_snapshot", self.selector, dict(kwargs), tuple(self.context.frame_path))
        )
        if getattr(self.context, "aria_snapshot_text", None) is not None:
            return str(self.context.aria_snapshot_text)
        lines: list[str] = []
        for item in self._scoped_items():
            role = str(item.get("role") or "").strip()
            if not role:
                continue
            label = str(item.get("label") or "").strip()
            line = f"- {role}"
            if label:
                line += f' "{label}"'
            lines.append(line)
        return "\n".join(lines)

    def _resolved_selector(self) -> str:
        if self.candidates:
            if self.nth_index is not None and 0 <= self.nth_index < len(self.candidates):
                candidate = self.candidates[self.nth_index]
                selector = candidate.get("resolved_selector") or candidate.get("selector")
                if isinstance(selector, str) and selector:
                    return selector
            if len(self.candidates) == 1:
                selector = self.candidates[0].get("resolved_selector") or self.candidates[0].get("selector")
                if isinstance(selector, str) and selector:
                    return selector
        return self.selector

    def _resolved_item(self) -> dict[str, object] | None:
        if self.candidates:
            if self.nth_index is not None and 0 <= self.nth_index < len(self.candidates):
                return dict(self.candidates[self.nth_index])
            if len(self.candidates) == 1:
                return dict(self.candidates[0])
        scoped_items = self._scoped_items()
        if len(scoped_items) == 1:
            return dict(scoped_items[0])
        resolved_selector = self._resolved_selector()
        for item in scoped_items:
            selector = str(item.get("resolved_selector") or item.get("selector") or "").strip()
            if selector == resolved_selector:
                return dict(item)
        return None

    def locator(self, selector: str):  # noqa: ANN001
        base_scope = self.container_selector or self._resolved_selector()
        normalized_selector = str(selector).strip()
        candidates: list[dict[str, object]] = []
        for item in self.context.interactive_items:
            item_selector = str(item.get("selector") or "").strip()
            item_scope = str(item.get("scope_selector") or "").strip()
            if base_scope and item_scope != base_scope:
                continue
            if item_selector != normalized_selector:
                continue
            candidates.append(dict(item))
        return FakePlaywrightLocator(
            self.context,
            normalized_selector,
            candidates=candidates,
            container_selector=normalized_selector,
        )

    def get_by_role(self, role: str, **kwargs):  # noqa: ANN003
        base_scope = self.container_selector or self._resolved_selector()
        name = kwargs.get("name")
        exact = bool(kwargs.get("exact", False))
        candidates: list[dict[str, object]] = []
        for item in self.context.interactive_items:
            item_scope = str(item.get("scope_selector") or "").strip()
            if base_scope and item_scope != base_scope:
                continue
            item_role = str(item.get("role") or "").strip().lower()
            if item_role != str(role).strip().lower():
                continue
            item_label = str(item.get("label") or item.get("text") or "").strip()
            if name is not None:
                target_name = str(name).strip()
                if exact:
                    if item_label != target_name:
                        continue
                elif target_name not in item_label:
                    continue
            candidates.append(dict(item))
        selector = f"role={str(role).strip().lower()}"
        if isinstance(name, str) and name.strip():
            selector += f'[name="{name.strip()}"]'
        return FakePlaywrightLocator(self.context, selector, candidates=candidates, container_selector=base_scope)

    def get_by_text(self, text: str, **kwargs):  # noqa: ANN003
        base_scope = self.container_selector or self._resolved_selector()
        normalized_text = str(text).strip()
        exact = bool(kwargs.get("exact", False))
        candidates: list[dict[str, object]] = []
        for item in self.context.interactive_items:
            item_scope = str(item.get("scope_selector") or "").strip()
            if base_scope and item_scope != base_scope:
                continue
            item_text = str(item.get("text") or item.get("label") or "").strip()
            if exact:
                if item_text != normalized_text:
                    continue
            elif normalized_text not in item_text:
                continue
            candidates.append(dict(item))
        selector = f'text={normalized_text}'
        return FakePlaywrightLocator(self.context, selector, candidates=candidates, container_selector=base_scope)

    def click(self, **kwargs) -> None:  # noqa: ANN003
        self.page.operations.append(
            ("click", self._resolved_selector(), dict(kwargs), tuple(self.context.frame_path))
        )
        failures = self.page.click_failures.get(self._resolved_selector())
        if failures and not kwargs.get("force", False):
            raise failures.pop(0)

    def dblclick(self, **kwargs) -> None:  # noqa: ANN003
        self.page.operations.append(
            ("dblclick", self._resolved_selector(), dict(kwargs), tuple(self.context.frame_path))
        )
        failures = self.page.click_failures.get(self._resolved_selector())
        if failures and not kwargs.get("force", False):
            raise failures.pop(0)

    def type(self, text: str, **kwargs) -> None:  # noqa: ANN003
        self.page.operations.append(
            ("type", self._resolved_selector(), text, dict(kwargs), tuple(self.context.frame_path))
        )

    def fill(self, text: str, **kwargs) -> None:  # noqa: ANN003
        self.page.operations.append(
            ("fill", self._resolved_selector(), text, dict(kwargs), tuple(self.context.frame_path))
        )

    def set_checked(self, checked: bool, **kwargs) -> None:  # noqa: ANN003
        self.page.operations.append(
            (
                "set_checked",
                self._resolved_selector(),
                checked,
                dict(kwargs),
                tuple(self.context.frame_path),
            )
        )

    def press(self, key: str, **kwargs) -> None:  # noqa: ANN003
        self.page.operations.append(
            ("press", self._resolved_selector(), key, dict(kwargs), tuple(self.context.frame_path))
        )

    def hover(self, **kwargs) -> None:  # noqa: ANN003
        self.page.operations.append(
            ("hover", self._resolved_selector(), dict(kwargs), tuple(self.context.frame_path))
        )

    def drag_to(self, target, **kwargs) -> None:  # noqa: ANN001, ANN003
        self.page.operations.append(
            (
                "drag",
                self._resolved_selector(),
                target._resolved_selector(),
                dict(kwargs),
                tuple(self.context.frame_path),
            )
        )

    def scroll_into_view_if_needed(self, **kwargs) -> None:  # noqa: ANN003
        self.page.operations.append(
            (
                "scroll-into-view",
                self._resolved_selector(),
                dict(kwargs),
                tuple(self.context.frame_path),
            )
        )

    def select_option(self, values, **kwargs):  # noqa: ANN001, ANN003
        normalized = list(values) if isinstance(values, list | tuple) else values
        self.page.operations.append(
            (
                "select",
                self._resolved_selector(),
                normalized,
                dict(kwargs),
                tuple(self.context.frame_path),
            )
        )
        if isinstance(normalized, list):
            return normalized
        return [normalized]

    def wait_for(self, **kwargs) -> None:  # noqa: ANN003
        self.page.operations.append(
            ("wait", self._resolved_selector(), dict(kwargs), tuple(self.context.frame_path))
        )

    def evaluate(self, expression: str, arg=None):  # noqa: ANN001
        self.page.operations.append(
            (
                "locator.evaluate",
                self._resolved_selector(),
                expression,
                arg,
                tuple(self.context.frame_path),
            )
        )
        if "__crxzipple_widget_target_info__" in expression:
            item = self._resolved_item() or {}
            return {
                "tag": str(item.get("tag") or "").strip().lower() or None,
                "role": str(item.get("role") or "").strip().lower() or None,
                "type": str(item.get("input_type") or item.get("type") or "").strip().lower() or None,
                "contentEditable": bool(item.get("contenteditable", False)),
                "readOnly": bool(item.get("readonly", False)),
                "disabled": bool(item.get("disabled", False)),
                "visible": bool(item.get("visible", True)),
                "focused": bool(item.get("focused", False)),
                "checked": bool(item.get("checked", False)),
                "value": item.get("value"),
            }
        if "__crxzipple_collect_bulk_selection_candidates__" in expression:
            item_selector = None
            if isinstance(arg, dict):
                raw_selector = arg.get("itemSelector")
                if isinstance(raw_selector, str):
                    item_selector = raw_selector
            return [
                dict(item)
                for item in self._scoped_items()
                if _matches_fake_item_selector(dict(item), item_selector)
            ]
        if "__crxzipple_find_preferred_text_ordinal__" in expression:
            normalized_text = ""
            exact = False
            source_selector = None
            source_scope_selector = None
            if isinstance(arg, dict):
                normalized_text = str(arg.get("text") or "").strip()
                exact = bool(arg.get("exact", False))
                raw_source = arg.get("sourceSelector")
                if isinstance(raw_source, str):
                    source_selector = raw_source.strip() or None
                raw_source_scope = arg.get("sourceScopeSelector")
                if isinstance(raw_source_scope, str):
                    source_scope_selector = raw_source_scope.strip() or None
            candidates: list[tuple[int, int]] = []
            for index, item in enumerate(self._scoped_items()):
                item_text = str(item.get("text") or item.get("label") or "").strip()
                if exact:
                    if item_text != normalized_text:
                        continue
                elif normalized_text not in item_text:
                    continue
                score = 0
                if bool(item.get("visible", True)):
                    score += 1000
                if not bool(item.get("disabled", False)):
                    score += 250
                if (
                    source_scope_selector is not None
                    and str(item.get("scope_selector") or "").strip() == source_scope_selector
                ):
                    score += 900
                if source_selector is not None and str(item.get("source_selector") or "").strip() == source_selector:
                    score += 600
                candidates.append((score, index))
            if not candidates:
                return None
            candidates.sort(key=lambda item: (-item[0], item[1]))
            return candidates[0][1]
        if "__crxzipple_collect_text_match_details__" in expression:
            normalized_text = ""
            exact = False
            explicit_ordinal = None
            source_selector = None
            source_scope_selector = None
            if isinstance(arg, dict):
                normalized_text = str(arg.get("text") or "").strip()
                exact = bool(arg.get("exact", False))
                raw_ordinal = arg.get("explicitOrdinal")
                if isinstance(raw_ordinal, int):
                    explicit_ordinal = raw_ordinal
                raw_source = arg.get("sourceSelector")
                if isinstance(raw_source, str):
                    source_selector = raw_source.strip() or None
                raw_source_scope = arg.get("sourceScopeSelector")
                if isinstance(raw_source_scope, str):
                    source_scope_selector = raw_source_scope.strip() or None
            return _fake_text_match_details(
                self._scoped_items(),
                text=normalized_text,
                exact=exact,
                explicit_ordinal=explicit_ordinal,
                source_selector=source_selector,
                source_scope_selector=source_scope_selector,
            )
        if "__crxzipple_collect_datepicker_panel_status__" in expression:
            overlay_selector = None
            month_header_selector = None
            limit = 7
            if isinstance(arg, dict):
                raw_overlay = arg.get("overlaySelector")
                if isinstance(raw_overlay, str):
                    overlay_selector = raw_overlay.strip() or None
                raw_header = arg.get("monthHeaderSelector")
                if isinstance(raw_header, str):
                    month_header_selector = raw_header.strip() or None
                try:
                    limit = max(1, int(arg.get("limit", 7)))
                except (TypeError, ValueError):
                    limit = 7
            return self.page.resolve_datepicker_panel_status(
                overlay_selector=overlay_selector,
                month_header_selector=month_header_selector,
                limit=limit,
            )
        if "__crxzipple_collect_datepicker_day_ordinal__" in expression:
            normalized_text = ""
            exact = False
            month_header_selector = None
            month_header_text = None
            if isinstance(arg, dict):
                normalized_text = str(arg.get("text") or "").strip()
                exact = bool(arg.get("exact", False))
                raw_header_selector = arg.get("monthHeaderSelector")
                if isinstance(raw_header_selector, str):
                    month_header_selector = raw_header_selector.strip() or None
                raw_header_text = arg.get("monthHeaderText")
                if isinstance(raw_header_text, str):
                    month_header_text = raw_header_text.strip() or None
            header_month_scope = None
            if month_header_selector is not None:
                for item in self._scoped_items():
                    if str(item.get("selector") or "").strip() == month_header_selector:
                        header_month_scope = str(item.get("month_scope_selector") or "").strip() or None
                        break
            if header_month_scope is None and month_header_text is not None:
                for item in self._scoped_items():
                    item_text = str(item.get("text") or item.get("label") or "").strip()
                    if month_header_text in item_text:
                        header_month_scope = str(item.get("month_scope_selector") or "").strip() or None
                        break
            matched_items: list[dict[str, object]] = []
            for item in self._scoped_items():
                item_text = str(item.get("text") or item.get("label") or "").strip()
                if exact:
                    if item_text != normalized_text:
                        continue
                elif normalized_text not in item_text:
                    continue
                matched_items.append(dict(item))
            candidates: list[tuple[int, int]] = []
            for ordinal, item in enumerate(matched_items):
                score = 0
                if bool(item.get("visible", True)):
                    score += 1000
                if not bool(item.get("disabled", False)):
                    score += 800
                if bool(item.get("outside_current_month", False)):
                    score -= 600
                if header_month_scope is not None and str(item.get("month_scope_selector") or "").strip() == header_month_scope:
                    score += 1000
                candidates.append((score, ordinal))
            if not candidates:
                return None
            candidates.sort(key=lambda item: (-item[0], item[1]))
            return candidates[0][1]
        if "innerText" in expression or "textContent" in expression:
            item = self._resolved_item() or {}
            return str(item.get("text") or item.get("label") or "").strip()
        return {
            "selector": self._resolved_selector(),
            "expression": expression,
            "arg": arg,
            "frame_path": list(self.context.frame_path),
        }

    def inner_text(self) -> str:
        return self.context.body_text


class _FakeKeyboard:
    def __init__(self, page: "FakePlaywrightPage") -> None:
        self.page = page

    def press(self, key: str, **kwargs) -> None:  # noqa: ANN003
        self.page.operations.append(("keyboard.press", key, dict(kwargs)))


class FakePlaywrightFrame:
    def __init__(
        self,
        *,
        page: "FakePlaywrightPage",
        frame_path: tuple[int, ...],
        body_text: str | None = None,
        interactive_items: list[dict[str, object]] | None = None,
        aria_snapshot_text: str | None = None,
    ) -> None:
        self.page = page
        self.frame_path = frame_path
        self.body_text = body_text or page.body_text
        self.aria_snapshot_text = aria_snapshot_text
        self.evaluate_failures: list[Exception] = []
        self.interactive_items = [
            dict(item)
            for item in (
                interactive_items
                if interactive_items is not None
                else page.interactive_items
            )
        ]
        self.child_frames: list["FakePlaywrightFrame"] = []

    def locator(self, selector: str) -> FakePlaywrightLocator:
        return FakePlaywrightLocator(
            self,
            selector,
            candidates=self.items_for_selector(selector),
            container_selector=selector,
        )

    def items_for_selector(self, selector: str) -> list[dict[str, object]]:
        normalized = str(selector).strip()
        if not normalized or normalized in {"body", ":root"}:
            return [dict(item) for item in self.interactive_items]
        resolved: list[dict[str, object]] = []
        for item in self.interactive_items:
            item_selector = str(item.get("selector") or "").strip()
            scope_selector = str(item.get("scope_selector") or "").strip()
            if item_selector == normalized or scope_selector == normalized:
                resolved.append(dict(item))
        return resolved

    def get_by_role(self, role: str, **kwargs):  # noqa: ANN003
        name = kwargs.get("name")
        exact = bool(kwargs.get("exact", False))
        candidates = []
        for item in self.interactive_items:
            item_role = str(item.get("role") or "").strip().lower()
            if item_role != str(role).strip().lower():
                continue
            item_label = str(item.get("label") or item.get("text") or "").strip()
            if name is not None:
                target_name = str(name).strip()
                if exact:
                    if item_label != target_name:
                        continue
                elif target_name not in item_label:
                    continue
            candidates.append(dict(item))
        selector = f"role={str(role).strip().lower()}"
        if isinstance(name, str) and name.strip():
            selector += f'[name="{name.strip()}"]'
        return FakePlaywrightLocator(self, selector, candidates=candidates)

    def get_by_text(self, text: str, **kwargs):  # noqa: ANN003
        normalized_text = str(text).strip()
        exact = bool(kwargs.get("exact", False))
        candidates = []
        for item in self.interactive_items:
            item_text = str(item.get("text") or item.get("label") or "").strip()
            if exact:
                if item_text != normalized_text:
                    continue
            elif normalized_text not in item_text:
                continue
            candidates.append(dict(item))
        selector = f"text={normalized_text}"
        return FakePlaywrightLocator(self, selector, candidates=candidates)

    def evaluate(self, expression: str, arg=None):  # noqa: ANN001
        self.page.operations.append(
            ("frame.evaluate", expression, arg, tuple(self.frame_path))
        )
        if self.evaluate_failures:
            raise self.evaluate_failures.pop(0)
        if "__crxzipple_collect_interactive_refs__" in expression:
            if isinstance(arg, str) and arg.strip():
                return self.items_for_selector(arg)
            return [dict(item) for item in self.interactive_items]
        if "__crxzipple_collect_bulk_selection_candidates__" in expression:
            item_selector = None
            if isinstance(arg, dict):
                raw_selector = arg.get("itemSelector")
                if isinstance(raw_selector, str):
                    item_selector = raw_selector
            return [
                dict(item)
                for item in self.interactive_items
                if _matches_fake_item_selector(dict(item), item_selector)
            ]
        if "__crxzipple_find_preferred_text_ordinal__" in expression:
            normalized_text = ""
            exact = False
            source_selector = None
            source_scope_selector = None
            if isinstance(arg, dict):
                normalized_text = str(arg.get("text") or "").strip()
                exact = bool(arg.get("exact", False))
                raw_source = arg.get("sourceSelector")
                if isinstance(raw_source, str):
                    source_selector = raw_source.strip() or None
                raw_source_scope = arg.get("sourceScopeSelector")
                if isinstance(raw_source_scope, str):
                    source_scope_selector = raw_source_scope.strip() or None
            candidates: list[tuple[int, int]] = []
            for index, item in enumerate(self.interactive_items):
                item_text = str(item.get("text") or item.get("label") or "").strip()
                if exact:
                    if item_text != normalized_text:
                        continue
                elif normalized_text not in item_text:
                    continue
                score = 0
                if bool(item.get("visible", True)):
                    score += 1000
                if not bool(item.get("disabled", False)):
                    score += 250
                if (
                    source_scope_selector is not None
                    and str(item.get("scope_selector") or "").strip() == source_scope_selector
                ):
                    score += 900
                if source_selector is not None and str(item.get("source_selector") or "").strip() == source_selector:
                    score += 600
                candidates.append((score, index))
            if not candidates:
                return None
            candidates.sort(key=lambda item: (-item[0], item[1]))
            return candidates[0][1]
        if "__crxzipple_collect_text_match_details__" in expression:
            normalized_text = ""
            exact = False
            explicit_ordinal = None
            source_selector = None
            source_scope_selector = None
            if isinstance(arg, dict):
                normalized_text = str(arg.get("text") or "").strip()
                exact = bool(arg.get("exact", False))
                raw_ordinal = arg.get("explicitOrdinal")
                if isinstance(raw_ordinal, int):
                    explicit_ordinal = raw_ordinal
                raw_source = arg.get("sourceSelector")
                if isinstance(raw_source, str):
                    source_selector = raw_source.strip() or None
                raw_source_scope = arg.get("sourceScopeSelector")
                if isinstance(raw_source_scope, str):
                    source_scope_selector = raw_source_scope.strip() or None
            return _fake_text_match_details(
                [dict(item) for item in self.interactive_items],
                text=normalized_text,
                exact=exact,
                explicit_ordinal=explicit_ordinal,
                source_selector=source_selector,
                source_scope_selector=source_scope_selector,
            )
        if "__crxzipple_collect_datepicker_panel_status__" in expression:
            overlay_selector = None
            month_header_selector = None
            limit = 7
            if isinstance(arg, dict):
                raw_overlay = arg.get("overlaySelector")
                if isinstance(raw_overlay, str):
                    overlay_selector = raw_overlay.strip() or None
                raw_header = arg.get("monthHeaderSelector")
                if isinstance(raw_header, str):
                    month_header_selector = raw_header.strip() or None
                try:
                    limit = max(1, int(arg.get("limit", 7)))
                except (TypeError, ValueError):
                    limit = 7
            return self.page.resolve_datepicker_panel_status(
                overlay_selector=overlay_selector,
                month_header_selector=month_header_selector,
                limit=limit,
            )
        if "__crxzipple_collect_datepicker_day_ordinal__" in expression:
            normalized_text = ""
            exact = False
            month_header_selector = None
            month_header_text = None
            if isinstance(arg, dict):
                normalized_text = str(arg.get("text") or "").strip()
                exact = bool(arg.get("exact", False))
                raw_header_selector = arg.get("monthHeaderSelector")
                if isinstance(raw_header_selector, str):
                    month_header_selector = raw_header_selector.strip() or None
                raw_header_text = arg.get("monthHeaderText")
                if isinstance(raw_header_text, str):
                    month_header_text = raw_header_text.strip() or None
            header_month_scope = None
            if month_header_selector is not None:
                for item in self.interactive_items:
                    if str(item.get("selector") or "").strip() == month_header_selector:
                        header_month_scope = str(item.get("month_scope_selector") or "").strip() or None
                        break
            if header_month_scope is None and month_header_text is not None:
                for item in self.interactive_items:
                    item_text = str(item.get("text") or item.get("label") or "").strip()
                    if month_header_text in item_text:
                        header_month_scope = str(item.get("month_scope_selector") or "").strip() or None
                        break
            matched_items: list[dict[str, object]] = []
            for item in self.interactive_items:
                item_text = str(item.get("text") or item.get("label") or "").strip()
                if exact:
                    if item_text != normalized_text:
                        continue
                elif normalized_text not in item_text:
                    continue
                matched_items.append(dict(item))
            candidates: list[tuple[int, int]] = []
            for ordinal, item in enumerate(matched_items):
                score = 0
                if bool(item.get("visible", True)):
                    score += 1000
                if not bool(item.get("disabled", False)):
                    score += 800
                if bool(item.get("outside_current_month", False)):
                    score -= 600
                if header_month_scope is not None and str(item.get("month_scope_selector") or "").strip() == header_month_scope:
                    score += 1000
                candidates.append((score, ordinal))
            if not candidates:
                return None
            candidates.sort(key=lambda item: (-item[0], item[1]))
            return candidates[0][1]
        return {
            "expression": expression,
            "arg": arg,
            "frame_path": list(self.frame_path),
        }


class FakePlaywrightPage:
    def __init__(self, *, target_id: str, url: str = "https://example.com") -> None:
        self.target_id = target_id
        self.url = url
        self.body_text = f"body:{target_id}"
        self._interactive_items: list[dict[str, object]] = [
            {
                "selector": "#submit",
                "label": "Submit",
                "role": "button",
                "text": "Submit",
                "tag": "button",
            },
            {
                "selector": "#query",
                "label": "Query",
                "role": "textbox",
                "text": "",
                "tag": "input",
            },
        ]
        self.operations: list[tuple[object, ...]] = []
        self.click_failures: dict[str, list[Exception]] = {}
        self.evaluate_failures: list[Exception] = []
        self.wait_for_function_failures: dict[str, list[Exception]] = {}
        self.keyboard = _FakeKeyboard(self)
        self.viewport = {"width": 1280, "height": 720}
        self.active_overlay_selector: str | None = None
        self.overlay_candidates: list[dict[str, object]] = []
        self.main_frame = FakePlaywrightFrame(page=self, frame_path=())
        self.main_frame.interactive_items = [dict(item) for item in self._interactive_items]
        self._frame_selector_map: dict[str, tuple[int, ...]] = {}

    def locator(self, selector: str) -> FakePlaywrightLocator:
        return self.main_frame.locator(selector)

    def get_by_role(self, role: str, **kwargs):  # noqa: ANN003
        return self.main_frame.get_by_role(role, **kwargs)

    def get_by_text(self, text: str, **kwargs):  # noqa: ANN003
        return self.main_frame.get_by_text(text, **kwargs)

    def wait_for_url(self, url: str, **kwargs) -> None:  # noqa: ANN003
        self.operations.append(("wait_for_url", url, dict(kwargs)))
        self.url = url

    def wait_for_function(self, expression: str, arg=None, **kwargs) -> None:  # noqa: ANN003
        self.operations.append(("wait_for_function", expression, arg, dict(kwargs)))
        for marker, failures in self.wait_for_function_failures.items():
            if marker in expression and failures:
                raise failures.pop(0)

    def wait_for_load_state(self, state: str, **kwargs) -> None:  # noqa: ANN003
        self.operations.append(("wait_for_load_state", state, dict(kwargs)))

    def wait_for_timeout(self, delay_ms: float) -> None:
        self.operations.append(("wait_for_timeout", delay_ms))

    def set_viewport_size(self, viewport: dict[str, int]) -> None:
        self.viewport = {
            "width": int(viewport["width"]),
            "height": int(viewport["height"]),
        }
        self.operations.append(("set_viewport_size", dict(self.viewport)))

    def evaluate(self, expression: str, arg=None):  # noqa: ANN001
        self.operations.append(("evaluate", expression, arg))
        if self.evaluate_failures:
            raise self.evaluate_failures.pop(0)
        if "__crxzipple_collect_interactive_refs__" in expression:
            return [dict(item) for item in self.interactive_items]
        if "__crxzipple_find_active_overlay__" in expression:
            return self.active_overlay_selector
        if "__crxzipple_find_associated_overlay__" in expression:
            return self.resolve_associated_overlay_selector(
                overlay_kind=(
                    str(arg.get("overlayKind")).strip()
                    if isinstance(arg, dict) and isinstance(arg.get("overlayKind"), str)
                    else None
                ),
                source_selector=(
                    str(arg.get("sourceSelector")).strip()
                    if isinstance(arg, dict) and isinstance(arg.get("sourceSelector"), str)
                    else None
                ),
                source_scope_selector=(
                    str(arg.get("sourceScopeSelector")).strip()
                    if isinstance(arg, dict) and isinstance(arg.get("sourceScopeSelector"), str)
                    else None
                ),
            )
        if "__crxzipple_collect_autocomplete_overlay_status__" in expression:
            return self.resolve_autocomplete_overlay_status(
                overlay_kind=(
                    str(arg.get("overlayKind")).strip()
                    if isinstance(arg, dict) and isinstance(arg.get("overlayKind"), str)
                    else None
                ),
                overlay_selector=(
                    str(arg.get("overlaySelector")).strip()
                    if isinstance(arg, dict) and isinstance(arg.get("overlaySelector"), str)
                    else None
                ),
                option_selector=(
                    str(arg.get("optionSelector")).strip()
                    if isinstance(arg, dict) and isinstance(arg.get("optionSelector"), str)
                    else None
                ),
                option_text=(
                    str(arg.get("optionText")).strip()
                    if isinstance(arg, dict) and isinstance(arg.get("optionText"), str)
                    else None
                ),
                exact=bool(arg.get("exact", False)) if isinstance(arg, dict) else False,
                active_overlay=bool(arg.get("activeOverlay", False)) if isinstance(arg, dict) else False,
                require_ready=bool(arg.get("requireReady", True)) if isinstance(arg, dict) else True,
                source_selector=(
                    str(arg.get("sourceSelector")).strip()
                    if isinstance(arg, dict) and isinstance(arg.get("sourceSelector"), str)
                    else None
                ),
                source_scope_selector=(
                    str(arg.get("sourceScopeSelector")).strip()
                    if isinstance(arg, dict) and isinstance(arg.get("sourceScopeSelector"), str)
                    else None
                ),
            )
        if "__crxzipple_collect_bulk_selection_candidates__" in expression:
            item_selector = None
            if isinstance(arg, dict):
                raw_selector = arg.get("itemSelector")
                if isinstance(raw_selector, str):
                    item_selector = raw_selector
            return [
                dict(item)
                for item in self.interactive_items
                if _matches_fake_item_selector(dict(item), item_selector)
            ]
        return {"expression": expression, "arg": arg}

    def screenshot(self, **kwargs) -> bytes:  # noqa: ANN003
        self.operations.append(("screenshot", dict(kwargs)))
        return b"fake-image"

    def pdf(self, **kwargs) -> bytes:  # noqa: ANN003
        self.operations.append(("pdf", dict(kwargs)))
        return b"fake-pdf"

    def content(self) -> str:
        self.operations.append(("content",))
        return f"<html><body>{self.body_text}</body></html>"

    def title(self) -> str:
        self.operations.append(("title",))
        return f"title:{self.target_id}"

    @property
    def interactive_items(self) -> list[dict[str, object]]:
        return [dict(item) for item in self._interactive_items]

    @interactive_items.setter
    def interactive_items(self, value: list[dict[str, object]]) -> None:
        self._interactive_items = [dict(item) for item in value]
        self.main_frame.interactive_items = [dict(item) for item in self._interactive_items]

    @property
    def frames(self) -> list[FakePlaywrightFrame]:
        resolved: list[FakePlaywrightFrame] = [self.main_frame]
        stack = list(self.main_frame.child_frames)
        while stack:
            frame = stack.pop(0)
            resolved.append(frame)
            stack[0:0] = frame.child_frames
        return resolved

    def add_child_frame(
        self,
        *,
        path: tuple[int, ...],
        body_text: str | None = None,
        interactive_items: list[dict[str, object]] | None = None,
        aria_snapshot_text: str | None = None,
        selector: str | None = None,
    ) -> FakePlaywrightFrame:
        if not path:
            return self.main_frame
        current = self.main_frame
        current_path: tuple[int, ...] = ()
        for depth_index in path:
            while len(current.child_frames) <= depth_index:
                child_path = current_path + (len(current.child_frames),)
                current.child_frames.append(
                    FakePlaywrightFrame(page=self, frame_path=child_path)
                )
            current = current.child_frames[depth_index]
            current_path = current.frame_path
        if body_text is not None:
            current.body_text = body_text
        if interactive_items is not None:
            current.interactive_items = [dict(item) for item in interactive_items]
        if aria_snapshot_text is not None:
            current.aria_snapshot_text = aria_snapshot_text
        if isinstance(selector, str) and selector.strip():
            self._frame_selector_map[selector.strip()] = current.frame_path
        return current

    def resolve_frame_selector(self, selector: str) -> FakePlaywrightFrame | None:
        normalized = str(selector).strip()
        if not normalized:
            return None
        frame_path = self._frame_selector_map.get(normalized)
        if frame_path is None:
            return None
        for frame in self.frames:
            if frame.frame_path == frame_path:
                return frame
        return None

    def resolve_active_overlay_selector(self) -> str | None:
        return self.active_overlay_selector

    def resolve_associated_overlay_selector(
        self,
        *,
        overlay_kind: str | None = None,
        source_selector: str | None = None,
        source_scope_selector: str | None = None,
    ) -> str | None:
        if not self.overlay_candidates:
            return self.active_overlay_selector
        best_selector = None
        best_score = None
        for index, item in enumerate(self.overlay_candidates):
            selector = str(item.get("selector") or "").strip()
            if not selector:
                continue
            score = index
            if overlay_kind is not None and str(item.get("kind") or "").strip() == overlay_kind:
                score += 3500
            if source_scope_selector is not None and str(item.get("source_scope_selector") or "").strip() == source_scope_selector:
                score += 1000
            if source_selector is not None and str(item.get("source_selector") or "").strip() == source_selector:
                score += 1500
            if bool(item.get("active", False)):
                score += 500
            if best_score is None or score > best_score:
                best_score = score
                best_selector = selector
        return best_selector or self.active_overlay_selector

    def resolve_autocomplete_overlay_status(
        self,
        *,
        overlay_kind: str | None = None,
        overlay_selector: str | None = None,
        option_selector: str | None = None,
        option_text: str | None = None,
        exact: bool = False,
        active_overlay: bool = False,
        require_ready: bool = True,
        source_selector: str | None = None,
        source_scope_selector: str | None = None,
    ) -> dict[str, object] | None:
        normalized_option_text = str(option_text).strip() if isinstance(option_text, str) and option_text.strip() else None
        normalized_option_selector = str(option_selector).strip() if isinstance(option_selector, str) and option_selector.strip() else None
        resolved_overlay = (
            (str(overlay_selector).strip() if isinstance(overlay_selector, str) and overlay_selector.strip() else None)
            or self.resolve_associated_overlay_selector(
                overlay_kind=overlay_kind,
                source_selector=source_selector,
                source_scope_selector=source_scope_selector,
            )
            or (self.active_overlay_selector if active_overlay else None)
            or self.active_overlay_selector
        )
        if not resolved_overlay:
            if require_ready:
                return None
            return {
                "overlaySelector": None,
                "overlayKind": overlay_kind,
                "candidateCount": 0,
                "matchedCandidateCount": 0,
                "ready": False,
                "readyVia": "text-match" if normalized_option_text is not None else "candidate-count",
                "optionSelector": normalized_option_selector,
                "sourceBound": bool(source_selector or source_scope_selector),
                "associationReason": None,
                "failureReason": "overlay-not-found",
                "candidatePreview": [],
            }
        candidates: list[dict[str, object]] = []
        matched_candidates: list[dict[str, object]] = []
        for item in self.interactive_items:
            item_scope = str(item.get("scope_selector") or "").strip()
            if item_scope != resolved_overlay:
                continue
            if normalized_option_selector is not None:
                item_selector = str(item.get("selector") or "").strip()
                if item_selector != normalized_option_selector:
                    continue
            if not bool(item.get("visible", True)):
                continue
            if bool(item.get("disabled", False)):
                continue
            candidate = dict(item)
            candidates.append(candidate)
            if normalized_option_text is None:
                matched_candidates.append(candidate)
                continue
            candidate_text = str(item.get("text") or item.get("label") or "").strip()
            if exact:
                if candidate_text == normalized_option_text:
                    matched_candidates.append(candidate)
            elif normalized_option_text in candidate_text:
                matched_candidates.append(candidate)
        association_reason = "explicit-overlay-selector" if overlay_selector else (
            "source-scope" if source_scope_selector else (
                "source-selector" if source_selector else (
                    "active-overlay" if active_overlay or self.active_overlay_selector == resolved_overlay else "best-score"
                )
            )
        )
        if not candidates:
            if require_ready:
                return None
            return {
                "overlaySelector": resolved_overlay,
                "overlayKind": overlay_kind,
                "candidateCount": 0,
                "matchedCandidateCount": 0,
                "ready": False,
                "readyVia": "text-match" if normalized_option_text is not None else "candidate-count",
                "optionSelector": normalized_option_selector,
                "sourceBound": bool(source_selector or source_scope_selector),
                "associationReason": association_reason,
                "failureReason": "overlay-without-candidates",
                "candidatePreview": [],
            }
        if normalized_option_text is not None and not matched_candidates:
            if require_ready:
                return None
            return {
                "overlaySelector": resolved_overlay,
                "overlayKind": overlay_kind,
                "candidateCount": len(candidates),
                "matchedCandidateCount": 0,
                "ready": False,
                "readyVia": "text-match",
                "optionSelector": normalized_option_selector,
                "sourceBound": bool(source_selector or source_scope_selector),
                "associationReason": association_reason,
                "failureReason": "overlay-without-matching-candidates",
                "candidatePreview": [
                    str(item.get("text") or item.get("label") or "").strip()
                    for item in candidates[:5]
                    if str(item.get("text") or item.get("label") or "").strip()
                ],
            }
        return {
            "overlaySelector": resolved_overlay,
            "overlayKind": overlay_kind,
            "candidateCount": len(candidates),
            "matchedCandidateCount": len(matched_candidates),
            "readyVia": "text-match" if normalized_option_text is not None else "candidate-count",
            "optionSelector": normalized_option_selector,
            "sourceBound": bool(source_selector or source_scope_selector),
            "associationReason": association_reason,
            "failureReason": None,
            "candidatePreview": [
                str(item.get("text") or item.get("label") or "").strip()
                for item in candidates[:5]
                if str(item.get("text") or item.get("label") or "").strip()
            ],
        }

    def resolve_datepicker_panel_status(
        self,
        *,
        overlay_selector: str | None = None,
        month_header_selector: str | None = None,
        limit: int = 7,
    ) -> dict[str, object] | None:
        resolved_overlay = (
            str(overlay_selector).strip()
            if isinstance(overlay_selector, str) and overlay_selector.strip()
            else self.active_overlay_selector
        )
        if not resolved_overlay:
            return None
        scoped_items = [
            dict(item)
            for item in self.interactive_items
            if str(item.get("scope_selector") or "").strip() == resolved_overlay
        ]
        current_month_text = None
        normalized_header_selector = (
            str(month_header_selector).strip()
            if isinstance(month_header_selector, str) and month_header_selector.strip()
            else None
        )
        if normalized_header_selector is not None:
            for item in scoped_items:
                if str(item.get("selector") or "").strip() == normalized_header_selector:
                    current_month_text = str(item.get("text") or item.get("label") or "").strip() or None
                    break
        if current_month_text is None:
            for item in scoped_items:
                role = str(item.get("role") or "").strip().lower()
                selector = str(item.get("selector") or "").strip().lower()
                if role == "heading" or "header" in selector or "month" in selector:
                    current_month_text = str(item.get("text") or item.get("label") or "").strip() or None
                    if current_month_text is not None:
                        break
        day_preview: list[str] = []
        disabled_day_count = 0
        for item in scoped_items:
            text = str(item.get("text") or item.get("label") or "").strip()
            if text.isdigit() and 1 <= len(text) <= 2:
                day_preview.append(text)
                if bool(item.get("disabled", False)) or bool(item.get("outside_current_month", False)):
                    disabled_day_count += 1
        return {
            "overlaySelector": resolved_overlay,
            "currentMonthText": current_month_text,
            "dayPreview": day_preview[: max(1, int(limit))],
            "dayCount": len(day_preview),
            "disabledDayCount": disabled_day_count,
        }


class FakePlaywrightCdpSessionPool:
    last_created: "FakePlaywrightCdpSessionPool | None" = None
    page_initializers: dict[str, object] = {}

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        del args, kwargs
        self.pages: dict[str, FakePlaywrightPage] = {}
        self.resolve_calls: list[dict[str, object]] = []
        type(self).last_created = self

    def resolve_page(
        self,
        *,
        profile,
        target_id: str,
        timeout_ms: int | None = None,
        cdp_url: str | None = None,
    ):  # noqa: ANN001
        self.resolve_calls.append(
            {
                "profile_name": getattr(profile, "name", None),
                "target_id": target_id,
                "timeout_ms": timeout_ms,
                "cdp_url": cdp_url,
            }
        )
        page = self.pages.get(target_id)
        if page is None:
            page = FakePlaywrightPage(target_id=target_id)
            self.pages[target_id] = page
        initializer = type(self).page_initializers.get(target_id)
        if callable(initializer):
            initializer(page)
        return page

    def clear_profile(self, *, profile_name: str) -> None:
        del profile_name
        self.pages.clear()

    def close(self) -> None:
        self.pages.clear()

    @staticmethod
    def browser_ref_to_cdp_url(browser_ref: str | None) -> str | None:
        if not isinstance(browser_ref, str):
            return None
        if browser_ref.startswith("ws://"):
            return "http://" + browser_ref[len("ws://") :].split("/", 1)[0]
        if browser_ref.startswith("wss://"):
            return "https://" + browser_ref[len("wss://") :].split("/", 1)[0]
        return None


class FakeChromeMcpClientPool:
    def __init__(self) -> None:
        self.operations: list[tuple[object, ...]] = []
        self._tabs: dict[str, list[BrowserTab]] = {}
        self._next_ids: dict[str, int] = {}
        self._snapshots: dict[tuple[str, str], dict[str, object]] = {}
        self._evaluate_overrides: dict[tuple[str, str, str], object] = {}
        self._pids: dict[str, int | None] = {}

    def ensure_available(self, *, profile_name: str, system, user_data_dir: str | None = None) -> None:  # noqa: ANN001
        del system
        self.operations.append(("ensure_available", profile_name, user_data_dir))

    def get_pid(self, *, profile_name: str, system, user_data_dir: str | None = None) -> int | None:  # noqa: ANN001
        del system, user_data_dir
        return self._pids.get(profile_name, 4321)

    def close_profile(self, *, profile_name: str) -> None:
        self.operations.append(("close_profile", profile_name))

    def close(self) -> None:
        self.operations.append(("close",))

    def list_tabs(self, *, profile_name: str, system, user_data_dir: str | None = None) -> tuple[BrowserTab, ...]:  # noqa: ANN001
        del system
        self.operations.append(("list_tabs", profile_name, user_data_dir))
        return tuple(self._tabs.get(profile_name, ()))

    def open_tab(self, *, profile_name: str, system, url: str, user_data_dir: str | None = None) -> BrowserTab:  # noqa: ANN001
        del system
        next_id = self._next_ids.get(profile_name, 1)
        self._next_ids[profile_name] = next_id + 1
        tab = BrowserTab(target_id=str(next_id), url=url, title="", type="page")
        self._tabs.setdefault(profile_name, []).append(tab)
        self.operations.append(("open_tab", profile_name, url, user_data_dir))
        return tab

    def focus_tab(self, *, profile_name: str, system, target_id: str, user_data_dir: str | None = None) -> None:  # noqa: ANN001
        del system
        self.operations.append(("focus_tab", profile_name, target_id, user_data_dir))

    def close_tab(self, *, profile_name: str, system, target_id: str, user_data_dir: str | None = None) -> None:  # noqa: ANN001
        del system
        self.operations.append(("close_tab", profile_name, target_id, user_data_dir))
        self._tabs[profile_name] = [
            tab for tab in self._tabs.get(profile_name, []) if tab.target_id != target_id
        ]

    def navigate_tab(
        self,
        *,
        profile_name: str,
        system,
        target_id: str,
        url: str,
        user_data_dir: str | None = None,
        timeout_ms: int | None = None,
    ) -> BrowserTab:  # noqa: ANN001
        del system
        self.operations.append(
            ("navigate_tab", profile_name, target_id, url, user_data_dir, timeout_ms)
        )
        updated_tabs: list[BrowserTab] = []
        resolved: BrowserTab | None = None
        for tab in self._tabs.get(profile_name, []):
            if tab.target_id == target_id:
                resolved = BrowserTab(target_id=tab.target_id, url=url, title="", type=tab.type)
                updated_tabs.append(resolved)
            else:
                updated_tabs.append(tab)
        self._tabs[profile_name] = updated_tabs
        if resolved is None:
            resolved = BrowserTab(target_id=target_id, url=url, title="", type="page")
        return resolved

    def take_snapshot(self, *, profile_name: str, system, target_id: str, user_data_dir: str | None = None) -> dict[str, object]:  # noqa: ANN001
        del system
        self.operations.append(("take_snapshot", profile_name, target_id, user_data_dir))
        return dict(
            self._snapshots.get(
                (profile_name, target_id),
                {
                    "role": "document",
                    "children": [
                        {
                            "id": "e1",
                            "role": "button",
                            "name": "Submit",
                        },
                        {
                            "id": "e2",
                            "role": "textbox",
                            "name": "Search",
                        },
                    ],
                },
            )
        )

    def take_screenshot(
        self,
        *,
        profile_name: str,
        system,
        target_id: str,
        user_data_dir: str | None = None,
        uid: str | None = None,
        full_page: bool = False,
        image_format: str = "png",
    ) -> bytes:  # noqa: ANN001
        del system
        self.operations.append(
            (
                "take_screenshot",
                profile_name,
                target_id,
                uid,
                user_data_dir,
                full_page,
                image_format,
            )
        )
        return b"fake-mcp-image"

    def click_element(
        self,
        *,
        profile_name: str,
        system,
        target_id: str,
        uid: str,
        user_data_dir: str | None = None,
        double_click: bool = False,
    ) -> None:  # noqa: ANN001
        del system
        self.operations.append(
            ("click", profile_name, target_id, uid, user_data_dir, double_click)
        )

    def fill_element(
        self,
        *,
        profile_name: str,
        system,
        target_id: str,
        uid: str,
        value: str,
        user_data_dir: str | None = None,
    ) -> None:  # noqa: ANN001
        del system
        self.operations.append(("fill", profile_name, target_id, uid, value, user_data_dir))

    def hover_element(
        self,
        *,
        profile_name: str,
        system,
        target_id: str,
        uid: str,
        user_data_dir: str | None = None,
    ) -> None:  # noqa: ANN001
        del system
        self.operations.append(("hover", profile_name, target_id, uid, user_data_dir))

    def drag_element(
        self,
        *,
        profile_name: str,
        system,
        target_id: str,
        from_uid: str,
        to_uid: str,
        user_data_dir: str | None = None,
    ) -> None:  # noqa: ANN001
        del system
        self.operations.append(
            ("drag", profile_name, target_id, from_uid, to_uid, user_data_dir)
        )

    def resize_page(
        self,
        *,
        profile_name: str,
        system,
        target_id: str,
        width: int,
        height: int,
        user_data_dir: str | None = None,
    ) -> None:  # noqa: ANN001
        del system
        self.operations.append(
            ("resize_page", profile_name, target_id, width, height, user_data_dir)
        )

    def press_key(
        self,
        *,
        profile_name: str,
        system,
        target_id: str,
        key: str,
        user_data_dir: str | None = None,
    ) -> None:  # noqa: ANN001
        del system
        self.operations.append(("press_key", profile_name, target_id, key, user_data_dir))

    def evaluate_script(
        self,
        *,
        profile_name: str,
        system,
        target_id: str,
        fn: str,
        user_data_dir: str | None = None,
        args: list[str] | None = None,
    ):  # noqa: ANN001
        del system
        self.operations.append(
            ("evaluate_script", profile_name, target_id, fn, user_data_dir, tuple(args or ()))
        )
        override_key = (profile_name, target_id, fn)
        if override_key in self._evaluate_overrides:
            return self._evaluate_overrides[override_key]
        if "document.title" in fn:
            return f"title:{target_id}"
        if "window.location.href" in fn or "location.href" in fn:
            for tab in self._tabs.get(profile_name, []):
                if tab.target_id == target_id:
                    return tab.url
            return ""
        if "document.readystate" in fn.lower():
            return "complete"
        if "document.queryselector" in fn.lower():
            return True
        if "outerHTML" in fn:
            return f"<html><body>{target_id}</body></html>"
        if "innerText" in fn:
            return f"body:{target_id}"
        return {"fn": fn, "args": list(args or ())}

    def wait_for_text(
        self,
        *,
        profile_name: str,
        system,
        target_id: str,
        text: list[str],
        user_data_dir: str | None = None,
        timeout_ms: int | None = None,
    ) -> None:  # noqa: ANN001
        del system
        self.operations.append(
            ("wait_for_text", profile_name, target_id, tuple(text), user_data_dir, timeout_ms)
        )

    def set_snapshot(
        self,
        *,
        profile_name: str,
        target_id: str,
        snapshot: dict[str, object],
    ) -> None:
        self._snapshots[(profile_name, target_id)] = dict(snapshot)

    def set_evaluate_result(
        self,
        *,
        profile_name: str,
        target_id: str,
        fn: str,
        value: object,
    ) -> None:
        self._evaluate_overrides[(profile_name, target_id, fn)] = value


class SampleLlmApiServer:
    def __init__(self, *, tool_calls_on_tools: bool = False) -> None:
        self._server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            _build_sample_llm_api_handler(tool_calls_on_tools=tool_calls_on_tools),
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="sample-llm-api-server",
            daemon=True,
        )

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


class SampleEmbeddingApiServer:
    def __init__(self) -> None:
        self._server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            _build_sample_embedding_api_handler(),
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="sample-embedding-api-server",
            daemon=True,
        )

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


def _build_sample_api_handler() -> type[BaseHTTPRequestHandler]:
    class SampleApiHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.startswith("/echo/"):
                message = parsed.path.removeprefix("/echo/")
                query = parse_qs(parsed.query)
                if query.get("api_key", [""])[0] != "sample-api-key":
                    self._write_json(401, {"detail": "invalid api key"})
                    return
                uppercase = query.get("uppercase", ["false"])[0].lower() == "true"
                payload = {
                    "message": message.upper() if uppercase else message,
                    "uppercase": uppercase,
                }
                self._write_json(200, payload)
                return

            if parsed.path == "/search":
                if self.headers.get("Authorization") != "Bearer sample-bearer-token":
                    self._write_json(401, {"detail": "missing bearer token"})
                    return
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                payload = {
                    "query": body.get("query"),
                    "limit": body.get("limit", 10),
                    "items": [f"result:{body.get('query', '')}"],
                }
                self._write_json(200, payload)
                return

            self._write_json(404, {"detail": "not found"})

        def log_message(self, format: str, *args: object) -> None:
            return

        def _write_json(self, status_code: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return SampleApiHandler


def _build_fake_cdp_handler() -> type[BaseHTTPRequestHandler]:
    class FakeCdpHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            server = self.server

            if parsed.path == "/json/version":
                host, port = server.server_address
                self._write_json(
                    200,
                    {
                        "Browser": "FakeCDP/1.0",
                        "webSocketDebuggerUrl": f"ws://{host}:{port}/devtools/browser/fake-browser",
                    },
                )
                return

            if parsed.path == "/json/list":
                tabs = list(server.tabs.values())  # type: ignore[attr-defined]
                self._write_json(200, tabs)
                return

            if parsed.path.startswith("/json/activate/"):
                target_id = parsed.path.rsplit("/", 1)[-1]
                if target_id not in server.tabs:  # type: ignore[attr-defined]
                    self._write_json(404, {"detail": "tab not found"})
                    return
                server.active_target_id = target_id  # type: ignore[attr-defined]
                self._write_json(200, {"ok": True, "target_id": target_id})
                return

            if parsed.path.startswith("/json/close/"):
                target_id = parsed.path.rsplit("/", 1)[-1]
                tabs = server.tabs  # type: ignore[attr-defined]
                if target_id not in tabs:
                    self._write_json(404, {"detail": "tab not found"})
                    return
                tabs.pop(target_id, None)
                if server.active_target_id == target_id:  # type: ignore[attr-defined]
                    server.active_target_id = None  # type: ignore[attr-defined]
                self._write_json(200, {"ok": True, "target_id": target_id})
                return

            if parsed.path == "/json/new":
                self._handle_new_tab(parsed)
                return

            self._write_json(404, {"detail": "not found"})

        def do_PUT(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/json/new":
                self._handle_new_tab(parsed)
                return
            self._write_json(404, {"detail": "not found"})

        def log_message(self, format: str, *args: object) -> None:
            return

        def _handle_new_tab(self, parsed) -> None:  # noqa: ANN001
            raw_query = parsed.query or ""
            query = parse_qs(raw_query)
            url = query.get("url", [unquote(raw_query)])[0] or "about:blank"
            server = self.server
            target_id = f"tab-{server.next_tab_id}"  # type: ignore[attr-defined]
            server.next_tab_id += 1  # type: ignore[attr-defined]
            host, port = server.server_address
            payload = {
                "id": target_id,
                "type": "page",
                "title": url,
                "url": url,
                "webSocketDebuggerUrl": f"ws://{host}:{port}/devtools/page/{target_id}",
            }
            server.tabs[target_id] = payload  # type: ignore[attr-defined]
            server.active_target_id = target_id  # type: ignore[attr-defined]
            self._write_json(200, payload)

        def _write_json(self, status_code: int, payload: dict[str, object] | list[object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return FakeCdpHandler


def _build_sample_llm_api_handler(
    *,
    tool_calls_on_tools: bool = False,
) -> type[BaseHTTPRequestHandler]:
    class SampleLlmApiHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/v1/chat/completions":
                self._write_json(404, {"detail": "not found"})
                return

            if self.headers.get("Authorization") != "Bearer sample-compat-token":
                self._write_json(401, {"detail": "invalid bearer token"})
                return

            length = int(self.headers.get("Content-Length", "0"))
            payload = (
                json.loads(self.rfile.read(length).decode("utf-8"))
                if length
                else {}
            )
            messages = payload.get("messages")
            if not isinstance(messages, list) or not messages:
                self._write_json(400, {"detail": "messages are required"})
                return

            tool_calls: list[dict[str, object]] = []
            tools = payload.get("tools")
            if tool_calls_on_tools and isinstance(tools, list) and tools:
                first_tool = tools[0]
                function_payload = (
                    first_tool.get("function")
                    if isinstance(first_tool, dict)
                    else None
                )
                tool_name = (
                    function_payload.get("name")
                    if isinstance(function_payload, dict)
                    else "search_docs"
                )
                tool_calls.append(
                    {
                        "id": "call_sample_1",
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps({"query": "ddd"}),
                        },
                    },
                )

            self._write_json(
                200,
                {
                    "id": "chatcmpl_sample_1",
                    "model": payload.get("model", "sample-model"),
                    "choices": [
                        {
                            "finish_reason": "tool_calls" if tool_calls else "stop",
                            "message": {
                                "role": "assistant",
                                "content": "hello from sample llm",
                                "tool_calls": tool_calls,
                            },
                        },
                    ],
                    "usage": {
                        "prompt_tokens": 13,
                        "completion_tokens": 8,
                        "total_tokens": 21,
                    },
                },
            )

        def log_message(self, format: str, *args: object) -> None:
            return

        def _write_json(self, status_code: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return SampleLlmApiHandler


def _build_sample_embedding_api_handler() -> type[BaseHTTPRequestHandler]:
    class SampleEmbeddingApiHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/v1/embeddings":
                self._write_json(404, {"detail": "not found"})
                return

            if self.headers.get("Authorization") != "Bearer sample-embedding-token":
                self._write_json(401, {"detail": "invalid bearer token"})
                return

            length = int(self.headers.get("Content-Length", "0"))
            payload = (
                json.loads(self.rfile.read(length).decode("utf-8"))
                if length
                else {}
            )
            inputs = payload.get("input")
            if isinstance(inputs, str):
                normalized_inputs = [inputs]
            elif isinstance(inputs, list):
                normalized_inputs = [str(item) for item in inputs]
            else:
                self._write_json(400, {"detail": "input is required"})
                return

            self._write_json(
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "object": "embedding",
                            "index": index,
                            "embedding": _sample_embedding_for_text(text),
                        }
                        for index, text in enumerate(normalized_inputs)
                    ],
                    "model": payload.get("model", "sample-embedding-model"),
                },
            )

        def log_message(self, format: str, *args: object) -> None:
            return

        def _write_json(self, status_code: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return SampleEmbeddingApiHandler


def _sample_embedding_for_text(text: str) -> list[float]:
    normalized = " ".join(text.casefold().split())
    if "checklist" in normalized or "cheklist" in normalized:
        return [1.0, 0.0, 0.0]
    if "approval" in normalized or "effect" in normalized:
        return [0.0, 1.0, 0.0]
    return [0.0, 0.0, 1.0]
