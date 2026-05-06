# Channels And Events Upgrade Blueprint

## Goal

Establish a clean, event-driven multi-channel runtime architecture that:

- keeps `session` as the conversation continuity core
- keeps `orchestration` as the business execution core
- keeps `dispatch` as the scheduling core
- upgrades `events` into a real cross-process event subsystem
- introduces `channels` as the transport-facing communication runtime
- separates directed delivery from broadcast while letting both use one event infrastructure

This blueprint intentionally favors the target architecture over compatibility shims.

Current implementation reference:

- [current-ui-design-functional-spec.md](ui/current-ui-design-functional-spec.md)
- [web-channel-guide.md](web-channel-guide.md)
- [webhook-channel-guide.md](webhook-channel-guide.md)
- [inbox-channel-guide.md](inbox-channel-guide.md)
- [lark-channel-guide.md](lark-channel-guide.md)

## Upgrade Stance

This is a new system.

We do not preserve accidental coupling if that coupling weakens the model.

We prefer:

- explicit subsystem boundaries
- one event foundation with clear event semantics
- `session_key` as the stable conversation anchor
- transport/runtime state outside `session`
- daemon-managed long-lived runtimes
- `dispatch` for scheduling, not for observability

## Core Principles

### Session Owns Continuity

`session` continues to own:

- stable conversation buckets
- active instance identity
- transcript persistence
- fresh reset semantics
- instance-local compaction

`session` does not own:

- channel connections
- delivery paths
- external protocol state
- routing across transport runtimes

### Orchestration Owns Execution

`orchestration` continues to own:

- inbound route decision
- session resolution and synchronization
- run lifecycle
- llm and tool coordination
- subagent execution

`orchestration` does not own:

- live channel connections
- protocol-specific formatting
- connection affinity
- subscriber fanout

### Dispatch Owns Scheduling

`dispatch` remains the durable scheduling subsystem.

It continues to own:

- priority
- lane serialization
- claim and heartbeat
- requeue and recovery
- queue policy

It does not own:

- transcript history
- channel runtime state
- broadcast fanout
- user-facing observation streams

### Events Own Communication Semantics

The upgraded `events` module becomes the formal cross-process event subsystem.

It is no longer defined by the current in-process event bus implementation.

`events` provides one shared event foundation for:

- internal facts
- scheduling wakeups
- directed delivery requests
- scoped broadcast notifications

The infrastructure is unified.

The semantics are still distinct.

### Channels Own Transport Runtime

The `channels` subsystem owns:

- external channel adapters
- long-lived runtime instances
- account and connection state
- inbound normalization
- outbound sending
- cursor, receipt, retry, dedupe, and presence

`channels` does not own:

- agent reasoning
- prompt assembly
- session continuity rules

## Final Top-Level Architecture

```text
External Channels
  -> Channel Adapters
  -> Channel Runtime
  -> Orchestration Ingress
  -> Session
  -> Dispatch
  -> Orchestration Worker
  -> DB
  -> Events
     -> Delivery
        -> Channel Runtime
     -> Broadcast
        -> Matching Channel Runtimes / Subscribers
```

There is only one cross-process event subsystem: `events`.

Directed delivery and broadcast are two event modes, not two different buses.

## Subsystem Overview

### Session

Existing subsystem.

Keeps:

- `session_key`
- `active_session_id`
- transcript messages
- archived instances

This blueprint assumes the semantics defined in [session-semantics-design.md](session-semantics-design.md).

### Orchestration

Existing subsystem.

The orchestration intake path becomes the shared inbound business entry for:

- HTTP turns
- web channel runtime
- future IM/webhook/poll runtimes

The system should not introduce a parallel ingress center outside orchestration.

### Dispatch

Existing subsystem.

This blueprint assumes the boundary defined in [dispatch-design.md](dispatch-design.md).

Dispatch remains the authoritative scheduler for:

- `orchestration.run`
- `tool.run`
- future `delivery.send` work items when durable scheduling is needed

### Events

New formal cross-process subsystem.

Owns:

- event envelope model
- publish and subscribe contracts
- consumer cursor semantics
- targeted and scoped fanout semantics
- event transport implementation

`events` should support multi-process communication as a first-class behavior, not as a compatibility extension.

### Channels

New subsystem.

Owns:

- channel profiles
- channel runtime instances
- adapter lifecycle
- conversation binding
- connection binding
- delivery tracking
- runtime registration and route discovery

### Delivery

New narrow subsystem or application layer.

Owns:

- directed outbound route resolution
- runtime target lookup
- transport path selection
- send request shaping

It does not maintain connections itself.

### Broadcast

New narrow subsystem or application layer.

Owns:

- scoped notification matching
- fanout policy
- audience targeting by scope

Broadcast is not normal user reply delivery.

## Web Channel Cutover

`web` is now treated as a first-class channel.

For browser clients, the intended realtime path is:

```text
GET /channels/web/events
```

This stream is the primary channel-facing event surface for:

- `observe`
- `delivery`
- `broadcast`

The browser now uses a single primary stream:

- `/channels/web/events`
  - `X-Crx-Stream-Role: primary`
  - `X-Crx-Stream-Scope: channel`

## Events Model

### Event Envelope

Recommended canonical model:

```text
EventEnvelope
- id
- kind
- topic
- ordering_key
- dedupe_key
- target
- trace
- payload
- created_at
```

### Event Kinds

Use four semantic kinds:

- `command`
- `fact`
- `delivery`
- `broadcast`

#### Command

Represents work that should be scheduled or executed.

Examples:

- `orchestration.run.requested`
- `tool.run.requested`
- `dispatch.wakeup`

#### Fact

Represents something that has already happened.

Examples:

- `run.started`
- `run.completed`
- `tool.completed`
- `session.message.appended`

Facts are not automatically user-visible messages.

#### Delivery

Represents directed delivery to a concrete channel target.

Examples:

- deliver one assistant reply to one web account and one SSE connection
- deliver one assistant reply to one telegram account and one thread

Web SSE and WS belong here.

They are not broadcast.

#### Broadcast

Represents scoped notifications to a wider audience.

Examples:

- queue depth updates
- estimated wait notices
- maintenance announcements
- tenant-wide alerts

Broadcast is intentionally separate from normal conversation delivery.

### Event Targets

Directed delivery targets should support at least:

- `channel_type`
- `channel_account_id`
- `conversation_id`
- `connection_id`
- `route_hint`

Broadcast targets should support scopes such as:

- `global`
- `tenant`
- `channel`
- `account`

## Channels Subsystem

### Goal

Provide a transport-facing, protocol-adaptive, stateful communication runtime.

The channels subsystem converts heterogeneous external channel traffic into canonical inbound messages, and routes canonical outbound messages back through the correct runtime and adapter.

### Channel Adapter

Each channel adapter is a protocol plugin.

Examples:

- `WebChannelAdapter`
- `TelegramChannelAdapter`
- `DiscordChannelAdapter`
- `WebhookChannelAdapter`
- `PollingInboxAdapter`

Adapters own:

- authentication and signature validation
- raw payload parsing
- channel-specific request and response formats
- low-level send operations
- channel-specific retry and rate limit behavior

Adapters do not own:

- session continuity
- agent logic
- conversation routing policy

### Channel Runtime

Each channel runtime is a long-lived runtime container for one channel family.

It owns:

- adapter lifecycle
- account lifecycle
- connection management
- polling loops
- inbound normalization
- outbound execution
- retries and receipts
- connection presence

The recommended V1 topology is:

- one runtime process per channel type

Not:

- one process per account
- one process per connection

Each channel runtime may maintain:

- multiple accounts
- multiple websocket connections
- multiple SSE subscribers
- multiple poll cursors

### Channel Profile Layer

The channels subsystem should have a formal profile/config layer.

Use a configuration model similar in spirit to browser/mobile system config.

Recommended objects:

- `ChannelSystemConfig`
- `ChannelProfile`
- `ChannelAccountProfile`

Profile data should cover:

- `channel_type`
- account configuration
- auth and secret references
- transport mode
- capabilities
- shard policy
- retry policy
- routing policy
- rate limit policy

This configuration must not be hardcoded inside adapters or scattered inside daemon metadata.

### Channel Runtime Manager

Introduce a dedicated `ChannelRuntimeManager`.

It is not the daemon.

It is not an adapter.

It is the runtime registry and route discovery layer.

It owns:

- runtime registration
- runtime heartbeat view
- account-to-runtime assignment
- connection-to-runtime assignment
- runtime capability lookup
- runtime affinity and route hints

It answers questions such as:

- which runtime currently owns this channel account
- which runtime currently holds this websocket or SSE connection
- does this runtime support streaming, edit, or thread reply
- where should this outbound message be sent now

Daemon manages process life.

`ChannelRuntimeManager` manages runtime view and routing state.

## Delivery Model

### Standard Message

All channels should converge to a canonical `StandardMessage`.

Recommended shape:

```text
StandardMessage
- id
- role: user | assistant | system | tool
- type: text | image | file | event | command
- text
- parts
- attachments
- timestamp
- metadata
```

### Inbound Envelope

Push and poll both normalize into the same inbound shape.

Recommended shape:

```text
InboundEnvelope
- envelope_id
- channel_type
- channel_account_id
- transport_kind: push | poll
- external_message_id
- external_conversation_id
- external_user_id
- received_at
- dedupe_key
- payload: StandardMessage
- reply_address
- metadata
```

### Reply Address

Reply routing must not depend on holding an in-memory socket reference in orchestration.

Recommended shape:

```text
ReplyAddress
- channel_type
- channel_account_id
- connection_id
- external_conversation_id
- external_thread_id
- external_user_id
- route_hint
```

### Outbound Envelope

Directed outbound delivery should use a canonical envelope.

Recommended shape:

```text
OutboundEnvelope
- outbound_id
- conversation_id
- session_key
- reply_address
- message: StandardMessage
- mode: final | delta | event
- created_at
```

### Conversation Binding

Store external-to-internal conversation binding explicitly.

Important:

Bind to `session_key`, not to `active_session_id`.

Recommended shape:

```text
ConversationBinding
- binding_id
- channel_type
- channel_account_id
- external_conversation_id
- external_user_id
- internal_conversation_id
- session_key
- runtime_affinity
- created_at
- updated_at
```

This keeps bindings stable across fresh resets.

### Connection Binding

Connection binding is separate from conversation binding.

It records:

- `connection_id`
- `channel_type`
- `channel_account_id`
- `runtime_id`
- online presence
- streaming support
- last activity

Conversation binding is persistent.

Connection binding is runtime-hot state.

Do not conflate them.

## Inbound Flow

### Push Sources

Examples:

- webhook callbacks
- inbound websocket messages
- IM event callbacks

Flow:

```text
external push
  -> adapter receive
  -> validate and parse
  -> normalize InboundEnvelope
  -> channel runtime
  -> orchestration intake
  -> session sync and append
  -> dispatch enqueue
  -> command wakeup event
```

### Poll Sources

Examples:

- polling external mailbox APIs
- inbox scraping APIs
- ticket queues

Flow:

```text
poll manager
  -> adapter poll
  -> parse raw events
  -> normalize InboundEnvelope
  -> channel runtime
  -> orchestration intake
  -> session sync and append
  -> dispatch enqueue
  -> command wakeup event
```

Push and poll differ only below the normalized envelope.

Above that point, orchestration should not care.

## Execution Flow

```text
dispatch
  -> orchestration worker claim
  -> execute run
  -> write DB state
  -> emit fact events
  -> optionally emit delivery events
  -> optionally emit broadcast events
```

Worker output should not directly hold channel connection references.

Worker output should remain canonical and transport-independent.

## Directed Delivery Flow

Directed delivery is not broadcast.

Directed delivery includes:

- web SSE reply to one connection
- web WS reply to one connection
- IM reply to one account/thread
- callback delivery to one target

Flow:

```text
delivery event
  -> delivery resolver
  -> ChannelRuntimeManager.resolve_route(...)
  -> target channel runtime
  -> adapter.send(...)
  -> delivery receipt and retry tracking
```

### Delivery Responsibilities

Delivery should own:

- route resolution
- target runtime resolution
- target adapter selection
- fallback path selection

Delivery should not own:

- transport connection lifecycle
- session continuity
- agent reasoning

## Broadcast Flow

Broadcast is for scoped system notifications.

Examples:

- queue depth
- estimated wait time
- maintenance window
- system notice

Flow:

```text
broadcast event
  -> broadcast matcher
  -> target scope expansion
  -> fanout to matching runtimes/subscribers
```

Broadcast should be modeled separately from directed reply delivery even though both use the same `events` infrastructure.

## Daemon And Runtime Lifecycle

`daemon` remains the lifecycle authority for long-lived internal processes.

Recommended managed service families:

- `worker:orchestration`
- `worker:tool`
- `channel:web`
- `channel:telegram`
- `channel:discord`

The `channels` subsystem should not start arbitrary long-lived runtimes outside daemon governance.

### Manager And Daemon Relationship

Use the following split:

- profile layer defines desired static configuration
- `ChannelRuntimeManager` computes and exposes runtime topology and live registry state
- `daemon` starts and reconciles actual runtime processes
- runtime instances register and heartbeat back into `ChannelRuntimeManager`

The manager informs runtime topology.

The daemon owns process start and stop.

## Process Topology

### V1

Recommended initial process groups:

- `api`
- `worker:orchestration`
- `worker:tool`
- `channel:web`
- `channel:telegram`
- `channel:discord`

### Channel Runtime Granularity

Start with:

- one process per channel type

Not:

- one process per account
- one process per connection

Keep the design open for future sharding:

- `channel:web:shard:1`
- `channel:web:shard:2`

This can be introduced later without changing the core abstractions.

## Storage Split

### Database

Database remains the domain truth source.

Recommended strong state:

- `session`
- `session_instance`
- `session_message`
- `run`
- `tool_run`
- `conversation_binding`
- `delivery_record`
- `poll_cursor`
- approval and artifact metadata
- subagent tree metadata

### Redis

Redis becomes the runtime communication and hot-state layer.

Recommended hot state:

- cross-process event streams
- dispatch wakeup hints
- runtime heartbeat cache
- account-to-runtime cache
- connection-to-runtime cache
- online presence
- short-lived dedupe windows
- lock tokens and rate-limit counters

Database is still the business truth.

Redis is the runtime backbone.

## Ordering, Idempotency, And Concurrency

### Conversation Ordering

Default to serial execution per conversation for conversational agents.

Use:

- `ordering_key = internal_conversation_id`

This prevents:

- overlapping reply ordering
- prompt context races
- tool interference inside one active conversational thread

### Side Effects That May Run In Parallel

These can avoid the main conversation ordering lane:

- typing indicators
- ack and read receipts
- analytics
- non-blocking metrics

### Delivery Semantics

Design for:

- at-least-once ingress
- at-least-once delivery
- business-side idempotency

Recommended dedupe keys:

- ingress: `channel_type + channel_account_id + external_message_id`
- outbound: per-message idempotency key

## Container Composition

The target architecture should avoid one monolithic full container for every process type.

Preferred long-term composition roots:

- `build_api_container()`
- `build_worker_container()`
- `build_channel_runtime_container()`
- `build_cli_container()`

These should share the same application core contracts while avoiding unnecessary interface-layer coupling.

## Event And Scheduling Interaction

The system should move from:

- write to DB
- worker polls for tasks
- SSE polls DB state

to:

- write to DB
- publish wakeup or state events
- workers wake and then claim from `dispatch`
- SSE and other delivery paths consume event-driven updates
- low-frequency polling remains only as a resilience fallback

This preserves durable scheduling while removing hot-path polling as the normal behavior.

## Phased Delivery Plan

### Phase 1: Event Foundation

- create the formal `events` module
- define `EventEnvelope`
- implement cross-process publish and subscribe
- keep an in-memory test implementation only as a local testing backend

### Phase 2: Dispatch Wakeup Upgrade

- keep `dispatch` as the scheduler of truth
- publish wakeup events after enqueue
- make workers wake from events and claim from `dispatch`
- retain low-frequency polling as fallback

### Phase 3: Channel Core

- introduce `channels` domain and application structure
- define `StandardMessage`, `InboundEnvelope`, `OutboundEnvelope`, `ReplyAddress`
- implement `ConversationBinding`
- implement `ConnectionBinding`

### Phase 4: Channel Profile And Runtime Manager

- define profile/config layer
- add `ChannelRuntimeManager`
- add runtime registry, heartbeat, and route resolution

### Phase 5: Web Channel

- promote web into a first-class channel
- treat SSE and WS as directed delivery paths under web
- stop treating frontend SSE as a special global observer path

### Phase 6: Additional Channel Runtimes

- add telegram/discord or other external channel runtimes
- add polling adapters where needed
- add delivery retries and fallback policies

### Phase 7: Broadcast And Operations

- introduce scoped broadcast matching
- add system notification channels
- add repair, replay, and dead-letter tooling

## Deferred Decisions

The following points should remain explicit implementation decisions rather than hidden assumptions:

- whether `delivery.send` should always be scheduled through `dispatch`, or may use direct runtime handoff in selected low-latency cases
- whether `channel:web` should be physically colocated with `api` in V1, while still remaining a separate runtime concept
- when a channel should evolve from one runtime process to sharded runtime processes
- whether some low-state webhook-only channels need a long-lived dedicated runtime at all
- which Redis features should be treated as required in production versus optional acceleration in development

## What This Blueprint Explicitly Avoids

- a giant all-knowing message center
- channel runtimes directly holding orchestration object references
- orchestration directly holding live transport connections
- treating web SSE as the same thing as global broadcast
- binding external conversations to `active_session_id`
- replacing `dispatch` with raw event fanout
- using Redis as the sole business truth source

## Final Summary

The upgraded system should be understood as:

- `session` owns continuity
- `orchestration` owns execution
- `dispatch` owns scheduling
- `events` owns cross-process event transport
- `channels` owns transport-facing runtime state
- `delivery` owns directed route resolution
- `broadcast` owns scoped notification fanout
- `daemon` owns long-lived process lifecycle

Web is only one channel among many.

SSE and WS are directed delivery paths inside the web channel.

Broadcast is reserved for scoped system notifications.

This blueprint is the target model for the next communication-runtime upgrade.
