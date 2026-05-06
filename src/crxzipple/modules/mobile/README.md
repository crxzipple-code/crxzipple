# Mobile Module

`modules/mobile` is the mobile-device bounded context.

The current implementation targets `Android + adb-backed automation`, with the
module boundary intentionally broader than one concrete backend so future iOS
or vision-assisted paths can reuse the same core model.

## Goals

- separate device identity from one concrete automation backend
- separate device lifecycle from in-app interaction
- keep screenshot and snapshot output aligned with the shared artifact and
  tool result contracts
- expose one transport-agnostic facade for HTTP, CLI, and tool adapters

## Core Model

- `MobileSystemConfig`
  - global mobile settings and configured devices
- `MobileDeviceConfig`
  - one configured mobile target
- `ResolvedMobileDevice`
  - normalized device identity + backend binding
- `MobileDeviceRuntimeState`
  - mutable per-device runtime state
- `MobileControlCommand`
  - one device lifecycle request
- `MobileActionCommand`
  - one device interaction request
- `MobileExecutionPlan`
  - one resolved execution plan
- `MobileStoredRef`
  - one stored mobile UI ref from a snapshot

## Main Chain

```text
MobileControlRequest | MobileActionRequest
-> MobileInterfaceFacade.execute(request)
-> MobileControlCommand | MobileActionCommand
-> MobileExecutionCoordinator.execute(command)
-> adb-backed engines
-> MobileActionResult
```

## Current Scope

The initial slice focuses on:

- device discovery through `adb devices -l`
- app launch/activate/terminate control
- `snapshot`
- `screenshot`
- basic `tap`, `type`, `press`, and `wait`

`list-devices` is a device probe, not just a raw list dump. It reports:

- whether `adb` is available
- whether the probe itself succeeded
- whether any Android device is currently connected and online
- the parsed `adb devices -l` rows when available

Connected Android devices are the truth source for device presence. The
persisted mobile config is used as a stable mapping layer:

- discovered device serials can be persisted as immutable device mappings
- a configured mapping can add server/app defaults on top of that serial
- when exactly one Android device is connected, mobile execution can resolve
  it even before a friendly alias is configured

Snapshot output is tree-first and also derives:

- a text excerpt
- a parallel `refs` index for follow-up actions scoped to the latest snapshot generation

The default `snapshot` format is `interactive_text`, which combines the
tree-shaped interactive view with the text excerpt in one result. Explicit
`interactive`, `tree`, or `text` formats are still supported when a caller
needs a narrower view.

## Contract Notes

- screenshots should be externalized into artifacts whenever the artifact
  service is available
- model/user-facing content belongs in the higher tool layer, not in device
  `details`
- selectors are adb-backed UI tree expressions:
  - `xpath=...`
  - `text=...`
  - `id=...`
  - raw strings starting with `//` are treated as XPath
