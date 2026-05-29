from __future__ import annotations

from crxzipple.modules.browser.application.events import BROWSER_OPERATION_EVENT_NAMES
from crxzipple.shared import EventDefinition, EventDefinitionField, EventSurface
from crxzipple.shared.domain.events import named_event_topic


def browser_event_definitions() -> tuple[EventDefinition, ...]:
    common_fields = (
        EventDefinitionField("event_name", "Published browser operation event name.", "string", True),
        EventDefinitionField("status", "Operation status such as created, updated, deleted, enabled, or disabled.", "string", True),
        EventDefinitionField("level", "Operational severity level.", "string"),
        EventDefinitionField("summary", "Human-readable event summary.", "string"),
        EventDefinitionField("display_label", "Short display label for Operations.", "string"),
        EventDefinitionField("display_summary", "Display-safe event summary for Operations.", "string"),
        EventDefinitionField("entity_type", "Operational entity type affected by the event.", "string"),
        EventDefinitionField("entity_id", "Operational entity identifier affected by the event.", "string"),
        EventDefinitionField("profile_name", "Browser profile identifier affected by the event.", "string"),
        EventDefinitionField("pool_id", "Browser profile pool identifier affected by the event.", "string"),
        EventDefinitionField("display_name", "Human-readable pool label.", "string"),
        EventDefinitionField("driver", "Browser profile driver.", "string"),
        EventDefinitionField("enabled", "Whether the browser profile is enabled.", "boolean"),
        EventDefinitionField("default_profile", "Current default browser profile.", "string"),
        EventDefinitionField("is_default", "Whether the affected profile is default.", "boolean"),
        EventDefinitionField("attach_only", "Whether the profile can only attach to an existing endpoint.", "boolean"),
        EventDefinitionField("autostart", "Whether managed daemon autostart is enabled.", "boolean"),
        EventDefinitionField("has_cdp_url", "Whether an explicit CDP URL is configured.", "boolean"),
        EventDefinitionField("cdp_port", "Configured or allocated CDP port.", "number"),
        EventDefinitionField("proxy_mode", "Browser proxy mode.", "string"),
        EventDefinitionField("proxy_binding_id", "Access credential binding id for proxy credentials.", "string"),
        EventDefinitionField("proxy_credential_kind", "Expected Access credential kind for authenticated proxy.", "string"),
        EventDefinitionField("proxy_egress_status", "Last proxy egress readiness status recorded for a profile.", "string"),
        EventDefinitionField("proxy_egress_ip", "Last observed proxy egress IP for a profile, when available.", "string"),
        EventDefinitionField("proxy_egress_checked_at", "Last proxy egress check timestamp.", "datetime"),
        EventDefinitionField("profile_names", "Browser profiles in a pool.", "array"),
        EventDefinitionField("target_hosts", "Target hosts associated with a pool.", "array"),
        EventDefinitionField("selection_strategy", "Pool profile selection strategy.", "string"),
        EventDefinitionField("allow_attach_only", "Whether attach-only profiles may be members.", "boolean"),
        EventDefinitionField("close_targets_on_release", "Whether owned targets close when an allocation is released.", "boolean"),
        EventDefinitionField("close_targets_on_expire", "Whether owned targets close when an allocation expires.", "boolean"),
        EventDefinitionField("allocation_id", "Browser profile allocation id.", "string"),
        EventDefinitionField("consumer_kind", "Allocation consumer kind.", "string"),
        EventDefinitionField("consumer_id", "Allocation consumer id.", "string"),
        EventDefinitionField("target_host", "Allocation target host.", "string"),
        EventDefinitionField("acquired_at", "Allocation acquisition timestamp.", "datetime"),
        EventDefinitionField("expires_at", "Allocation expiration timestamp.", "datetime"),
        EventDefinitionField("last_heartbeat_at", "Allocation heartbeat timestamp.", "datetime"),
        EventDefinitionField("released_at", "Allocation release timestamp.", "datetime"),
        EventDefinitionField("release_reason", "Allocation release reason.", "string"),
        EventDefinitionField("changed_fields", "Profile fields changed by an update.", "array"),
        EventDefinitionField("target_id", "Browser page target id affected by the event.", "string"),
        EventDefinitionField("capture_id", "Browser network capture identifier.", "string"),
        EventDefinitionField("request_id", "Browser network request identifier.", "string"),
        EventDefinitionField("url", "Redacted browser network request URL.", "string"),
        EventDefinitionField("method", "HTTP method for a browser network request.", "string"),
        EventDefinitionField("resource_type", "Browser network resource type.", "string"),
        EventDefinitionField("status_code", "HTTP status code when known.", "number"),
        EventDefinitionField("failure_text", "Browser network loading failure reason.", "string"),
        EventDefinitionField("request_count", "Number of requests observed in a capture.", "number"),
        EventDefinitionField("max_requests", "Capture request ring buffer size.", "number"),
        EventDefinitionField("max_body_bytes", "Maximum bytes retained per captured body.", "number"),
        EventDefinitionField("operation_kind", "Browser network operation kind.", "string"),
        EventDefinitionField("source_kind", "Browser network request source kind.", "string"),
        EventDefinitionField("source_request_id", "Captured request id used as replay source.", "string"),
        EventDefinitionField("source_capture_id", "Captured request capture id used as replay source.", "string"),
        EventDefinitionField("page_url", "Redacted page URL that executed the browser-context fetch.", "string"),
        EventDefinitionField("origin", "Origin of the page that executed the fetch.", "string"),
        EventDefinitionField("target_origin", "Origin of the requested URL.", "string"),
        EventDefinitionField("allow_cross_origin", "Whether the operation explicitly allowed cross-origin requests.", "boolean"),
        EventDefinitionField("allow_mutating", "Whether the operation explicitly allowed mutating HTTP methods.", "boolean"),
        EventDefinitionField("redacted", "Whether response body redaction changed the returned content.", "boolean"),
        EventDefinitionField("truncated", "Whether response body storage was truncated.", "boolean"),
        EventDefinitionField("body_size_bytes", "Original response body size in bytes when known.", "number"),
        EventDefinitionField("stored_size_bytes", "Stored response body size in bytes when known.", "number"),
        EventDefinitionField("error_type", "Failure error type.", "string"),
        EventDefinitionField("error_message", "Display-safe failure reason.", "string"),
        EventDefinitionField("environment_action", "Browser environment control action.", "string"),
        EventDefinitionField("environment_scope", "Runtime scope affected by the environment control action.", "string"),
        EventDefinitionField("persistent_profile_affected", "Whether the action may affect durable profile state.", "boolean"),
        EventDefinitionField("changed_controls", "Environment controls changed by the action.", "array"),
        EventDefinitionField("permission_names", "Browser permissions affected by the action.", "array"),
        EventDefinitionField("diagnostic_kind", "Browser diagnostic operation kind.", "string"),
        EventDefinitionField("issue_count", "Number of diagnostic issues found.", "number"),
        EventDefinitionField("console_count", "Number of buffered console messages inspected.", "number"),
        EventDefinitionField("error_count", "Number of console/page JavaScript errors found.", "number"),
        EventDefinitionField("performance_error_count", "Number of performance collection errors.", "number"),
        EventDefinitionField("ready_state", "Document readyState observed by diagnostics.", "string"),
        EventDefinitionField("visibility_state", "Document visibilityState observed by diagnostics.", "string"),
        EventDefinitionField("trace_id", "Browser trace artifact identifier.", "string"),
        EventDefinitionField("trace_size_bytes", "Browser trace artifact size.", "number"),
        EventDefinitionField("content_type", "Browser diagnostic artifact content type.", "string"),
    )
    return tuple(
        EventDefinition(
            definition_id=event_name,
            owner="browser",
            event_name=event_name,
            description="Browser operational fact consumed by Operations.",
            topics=(named_event_topic(event_name),),
            producers=(
                "BrowserProfileAdminService",
                "BrowserNetworkCaptureService",
                "BrowserPageNetworkFetchService",
                "BrowserEnvironmentControlService",
                "BrowserDiagnosticsService",
            ),
            consumers=("OperationsEventObserver", "BrowserOperationsReadModelProvider"),
            fields=common_fields,
            durability="persistent",
            publication_mode="direct",
        )
        for event_name in BROWSER_OPERATION_EVENT_NAMES
    )


def browser_event_surfaces() -> tuple[EventSurface, ...]:
    return (
        EventSurface(
            surface_id="browser.operations",
            owner="browser",
            description="Browser profile governance facts consumed by Operations.",
            definition_ids=BROWSER_OPERATION_EVENT_NAMES,
            topics=tuple(named_event_topic(event_name) for event_name in BROWSER_OPERATION_EVENT_NAMES),
            consumers=("operations.observer", "operations.browser"),
        ),
    )


__all__ = [
    "browser_event_definitions",
    "browser_event_surfaces",
]
