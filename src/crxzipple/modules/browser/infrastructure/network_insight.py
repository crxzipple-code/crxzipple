from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from crxzipple.modules.browser.domain import BrowserValidationError

from .cdp_sessions import BrowserCdpSessionBroker

CDP_RESOURCE_SAMPLE_LIMIT = 25
CDP_FRAME_SAMPLE_LIMIT = 8
CDP_TEXT_LIMIT = 512
NETWORK_PERFORMANCE_MARKER = "__crxzipple_network_performance_entries__"
NETWORK_PERFORMANCE_EXPRESSION = """
/*__crxzipple_network_performance_entries__*/
(raw) => {
  const input = raw && typeof raw === "object" ? raw : {};
  const limit = Math.max(1, Number(input.limit || 50));
  const includeNavigation = input.include_navigation !== false && input.includeNavigation !== false;
  const includeResources = input.include_resources !== false && input.includeResources !== false;
  const entries = [];
  const toNumber = (value) => {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : null;
  };
  const pushEntry = (entry) => {
    if (!entry || entries.length >= limit) return;
    entries.push({
      name: String(entry.name || ""),
      entry_type: String(entry.entryType || ""),
      initiator_type: entry.initiatorType == null ? null : String(entry.initiatorType),
      start_time: toNumber(entry.startTime),
      duration: toNumber(entry.duration),
      transfer_size: toNumber(entry.transferSize),
      encoded_body_size: toNumber(entry.encodedBodySize),
      decoded_body_size: toNumber(entry.decodedBodySize),
      next_hop_protocol: entry.nextHopProtocol == null ? null : String(entry.nextHopProtocol),
      response_status: toNumber(entry.responseStatus),
    });
  };
  if (includeNavigation && performance.getEntriesByType) {
    for (const entry of performance.getEntriesByType("navigation")) pushEntry(entry);
  }
  if (includeResources && performance.getEntriesByType) {
    for (const entry of performance.getEntriesByType("resource")) pushEntry(entry);
  }
  return {
    url: String(window.location.href || ""),
    entries,
    entry_count: entries.length,
    limit,
  };
}
""".strip()


@dataclass(slots=True)
class BrowserNetworkInsightService:
    cdp_session_broker: BrowserCdpSessionBroker = field(
        default_factory=BrowserCdpSessionBroker,
        repr=False,
    )

    def execute(
        self,
        *,
        page: Any,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        limit = _payload_int_any(payload, "limit", minimum=1) or 50
        include_navigation = _payload_bool_any(
            payload,
            "include_navigation",
            "includeNavigation",
        )
        include_resources = _payload_bool_any(
            payload,
            "include_resources",
            "includeResources",
        )
        include_cdp_tree = _payload_bool_any(
            payload,
            "include_cdp_tree",
            "includeCdpTree",
        )
        include_performance_metrics = _payload_bool_any(
            payload,
            "include_performance_metrics",
            "includePerformanceMetrics",
        )
        if include_navigation is None:
            include_navigation = True
        if include_resources is None:
            include_resources = True
        if include_cdp_tree is None:
            include_cdp_tree = True
        if include_performance_metrics is None:
            include_performance_metrics = True

        errors: list[dict[str, str]] = []
        performance_entries: dict[str, Any] = {}
        try:
            raw_performance_entries = page.evaluate(
                NETWORK_PERFORMANCE_EXPRESSION,
                {
                    "limit": limit,
                    "include_navigation": include_navigation,
                    "include_resources": include_resources,
                },
            )
            if isinstance(raw_performance_entries, dict):
                performance_entries = dict(raw_performance_entries)
        except Exception as exc:  # pragma: no cover - exercised by live browser variance
            errors.append(
                {
                    "source": "performance_entries",
                    "message": str(exc),
                }
            )

        cdp_payload: dict[str, Any] = {}
        if include_cdp_tree or include_performance_metrics:
            session = None
            try:
                session = self.cdp_session_broker.open_command_session(page)
                if include_performance_metrics:
                    try:
                        self.cdp_session_broker.send_command(
                            session,
                            "Performance.enable",
                            {},
                        )
                        cdp_payload["metrics"] = _json_safe_payload(
                            self.cdp_session_broker.send_command(
                                session,
                                "Performance.getMetrics",
                                {},
                            )
                        )
                    except Exception as exc:  # pragma: no cover - CDP support varies by target
                        errors.append(
                            {
                                "source": "Performance.getMetrics",
                                "message": str(exc),
                            }
                        )
                if include_cdp_tree:
                    try:
                        cdp_payload["resource_tree"] = _summarize_resource_tree(
                            self.cdp_session_broker.send_command(
                                session,
                                "Page.getResourceTree",
                                {},
                            ),
                            sample_limit=min(limit, CDP_RESOURCE_SAMPLE_LIMIT),
                        )
                    except Exception as exc:  # pragma: no cover - CDP support varies by target
                        errors.append(
                            {
                                "source": "Page.getResourceTree",
                                "message": str(exc),
                            }
                        )
            except Exception as exc:  # pragma: no cover - CDP support varies by target
                errors.append(
                    {
                        "source": "cdp_session",
                        "message": str(exc),
                    }
                )
            finally:
                if session is not None:
                    self.cdp_session_broker.detach(session)

        return {
            "kind": "network-inspect",
            "url": _payload_text_any(performance_entries, "url") or getattr(page, "url", None),
            "limit": limit,
            "performance": _json_safe_payload(performance_entries),
            "cdp": cdp_payload,
            "errors": errors,
        }


def _payload_text_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _payload_bool_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> bool | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            return value
    return None


def _payload_value_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def _payload_int_any(
    payload: Mapping[str, Any],
    *keys: str,
    minimum: int = 0,
) -> int | None:
    value = _payload_value_any(payload, *keys)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BrowserValidationError(f"payload.{keys[0]} must be an integer.")
    resolved = int(value)
    if resolved < minimum:
        raise BrowserValidationError(
            f"payload.{keys[0]} must be greater than or equal to {minimum}.",
        )
    return resolved


def _json_safe_payload(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_payload(item) for item in value]
    return str(value)


def _summarize_resource_tree(
    value: Any,
    *,
    sample_limit: int,
) -> dict[str, Any]:
    if sample_limit < 1:
        sample_limit = 1
    frame_tree = value.get("frameTree") if isinstance(value, Mapping) else None
    if not isinstance(frame_tree, Mapping):
        return {
            "frame_count": 0,
            "resource_count": 0,
            "types": {},
            "frames": [],
            "resources": [],
            "sample_limit": sample_limit,
            "raw_omitted": True,
        }

    frames: list[Mapping[str, Any]] = []
    resources: list[Mapping[str, Any]] = []
    _collect_resource_tree(frame_tree, frames=frames, resources=resources)

    types: dict[str, int] = {}
    for resource in resources:
        resource_type = _compact_text(resource.get("type")) or "unknown"
        types[resource_type] = types.get(resource_type, 0) + 1

    frame_samples = [_frame_sample(frame) for frame in frames[:CDP_FRAME_SAMPLE_LIMIT]]
    resource_samples = [_resource_sample(resource) for resource in resources[:sample_limit]]

    return {
        "frame_count": len(frames),
        "resource_count": len(resources),
        "types": dict(sorted(types.items())),
        "frames": frame_samples,
        "resources": resource_samples,
        "sample_limit": sample_limit,
        "frame_sample_limit": CDP_FRAME_SAMPLE_LIMIT,
        "truncated": len(frames) > len(frame_samples) or len(resources) > len(resource_samples),
        "raw_omitted": True,
    }


def _collect_resource_tree(
    node: Mapping[str, Any],
    *,
    frames: list[Mapping[str, Any]],
    resources: list[Mapping[str, Any]],
) -> None:
    frame = node.get("frame")
    if isinstance(frame, Mapping):
        frames.append(frame)
    raw_resources = node.get("resources")
    if isinstance(raw_resources, (list, tuple)):
        resources.extend(item for item in raw_resources if isinstance(item, Mapping))
    child_frames = node.get("childFrames")
    if isinstance(child_frames, (list, tuple)):
        for child in child_frames:
            if isinstance(child, Mapping):
                _collect_resource_tree(child, frames=frames, resources=resources)


def _frame_sample(frame: Mapping[str, Any]) -> dict[str, Any]:
    sample: dict[str, Any] = {}
    for key in ("id", "url", "name", "securityOrigin", "mimeType"):
        value = _compact_text(frame.get(key))
        if value is not None:
            sample[key] = value
    return sample


def _resource_sample(resource: Mapping[str, Any]) -> dict[str, Any]:
    sample: dict[str, Any] = {}
    for key in ("url", "type", "mimeType"):
        value = _compact_text(resource.get(key))
        if value is not None:
            sample[key] = value
    for key in ("lastModified", "contentSize", "failed", "canceled"):
        value = resource.get(key)
        if isinstance(value, (str, int, float, bool)):
            sample[key] = value
    return sample


def _compact_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("data:"):
        header, separator, payload = text.partition(",")
        if separator:
            return f"{header},[omitted {len(payload)} chars]"
    if len(text) > CDP_TEXT_LIMIT:
        return f"{text[: CDP_TEXT_LIMIT - 3].rstrip()}..."
    return text
