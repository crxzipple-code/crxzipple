# Channel Credential Requirements Guide

Channel profiles declare external credentials as Access-owned account slots.
Channel code must not read secrets directly from `env:`, `file:`, inline
metadata, or local auth files.

## Account Slots

Use `credential_bindings` on each account:

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

`auth_ref` is retired. Metadata `*_binding` fields are only materialized from
`credential_bindings` by the domain object and should not be authored by hand.

## Lark Slots

The Lark channel currently declares:

- `lark_app_id`, kind `api_key`, required.
- `lark_app_secret`, kind `app_secret`, required.
- `lark_verification_token`, kind `webhook_secret`, optional.
- `lark_encrypt_key`, kind `webhook_secret`, optional.
- `lark_bot_open_id`, kind `api_key`, optional.

If `lark_bot_open_id` is omitted, the runtime may discover it through
`GET /open-apis/bot/v3/info` using the configured app credentials.

## WeCom Slots

Enterprise WeChat / WeCom uses app credentials rather than a user OAuth login.
Declare these account slots:

```yaml
channel_type: wecom
accounts:
  - account_id: default
    credential_bindings:
      wecom_corp_id: access-binding:wecom-corp-id
      wecom_agent_id: access-binding:wecom-agent-id
      wecom_corp_secret: access-binding:wecom-corp-secret
      wecom_token: access-binding:wecom-token
      wecom_encoding_aes_key: access-binding:wecom-encoding-aes-key
```

- `wecom_corp_id`, kind `api_key`, required.
- `wecom_agent_id`, kind `api_key`, required.
- `wecom_corp_secret`, kind `app_secret`, required.
- `wecom_token`, kind `webhook_secret`, optional.
- `wecom_encoding_aes_key`, kind `webhook_secret`, optional.

These slots use manual Access setup and must not be modeled as
`oauth2_account` / browser login assets.

## Webhook Secrets

Webhook inbound signatures must use an Access binding:

```yaml
channel_type: webhook
accounts:
  - account_id: default
    transport_mode: webhook
    credential_bindings:
      webhook_signing_secret: access-binding:webhook-secret
```

Do not put `webhook_signing_secret` inline in metadata.

## Runtime Resolution

Runtime services call `resolve_channel_metadata_binding`, which accepts only
Access binding ids for secret-bearing fields. If a profile contains a direct
credential source, startup or request handling fails fast with a configuration
error.

Non-secret channel settings such as `agent_id`, `llm_id`, `lark_base_url`,
receive id strategy, and group mention policy remain regular metadata.

## Operations And Settings

Access is the governance surface for credential readiness, setup, audit, and
binding selection. Channel settings should present the account slots and let the
operator pick compatible Access bindings; the channel module remains focused on
transport behavior.
