# Lark Channel Guide

## Purpose

`lark` is the first real IM platform channel in the upgraded runtime
architecture.

It validates that the shared channel model can handle a production-style
integration with:

- event subscription callback ingress
- platform credential management
- platform-specific outbound API calls
- tenant-scoped account configuration

This implementation currently focuses on the smallest useful self-built app
path, with runtime ingress preferring long connection:

- Feishu/Lark self-built app
- long connection event ingress in `channel:lark` runtime
- webhook callback kept as fallback/debug ingress
- `tenant_access_token` retrieval
- text message reply through `im/v1/messages`

## Official Platform References

Primary Feishu Open Platform references used for this implementation:

- Event subscription callback configuration:
  https://open.feishu.cn/document/server-docs/event-subscription-guide/event-subscription-configure-/request-url-configuration-case
- Self-built app `tenant_access_token`:
  https://open.feishu.cn/document/server-docs/authentication-management/access-token/tenant_access_token_internal
- Send message:
  https://open.feishu.cn/document/server-docs/im-v1/message/create

## Runtime Shape

The lark channel follows the same runtime model as the other channels:

- `ChannelProfile` defines static account config
- `ChannelControlService` produces `channel:lark` daemon specs
- `LarkChannelRuntimeService` self-registers and consumes runtime delivery
- `ChannelRuntimeManager` tracks runtime/account ownership

The lark runtime does not own orchestration or session logic.

It only:

- accepts normalized inbound message callbacks
- resolves and caches `tenant_access_token`
- sends outbound messages through Lark server APIs
- records delivery failures into dead-letter

## Minimal Profile Example

The smallest useful lark profile looks like this in code:

```python
ChannelProfile(
    channel_type="lark",
    accounts=(
        ChannelAccountProfile(
            account_id="default",
            transport_mode="webhook",
            credential_bindings={
                "lark_app_id": "access-binding:lark-app-id",
                "lark_app_secret": "access-binding:lark-app-secret",
                "lark_verification_token": "access-binding:lark-verification-token",
            },
            metadata={
                "agent_id": "crxzipple",
            },
        ),
    ),
)
```

Useful account metadata fields currently supported:

- `agent_id`
- `llm_id`
- `credential_bindings`
- `lark_base_url`
- `lark_receive_id_type`
- `lark_default_receive_id_type`
- `lark_group_require_bot_mention`
- `lark_bot_open_id`

Field meanings:

- `agent_id`
  default agent profile used for inbound callbacks
- `llm_id`
  optional llm override
- `credential_bindings`
  preferred Access-owned binding map keyed by credential slot. Lark currently
  recognizes `lark_app_id`, `lark_app_secret`, `lark_verification_token`,
  `lark_encrypt_key`, and `lark_bot_open_id`.
- `lark_base_url`
  optional server base URL override
  default is `https://open.feishu.cn`
- `lark_receive_id_type`
  hard override for outbound receive id type on this account
- `lark_default_receive_id_type`
  fallback outbound receive id type when reply metadata does not specify one
- `lark_group_require_bot_mention`
  when true, group messages are only accepted if the configured bot is mentioned
- `lark_bot_open_id`
  optional bot `open_id` used to evaluate group mention gating.
  If omitted, the runtime will try to resolve it automatically through
  `GET /open-apis/bot/v3/info` using the configured app credentials.

Profile YAML should reference Access credential binding IDs, not direct
environment credential sources:

```yaml
channel_type: lark
accounts:
  - account_id: default
    transport_mode: long_connection
    credential_bindings:
      lark_app_id: access-binding:lark-app-id
      lark_app_secret: access-binding:lark-app-secret
      lark_verification_token: access-binding:lark-verification-token
      lark_encrypt_key: access-binding:lark-encrypt-key
      lark_bot_open_id: access-binding:lark-bot-open-id
    metadata:
      agent_id: crxzipple
      lark_group_require_bot_mention: true
```

## Inbound Endpoint

Inbound event callbacks are received through:

```text
POST /channels/lark/events/{channel_account_id}
```

Current behavior:

- `url_verification` challenge requests are answered inline
- `im.message.receive_v1` is normalized into our shared turn submission path
- unsupported event types are accepted and ignored

## Current Inbound Message Mapping

Current message mapping for `im.message.receive_v1`:

- `message.chat_id` -> internal `conversation_id`
- `message.thread_id` or `message.root_id` -> internal `thread_id`
- `sender.sender_id.open_id` -> internal `peer_id`
- `message.chat_type` -> normalized `chat_type`
- `message.content` for `text` messages -> standard text blocks
- `message.mentions` and `<at user_id="...">...</at>` tags -> normalized mention metadata

## Group Mention Gating

If `lark_group_require_bot_mention=true`, group messages are only accepted when
the configured bot appears in the inbound mention set.

Current evaluation order is:

1. collect mentions from `message.mentions`
2. also parse `<at user_id="...">...</at>` tags from text content
3. resolve bot `open_id`:
   first from `lark_bot_open_id`, otherwise by calling `bot/v3/info`
4. compare mention `open_id` values against the resolved bot `open_id`

If the message is a group chat and the bot is not mentioned, the event is
accepted but ignored, and no orchestration run is queued.

This lets us keep noisy group traffic out of the runtime without rejecting the
platform callback.

## Non-Text Message Normalization

Non-text inbound messages are currently accepted and normalized into a stable
text placeholder so they can still participate in the shared orchestration path.

Current examples:

- `image` -> `[Lark image message]`
- `file` -> `[Lark file: <file_name>]` when file name is present
- `post` -> flattened readable text lines from title/body content
- unknown -> `[Lark unknown message]`

The normalized payload also retains:

- `metadata.message_type`
- `metadata.raw_content`
- `metadata.mentions`
- type-specific fields such as:
  - `metadata.image_key`
  - `metadata.file_key`
  - `metadata.file_name`
  - `metadata.post_lines`

This is intentionally simple, but it gives us a durable starting point before
we add richer platform-native content handling.

Current text normalization example:

```json
{
  "header": {
    "event_type": "im.message.receive_v1",
    "event_id": "evt_lark_1"
  },
  "event": {
    "sender": {
      "sender_id": {
        "open_id": "ou_sender_1"
      }
    },
    "message": {
      "message_id": "om_msg_1",
      "chat_id": "oc_chat_1",
      "chat_type": "p2p",
      "message_type": "text",
      "content": "{\"text\":\"hello from lark\"}"
    }
  }
}
```

This becomes a normal orchestration turn with:

- `channel = "lark"`
- `conversation_id = "oc_chat_1"`
- `peer_id = "ou_sender_1"`
- `source = "lark_event"`

## Verification Token And Encrypted Callbacks

If `lark_verification_token` is configured, callback payload token validation is
enforced.

Current token matching checks:

- top-level `token`
- or `header.token`

If `lark_encrypt_key` is configured and the callback body contains `encrypt`,
the endpoint currently:

1. verifies:
   - `X-Lark-Request-Timestamp`
   - `X-Lark-Request-Nonce`
   - `X-Lark-Signature`
2. decrypts the event body
3. continues token validation on the decrypted payload

Current signature algorithm in the implementation:

```text
sha256(timestamp + nonce + encrypt_key + raw_request_body)
```

Current decryption shape in the implementation:

- base64 decode the `encrypt` payload
- first 16 bytes are IV
- AES-CBC with `sha256(encrypt_key)` as the key
- extract the JSON object from the decrypted bytes

This matches the public Lark SDK event handling approach we referenced while
implementing the handler.

## Outbound Delivery

When orchestration completes with a lark delivery target, `delivery` emits an
`OutboundEnvelope` for `channel_type="lark"`.

`LarkChannelRuntimeService` consumes its runtime delivery topic and:

1. resolves target account config
2. fetches or reuses `tenant_access_token`
3. determines `receive_id_type`
4. calls:

```text
POST /open-apis/im/v1/messages
```

Current supported outbound mode:

- text reply via `msg_type="text"`

Current outbound target resolution:

- resolution order is:
  1. account metadata `lark_receive_id_type`
  2. `ReplyAddress.metadata.receive_id_type`
  3. inferred from `ReplyAddress.metadata.chat_type`
  4. account metadata `lark_default_receive_id_type`
- inferred chat behavior is:
  - `direct` -> `open_id`
  - other chat types -> `chat_id`
- `chat_id` uses `ReplyAddress.external_conversation_id`
- `open_id` uses `ReplyAddress.external_user_id`

## Thread Reply Context

Current inbound normalization also preserves reply context:

- `message.message_id` -> `ReplyAddress.metadata.message_id`
- `message.thread_id` or `message.root_id` -> `ReplyAddress.external_thread_id`
- thread presence -> `ReplyAddress.metadata.reply_in_thread = true`

Current outbound text replies forward that context when available:

- `reply_message_id`
- `thread_id`
- `reply_in_thread`

## Current ReplyAddress Expectations

The current minimal reply address for a lark reply looks like:

```json
{
  "channel_type": "lark",
  "channel_account_id": "default",
  "external_conversation_id": "oc_chat_1",
  "external_thread_id": "omt_thread_1",
  "external_user_id": "ou_sender_1",
  "metadata": {
    "receive_id_type": "open_id",
    "chat_type": "direct",
    "message_id": "om_msg_1",
    "event_id": "evt_lark_1",
    "reply_in_thread": true
  }
}
```

## Failure Handling

Lark delivery currently uses the same small bounded retry policy as the webhook
runtime:

- up to `3` attempts per outbound delivery
- failure records written to dead-letter on final failure

Runtime metadata records:

- `delivery_observed_count`
- `delivery_success_count`
- `delivery_failed_count`
- `delivery_retry_attempt_count`
- `delivery_dead_letter_count`
- `last_delivery_receive_id`
- `last_delivery_status`
- `last_dead_letter_outbound_id`

Dead letters can be queried through:

```text
GET /channels/dead-letters/lark
```

## Current Scope And Known Gaps

What is implemented now:

- self-built app credentials
- verification token
- encrypted callback verification/decryption
- `im.message.receive_v1`
- text message reply
- group mention gating
- non-text inbound placeholder normalization
- daemon-managed runtime

What is intentionally not complete yet:

- richer outbound message types
- card messages
- edit/update existing message
- tenant-scoped multi-account auth refresh policies
- platform-specific retry classification

This is the correct point to start real integration, but not the final
feature-complete Lark channel.
