from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from crxzipple.modules.browser.domain import (
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserProfileRuntimeState,
    BrowserStoredRef,
    BrowserTab,
    BrowserValidationError,
)
from crxzipple.modules.browser.domain.value_objects import _normalize_optional_text

from .action_engine_locators import (
    _active_overlay,
    _command_overlay_source_refs,
    _command_overlay_source_scope_selectors,
    _command_overlay_source_selectors,
    _devtools_ref_marker_value,
    _explicit_overlay_kind,
    _locator_exact,
    _locator_ordinal,
    _scope_ref_id,
    _scope_selector,
    _stored_ref_name,
    _wait_prefers_active_overlay,
)
from .action_engine_payloads import _payload_text_any, _timeout_kwargs
from .action_engine_scripts import (
    _ACTIVE_OVERLAY_SELECTOR_EXPRESSION,
    _ASSOCIATED_OVERLAY_SELECTOR_EXPRESSION,
    _TEXT_MATCH_ORDINAL_EXPRESSION,
)
from .action_engine_snapshots import (
    _active_overlay_selector,
    _associated_overlay_selector,
    _main_frame,
)
from .role_snapshot import describe_role_locator

_DEVTOOLS_REF_ATTRIBUTE = "data-crxzipple-backend-ref"


def _stored_ref_has_precise_locator(item: BrowserStoredRef) -> bool:
    return item.selector is not None or item.backend_node_id is not None or item.uid is not None


def _stored_refs_look_compatible(
    protected: BrowserStoredRef,
    current: BrowserStoredRef,
) -> bool:
    if protected.frame_path != current.frame_path:
        return False
    protected_role = _normalize_optional_text(protected.role)
    current_role = _normalize_optional_text(current.role)
    if protected_role is not None and current_role is not None and protected_role != current_role:
        return False
    protected_name = _stored_ref_name(protected)
    current_name = _stored_ref_name(current)
    if protected_name is not None and current_name is not None and protected_name != current_name:
        return False
    return True


def _merge_protected_ref_locator(
    *,
    current: BrowserStoredRef,
    protected: BrowserStoredRef,
) -> BrowserStoredRef:
    return replace(
        current,
        selector=protected.selector or current.selector,
        scope_selector=protected.scope_selector or current.scope_selector,
        uid=protected.uid or current.uid,
        backend_node_id=protected.backend_node_id or current.backend_node_id,
        bbox=current.bbox or protected.bbox,
        evidence=current.evidence or protected.evidence,
        confidence=(
            current.confidence
            if current.confidence is not None
            else protected.confidence
        ),
    )



class BrowserRefOverlayMixin:
    def _action_trace_protected_ref(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        command: BrowserPageActionCommand,
    ) -> BrowserStoredRef | None:
        ref_id = (
            _payload_text_any(command.payload, "action_ref", "actionRef")
            or command.target.ref
        )
        if ref_id is None:
            return None
        item = self._stored_ref_for_ref_id(plan=plan, tab=tab, ref_id=ref_id)
        if item is None or not _stored_ref_has_precise_locator(item):
            return None
        return item

    def _restore_action_trace_protected_ref(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        protected_ref: BrowserStoredRef,
    ) -> None:
        current_refs = list(
            self.ref_store.get_tab_refs(
                profile_name=plan.profile.name,
                target_id=tab.target_id,
            )
        )
        for index, item in enumerate(current_refs):
            if item.ref != protected_ref.ref:
                continue
            if not _stored_refs_look_compatible(protected_ref, item):
                return
            if _stored_ref_has_precise_locator(item):
                return
            current_refs[index] = _merge_protected_ref_locator(
                current=item,
                protected=protected_ref,
            )
            self.ref_store.save_tab_refs(
                profile_name=plan.profile.name,
                target_id=tab.target_id,
                refs=tuple(current_refs),
            )
            return

    def _stored_ref_for_command(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        command: BrowserPageActionCommand,
    ) -> BrowserStoredRef | None:
        ref_id = command.target.ref
        if ref_id is None:
            return None
        return self._stored_ref_for_ref_id(plan=plan, tab=tab, ref_id=ref_id)

    def _stored_ref_for_ref_id(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        ref_id: str,
    ) -> BrowserStoredRef | None:
        for item in self.ref_store.get_tab_refs(
            profile_name=plan.profile.name,
            target_id=tab.target_id,
        ):
            if item.ref == ref_id:
                return item
        return None

    def _devtools_event_listeners_for_command(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        command: BrowserPageActionCommand,
    ) -> dict[str, Any] | None:
        if self.devtools_adapter is None:
            return None
        item = self._stored_ref_for_command(plan=plan, tab=tab, command=command)
        if item is None or item.backend_node_id is None or item.frame_path:
            return None
        try:
            return self.devtools_adapter.get_event_listeners_for_backend_node(
                page,
                backend_node_id=item.backend_node_id,
                depth=1,
                pierce=True,
            )
        except BrowserValidationError as exc:
            return {"error": str(exc), "listeners": []}

    def _devtools_locator_from_ref_item(
        self,
        *,
        page,
        context,
        item: BrowserStoredRef,
    ) -> tuple[Any, str] | tuple[None, None]:
        if item.backend_node_id is None:
            return None, None
        if item.frame_path:
            return None, None
        locator_factory = getattr(context, "locator", None)
        if not callable(locator_factory):
            return None, None
        adapter = self.devtools_adapter
        if adapter is None:
            return None, None
        marker_value = _devtools_ref_marker_value(item)
        try:
            adapter.mark_backend_node(
                page,
                backend_node_id=item.backend_node_id,
                attribute_name=_DEVTOOLS_REF_ATTRIBUTE,
                attribute_value=marker_value,
            )
        except BrowserValidationError:
            return None, None
        selector = f'[{_DEVTOOLS_REF_ATTRIBUTE}="{marker_value}"]'
        return locator_factory(selector), f"backendNodeId={item.backend_node_id}"

    def _anchored_locator_from_ref_item(
        self,
        *,
        context,
        item: BrowserStoredRef,
    ) -> tuple[Any, str] | tuple[None, None]:
        scope_selector = _normalize_optional_text(item.scope_selector)
        if scope_selector is None:
            return None, None
        scoped_root = context.locator(scope_selector)

        role_locator = self._semantic_locator_from_ref_item(context=scoped_root, item=item)
        if role_locator is not None:
            return (
                role_locator,
                f"{scope_selector} >> {describe_role_locator(role=item.role or 'generic', name=_stored_ref_name(item), nth=item.nth)}",
            )

        name = _stored_ref_name(item)
        if name is None:
            return None, None
        text_factory = getattr(scoped_root, "get_by_text", None)
        if not callable(text_factory):
            return None, None
        text_locator = text_factory(name, exact=True)
        if item.nth is not None:
            nth_method = getattr(text_locator, "nth", None)
            if not callable(nth_method):
                raise BrowserValidationError(
                    f"Browser ref '{item.ref}' requires nth text resolution, but the Playwright locator does not support nth().",
                )
            text_locator = nth_method(item.nth)
        description = f'{scope_selector} >> text="{name}"'
        if item.nth is not None:
            description = f"{description}[nth={item.nth}]"
        return text_locator, description

    def _semantic_locator_from_ref_item(self, *, context, item: BrowserStoredRef):  # noqa: ANN001
        locator_factory = getattr(context, "get_by_role", None)
        if not callable(locator_factory) or item.role is None:
            return None
        role_kwargs: dict[str, Any] = {}
        name = _stored_ref_name(item)
        if name is not None:
            role_kwargs["name"] = name
            role_kwargs["exact"] = True
        role_locator = locator_factory(item.role, **role_kwargs)
        if item.nth is not None:
            nth_method = getattr(role_locator, "nth", None)
            if not callable(nth_method):
                raise BrowserValidationError(
                    f"Browser ref '{item.ref}' requires nth role resolution, but the Playwright locator does not support nth().",
                )
            role_locator = nth_method(item.nth)
        return role_locator

    def _resolved_active_overlay_selector(
        self,
        *,
        page,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab,
        command: BrowserPageActionCommand | None = None,
        overlay_kind: str | None = None,
        source_refs: tuple[str, ...] = (),
        source_selectors: tuple[str, ...] = (),
        source_scope_selectors: tuple[str, ...] = (),
    ) -> str | None:
        candidate_refs = source_refs
        candidate_selectors = source_selectors
        candidate_scope_selectors = source_scope_selectors
        if command is not None:
            candidate_refs = candidate_refs + _command_overlay_source_refs(command)
            candidate_selectors = candidate_selectors + _command_overlay_source_selectors(
                command,
            )
            candidate_scope_selectors = (
                candidate_scope_selectors
                + _command_overlay_source_scope_selectors(command)
                + self._overlay_source_scope_selectors_for_command(
                    plan=None,
                    tab=tab,
                    runtime_state=runtime_state,
                    command=command,
                )
            )
            if overlay_kind is None:
                overlay_kind = self._overlay_kind_for_command(
                    runtime_state=runtime_state,
                    tab=tab,
                    command=command,
                )
        stored = runtime_state.active_overlay_selector(
            target_id=tab.target_id,
            overlay_kind=overlay_kind,
            source_refs=candidate_refs,
            source_selectors=candidate_selectors,
            source_scope_selectors=candidate_scope_selectors,
        )
        if stored is not None:
            return stored
        return _active_overlay_selector(page)

    def _overlay_source_selector_for_command(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
    ) -> str | None:
        explicit_selector = _payload_text_any(
            command.payload,
            "overlay_source_selector",
            "overlaySourceSelector",
        )
        if explicit_selector is not None:
            return explicit_selector

        source_ref = _payload_text_any(
            command.payload,
            "overlay_source_ref",
            "overlaySourceRef",
        )
        if source_ref is not None:
            try:
                _context, _locator, description, _frame_path = self._locator_from_ref(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    ref_id=source_ref,
                )
            except BrowserValidationError:
                description = None
            if isinstance(description, str) and description.strip().startswith(("#", ".", "body ", "body>", "input", "button", "select", "textarea", "[")):
                return description.strip()

        overlay_context = runtime_state.active_overlay_context(target_id=tab.target_id)
        if isinstance(overlay_context, dict):
            return _normalize_optional_text(overlay_context.get("source_selector"))
        return None

    def _overlay_source_scope_selectors_for_command(
        self,
        *,
        plan: BrowserExecutionPlan | None,
        tab: BrowserTab,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
    ) -> tuple[str, ...]:
        candidates: list[str] = list(_command_overlay_source_scope_selectors(command))
        for ref_id in _command_overlay_source_refs(command):
            resolved_scope = self._stored_ref_scope_selector(
                plan=plan,
                tab=tab,
                ref_id=ref_id,
            )
            if resolved_scope is not None:
                candidates.append(resolved_scope)
        overlay_context = runtime_state.active_overlay_context(target_id=tab.target_id)
        if isinstance(overlay_context, dict):
            runtime_scope = _normalize_optional_text(
                overlay_context.get("source_scope_selector"),
            )
            if runtime_scope is not None:
                candidates.append(runtime_scope)
        seen: set[str] = set()
        resolved: list[str] = []
        for candidate in candidates:
            normalized = _normalize_optional_text(candidate)
            if normalized is None or normalized in seen:
                continue
            seen.add(normalized)
            resolved.append(normalized)
        return tuple(resolved)

    def _stored_ref_scope_selector(
        self,
        *,
        plan: BrowserExecutionPlan | None,
        tab: BrowserTab,
        ref_id: str,
    ) -> str | None:
        if plan is None:
            return None
        for item in self.ref_store.get_tab_refs(
            profile_name=plan.profile.name,
            target_id=tab.target_id,
        ):
            if item.ref == ref_id:
                return _normalize_optional_text(item.scope_selector)
        return None

    def _remember_overlay_binding(
        self,
        *,
        plan: BrowserExecutionPlan,
        page,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab,
        command: BrowserPageActionCommand,
        payload: Mapping[str, Any],
        resolved_selector: str | None = None,
        overlay_selector: str | None = None,
    ) -> str | None:
        resolved_overlay = overlay_selector
        if resolved_overlay is None:
            resolved_overlay = _payload_text_any(
                payload,
                "overlay_selector",
                "overlaySelector",
            )
        if resolved_overlay is None:
            resolved_overlay = _active_overlay_selector(page)
        if resolved_overlay is None:
            return None
        runtime_state.remember_active_overlay(
            target_id=tab.target_id,
            overlay_selector=resolved_overlay,
            overlay_kind=self._overlay_kind_for_command(
                runtime_state=runtime_state,
                tab=tab,
                command=command,
            ),
            source_ref=next(iter(_command_overlay_source_refs(command)), None),
            source_selector=next(
                iter(
                    _command_overlay_source_selectors(
                        command,
                        resolved_selector=resolved_selector,
                    )
                ),
                None,
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
        return resolved_overlay

    def _overlay_kind_for_command(
        self,
        *,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab,
        command: BrowserPageActionCommand,
    ) -> str | None:
        explicit = _explicit_overlay_kind(command.payload)
        if explicit is not None:
            return explicit
        overlay_context = runtime_state.active_overlay_context(target_id=tab.target_id)
        if isinstance(overlay_context, dict):
            return _normalize_optional_text(overlay_context.get("kind"))
        return None

    def _clear_overlay_binding(
        self,
        *,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab,
    ) -> None:
        runtime_state.clear_active_overlay(target_id=tab.target_id)

    def _scoped_root(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
    ):
        scope_ref = _scope_ref_id(command.payload)
        scope_selector = _scope_selector(command.payload)
        if scope_ref is not None and scope_selector is not None:
            raise BrowserValidationError(
                "payload.scope_ref and payload.scope_selector are mutually exclusive.",
            )
        if scope_ref is not None:
            _context, scope_locator, _description, _frame_path = self._locator_from_ref(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                ref_id=scope_ref,
            )
            return scope_locator
        context = _main_frame(page)
        if scope_selector is not None:
            return context.locator(scope_selector)
        if _active_overlay(command.payload) or _wait_prefers_active_overlay(command):
            overlay_selector = self._resolved_active_overlay_selector(
                page=page,
                runtime_state=runtime_state,
                tab=tab,
                command=command,
            )
            if overlay_selector is not None:
                return context.locator(overlay_selector)
        return context

    def _text_locator(
        self,
        *,
        root,
        text: str,
        exact: bool,
        ordinal: int | None,
        source_selector: str | None = None,
        source_scope_selector: str | None = None,
    ):
        search_root = root
        if not callable(getattr(search_root, "get_by_text", None)):
            locator_factory = getattr(root, "locator", None)
            if callable(locator_factory):
                search_root = locator_factory("body")

        text_factory = getattr(search_root, "get_by_text", None)
        if callable(text_factory):
            locator = text_factory(text, exact=exact)
        else:
            locator_factory = getattr(search_root, "locator", None)
            if not callable(locator_factory):
                raise BrowserValidationError("Browser text wait could not construct a locator.")
            locator = locator_factory("text=" + text)
        resolved_ordinal = ordinal
        if resolved_ordinal is None:
            resolved_ordinal = self._preferred_text_ordinal(
                root=search_root,
                text=text,
                exact=exact,
                source_selector=source_selector,
                source_scope_selector=source_scope_selector,
            )
        if resolved_ordinal is not None:
            nth_method = getattr(locator, "nth", None)
            if not callable(nth_method):
                raise BrowserValidationError("Browser text wait does not support ordinal selection.")
            locator = nth_method(resolved_ordinal)
        return locator

    def _preferred_text_ordinal(
        self,
        *,
        root,
        text: str,
        exact: bool,
        source_selector: str | None,
        source_scope_selector: str | None,
    ) -> int | None:
        normalized_source = _normalize_optional_text(source_selector)
        normalized_source_scope = _normalize_optional_text(source_scope_selector)
        if normalized_source is None and normalized_source_scope is None:
            return None
        evaluate = getattr(root, "evaluate", None)
        if not callable(evaluate):
            return None
        try:
            resolved = evaluate(
                _TEXT_MATCH_ORDINAL_EXPRESSION,
                {
                    "text": text,
                    "exact": exact,
                    "sourceSelector": normalized_source,
                    "sourceScopeSelector": normalized_source_scope,
                },
            )
        except Exception:  # noqa: BLE001
            return None
        try:
            numeric = int(resolved)
        except (TypeError, ValueError):
            return None
        return numeric if numeric >= 0 else None


    def _wait_for_overlay_surface(
        self,
        *,
        plan: BrowserExecutionPlan,
        page,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab,
        command: BrowserPageActionCommand,
        payload: Mapping[str, Any],
        timeout: float | None,
    ) -> dict[str, Any]:
        overlay_selector = _payload_text_any(payload, "overlay_selector", "overlaySelector")
        if overlay_selector is not None:
            page.locator(overlay_selector).wait_for(
                state="visible",
                **_timeout_kwargs(timeout),
            )
            return {
                "waited_for_overlay": True,
                "overlay_selector": overlay_selector,
            }

        overlay_text = _payload_text_any(payload, "overlay_text", "overlayText")
        if overlay_text is not None:
            overlay_locator = self._text_locator(
                root=_main_frame(page),
                text=overlay_text,
                exact=_locator_exact(payload),
                ordinal=_locator_ordinal(payload),
                source_selector=_payload_text_any(
                    payload,
                    "overlay_source_selector",
                    "overlaySourceSelector",
                ),
                source_scope_selector=_payload_text_any(
                    payload,
                    "overlay_source_scope_selector",
                    "overlaySourceScopeSelector",
                )
                or _scope_selector(payload),
            )
            overlay_locator.wait_for(**_timeout_kwargs(timeout))
            resolved_overlay_selector = _active_overlay_selector(page) or self._resolved_active_overlay_selector(
                page=page,
                runtime_state=runtime_state,
                tab=tab,
                command=command,
            )
            return {
                "waited_for_overlay": True,
                "overlay_text": overlay_text,
                "exact": _locator_exact(payload),
                "ordinal": _locator_ordinal(payload),
                "overlay_selector": resolved_overlay_selector,
            }

        if _active_overlay(payload):
            overlay_kind = self._overlay_kind_for_command(
                runtime_state=runtime_state,
                tab=tab,
                command=command,
            )
            source_selector = self._overlay_source_selector_for_command(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                command=command,
            )
            source_scope_selector = next(
                iter(
                    self._overlay_source_scope_selectors_for_command(
                        plan=plan,
                        tab=tab,
                        runtime_state=runtime_state,
                        command=command,
                    )
                ),
                None,
            )
            if source_selector is not None or source_scope_selector is not None:
                page.wait_for_function(
                    _ASSOCIATED_OVERLAY_SELECTOR_EXPRESSION,
                    {
                        "overlayKind": _normalize_optional_text(overlay_kind),
                        "sourceSelector": source_selector,
                        "sourceScopeSelector": source_scope_selector,
                    },
                    **_timeout_kwargs(timeout),
                )
            else:
                page.wait_for_function(
                    _ACTIVE_OVERLAY_SELECTOR_EXPRESSION,
                    **_timeout_kwargs(timeout),
                )
            resolved_overlay_selector = (
                _associated_overlay_selector(
                    page,
                    overlay_kind=overlay_kind,
                    source_selector=source_selector,
                    source_scope_selector=source_scope_selector,
                )
                or _active_overlay_selector(page)
                or self._resolved_active_overlay_selector(
                    page=page,
                    runtime_state=runtime_state,
                    tab=tab,
                    command=command,
                    overlay_kind=overlay_kind,
                    source_scope_selectors=(
                        (source_scope_selector,) if source_scope_selector is not None else ()
                    ),
                )
            )
            return {
                "waited_for_overlay": True,
                "active_overlay": True,
                "overlay_source_bound": bool(source_selector or source_scope_selector),
                "overlay_selector": resolved_overlay_selector,
            }

        return {"waited_for_overlay": False}



    def _overlay_association_reason(
        self,
        *,
        payload: Mapping[str, Any],
        resolved_overlay_selector: str | None,
        source_selector: str | None,
        source_scope_selector: str | None,
    ) -> str | None:
        if _payload_text_any(payload, "overlay_selector", "overlaySelector") is not None:
            return "explicit-overlay-selector"
        if source_scope_selector is not None and resolved_overlay_selector is not None:
            return "source-scope"
        if source_selector is not None and resolved_overlay_selector is not None:
            return "source-selector"
        if _active_overlay(payload) and resolved_overlay_selector is not None:
            return "active-overlay"
        if resolved_overlay_selector is not None:
            return "overlay-detected"
        return None
