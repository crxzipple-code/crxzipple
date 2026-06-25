"""Marker constants embedded in browser-side JavaScript expressions."""

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

__all__ = (
    "_INTERACTIVE_SNAPSHOT_MARKER",
    "_ACTIVE_OVERLAY_MARKER",
    "_ASSOCIATED_OVERLAY_MARKER",
    "_AUTOCOMPLETE_OVERLAY_STATUS_MARKER",
    "_DATEPICKER_PANEL_STATUS_MARKER",
    "_DATEPICKER_DAY_ORDINAL_MARKER",
    "_TARGET_INFO_MARKER",
    "_BULK_SELECTION_MARKER",
    "_TEXT_MATCH_ORDINAL_MARKER",
    "_TEXT_MATCH_DETAILS_MARKER",
)
