from __future__ import annotations

from dataclasses import dataclass, field, replace

from crxzipple.modules.session.domain.value_objects import SessionItem


@dataclass(frozen=True, slots=True)
class MergeSessionMetadataInput:
    session_key: str
    metadata: dict[str, object] = field(default_factory=dict)
    touch_activity: bool = True


@dataclass(frozen=True, slots=True)
class MergeSessionItemMetadataInput:
    item_id: str
    metadata: dict[str, object] = field(default_factory=dict)
    touch_activity: bool = False


def merge_metadata_payload(
    current: dict[str, object],
    patch: dict[str, object],
) -> dict[str, object]:
    metadata = dict(current)
    metadata.update(patch)
    return metadata


def merge_session_item_metadata(
    item: SessionItem,
    patch: dict[str, object],
) -> SessionItem:
    return replace(item, metadata=merge_metadata_payload(item.metadata, patch))
