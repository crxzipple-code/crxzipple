from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.browser_runtime_facts import (
    page_stale,
    proxy_egress_label,
    proxy_label,
    proxy_readiness_label,
    runtime,
    runtime_proxy_metadata,
    runtime_status,
)
from crxzipple.modules.operations.application.read_models.browser_tones import (
    status_tone,
)
from crxzipple.modules.operations.application.read_models.browser_values import (
    dict_value,
    int_value,
    list_value,
    short_generation,
    text,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)


def profile_rows(
    profiles: tuple[Any, ...],
    *,
    access_service: Any | None,
    proxy_metadata_by_profile: dict[str, dict[str, Any]] | None = None,
) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    proxy_metadata_by_profile = proxy_metadata_by_profile or {}
    for profile in profiles:
        profile_name = text(getattr(profile, "name", None), "unknown")
        proxy_metadata = proxy_metadata_by_profile.get(profile_name, {})
        driver = text(getattr(profile, "driver", None))
        enabled = bool(getattr(profile, "enabled", True))
        runtime_value = runtime(profile)
        status = runtime_status(runtime_value) if enabled else "disabled"
        proxy_metadata = {**runtime_proxy_metadata(runtime_value), **proxy_metadata}
        page_state = dict_value(runtime_value.get("page_state"))
        active_page = dict_value(page_state.get("active_page"))
        endpoint = text(
            getattr(profile, "resolved_cdp_url", None)
            or getattr(profile, "configured_cdp_url", None),
        )
        rows.append(
            OperationsTableRowModel(
                id=f"profile:{text(getattr(profile, 'name', 'unknown'), 'unknown')}",
                status=status,
                tone=status_tone(status, driver=driver),
                cells={
                    "profile": profile_name,
                    "driver": driver,
                    "enabled": "Yes" if enabled else "No",
                    "mode": text(getattr(profile, "mode", None)),
                    "status": status,
                    "endpoint": endpoint,
                    "host_generation": short_generation(
                        runtime_value.get("host_generation"),
                    ),
                    "active_target": text(page_state.get("active_target_id")),
                    "pages": str(int_value(page_state.get("page_count"))),
                    "page_generation": text(active_page.get("page_generation")),
                    "snapshot_generation": text(active_page.get("snapshot_generation")),
                    "proxy": proxy_label(profile),
                    "proxy_readiness": proxy_readiness_label(
                        profile,
                        access_service=access_service,
                    ),
                    "proxy_egress": proxy_egress_label(proxy_metadata),
                },
            ),
        )
    return tuple(rows)


def page_rows(profiles: tuple[Any, ...]) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    for profile in profiles:
        profile_name = text(getattr(profile, "name", None))
        runtime_value = runtime(profile)
        page_state = dict_value(runtime_value.get("page_state"))
        for page in list_value(page_state.get("pages")):
            page_record = dict_value(page)
            target_id = text(page_record.get("target_id"))
            stale = page_stale(page_record)
            rows.append(
                OperationsTableRowModel(
                    id=f"page:{profile_name}:{target_id}",
                    status="stale" if stale else "fresh",
                    tone="warning" if stale else "success",
                    cells={
                        "profile": profile_name,
                        "target_id": target_id,
                        "page_generation": text(page_record.get("page_generation")),
                        "reason": text(page_record.get("page_generation_reason")),
                        "snapshot_generation": text(
                            page_record.get("snapshot_generation"),
                        ),
                        "ref_generation": text(
                            page_record.get("current_ref_generation"),
                        ),
                        "last_action": text(page_record.get("last_action_kind")),
                        "refs": text(page_record.get("last_snapshot_ref_count")),
                        "frames": text(page_record.get("last_snapshot_frame_count")),
                        "stale": "Yes" if stale else "No",
                    },
                ),
            )
    return tuple(rows)
