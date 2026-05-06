# Web Channel Guide

## Purpose

`web` is a formal channel, not a frontend-only special case.

The web channel is the browser-facing transport path for:

- directed `delivery`
- scoped `broadcast`
- run `observe` events

This document describes the transport layer only.

The current web frontend product surface is defined separately in
[docs/ui/current-ui-design-functional-spec.md](ui/current-ui-design-functional-spec.md).

That distinction matters:

- the web console is the global session management UI
- `channel:web` is the browser transport used by that UI

The browser no longer needs any turn-scoped SSE endpoint for normal realtime UI
behavior.

## Stream Roles

There is now a single browser-facing SSE path for web conversations.

### Web Channel Stream

```text
GET /channels/web/events
```

This is the primary stream for browser clients.

It carries:

- `connected`
- `observe`
- `delivery`
- `broadcast`
- `timeout`

The endpoint now returns explicit stream role headers:

```text
X-Crx-Stream-Role: primary
X-Crx-Stream-Scope: channel
```

The initial `connected` event also carries:

- `stream_role = "primary"`
- `observe_mode = "preferred"`

Those fields make the preferred client behavior explicit instead of relying on
implicit frontend conventions.

## Event Semantics

The web channel stream intentionally separates three outward-facing event types.

### Observe

`observe` is for execution observation.

Examples:

- run advanced
- llm stream synced
- session message appended
- approval requested
- approval resolved
- run completed

These are not directed user messages.

They describe what the current execution is doing and let subscribed web
connections reconstruct UI state.

### Delivery

`delivery` is for directed outbound user-visible messages.

Examples:

- assistant reply to the current conversation
- out-of-band assistant notification
- channel-directed message payloads that should be rendered into the timeline

These are routed through the web connection delivery path and are separate from
execution observation.

### Broadcast

`broadcast` is for scoped system notification.

Examples:

- queue position updates
- maintenance notices
- tenant-wide service warnings

Broadcast is not a normal reply path.

## Frontend Behavior

The frontend now uses `/channels/web/events` as its single realtime stream for:

- `observe`
- `delivery`
- `broadcast`

The browser no longer opens a separate turn-scoped SSE stream for run
observation or fallback.

## Connection Model

The web channel endpoint accepts:

- `channel_account_id`
- `connection_id`
- `conversation_id`

The runtime binds that connection into the web channel registry and routes:

- directed delivery to the connection delivery topic
- observe events to the connection observe topic
- matching broadcasts to the connection subscriber

The browser does not need to know runtime ids or event routing details.

## Current Direction

The target model is now the active model:

- browser clients consume `/channels/web/events`
- run observation, delivery, and broadcast all flow through the web channel
