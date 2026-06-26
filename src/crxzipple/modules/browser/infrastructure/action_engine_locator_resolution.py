from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.browser.domain import (
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserProfileRuntimeState,
    BrowserTab,
    BrowserValidationError,
)

from .action_engine_locators import (
    _allows_implicit_selector_ordinal,
    _locator_ordinal,
    _scope_ref_id,
    _scope_selector,
    _stored_ref_name,
)
from .action_engine_scripts import _TARGET_INFO_EXPRESSION
from .action_engine_snapshots import _main_frame, _resolve_frame_context
from .role_snapshot import describe_role_locator


class BrowserLocatorResolutionMixin:
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
            ordinal_label = (
                "auto-ordinal" if _locator_ordinal(command.payload) is None else "ordinal"
            )
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
            if (
                item.selector is None
                and item.role is None
                and item.backend_node_id is None
            ):
                raise BrowserValidationError(
                    f"Browser ref '{ref_id}' does not expose a supported locator.",
                )
            context = _resolve_frame_context(page, item.frame_path)
            generation_mismatch = (
                current_generation and item.generation != current_generation
            )
            devtools_locator, devtools_description = self._devtools_locator_from_ref_item(
                page=page,
                context=context,
                item=item,
            )
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
                if devtools_locator is not None:
                    return (
                        context,
                        devtools_locator,
                        devtools_description,
                        item.frame_path,
                    )
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
            if devtools_locator is not None:
                return (
                    context,
                    devtools_locator,
                    devtools_description,
                    item.frame_path,
                )
            if (
                item.selector is not None
                and not generation_mismatch
                and item.nth is None
            ):
                return (
                    context,
                    context.locator(item.selector),
                    item.selector,
                    item.frame_path,
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


__all__ = ["BrowserLocatorResolutionMixin"]
