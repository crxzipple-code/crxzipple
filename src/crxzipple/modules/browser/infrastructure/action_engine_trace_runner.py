from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.browser.domain import (
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserProfileRuntimeState,
    BrowserTab,
    BrowserValidationError,
)


class BrowserActionTraceRunnerMixin:
    def _execute_action_trace(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
        batch_depth: int,
    ) -> Mapping[str, Any]:
        protected_ref = self._action_trace_protected_ref(
            plan=plan,
            tab=tab,
            command=command,
        )
        snapshot_calls = 0

        def snapshot_action(
            snapshot_command: BrowserPageActionCommand,
        ) -> Mapping[str, Any]:
            nonlocal snapshot_calls
            snapshot_calls += 1
            result = self._snapshot(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                command=snapshot_command,
            )
            runtime_state.remember_page_snapshot(
                target_id=tab.target_id,
                generation=int(result.get("generation") or 1),
                snapshot_format=str(result.get("format") or "snapshot"),
                ref_count=int(result.get("ref_count") or 0),
                frame_count=int(result.get("frame_count") or 0),
            )
            if snapshot_calls == 1 and protected_ref is not None:
                self._restore_action_trace_protected_ref(
                    plan=plan,
                    tab=tab,
                    protected_ref=protected_ref,
                )
            return result

        def network_action(
            network_command: BrowserPageActionCommand,
        ) -> Mapping[str, Any]:
            if self.network_action_service is None:
                raise BrowserValidationError("Browser network action service is not configured.")
            return self.network_action_service.execute(
                plan=plan,
                tab=tab,
                page=page,
                command=network_command,
            )

        def execute_inner(
            inner_command: BrowserPageActionCommand,
            next_batch_depth: int,
        ) -> tuple[Any, str | None, tuple[int, ...] | None]:
            return self._execute_on_page(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                command=inner_command,
                batch_depth=next_batch_depth,
            )

        def console_messages(limit: int) -> list[dict[str, Any]]:
            return [
                dict(item)
                for item in self.session_pool.get_console_messages(
                    page=page,
                    level=None,
                    limit=limit,
                    clear=False,
                )
                if isinstance(item, dict)
            ]

        def page_errors(limit: int) -> list[dict[str, Any]]:
            get_page_errors = getattr(self.session_pool, "get_page_errors", None)
            if not callable(get_page_errors):
                return []
            return [
                dict(item)
                for item in get_page_errors(
                    page=page,
                    limit=limit,
                    clear=False,
                )
                if isinstance(item, dict)
            ]

        return self.action_trace_service.execute(
            plan=plan,
            tab=tab,
            page=page,
            runtime_state=runtime_state,
            command=command,
            batch_depth=batch_depth,
            snapshot=snapshot_action,
            network_action=network_action,
            execute_inner=execute_inner,
            console_messages=console_messages,
            page_errors=page_errors,
        )
