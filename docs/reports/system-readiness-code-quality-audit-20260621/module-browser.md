# Module Audit: browser

## Verdict

High capability value, medium-high implementation risk. Browser is essential
for real-world agent tasks. The largest application/action-engine/trace
hotspots have now been split, but Browser still carries powerful external
runtime concerns that need ongoing isolation, cleanup, timeout, and retention
discipline.

## Evidence

- 118 Python files, about 33860 lines after the current split.
- `application/services.py` is now a thin 11-line export layer.
- `infrastructure/action_engines.py` is now a 131-line dependency assembly
  surface. Execution lifecycle lives in
  `infrastructure/action_engine_execution.py`; page-level action dispatch lives
  in `infrastructure/action_engine_page_dispatch.py`; batch execution, raw CDP
  execution, action-trace coordination, interaction primitives, locator/ref
  resolution, ref/overlay handling, wait actions, and primitive page actions
  live in focused infrastructure modules.
- `infrastructure/action_engine_interactions.py` is now a 349-line
  interaction primitive mixin after unused toolbar/date/bulk-selection helper
  methods were retired.
- `infrastructure/script_insight.py` is now a focused 668-line action facade
  after runtime expression, payload coercion, and source-analysis split.
- `infrastructure/action_engine_scripts.py` is now a thin 59-line expression
  export surface.
- `infrastructure/action_trace.py` is now a 380-line trace service entrypoint;
  snapshot command construction, storage/lifecycle state diffs, network
  causality, action envelope/recommendation logic, and payload coercion live in
  focused helper modules.
- `infrastructure/network_page_fetch.py` is now a 173-line service entrypoint;
  request normalization, browser-page fetch execution, safety/diff analysis,
  event payload projection, and common result helpers live in focused modules.
- `domain/value_objects.py` is now a 76-line export surface; Browser domain
  type aliases, validation helpers, profile config values, tab/ref values,
  network values, and command/result values live in focused modules.
- `interfaces/http.py` is now a 556-line route surface; Pydantic request
  models, profile/pool helper reads, proxy egress checks, and update-clear
  payload rules live in focused interface helper modules.
- `interfaces/profile_payloads.py` is now a 23-line export surface; profile
  diagnostics, profile/pool/allocation row projection, and aggregate payload
  builders live in focused interface modules.
- `interfaces/cli.py` is now a 36-line Typer composition root; profile, pool,
  allocation, host, and action command registration plus shared CLI helpers live
  in focused modules.
- `application/observation.py` is now a 354-line service entrypoint; payload
  primitives, page/snapshot projection, runtime/network/code projection,
  interaction/form/overlay guidance, and final observation assembly live in
  focused helper modules.
- `infrastructure/engines.py` is now a 413-line control-engine surface after
  tab operation orchestration, tab/runtime-state, CDP wire IO, host/process
  lifecycle helpers, and in-memory test engines were split out.
- Remaining medium-sized Browser infrastructure files are now scoped by
  responsibility: control attach/endpoint resolution, tab operations, host
  lifecycle, page-network fetch, trace, and script/action helpers.

## Findings

- Browser profile/runtime separation is the correct direction.
- Application service boundaries are now much cleaner.
- Action-engine dependency assembly is separated from execution lifecycle,
  page dispatch, batch, CDP, action-trace, interaction primitive, locator/ref
  resolution, primitive page action, ref/overlay, and wait execution details.
- The remaining Browser infrastructure engine surface remains an important
  follow-up review area because it still coordinates live control operations.
- Browser should expose generic capability/tool behavior, not task-specific paths.

## Launch Risks

- Browser runtime failures can block long-chain tasks and produce hard-to-debug states.
- Browser runtime files are smaller, but the module still controls live
  browser processes, CDP sessions, network capture, storage inspection, and
  snapshots; security and sandboxing review remains important.
- Profile/local state stores need explicit production behavior and cleanup.

## Recommendations

- Split action execution into command model, engine adapter, trace recorder, diagnostics, and script/network utilities.
- Keep browser task strategy in skills/tools, not Browser core.
- Add profile allocation/lease/load tests and cleanup tests.
- Define allowed CDP/network/file access boundaries for external integrations.

## Detailed Pass 1

### Files Reviewed

- `application/services.py`
- `application/observation.py`
- `application/network_capture.py`
- `infrastructure/action_engines.py`
- `infrastructure/action_engine_execution.py`
- `infrastructure/action_engine_page_dispatch.py`
- `infrastructure/action_engine_page_actions.py`
- `infrastructure/action_engine_locator_resolution.py`
- `infrastructure/engines.py`
- `infrastructure/script_insight.py`
- `infrastructure/action_trace.py`
- `infrastructure/network_page_fetch.py`
- `infrastructure/cdp_sessions.py`
- `interfaces/http.py`
- `interfaces/cli.py`

### File-Level Assessment

`application/services.py` has been reduced to a thin export layer over focused
modules for profile resolver, capability resolver, command/page action
assemblers, execution planner, tab ops, selection ops, allocation target
recycler/inspector, execution coordinator, profile admin, pool service, and
allocator service.

`infrastructure/action_engines.py` has been reduced to the CDP/Playwright-backed
action-engine dependency assembly surface. Focused modules now own execution
lifecycle, page dispatch, batch execution, `cdp-raw`, action-trace runner
glue, interaction primitives, locator/ref resolution, ref/overlay handling,
primitive page actions, and wait actions.

`infrastructure/script_insight.py`, `action_engine_scripts.py`,
`action_trace.py`, `network_page_fetch.py`, `domain/value_objects.py`,
`interfaces/http.py`, `interfaces/profile_payloads.py`, `interfaces/cli.py`,
and `application/observation.py` have been split into focused entrypoints plus
helper modules. `engines.py` has started the same treatment with tab operation
orchestration, tab state, CDP IO, host/process lifecycle helpers, and in-memory
engine exports extracted. It now holds the remaining attach/endpoint-resolution
coordination instead of mixed tab/host/process/test-engine logic.

### Boundary Cleanliness

Browser should own generic browser capability runtime, profile state, CDP/Playwright adapters, trace, network capture, and profile allocation. It should not own task-specific strategy such as airline page flows.

Current boundary appears mostly aligned, but the action engine is large enough that task-specific special cases could hide there.

### Lifecycle Clarity

Browser lifecycle includes:

- profile definition
- profile pool allocation
- daemon/host browser process availability
- CDP connection/session
- page/action execution
- trace/snapshot capture
- network/storage inspection
- cleanup/release

These concepts are present but spread through large files.

### Persistence And Efficiency

Browser uses local stores/state root and live external process state. That is acceptable for local runtime, but production multi-user use needs explicit isolation and cleanup.

### Concurrency And Multi-User Readiness

Browser is a major concurrency risk:

- profile leases must prevent cross-user state bleed
- CDP sessions must be cleaned up
- long-running actions must have timeouts
- network captures and snapshots can grow large
- daemon/browser process health must be observed

### External Integration Readiness

Browser can become a powerful external capability if exposed through stable tool actions. Raw CDP should stay behind controlled tools/adapters.

### Remediation Checklist

- [x] Split `application/services.py` into profile admin, pool allocation, execution coordination, action planning, tab ops, and selection ops.
- [x] Split `action_engines.py` into execution lifecycle/page dispatch, batch, raw CDP, action-trace runner, interaction primitives, locator/ref resolution, primitive page actions, reference/overlay handling, wait actions, and the remaining action-engine dependency assembly.
- [x] Split Browser trace helpers out of `action_trace.py` into payload, snapshot, state, network, and envelope/recommendation modules.
- [x] Split Browser domain value objects into type, helper, profile, tab/ref, network, and command/result modules.
- [x] Split Browser HTTP interface request models, profile helpers, proxy egress checks, and update payload rules out of the route surface.
- [x] Split Browser profile payload projection into diagnostics, entry, and aggregate payload modules.
- [x] Split Browser CLI into a root composition entrypoint plus profile, pool, allocation, host, action, and helper modules.
- [x] Split Browser observation projection into value, page/snapshot, runtime/code/network, interaction/guidance, and final assembly helpers.
- [x] Split Browser page-network fetch into request normalization, browser-page runtime execution, safety/diff analysis, event payload, and common result helpers.
- [x] Split Browser control-engine tab operations, tab/runtime-state, CDP IO, host/process lifecycle helpers, and in-memory engines out of `engines.py`.
- [x] Add profile lease/isolation guard tests for current Browser allocation cleanup scope.
- [x] Add CDP/action cleanup guard tests for current command-session, `cdp-raw`, network-inspect, and action-trace preview paths.
- [x] Add trace/snapshot retention and size budgets.
- [x] Keep site-specific navigation logic in skills/tool packages, not Browser core.

### Remediation Verification

Additional focused command passed for Browser core genericity:

```bash
PYTHONPATH=src pytest -q tests/unit/test_module_architecture_guards.py::test_browser_core_has_no_site_specific_navigation_logic --tb=short
PYTHONPATH=src pytest -q tests/unit/test_browser_playwright_actions.py::BrowserPlaywrightCoreActionsTestCase::test_action_trace_bounds_snapshot_preview_size tests/unit/test_browser_network_capture.py::BrowserNetworkCaptureTestCase::test_body_size_limit_and_ring_buffer_evict_old_requests tests/unit/test_browser_result_facts.py::test_browser_result_details_compacts_oversized_observation_payload --tb=short
python -m ruff check tests/unit/test_browser_playwright_actions.py tests/unit/test_browser_network_capture.py tests/unit/test_browser_result_facts.py src/crxzipple/modules/browser/infrastructure/action_trace.py src/crxzipple/modules/browser/infrastructure/network_capture.py --ignore F401,I001,E501
python -m ruff check src/crxzipple/modules/browser/infrastructure/action_trace.py src/crxzipple/modules/browser/infrastructure/action_trace_payloads.py src/crxzipple/modules/browser/infrastructure/action_trace_snapshot.py src/crxzipple/modules/browser/infrastructure/action_trace_state.py src/crxzipple/modules/browser/infrastructure/action_trace_network.py src/crxzipple/modules/browser/infrastructure/action_trace_envelope.py
PYTHONPATH=src pytest -q tests/unit/test_browser_playwright_actions.py tests/unit/test_browser_tool_http_advanced.py tests/unit/test_browser_result_facts.py --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_browser_playwright_runtime_actions.py tests/unit/test_browser_tool_http.py tests/unit/test_browser_observation.py --tb=short --maxfail=1
python -m ruff check src/crxzipple/modules/browser/domain/value_objects.py src/crxzipple/modules/browser/domain/value_helpers.py src/crxzipple/modules/browser/domain/value_types.py src/crxzipple/modules/browser/domain/profile_value_objects.py src/crxzipple/modules/browser/domain/tab_value_objects.py src/crxzipple/modules/browser/domain/network_value_objects.py src/crxzipple/modules/browser/domain/command_value_objects.py
PYTHONPATH=src pytest -q tests/unit/test_browser_domain.py tests/unit/test_browser_profile_allocator.py tests/unit/test_browser_network_capture.py --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_browser_tool_http.py tests/unit/test_browser_tool_http_advanced.py tests/unit/test_browser_playwright_actions.py tests/unit/test_browser_playwright_runtime_actions.py --tb=short --maxfail=1
python -m ruff check src/crxzipple/modules/browser/interfaces/http.py src/crxzipple/modules/browser/interfaces/http_request_models.py src/crxzipple/modules/browser/interfaces/http_profile_helpers.py src/crxzipple/modules/browser/interfaces/http_profile_egress.py src/crxzipple/modules/browser/interfaces/http_update_payloads.py
PYTHONPATH=src pytest -q tests/unit/test_browser_interfaces.py tests/unit/test_browser_tool_http.py tests/unit/test_browser_tool_http_advanced.py --tb=short --maxfail=1
python -m ruff check src/crxzipple/modules/browser/interfaces/profile_payloads.py src/crxzipple/modules/browser/interfaces/profile_diagnostics_payloads.py src/crxzipple/modules/browser/interfaces/profile_entry_payloads.py src/crxzipple/modules/browser/interfaces/profile_aggregate_payloads.py
PYTHONPATH=src pytest -q tests/unit/test_browser_profile_allocator.py tests/unit/test_browser_observation.py tests/unit/test_browser_domain.py tests/unit/test_operations_browser_read_model.py --tb=short --maxfail=1
python -m ruff check src/crxzipple/modules/browser/interfaces/cli.py src/crxzipple/modules/browser/interfaces/cli_helpers.py src/crxzipple/modules/browser/interfaces/cli_host_runtime.py src/crxzipple/modules/browser/interfaces/cli_profile_commands.py src/crxzipple/modules/browser/interfaces/cli_pool_commands.py src/crxzipple/modules/browser/interfaces/cli_allocation_commands.py src/crxzipple/modules/browser/interfaces/cli_host_commands.py src/crxzipple/modules/browser/interfaces/cli_action_commands.py
PYTHONPATH=src python - <<'PY'
from crxzipple.modules.browser.interfaces.cli import build_cli
app = build_cli()
assert sorted(cmd.name for cmd in app.registered_commands if cmd.name) == ['act', 'control', 'profiles']
assert sorted(group.name for group in app.registered_groups if group.name) == ['allocation', 'host', 'pool', 'profile']
PY
python -m ruff check src/crxzipple/modules/browser/application/observation.py src/crxzipple/modules/browser/application/observation_values.py src/crxzipple/modules/browser/application/observation_page_payloads.py src/crxzipple/modules/browser/application/observation_runtime_payloads.py src/crxzipple/modules/browser/application/observation_interaction_payloads.py src/crxzipple/modules/browser/application/observation_projection.py
PYTHONPATH=src pytest -q tests/unit/test_browser_observation.py tests/unit/test_browser_tool_application.py tests/unit/test_browser_result_facts.py --tb=short --maxfail=1
python -m ruff check src/crxzipple/modules/browser/infrastructure/network_page_fetch.py src/crxzipple/modules/browser/infrastructure/network_page_fetch_common.py src/crxzipple/modules/browser/infrastructure/network_page_fetch_request.py src/crxzipple/modules/browser/infrastructure/network_page_fetch_runtime.py src/crxzipple/modules/browser/infrastructure/network_page_fetch_analysis.py src/crxzipple/modules/browser/infrastructure/network_page_fetch_events.py
PYTHONPATH=src pytest -q tests/unit/test_browser_tool_http.py tests/unit/test_browser_tool_http_advanced.py tests/unit/test_browser_playwright_actions.py tests/unit/test_browser_playwright_runtime_actions.py tests/unit/test_browser_result_facts.py --tb=short --maxfail=1
python -m ruff check src/crxzipple/modules/browser/infrastructure/engines.py src/crxzipple/modules/browser/infrastructure/engines_control_tabs.py src/crxzipple/modules/browser/infrastructure/engines_tab_state.py src/crxzipple/modules/browser/infrastructure/engines_cdp_io.py src/crxzipple/modules/browser/infrastructure/engines_host_lifecycle.py src/crxzipple/modules/browser/infrastructure/engines_in_memory.py src/crxzipple/modules/browser/infrastructure/profile_probe.py
PYTHONPATH=src pytest -q tests/unit/test_browser_domain.py tests/unit/test_browser_interfaces.py tests/unit/test_browser_profile_allocator.py --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_browser_tool_http.py tests/unit/test_browser_tool_http_advanced.py tests/unit/test_browser_playwright_actions.py tests/unit/test_browser_playwright_runtime_actions.py --tb=short --maxfail=1
```

Result:

- Browser site/task-specific navigation guard: 1 passed
- Browser trace/snapshot/network budget suite: 3 passed
- Targeted ruff over Browser budget paths: passed
- Browser action trace split lint: passed
- Browser action trace regression: 42 passed
- 2026-06-26 Browser primitive page action split:
  `PYTHONPATH=src ruff check src/crxzipple/modules/browser/infrastructure/action_engines.py src/crxzipple/modules/browser/infrastructure/action_engine_page_actions.py tests/unit/test_browser_playwright_actions.py tests/unit/test_browser_playwright_runtime_actions.py tests/unit/test_browser_tool_http.py tests/unit/test_browser_tool_http_advanced.py`
  -> passed.
  `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/browser/infrastructure/action_engines.py src/crxzipple/modules/browser/infrastructure/action_engine_page_actions.py`
  -> passed.
  `PYTHONPATH=src pytest -q tests/unit/test_browser_playwright_actions.py tests/unit/test_browser_playwright_runtime_actions.py tests/unit/test_browser_tool_http.py tests/unit/test_browser_tool_http_advanced.py --tb=short --maxfail=1`
  -> 113 passed.
- 2026-06-26 Browser locator resolution split:
  `PYTHONPATH=src ruff check src/crxzipple/modules/browser/infrastructure/action_engines.py src/crxzipple/modules/browser/infrastructure/action_engine_interactions.py src/crxzipple/modules/browser/infrastructure/action_engine_locator_resolution.py src/crxzipple/modules/browser/infrastructure/action_engine_page_actions.py`
  -> passed.
  `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/browser/infrastructure/action_engines.py src/crxzipple/modules/browser/infrastructure/action_engine_interactions.py src/crxzipple/modules/browser/infrastructure/action_engine_locator_resolution.py src/crxzipple/modules/browser/infrastructure/action_engine_page_actions.py`
  -> passed.
  `PYTHONPATH=src pytest -q tests/unit/test_browser_playwright_actions.py tests/unit/test_browser_playwright_runtime_actions.py tests/unit/test_browser_tool_http.py tests/unit/test_browser_tool_http_advanced.py tests/unit/test_browser_playwright_locator_actions.py --tb=short --maxfail=1`
  -> 137 passed.
- 2026-06-26 Browser interaction primitive cleanup:
  `PYTHONPATH=src ruff check src/crxzipple/modules/browser/infrastructure/action_engine_interactions.py src/crxzipple/modules/browser/infrastructure/action_engines.py src/crxzipple/modules/browser/infrastructure/action_engine_locator_resolution.py src/crxzipple/modules/browser/infrastructure/action_engine_page_actions.py`
  -> passed.
  `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/browser/infrastructure/action_engine_interactions.py src/crxzipple/modules/browser/infrastructure/action_engines.py src/crxzipple/modules/browser/infrastructure/action_engine_locator_resolution.py src/crxzipple/modules/browser/infrastructure/action_engine_page_actions.py`
  -> passed.
  `PYTHONPATH=src pytest -q tests/unit/test_browser_playwright_actions.py tests/unit/test_browser_playwright_runtime_actions.py tests/unit/test_browser_tool_http.py tests/unit/test_browser_tool_http_advanced.py tests/unit/test_browser_playwright_locator_actions.py --tb=short --maxfail=1`
  -> 137 passed.
- 2026-06-26 Browser action execution split:
  `PYTHONPATH=src ruff check src/crxzipple/modules/browser/infrastructure/action_engines.py src/crxzipple/modules/browser/infrastructure/action_engine_execution.py src/crxzipple/modules/browser/infrastructure/action_engine_interactions.py src/crxzipple/modules/browser/infrastructure/action_engine_locator_resolution.py src/crxzipple/modules/browser/infrastructure/action_engine_page_actions.py`
  -> passed.
  `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/browser/infrastructure/action_engines.py src/crxzipple/modules/browser/infrastructure/action_engine_execution.py src/crxzipple/modules/browser/infrastructure/action_engine_interactions.py src/crxzipple/modules/browser/infrastructure/action_engine_locator_resolution.py src/crxzipple/modules/browser/infrastructure/action_engine_page_actions.py`
  -> passed.
  `PYTHONPATH=src pytest -q tests/unit/test_browser_playwright_actions.py tests/unit/test_browser_playwright_runtime_actions.py tests/unit/test_browser_tool_http.py tests/unit/test_browser_tool_http_advanced.py tests/unit/test_browser_playwright_locator_actions.py --tb=short --maxfail=1`
  -> 137 passed.
- 2026-06-26 Browser page dispatch split:
  `PYTHONPATH=src ruff check src/crxzipple/modules/browser/infrastructure/action_engines.py src/crxzipple/modules/browser/infrastructure/action_engine_execution.py src/crxzipple/modules/browser/infrastructure/action_engine_page_dispatch.py src/crxzipple/modules/browser/infrastructure/action_engine_interactions.py src/crxzipple/modules/browser/infrastructure/action_engine_locator_resolution.py src/crxzipple/modules/browser/infrastructure/action_engine_page_actions.py`
  -> passed.
  `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/browser/infrastructure/action_engines.py src/crxzipple/modules/browser/infrastructure/action_engine_execution.py src/crxzipple/modules/browser/infrastructure/action_engine_page_dispatch.py src/crxzipple/modules/browser/infrastructure/action_engine_interactions.py src/crxzipple/modules/browser/infrastructure/action_engine_locator_resolution.py src/crxzipple/modules/browser/infrastructure/action_engine_page_actions.py`
  -> passed.
  `PYTHONPATH=src pytest -q tests/unit/test_browser_playwright_actions.py tests/unit/test_browser_playwright_runtime_actions.py tests/unit/test_browser_tool_http.py tests/unit/test_browser_tool_http_advanced.py tests/unit/test_browser_playwright_locator_actions.py --tb=short --maxfail=1`
  -> 137 passed.
- 2026-06-26 Browser page dispatch readability cleanup:
  `PYTHONPATH=src ruff check src/crxzipple/modules/browser/infrastructure/action_engines.py src/crxzipple/modules/browser/infrastructure/action_engine_execution.py src/crxzipple/modules/browser/infrastructure/action_engine_page_dispatch.py`
  -> passed.
  `PYTHONPATH=src python -m compileall -q src/crxzipple/modules/browser/infrastructure/action_engines.py src/crxzipple/modules/browser/infrastructure/action_engine_execution.py src/crxzipple/modules/browser/infrastructure/action_engine_page_dispatch.py`
  -> passed.
  `PYTHONPATH=src pytest -q tests/unit/test_browser_playwright_actions.py tests/unit/test_browser_playwright_runtime_actions.py tests/unit/test_browser_tool_http.py tests/unit/test_browser_tool_http_advanced.py tests/unit/test_browser_playwright_locator_actions.py --tb=short --maxfail=1`
  -> 137 passed.
- Browser runtime/http/observation regression: 82 passed
- Browser domain value object split lint: passed
- Browser domain/profile/network regression: 53 passed
- Browser domain import/runtime regression: 113 passed
- Browser HTTP interface split lint and compileall: passed
- Browser interface/tool HTTP regression: 68 passed
- `tests/unit/test_browser_http.py` remains socket-bound in this sandbox: current
  environment rejects `ThreadingHTTPServer(("127.0.0.1", 0))` with
  `PermissionError`.
- Browser profile payload split lint and compileall: passed
- Browser profile/observation/domain/Operations Browser regression: 65 passed
- Browser CLI split lint and compileall: passed
- Browser CLI command registration smoke: passed
- `tests/unit/test_browser_cli.py` remains socket-bound in this sandbox for the
  same `FakeCdpServer` reason as `test_browser_http.py`.
- Browser observation split lint and compileall: passed
- Browser observation/tool/result regression: 16 passed
- Browser page-network fetch split lint and compileall: passed
- Browser page-network fetch/runtime regression: 116 passed
- Browser control-engine helper split lint and compileall: passed
- Browser domain/interface/profile allocator regression: 52 passed
- Browser tool/runtime regression after control-engine helper split: 113 passed
- `tests/unit/test_browser_cdp_control.py` and
  `tests/unit/test_browser_cdp_host_daemon.py` remain socket-bound in this
  sandbox for the same `ThreadingHTTPServer(("127.0.0.1", 0))` reason.
