from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.settings.application.services import SettingsQueryService
from crxzipple.modules.settings.domain.exceptions import SettingsNotFoundError


def get_existing_resource(query: SettingsQueryService, resource_id: str):
    try:
        return query.get_resource(resource_id)
    except SettingsNotFoundError:
        return None


def effective_payload_matches_seed(
    query: SettingsQueryService,
    resource_id: str,
    payload: Mapping[str, Any],
) -> bool:
    try:
        effective = dict(query.get_effective(resource_id).effective_value)
    except SettingsNotFoundError:
        return False
    expected = dict(payload)
    if "enabled" not in expected:
        effective.pop("enabled", None)
    return effective == expected
