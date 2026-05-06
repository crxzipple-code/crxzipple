# Webhook Channel Guide

## Purpose

`webhook` is the first non-`web` channel implementation used to validate the
multi-channel architecture end-to-end.

It is intentionally simple:

- inbound arrives through one HTTP endpoint
- orchestration processes the turn normally
- outbound delivery is posted to a callback URL by the webhook runtime
- failures are retried a small number of times and then written to dead-letter

This channel is meant to validate architecture and integration shape before
heavier IM platforms are added.

## Runtime Shape

The webhook channel uses the same core model as other channels:

- `ChannelProfile` defines static config
- `ChannelControlService` produces `channel:webhook` daemon specs
- `WebhookChannelRuntimeService` self-registers and consumes its delivery topic
- `ChannelRuntimeManager` tracks runtime/account ownership

The webhook runtime does not own orchestration logic.

It only:

- receives normalized inbound requests
- posts outbound callback payloads
- tracks retries and failures

## Minimal Profile Example

The smallest useful webhook profile looks like this in code:

```python
ChannelProfile(
    channel_type="webhook",
    accounts=(
        ChannelAccountProfile(
            account_id="default",
            transport_mode="webhook",
        ),
    ),
)
```

If inbound signature validation is required, add metadata on the account:

```python
ChannelProfile(
    channel_type="webhook",
    accounts=(
        ChannelAccountProfile(
            account_id="default",
            transport_mode="webhook",
            metadata={
                "webhook_signing_secret": "top-secret",
                # Optional. Defaults to X-Crx-Webhook-Signature
                "webhook_signature_header": "X-Crx-Webhook-Signature",
            },
        ),
    ),
)
```

`webhook_signing_secret` enables inbound request verification for that account.

## Inbound Endpoint

Inbound requests go to:

```text
POST /channels/webhook/inbound/{channel_account_id}
```

Example body:

```json
{
  "content": {
    "blocks": [
      {
        "type": "text",
        "text": "hello from webhook"
      }
    ]
  },
  "callback_url": "https://example.test/callback",
  "agent_id": "assistant",
  "conversation_id": "ext-conv-1",
  "peer_id": "ext-user-1"
}
```

Supported request fields:

- `content`
- `callback_url`
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
- `callback_metadata`

On success the endpoint returns the accepted run:

```json
{
  "run_id": "run_...",
  "status": "queued",
  "session_key": "agent:assistant:main",
  "active_session_id": "sess_...",
  "callback_url": "https://example.test/callback"
}
```

## Signature Validation

If the selected webhook account has `webhook_signing_secret`, the inbound
endpoint requires a signature header.

Default header:

```text
X-Crx-Webhook-Signature
```

Expected algorithm:

```text
hex(HMAC-SHA256(raw_request_body, webhook_signing_secret))
```

Both of these forms are accepted:

```text
<hex>
sha256=<hex>
```

If the header is missing or invalid, the endpoint returns `401`.

## Callback Delivery

When a run completes with textual output and a webhook `reply_target`,
`orchestration` emits an `OutboundEnvelope`.

The webhook runtime consumes that delivery and `POST`s the callback URL from
`ReplyAddress.webhook_callback_url`.

## Callback Payload Schema

Callback payload shape:

```json
{
  "outbound_id": "out_...",
  "mode": "final",
  "conversation_id": "ext-conv-1",
  "session_key": "agent:assistant:main",
  "message": {
    "role": "assistant",
    "type": "text",
    "text": "hello from webhook runtime"
  },
  "reply_address": {
    "channel_type": "webhook",
    "channel_account_id": "default",
    "webhook_callback_url": "https://example.test/callback",
    "external_conversation_id": "ext-conv-1",
    "external_thread_id": null,
    "external_user_id": "ext-user-1",
    "route_hint": null,
    "metadata": {}
  },
  "route": {
    "runtime_id": "webhook-runtime-1",
    "channel_type": "webhook",
    "path": "account",
    "channel_account_id": "default",
    "connection_id": null,
    "supports_streaming": false,
    "route_hint": null,
    "service_key": "channel:webhook",
    "metadata": {}
  },
  "metadata": {
    "run_id": "run_...",
    "delivery_interface": "webhook"
  },
  "created_at": "2026-04-13T00:00:00+00:00"
}
```

Current `mode` values follow `OutboundEnvelope.mode`:

- `final`
- `delta`
- `event`

In the current webhook implementation, `final` is the main path used.

## Retry And Dead-Letter Behavior

Webhook callback delivery currently uses a small bounded retry policy:

- up to `3` callback attempts per outbound delivery
- non-2xx responses count as failures
- transport exceptions count as failures

If delivery still fails, the runtime emits a dead-letter event and records
failure metadata on the runtime registration.

Runtime metadata currently includes fields such as:

- `delivery_observed_count`
- `delivery_success_count`
- `delivery_failed_count`
- `delivery_retry_attempt_count`
- `delivery_dead_letter_count`
- `last_delivery_callback_url`
- `last_delivery_callback_status`
- `last_dead_letter_outbound_id`

## Dead-Letter Query API

Dead-letter records can be queried through:

```text
GET /channels/dead-letters/{channel_type}
```

Useful query params:

- `runtime_id`
- `after_cursor`
- `limit`

Example:

```text
GET /channels/dead-letters/webhook?runtime_id=webhook-runtime-1
```

Each returned item includes:

- `cursor`
- `topic`
- `event_id`
- `kind`
- `created_at`
- `payload`
- `target`

## Operational Notes

- `channel:webhook` is planned and synced through `channels/control`
- daemon stays generic and only starts the produced service spec
- the runtime self-registers after startup
- runtime/account ownership is resolved through `ChannelRuntimeManager`

## Current Scope

The current webhook channel intentionally does not yet implement:

- callback authentication beyond outbound URL ownership
- custom retry policy per account
- dead-letter replay tools
- per-account callback formatting variants
- webhook-specific admin UI

Those are follow-up improvements, not blockers for architecture validation.
