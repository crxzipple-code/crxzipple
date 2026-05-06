## Daemon Module

`modules/daemon` governs independently running background services and
capability daemons.

The module does not own business semantics like orchestration runs, tool runs,
browser actions, or mobile actions. It owns the lifecycle surface around the
processes and endpoints that those business flows depend on.

## Goals

- provide one bounded context for independent service lifecycles
- keep worker daemons and capability daemons under the same vocabulary
- model service definitions separately from concrete running instances
- support future eager, lazy, attach-only, and ensure startup strategies
- keep lease semantics available for later resource/capability coordination

## Core Model

- `DaemonServiceSpec`
  - one logical daemon service definition
  - can optionally belong to a `service_group` such as `core`, `browser`, or `mobile`
- `DaemonInstance`
  - one concrete running or attached daemon instance
- `DaemonLease`
  - one optional ownership lease against an instance

## Examples

- worker daemons
  - `worker:orchestration-scheduler`
  - `worker:orchestration`
  - `worker:operations-observer`
  - `worker:tool-scheduler`
  - `worker:tool`
- capability daemons
  - `capability:chrome-mcp:user`
- host daemons
  - future managed browser hosts or similar long-lived runtimes

## Grouping

Supervisor and listing surfaces can target daemon services by:

- explicit `service_key`
- `role`
- `service_group`
- predefined `service_set`

The initial bootstrap groups are:

- `core`
  - orchestration scheduler/executor/observation and tool scheduler/worker
- `channels`
  - managed channel runtime services
- `browser`
  - managed browser hosts and Chrome MCP
- `ocr`
  - managed local OCR hosts

## Service Sets

Daemon supervisor surfaces also expose a few predefined service sets:

- `workers`
  - all worker-role services
- `orchestration-runtime`
  - orchestration scheduler, executor, and observation runtime
- `channels-stack`
  - channel runtime services
- `browser-stack`
  - browser-group services like managed browser hosts and Chrome MCP
- `ocr-stack`
  - OCR-group services

## First Slice

The initial implementation intentionally focuses on:

- domain model and validation
- file-backed state storage
- container wiring
- bootstrap service specs
- process-backed worker management for orchestration/tool workers
- minimal CLI and HTTP control surface for service listing, healthcheck,
  ensure, reconcile, and stop
- a dedicated daemon supervisor loop for periodic eager-service reconciliation
  and optional explicit service reconciliation

Today the module can actively manage internal process-backed worker daemons,
channel runtimes, and selected capability daemons. Capability daemons now also
include:

- process-backed Chrome MCP capabilities

Endpoint-only capabilities are still supported for attach-only cases.

## Observability

Daemon surfaces now expose two direct observability views:

- `leases`
  - list active/released/expired leases
  - filter by `service_key`, `status`, `owner_kind`, or `owner_id`
- `show <service_key>`
  - one service detail payload with:
    - service spec
    - current instances
    - current and historical leases
    - derived summary
      - instance and lease counts
      - current availability (`available` or `leased`)
      - active lease owners
      - recent errors

These are available from both:

- daemon CLI
- daemon HTTP API
