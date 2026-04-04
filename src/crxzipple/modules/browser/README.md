# Browser Module

`modules/browser` is the clean-slate browser bounded context.

It exists to replace the legacy browser execution model with a
structure that matches the real problem shape instead of layering more runtime
flags on top of historical paths.

## Goals

- separate browser environment identity from runtime attachment details
- separate control/attachment concerns from page action concerns
- unify `local-managed` and `remote-cdp` under one `cdp-backed-playwright`
  action family
- keep `existing-session` as a distinct `mcp-backed` family
- make runtime state explicit instead of hiding it inside profile-shaped
  objects
- use a clean browser state root instead of reusing legacy browser disk layout

## Core Model

The rebuilt module should center on these objects:

- `BrowserSystemConfig`
  - global browser settings
  - examples: `headless`, `executable_path`, `no_sandbox`,
    `default_profile`, `cdp_host`, `cdp_port_range`, `mcp_command`,
    `mcp_timeout_seconds`
- `BrowserProfileConfig`
  - raw configured profile input
- `ResolvedBrowserProfile`
  - normalized browser profile identity
  - examples: `name`, `driver`, `cdp_url`, `cdp_port`, `user_data_dir`,
    `attach_only`, `is_loopback`
- `BrowserProfileCapabilities`
  - derived routing view
  - examples: `mode`, `is_remote`, `uses_chrome_mcp`,
    `uses_persistent_playwright`, `supports_reset`
- `BrowserProfileRuntimeState`
  - mutable runtime state for one profile
  - examples: `attachment_status`, `browser_ref`, `last_target_id`,
    `running_pid`, `last_error`
- `BrowserStateRoot`
  - filesystem layout root for browser runtime data
  - examples: `config/`, `profiles/`, `runtime/`, `refs/`
- `BrowserControlCommand`
  - one normalized browser/tab lifecycle request
- `BrowserPageActionCommand`
  - one normalized page interaction request
- `BrowserExecutionPlan`
  - one request-scoped execution decision

## Main Chain

Static assembly:

```text
BrowserSystemConfig
-> BrowserProfileConfig
-> ResolvedBrowserProfile
-> BrowserProfileCapabilities
```

Per-request execution:

```text
BrowserControlCommand | BrowserPageActionCommand
+ ResolvedBrowserProfile
+ BrowserProfileRuntimeState
-> BrowserExecutionPlan
-> ControlEngine
-> TabResolver
-> ActionEngine
-> BrowserActionResult
```

## Protocol Layer

The protocol layer should be defined around these ports:

- `BrowserSystemConfigStore`
  - loads the global browser system config
- `BrowserProfileResolver`
  - resolves one configured profile into a normalized profile identity
- `BrowserCapabilitiesResolver`
  - derives capability shape from one resolved profile
- `BrowserRuntimeStateStore`
  - persists mutable per-profile runtime state
- `BrowserControlCommandAssembler`
  - converts interface input into one normalized `BrowserControlCommand`
- `BrowserPageActionAssembler`
  - converts interface input into one normalized `BrowserPageActionCommand`
- `BrowserExecutionPlanner`
  - builds one request-scoped `BrowserExecutionPlan`
- `BrowserControlEngine`
  - owns attachment and tab lifecycle behavior for one control family
- `BrowserTabResolver`
  - resolves the effective tab from request target plus runtime state
- `BrowserActionEngine`
  - owns action semantics for one action family
- `BrowserEngineRegistry`
  - resolves control and action engines by family
- `BrowserExecutionCoordinator`
  - orchestrates the end-to-end request flow

These ports should be the primary surface for the rebuilt browser module.
They intentionally model `control` and `action` as separate families.

## Interface Layer

The interface layer stays transport-agnostic and exposes two request DTOs:

- `BrowserControlRequest`
  - browser and tab lifecycle requests
  - examples: `open-tab`, `list-tabs`, `navigate`, `focus-tab`, `close-tab`
- `BrowserPageActionRequest`
  - page interaction requests
  - examples: `click`, `type`, `wait`, `snapshot`, `screenshot`

Those requests flow through one dispatch entry:

- `BrowserInterfaceFacade.execute(request)`

The facade maps request type to command type:

- `BrowserControlRequest -> BrowserControlCommand`
- `BrowserPageActionRequest -> BrowserPageActionCommand`

HTTP, CLI, and tool adapters should only translate external payloads into one
of these request DTOs, then call the same facade entrypoint.

Shared result shaping should live in `BrowserResultSerializer`, so HTTP, CLI,
and tool adapters do not each invent their own result envelope.

In practice the interface layer now has one stable request chain:

```text
BrowserControlRequest | BrowserPageActionRequest
-> BrowserInterfaceFacade.execute(request)
-> BrowserControlCommand | BrowserPageActionCommand
-> BrowserExecutionCoordinator.execute(command)
```

## Separation of Concerns

### Profile

This layer answers:

- which browser environment is this
- which user/session boundary does it represent
- which connection identity belongs to it

This layer does not answer:

- how the browser gets launched
- which action backend executes a click

### Control

This layer answers:

- how to attach to a browser environment
- how to check availability
- how to list/open/focus/close tabs
- how to keep `profile -> browser -> tab` association alive

Control families:

- `cdp-control`
- `mcp-control`

### Action

This layer answers:

- how to execute `click`, `type`, `wait`, `snapshot`, `screenshot`
- how to resolve `ref` or `selector`
- how execution semantics differ by backend family

Action families:

- `cdp-backed-playwright`
- `mcp-backed`

### Runtime State

This layer answers:

- what is currently attached
- what the last selected tab is
- whether a profile is degraded or healthy
- what refs or execution caches exist

## State Root

The rebuilt browser module should use a clean state root under
`browser_state_dir` with a fresh layout:

- `layout.json`
- `config/system.json`
- `profiles/<profile>/profile.json`
- `profiles/<profile>/userdata/`
- `runtime/<profile>.json`
- `refs/`

Stored refs are tab-scoped and frame-aware:

- refs are isolated by `profile + target_id`
- each stored ref keeps a `frame_path`
- actions using `ref` must resolve the correct frame before resolving the element
- `interactive` snapshots use a smaller default ref budget in `mode=efficient`
  than in `mode=focused`
  so the default action-oriented view stays more manageable on large pages
- `interactive` snapshots now prefer accessible role-tree refs
  (`role + name + nth`) and only fall back to DOM selector refs when Playwright
  cannot provide an aria snapshot for the current frame
- `interactive` is now tree-first for model and UI consumption
  while still carrying a parallel `refs` index for follow-up actions; when the
  Playwright path falls back to DOM candidates, the rendered tree groups leaf
  actions by scope selector so page regions remain legible
- `interactive` snapshots also accept `compact`, `depth`, and `mode=efficient`
  style controls; `interactive` now defaults to `mode=efficient`, which means a
  more compact interactive view with default `depth=6`
- Playwright-backed snapshots now also expose dedicated `role` and `aria`
  views; `role` returns a readable role tree and stores refs for follow-up
  actions, while `aria` returns the raw aria snapshot text
- snapshots also accept `refs_mode=role|aria` as an explicit ref-view selector;
  when used without `format`, it resolves to the matching `role` or `aria`
  snapshot view
- snapshots also accept `frame_selector` to scope `interactive`, `role`, or
  `aria` output to a specific iframe/frame subtree while preserving
  absolute `frame_path` values in stored refs
- snapshots also accept a root `selector`; on Playwright-backed profiles,
  `interactive`, `role`, and `aria` can be scoped to a specific
  subtree instead of always starting from the whole page body
- `interactive` is now the single ref-producing snapshot surface on
  Playwright-backed profiles and supports `mode=efficient|focused|wide`

## Live Smoke

There is an opt-in live smoke test for real iframe flows:

- test: `tests/integration/test_browser_live_iframe_smoke.py`
- default target: `https://music.163.com/`
- enable with `APP_BROWSER_LIVE_SMOKE=1`

Optional overrides:

- `APP_BROWSER_LIVE_IFRAME_URL`
- `APP_BROWSER_LIVE_WAIT_MS`

There is also an opt-in live smoke test for the real `existing-session` MCP
flow:

- test: `tests/integration/test_browser_live_mcp_smoke.py`
- launches a temporary local page and drives it through the `user` profile
- enable with `APP_BROWSER_MCP_LIVE_SMOKE=1`

Optional overrides:

- `APP_BROWSER_MCP_LIVE_WAIT_MS`
- `APP_BROWSER_MCP_LIVE_BROWSER`

There is also an opt-in live smoke test for the real `remote-cdp` flow:

- test: `tests/integration/test_browser_live_remote_cdp_smoke.py`
- launches a temporary local browser externally, then attaches through a
  `cdp_url` profile named `remote`
- enable with `APP_BROWSER_REMOTE_CDP_LIVE_SMOKE=1`

Optional overrides:

- `APP_BROWSER_REMOTE_CDP_LIVE_WAIT_MS`
- `APP_BROWSER_REMOTE_CDP_LIVE_BROWSER`
- `APP_BROWSER_REMOTE_CDP_LIVE_HOST`

`browser_state_dir` is the browser module's configuration source of truth.
At runtime:

- `config/system.json` owns global browser settings and `default_profile`
- `profiles/<profile>/profile.json` owns per-profile config
- `runtime/<profile>.json` owns mutable attachment state

`Settings.browser_profiles` only participate in first-time bootstrap when the
browser state root does not exist yet. After that, HTTP, CLI, and tool entry
points load browser config from the state root instead of replaying `Settings`.

Legacy directories like `profile-specs`, `session-tabs`, or reused Chromium
profile trees are not part of the new module shape.

## Family Mapping

The rebuilt design should map profile modes like this:

- `local-managed`
  - control family: `cdp-control`
  - action family: `cdp-backed-playwright`
  - may launch locally
- `remote-cdp`
  - control family: `cdp-control`
  - action family: `cdp-backed-playwright`
  - attach only
- `local-existing-session`
  - control family: `mcp-control`
  - action family: `mcp-backed`

## Existing-Session MCP

The rebuilt module now treats `existing-session` as a real browser family
instead of a stub:

- control goes through `mcp-control`
- page actions go through `mcp-backed`
- the global browser config carries:
  - `mcp_command`
  - `mcp_timeout_seconds`

The default command matches the Chrome DevTools MCP auto-connect flow:

```text
npx -y chrome-devtools-mcp@latest --autoConnect \
  --experimentalStructuredContent --experimental-page-id-routing
```

## Reset

`reset` is now a real control command instead of a placeholder capability:

- `local-managed` profiles support it
- `local-existing-session` and `remote-cdp` profiles reject it

For managed profiles, reset:

- closes any browser process launched by the module
- clears the profile `userdata/` directory
- deletes runtime state
- deletes stored refs

`supports_per_tab_ws` is also a real behavior now:

- `local-managed` tab payloads expose `ws_url`
- `local-existing-session` and `remote-cdp` tab payloads omit it

`supports_json_tab_endpoints` is also a real behavior now:

- `local-managed` tab payloads expose `json_endpoints`
- `local-existing-session` and `remote-cdp` tab payloads omit them

`supports_managed_tab_limit` is also a real behavior now:

- `managed_tab_limit` lives on `BrowserSystemConfig`
- `local-managed` `open-tab` requests enforce it
- `local-existing-session` and `remote-cdp` are not capped by it

Profile-scoped refs for `existing-session` are UID-backed:

- `snapshot format=interactive` stores `ref -> uid`
- later actions such as `click`, `fill`, and `hover` resolve through that UID
- selector targeting is intentionally not the primary path for `mcp-backed`
  - attach only

This means `local-managed` and `remote-cdp` should share the same action
family and differ mainly in control policy.

## Execution State Machines

Two state machines are expected.

### Attachment State

```text
idle
-> attaching
-> attached
-> degraded
-> recovering
-> attached | failed
-> closed
```

This state machine is profile-scoped and owned by
`BrowserProfileRuntimeState`.

### Execution State

```text
received
-> normalized
-> browser_ready
-> tab_resolved
-> engine_selected
-> executing
-> committed
-> succeeded | failed | cancelled
```

This state machine is request-scoped and owned by one
`BrowserExecutionPlan` / execution record.

## What Should Not Return

The rebuilt module should not reintroduce these as the main domain surface:

- `BrowserProfileInputBinding`
- `BrowserRuntimeInput`
- `runtime_mode` as the primary routing abstraction
- `transport` as the primary routing abstraction
- `proxy` and `sandbox` as profile matrix modes

Those are deployment details. They may still exist underneath infrastructure,
but not as the browser domain's public truth.

## Migration Intent

`modules/browser` is the target architecture, not a thin compatibility
wrapper over the removed legacy browser module.

The expectation is:

- design the new domain here first
- move control and action families behind explicit engines
- migrate interfaces only after the new source of truth is real
