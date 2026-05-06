# Channel Profiles

This directory is the repo-managed configuration source for channel profiles.

It mirrors the loading style used by `config/llm_profiles/`:

- `*.yaml`, `*.yml`, and `*.json` files in this directory are loaded at startup
- files are merged by `channel_type`
- later files with the same `channel_type` override earlier ones

Environment overrides are also supported:

- `APP_CHANNEL_PROFILE_PATHS`
- `APP_CHANNEL_PROFILES`

At startup, configured profiles are merged into the channel system config
backing store. Runtime state continues to live under `.crxzipple/channels/`.

Example files live under [`examples/`](./examples).
