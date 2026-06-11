from __future__ import annotations

import json

from tools.browser.local import (
    _browser_evidence_metadata,
    _browser_result_details,
)


def test_browser_evidence_metadata_records_shapes_without_raw_values() -> None:
    content = {
        "kind": "network-fetch-as-page",
        "url": "https://www.ceair.com/portal/v3/shopping/briefInfo?token=secret",
        "target_id": "tab-east",
        "request_id": "req-east-1",
        "body_ref": "body-ref-east",
        "endpoint": "/portal/v3/shopping/briefInfo",
        "method": "POST",
        "status_code": 200,
        "request_payload": {
            "depCityCode": "KMG",
            "arrCityCode": "BJS",
            "passengers": [{"type": "ADT"}],
        },
        "response": {
            "status": 200,
            "data": {
                "flightItems": [
                    {
                        "flightInfos": [{"flightNo": "MU5815"}],
                        "flightSort": {"price": 700},
                    },
                ],
            },
        },
        "runtime_globals": ["$nuxt", "__NUXT__", "$nuxt"],
        "body": "SECRET_RESPONSE_BODY",
    }

    evidence = _browser_evidence_metadata(
        tool_id="browser.network.fetch_as_page",
        family="page-action",
        kind="network-fetch-as-page",
        profile_name="crxzipple",
        profile_source="pool",
        content=content,
        details=_browser_result_details(content),
        runtime_metadata={
            "browser_host_service_key": "host:browser:crxzipple",
            "browser_allocation_id": "alloc-1",
        },
    )

    assert evidence["tool"] == "browser.network.fetch_as_page"
    assert evidence["url"] == "https://www.ceair.com/portal/v3/shopping/briefInfo"
    assert evidence["origin"] == "https://www.ceair.com"
    assert evidence["endpoint"] == "/portal/v3/shopping/briefInfo"
    assert evidence["target_id"] == "tab-east"
    assert evidence["request_id"] == "req-east-1"
    assert evidence["body_ref"] == "body-ref-east"
    assert evidence["host_service_key"] == "host:browser:crxzipple"
    assert evidence["allocation_id"] == "alloc-1"
    assert evidence["payload_shape"]["depCityCode"] == "str"
    assert evidence["payload_shape"]["passengers"]["type"] == "list"
    assert evidence["result_shape"]["data"]["flightItems"]["type"] == "list"
    assert evidence["runtime_globals"] == ["$nuxt", "__NUXT__"]
    assert "SECRET_RESPONSE_BODY" not in str(evidence)
    assert "token=secret" not in str(evidence)


def test_browser_evidence_metadata_records_action_replay_and_script_indices() -> None:
    content = {
        "kind": "action-trace",
        "target_id": "tab-east",
        "action": {
            "kind": "click",
            "ok": True,
            "resolved_selector": "#submit",
            "field_label": "Search",
        },
        "network": {
            "causality": {
                "script_frames": [
                    {
                        "request_id": "req-flight",
                        "function_name": "searchFlights",
                        "script_url": "https://www.ceair.com/app.js?token=secret",
                        "line_number": 42,
                        "column_number": 7,
                        "url": "https://www.ceair.com/portal/v3/shopping/briefInfo?token=secret",
                    },
                ],
                "api_candidates": [
                    {
                        "request_id": "req-flight",
                        "method": "POST",
                        "status": 200,
                        "resource_type": "xhr",
                        "url": "https://www.ceair.com/portal/v3/shopping/briefInfo?token=secret",
                        "initiator": {
                            "type": "script",
                            "script_url": "https://www.ceair.com/app.js?token=secret",
                        },
                    },
                ],
            },
        },
        "result": {
            "kind": "network-replay-request",
            "source_request_id": "req-flight",
            "source_capture_id": "cap-flight",
            "request_diff": {
                "changed_fields": ["url", "body_unknown", "secret_field"],
                "body_source": "override-json",
                "source": {"body": {"state": "redacted"}},
            },
            "response_summary": {
                "ok": True,
                "status": 201,
                "mime_type": "application/json",
                "size_bytes": 128,
                "truncated": False,
                "redacted": False,
            },
            "body": "SECRET_REPLAY_BODY",
        },
    }

    evidence = _browser_evidence_metadata(
        tool_id="browser.action_trace",
        family="page-action",
        kind="action-trace",
        profile_name="crxzipple",
        profile_source="pool",
        content=content,
        details=_browser_result_details(content),
        runtime_metadata={},
    )

    assert evidence["action_kind"] == "click"
    assert evidence["action_ok"] is True
    assert evidence["verified_selector"] == "#submit"
    assert evidence["field_label"] == "Search"
    assert evidence["source_request_id"] == "req-flight"
    assert evidence["source_capture_id"] == "cap-flight"
    assert evidence["request_diff_changed_fields"] == [
        "url",
        "body_unknown",
        "secret_field",
    ]
    assert evidence["request_diff_body_source"] == "override-json"
    assert evidence["source_body_state"] == "redacted"
    assert evidence["response_summary"] == {
        "ok": True,
        "status": 201,
        "mime_type": "application/json",
        "size_bytes": 128,
        "truncated": False,
        "redacted": False,
    }
    assert evidence["script_frames"] == [
        {
            "request_id": "req-flight",
            "function_name": "searchFlights",
            "line_number": 42,
            "column_number": 7,
            "script_url": "https://www.ceair.com/app.js",
            "url": "https://www.ceair.com/portal/v3/shopping/briefInfo",
        },
    ]
    assert evidence["api_candidates"] == [
        {
            "request_id": "req-flight",
            "method": "POST",
            "status": 200,
            "resource_type": "xhr",
            "url": "https://www.ceair.com/portal/v3/shopping/briefInfo",
            "initiator_type": "script",
            "initiator_script_url": "https://www.ceair.com/app.js",
        },
    ]
    assert "token=secret" not in str(evidence)
    assert "SECRET_REPLAY_BODY" not in str(evidence)


def test_browser_result_details_compacts_oversized_observation_payload() -> None:
    content = {
        "command": {"kind": "snapshot"},
        "kind": "snapshot",
        "target_id": "tab-large",
        "url": "https://example.com/app?token=secret",
        "value": {
            "result": {
                "format": "interactive",
                "text": "\n".join(f"line {index} " + ("x" * 400) for index in range(500)),
                "refs": [
                    {
                        "ref": f"r{index}",
                        "name": "large option " + ("y" * 300),
                        "selector": f"#option-{index}",
                    }
                    for index in range(500)
                ],
            },
        },
    }

    details = _browser_result_details(content)
    serialized = json.dumps(
        details,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    assert len(serialized) < 131072
    assert details["details_compacted"] is True
    assert details["target_id"] == "tab-large"
    assert details["value"]["result"]["refs"][-1]["items_omitted_from_details"] == 460
