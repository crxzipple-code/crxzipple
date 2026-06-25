from __future__ import annotations

from typing import Any

from crxzipple.modules.browser.domain import (
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserProfileRuntimeState,
    BrowserTab,
    BrowserValidationError,
)

from .action_engine_locators import _locator_exact, _locator_ordinal
from .action_engine_payloads import (
    _payload_number_any,
    _payload_text_any,
    _payload_value_any,
    _timeout_kwargs,
)
from .action_engine_snapshots import _normalize_text_payload


class BrowserWaitActionMixin:
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
