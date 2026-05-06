# Inbox Channel Guide

## Purpose

`inbox` is the first `poll`-style channel implementation used to validate the
multi-channel architecture beyond push-only delivery.

It is intentionally simple:

- inbound is enqueued into an account-specific inbox topic
- the inbox runtime polls that topic and submits normal orchestration turns
- completed delivery is routed into an account-specific outbox topic
- consumers can poll the outbox to observe assistant responses

This channel is not meant to model a specific external platform. It exists to
prove that the architecture works for pull-based channels as cleanly as it does
for webhook-style push channels.

## Runtime Shape

The inbox channel uses the same core model as the other channels:

- `ChannelProfile` defines static config
- `ChannelControlService` produces `channel:inbox` daemon specs
- `InboxChannelRuntimeService` self-registers, polls inbox topics, and routes
  outbound delivery into outbox topics
- `ChannelRuntimeManager` tracks runtime/account ownership and executor lease

The inbox runtime does not own orchestration logic.

It only:

- reads normalized inbound records from inbox topics
- submits turns into `orchestration`
- reads routed delivery for its runtime
- publishes normalized outbound records into outbox topics

## Minimal Profile Example

The smallest useful inbox profile looks like this in code:

```python
ChannelProfile(
    channel_type="inbox",
    accounts=(
        ChannelAccountProfile(
            account_id="default",
            transport_mode="poll",
        ),
    ),
)
```

This is enough for:

- `channels/control` to produce a `channel:inbox` daemon spec
- the inbox runtime to bind the `default` account
- inbound events to be consumed from the `default` inbox topic
- outbound results to be published to the `default` outbox topic

## Inbound Endpoint

Inbound inbox records are enqueued through:

```text
POST /channels/inbox/inbound/{channel_account_id}
```

Example body:

```json
{
  "content": {
    "blocks": [
      {
        "type": "text",
        "text": "hello from inbox"
      }
    ]
  },
  "agent_id": "assistant",
  "conversation_id": "ext-inbox-conv-1",
  "peer_id": "ext-inbox-user-1"
}
```

Supported request fields:

- `content`
- `agent_id`
- `llm_id`
- `chat_type`
- `peer_id`
- `conversation_id`
- `thread_id`
- `main_key`
- `direct_scope`
- `source`
- `queue_policy`
- `priority`
- `max_steps`
- `reply_metadata`

Important behavior:

- this endpoint **does not** execute the turn inline
- it only writes a normalized command event to the account inbox topic
- the inbox runtime later polls that topic and submits the turn into
  `orchestration`

On success the endpoint returns the queued inbox event:

```json
{
  "event_id": "evt_...",
  "topic": "channel.inbox.inbox.account.default",
  "channel_account_id": "default",
  "conversation_id": "ext-inbox-conv-1"
}
```

## Poll Processing Model

When the inbox runtime wakes up, it:

1. lists account bindings for `channel_type="inbox"`
2. polls each bound inbox topic after its stored cursor
3. normalizes the record into the standard submission path
4. calls the normal orchestration ingress
5. records the per-account inbox cursor in runtime metadata

That means push and poll converge at the same orchestration/session boundary.

## Outbox Delivery

When orchestration completes with an inbox delivery target, `delivery` produces
an `OutboundEnvelope` for `channel_type="inbox"`.

The inbox runtime consumes its runtime delivery topic and republishes the
resolved delivery into an account-specific outbox topic:

```text
channel.outbox.inbox.account.{channel_account_id}
```

This lets a poll-style external integration fetch assistant results without
needing a live callback endpoint.

## Outbox Query API

Outbox records can be read through:

```text
GET /channels/inbox/outbox/{channel_account_id}
```

Useful query params:

- `after_cursor`
- `limit`

Example:

```text
GET /channels/inbox/outbox/default
```

Each returned item includes:

- `cursor`
- `outbound_id`
- `mode`
- `message`
- `reply_address`
- `route`
- `created_at`

## Outbox Payload Shape

Example outbox record:

```json
{
  "cursor": "17",
  "outbound_id": "out_...",
  "mode": "final",
  "message": {
    "role": "assistant",
    "type": "text",
    "text": "hello from inbox runtime"
  },
  "reply_address": {
    "channel_type": "inbox",
    "channel_account_id": "default",
    "external_conversation_id": "ext-inbox-conv-1",
    "external_thread_id": null,
    "external_user_id": "ext-inbox-user-1",
    "route_hint": null,
    "metadata": {}
  },
  "route": {
    "runtime_id": "inbox-runtime-1",
    "channel_type": "inbox",
    "path": "account",
    "channel_account_id": "default",
    "service_key": "channel:inbox"
  },
  "created_at": "2026-04-13T00:00:00+00:00"
}
```

Current `mode` values follow `OutboundEnvelope.mode`:

- `final`
- `delta`
- `event`

In the current inbox implementation, `final` is the main path used.

## Runtime Metadata

The inbox runtime records useful progress metadata such as:

- `inbox_cursors`
- `inbox_observed_count`
- `last_inbox_event_id`
- `last_inbox_account_id`
- `delivery_cursor`
- `delivery_observed_count`
- `outbox_route_cursor`
- `outbox_published_count`
- `last_outbox_outbound_id`
- `last_outbox_account_id`

These fields are visible through the channel runtime query APIs.

## What This Channel Validates

`inbox` is valuable because it proves the architecture handles poll-style
channels without special-casing them in `session` or `orchestration`.

Specifically it validates:

- poll ingress through channel runtime rather than HTTP direct execution
- `ReplyAddress`-based outbound routing for a non-webhook channel
- daemon-managed runtime ownership of a non-`web` channel
- account-specific outbox fanout for pull-based consumers
