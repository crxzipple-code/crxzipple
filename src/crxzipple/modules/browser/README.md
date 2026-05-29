# Browser Module

`modules/browser` owns browser profile identity, CDP attachment, tab lifecycle,
and page action execution. It does not own Tool source discovery or tool run
lifecycle. The default browser tool path is the single Tool Source
`configured.browser`; profile is runtime context, not a separate source.

## Current Shape

- Browser profiles are `managed`, `existing-session`, or remote CDP-shaped
  profiles.
- Browser profile config does not use `runtime_mode` or `transport`.
  Use `driver`, `cdp_url`, `attach_only`, `autostart`, and proxy fields for
  profile identity/runtime intent. Browser executable and headless mode are
  system-level settings.
- All Browser module execution uses:
  - control family: `cdp-control`
  - action family: `cdp-backed-playwright`
- `existing-session` is attach-only CDP. It requires an already reachable
  remote-debugging endpoint and the Browser module will not launch it.
- Managed profiles can be started through daemon-managed browser hosts.
- `browser host run` uses `BrowserHostProcessRunner` to launch and hold the
  browser process; `CdpControlEngine` only attaches to an already ready CDP
  endpoint and never starts or kills browser processes.
- Browser MCP is not part of the default browser runtime path. Any future
  experimental MCP source must stay separate from `configured.browser`.

## Core Model

- `BrowserSystemConfig`
  - global browser settings: default profile, headless, executable path,
    CDP host/range, managed tab limit.
- `BrowserProfileConfig`
  - raw configured profile input.
- `ResolvedBrowserProfile`
  - normalized profile identity and CDP endpoint.
- `BrowserProfileCapabilities`
  - derived runtime capability view.
- `BrowserProfileRuntimeState`
  - mutable attachment and tab state for one profile.
- `BrowserControlCommand`
  - browser/tab lifecycle commands.
- `BrowserPageActionCommand`
  - page interaction commands.
- `BrowserExecutionPlan`
  - request-scoped execution decision.

## Execution Chain

```text
BrowserControlRequest | BrowserPageActionRequest
-> BrowserInterfaceFacade.execute(request)
-> BrowserControlCommand | BrowserPageActionCommand
-> BrowserExecutionCoordinator.execute(command)
-> cdp-control
-> cdp-backed-playwright
-> BrowserActionResult
```

HTTP, CLI, and local tool adapters translate payloads into Browser interface
DTOs, then call the same facade. Shared result shaping lives in
`BrowserResultSerializer`.

## Daemon Relationship

Daemon owns long-running processes and endpoint readiness:

- `host:browser:{profile}`
  - launches and supervises a managed browser host process.
  - writes CDP endpoint, process id, profile, user data dir, and proxy metadata
    to daemon instance state.

Browser uses daemon-managed CDP endpoints. Tool invokes browser capabilities
through the Browser application port and records the resolved profile in the
ToolRun metadata. This keeps browser profile/runtime ownership in Browser and
tool catalog/run ownership in Tool without per-profile MCP duplication.

## CDP Sessions

All page-scoped CDP access goes through `BrowserCdpSessionBroker`.

- Short commands use command leases and are detached after the action.
- Network capture uses subscription leases so CDP event listeners can stay
  attached until capture stop/clear/profile cleanup.
- CDP target/browser connection failures are converted to short,
  display-safe `BrowserValidationError` messages with a recoverable next
  action.
- `cdp-raw` is not part of the normal `configured.browser` function catalog;
  ordinary agents and public Browser HTTP/CLI actions receive stable browser
  functions instead of arbitrary CDP.
