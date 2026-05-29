# Tool / Channel Access Credential Requirements Checklist 2026-05-11

本文档定义 Tool 与 Channel 的外部凭证需求如何在 Access 中可见、可绑定、可 setup、可审计，
并给 tool/channel 开发者一套稳定写法。它延续当前边界：`authorization` 负责内部 ABAC；
`access` 负责外部 provider/account/credential/readiness/setup/audit；业务模块只声明需求并在运行时
通过 port 取用。

## 目标结论

- Tool / Channel 开发者不直接读取 `env:`、`file:`、raw token 或本地 auth 文件。
- Tool / Channel manifest/profile 声明 credential requirement / slot / expected kind / scopes / setup metadata。
- Access 能展示所有声明出来的 requirement：来源模块、consumer、slot、凭证类型、绑定状态、readiness、setup 入口、最近使用和审计。
- API key、bearer、basic、app secret、webhook secret、OAuth2 / OpenID Connect 等外部访问都统一走 Access。
- OAuth 官方授权由 Access 提供 setup flow 和 lifecycle 管理，Tool / Channel 只声明 provider、scopes、callback/device-code 能力。
- OpenAPI tool 的 `securitySchemes` 是自动生成 credential requirement 的输入；native/local tool 使用同一份 manifest contract。
- Channel account 已移除 `auth_ref`，目标结构为多个 named credential slots，并只接受 Access binding id。

## 当前事实

- Tool OpenAPI runtime 已支持 `securitySchemes/security` 和 `credential_bindings`，执行时会通过
  `CredentialProvider.resolve_credential` 取凭证。
- Tool OpenAPI 配置已拒绝 `env:` / `file:` / `codex_auth_json` 这类直接来源写法，OpenAPI 与 native/local
  tool 都通过 credential requirement/slot 暴露凭证需求。
- Tool catalog response 已输出结构化 `credential_requirements`。
- Channel profile 已移除 `auth_ref`，Lark 使用 `credential_bindings` 声明多个 credential slots。
- Access read model 已有 credential binding、consumer binding、asset、setup session、audit 与 requirement catalog。
- Access domain 已保留 `OAUTH_PROVIDER`、`OAUTH_ACCOUNT` 等资源概念；当前 OAuth setup 仍返回 unsupported。
- Settings/Access 已形成基本边界：配置声明可通过 Settings action 写入，Access 负责运行时 readiness、setup、secret resolution。

## 2026-05-11 施工记录

- 已落地 shared credential requirement contract，并补充 `tests/unit/test_access_credential_requirements.py`。
- 已接通 Tool/OpenAPI requirement 投影：`ToolSpec`、Tool domain、DTO、HTTP response 均输出
  `credential_requirements`；OpenAPI runtime 优先用 Access binding id 解析 credential。
- 已接通 Channel profile credential slots：Lark 示例和指南已从 `env:LARK_*` 改为 Access binding id。
- 已接通 Access requirement catalog 第一版：`/ui/access` 输出 `credential_requirements`，
  新增 `/ui/access/credential-requirements`，overview counts 包含 missing/ready/kind mismatch。
- 已切掉 `collect_access_inventory` 对 Settings legacy LLM profile 的反向推断；Access inventory 只读
  Settings-owned Access 配置，不再从业务 profile 扫描出凭证事实。
- 已接通 Access requirement 动作第一版：`bind_credential_requirement` / `unbind_credential_requirement`
  通过 Settings 写入 consumer binding，`verify_credential_requirement` 通过 Access audit 记录校验结果。
- 已接通 Access requirement slot 维度：consumer binding read model/action 可按 slot 绑定、解绑和校验，
  避免一个 consumer 被粗粒度单 binding 卡住。
- 已移除 Tool/OpenAPI provider 运行路径的 direct credential source：`OpenApiCredentialBinding` 不再有
  `source` / `username_source` / `password_source`，内置 OpenAPI 工具包改为 Access binding id。
- 已接入 native/local tool package 的 `credential_requirements` manifest 字段，并把 OpenAI image
  工具迁到 `openai-api-key` Access binding。
- 已收口 Channel 凭证路径：`auth_ref` 已从 domain/runtime/config 读取路径移除，Lark profile
  及本地 state 已迁为 `credential_bindings` + Access binding id；Channel 运行时不再接受
  `env:` / `file:` / `codex_auth_json` 作为业务凭证来源。
- 已把 Webhook 签名密钥收为 `credential_bindings.webhook_signing_secret` 正式 slot，
  Access/Channel Settings 可统一展示签名密钥 readiness。
- 已接通 Access Operations Requirements tab、Access Settings requirement 绑定表、
  Tool provider/detail credential slots、Channel account/detail credential slots。
- 已补齐 Channel credential readiness 错误通道：credential binding 解析失败时返回
  `access_not_ready` 结构化 payload，Webhook/Lark HTTP 入口不再裸露底层 RuntimeError。
- 已切掉 Webhook profile-level secret fallback；Webhook 签名密钥只从 account
  `credential_bindings.webhook_signing_secret` 读取。Channel 持久化也不再写回运行时 materialized
  `*_binding` metadata。
- 已补齐 Access credential binding 停用/启用/注销动作：
  `disable_credential_binding`、`enable_credential_binding`、`revoke_credential_binding`。
  disabled/revoked binding 会在 requirement read model 中显示非 ready，运行时解析会被 Access 拦截。
- Access audits 现在合并 Settings-owned Access config 写审计；register/bind/unbind/disable/revoke 这类
  治理动作可在 Access audit read model 中看到。
- 已补充 Tool / Channel credential requirement developer guide，并更新 Tool README 与 Webhook guide。
- 已完成本轮目标验收：
  - `PYTHONPATH=src pytest -q tests/unit/test_access_*.py tests/unit/test_tool_access_architecture.py tests/unit/test_channel_access_architecture.py tests/unit/test_channel_bindings.py tests/unit/test_channels.py tests/unit/test_channels_http.py tests/unit/test_tool_settings_integration.py tests/unit/test_openapi_access.py tests/unit/test_openai_image_tool.py`
    通过，151 passed。
  - `cd frontend && npm run typecheck` 通过。
  - `cd frontend && npm run build` 通过。
  - `PYTHONPATH=src pytest -q tests/unit/test_access_actions.py tests/unit/test_access_read_models.py tests/unit/test_ui_access_http.py tests/unit/test_access_http.py`
    通过，33 passed。
  - `PYTHONPATH=src pytest -q tests/unit/test_access_*.py tests/unit/test_tool_access_architecture.py tests/unit/test_channel_access_architecture.py tests/unit/test_channel_bindings.py tests/unit/test_channels.py tests/unit/test_channels_http.py tests/unit/test_tool_settings_integration.py tests/unit/test_openapi_access.py tests/unit/test_openai_image_tool.py`
    通过，156 passed。
  - `cd frontend && npm run typecheck` 通过。
  - `cd frontend && npm run build` 通过。
- 收口后复验：
  - `PYTHONPATH=src pytest -q tests/unit/test_access_*.py tests/unit/test_tool_access_architecture.py tests/unit/test_channel_access_architecture.py tests/unit/test_channel_bindings.py tests/unit/test_channels.py tests/unit/test_channels_http.py tests/unit/test_tool_settings_integration.py tests/unit/test_openapi_access.py tests/unit/test_openai_image_tool.py`
    通过，154 passed。
  - `cd frontend && npm run typecheck` 通过。
  - `cd frontend && npm run build` 通过。
- OAuth 闭环第一版已落地：
  - Access runtime DB 新增 `access_oauth_providers` / `access_oauth_accounts`，migration 为
    `alembic/versions/0047_access_oauth_accounts.py`。
  - Access 私有 token store 落在 `APP_ACCESS_STATE_DIR`，DB 只保存 account 元数据和 storage key。
  - `register_oauth_provider`、`begin_oauth_setup_session`、`complete_oauth_setup_session`、
    `import_codex_cli_oauth_account`、`disable_oauth_account`、`revoke_oauth_account`
    已接入 Access action/audit。
  - Codex 从 `codex_auth_json` 业务凭证类型迁为 `openai-codex` OAuth account：
    默认 binding 为 `codex-oauth-default`，可从 macOS Keychain 或 `~/.codex/auth.json`
    导入到 Access OAuth account。
  - LLM/前端对 OpenAI Codex 的 credential expectation 已改为 `oauth2_account`。
- 本轮仍未做：OAuth device-code、真实浏览器 callback listener、rotate、完整人工端到端执行验收。
- 当前剩余未闭合项集中在三块：
  - OAuth device-code、真实浏览器回调监听、真实 provider 人工 E2E。
  - 更严格的历史兼容清理和必要数据库 migration。
  - 需要真实服务/凭证参与的人工 E2E。

## P0. 边界与 Contract

- [x] 在 `crxzipple.shared.access` 定义结构化 credential requirement contract：
  - `AccessCredentialRequirementDeclaration`
  - `AccessCredentialRequirementSet`
  - `AccessCredentialSlotRef`
  - `AccessCredentialKind`
  - `AccessSetupFlowHint`
- [x] 字段至少包含：
  - `requirement_id`
  - `consumer_module`
  - `consumer_kind`
  - `consumer_id`
  - `slot`
  - `display_name`
  - `provider`
  - `kind`
  - `required`
  - `scopes`
  - `transport`
  - `binding_id`
  - `setup_flow_hint`
  - `metadata`
- [x] 支持 kind 枚举：
  - `api_key`
  - `bearer_token`
  - `basic`
  - `oauth2_account`
  - `openid_connect`
  - `app_secret`
  - `webhook_secret`
  - `certificate`
  - `codex_auth_json`
- [x] 支持 transport 描述：
  - `header`
  - `query`
  - `cookie`
  - `body`
  - `oauth_authorization_header`
  - `runtime_context`
- [x] 明确 requirement declaration 不包含 secret 原值，也不包含 `env:` / `file:` 等来源。
- [x] 明确 credential binding 只引用 Access-owned `credential_binding_id` 或 OAuth account id。
- [x] 增加 Tool architecture guard：OpenAPI binding contract 不再包含 direct source 字段，内置 tool manifest 不得写 `env:` / `file:` / `codex_auth_json` direct credential source。
- [x] 增加 Channel architecture guard：Channel account 不再有 `auth_ref`，Channel profile config
  不得写 `env:` / `file:` / `codex_auth_json` direct credential source，运行时 profile 会拒绝这类 binding。

验收：

```bash
rg -n 'env:|file:|codex_auth_json|auth_ref' \
  config/tool_providers config/channel_profiles tools
rg -n 'os\\.environ|getenv|read_text\\(.*credential' \
  src/crxzipple/modules/tool src/crxzipple/modules/channels
```

## P1. Tool Requirement 接入

- [x] 修改 `OpenApiCredentialBinding`：将 `source` / `username_source` / `password_source` 迁为
  `credential_binding_id` / `username_binding_id` / `password_binding_id`。
- [x] 删除长期兼容：OpenAPI provider config 不再接受 `env:` / `file:` / `codex_auth_json` 直接来源。
- [x] OpenAPI discovery 从 `securitySchemes` 和 effective `security` 自动生成 credential requirement declarations。
- [x] 对 `apiKey` 生成 kind=`api_key`，并标注 header/query/cookie 参数名。
- [x] 对 HTTP bearer 生成 kind=`bearer_token`。
- [x] 对 HTTP basic 生成 kind=`basic`，并生成 username/password 两个 binding slots 或一个 compound binding slot。
- [x] 对 `oauth2` / `openIdConnect` 生成 kind=`oauth2_account` / `openid_connect`，并保留 scopes、authorization/token URL 元数据。
- [x] Native/local tool package manifest 增加同样的 `credential_requirements` 结构化字段。
- [x] Tool catalog API response 增加 `credential_requirements`，保留旧 `access_requirements` 仅用于内部授权/effect 文本语义时再明确命名。
- [x] Tool runtime 执行前按 slot 解析 credential，错误统一返回 `access_not_ready` / `credential_binding_missing` / `credential_kind_mismatch`。
- [x] Tool runtime request metadata 不得记录 credential value；query credential 在 sanitized URL 中必须 redacted。
- [x] Tool Settings 页面新增 provider credential slots 绑定区，从 `/ui/access` 或组合 API 选择兼容 binding。
- [x] Operations/Access 页面能看到 Tool consumer requirement 与 readiness。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_openapi.py tests/unit/test_access_tool_requirements.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/tool
cd frontend && npm run typecheck
```

## P2. Channel Requirement 接入

- [x] 为 `ChannelAccountProfile` 增加结构化 `credential_requirements` / `credential_bindings`，替代单个 `auth_ref`。
- [x] `auth_ref` 已从 `ChannelAccountProfile`、config builder、runtime access requirements 中移除。
- [x] Channel profile settings parser 支持 slots：
  - `lark_app_id`
  - `lark_app_secret`
  - `lark_verification_token`
  - `lark_encrypt_key`
  - `lark_bot_open_id`
  - provider-specific OAuth account slot
- [x] Lark channel 示例从 `env:LARK_*` 改为 Access binding id。
- [x] Webhook inbound signature 支持通过 Access binding id 读取 signing secret，不再要求 inline secret。
- [x] Inbox / web channel 如无 credential requirement，显式输出空 requirement 列表。
- [x] Channel runtime 通过 `CredentialProvider` 或 Channel credential port 解析 slot。
- [x] Channel binding/readiness 中断时应上报 Access readiness，而不是吞成 channel generic error。
- [x] Channel Settings 页面展示 account credential slots、绑定状态、setup 入口。
- [x] Operations/Access 页面能看到 Channel consumer requirement 与 readiness。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_channels.py tests/unit/test_access_channel_requirements.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/channels
rg -n 'env:LARK|file:' config/channel_profiles docs/lark-channel-guide.md
PYTHONPATH=src pytest -q tests/unit/test_channel_access_architecture.py
```

## P3. Access Requirement Catalog / Read Model

- [x] Access 增加 requirement catalog query port，用于聚合模块声明的 requirements。
- [x] Access query provider 输出：
  - `credential_requirements`
  - `requirements_by_consumer`
  - `missing_requirements`
  - `ready_requirements`
  - `oauth_requirements`
- [x] `AccessConsumerBindingReadModel` 增加 slot 维度，避免一个 consumer 只能粗粒度绑定一个 credential。
- [x] `AccessCredentialRequirementReadModel` 增加 `slot`、`expected_kind`、`binding_id`、`setup_flow_hint`、`last_checked_at`。
- [x] Access readiness 检查支持 credential kind mismatch。
- [x] Access overview counts 增加：
  - total requirements
  - missing bindings
  - incompatible bindings
  - OAuth setup needed
  - expired OAuth accounts
- [x] `/ui/access` 输出 requirement rows，不返回 secret 原值。
- [x] `/ui/settings/access-assets` 只展示治理配置；runtime readiness 从 Access read model 合并。
- [x] 新增 access action：bind credential requirement。
- [x] 新增 access action：unbind credential requirement。
- [x] 新增 access action：verify credential requirement。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_access_http.py tests/unit/test_access_actions.py tests/unit/test_access_requirement_catalog.py
curl -fsS http://127.0.0.1:8000/ui/access | jq '.credential_requirements, .counts'
```

## P4. OAuth 官方授权 Flow

- [x] Access domain 增加 OAuth provider config：
  - provider id
  - authorization URL
  - token URL
  - revocation URL
  - scopes
  - client credential binding
  - callback mode
  - device-code support
- [x] Access domain 增加 OAuth account resource：
  - account id
  - provider
  - granted scopes
  - expiry
  - refresh readiness
  - revoked/disabled status
- [x] Access setup session 支持 browser OAuth。
- [ ] Access setup session 支持 device code。
- [x] Access token refresh 通过 Access runtime service 完成，业务模块只拿 runtime credential。
- [ ] OAuth scope diff 可见：declared scopes vs granted scopes。
- [x] OAuth account disable / revoke 产生 Access audit；rotate 仍待补。
- [x] Access UI 可登记 OAuth account binding；完整 provider setup/status 操作面仍待补。
- [x] Tool/Channel requirement 可以绑定 OAuth account，而不是直接绑定 token 文件。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py
```

## P5. 前端页面调整

- [x] Access Operations 面板增加 `Requirements` tab：
  - Consumer
  - Module
  - Slot
  - Expected Kind
  - Binding
  - Readiness
  - Setup
  - Last Checked
- [x] Access Settings 页面增加 `Bindings by Requirement` 主表。
- [x] Tool Settings 页面 provider/detail 中展示 credential slots 和绑定选择。
- [x] Channel Settings 页面 account/detail 中展示 credential slots 和绑定选择。
- [x] 绑定选择器按 expected kind 过滤：
  - API key 不显示 Codex JSON。
  - OAuth account 不显示 env/file API key。
  - webhook secret 不显示普通 OAuth account。
- [x] 兼容但不推荐的 binding 用 warning 显示，不允许保存明显不兼容绑定。
- [x] setup flow 未接通时显示“需要 Access setup provider”，不能显示假成功。
- [x] 所有 secret/source ref 只显示 masked preview，不显示 env/file 具体敏感路径之外的原值。
- [x] 页面空态区分“无 credential requirement”和“requirement 未上报”。

验收：

```bash
cd frontend && npm run typecheck
cd frontend && npm run build
```

## P6. 开发者文档

- [x] 新增 Tool credential requirement developer guide。
- [x] 新增 Channel credential requirement developer guide。
- [x] 更新 `src/crxzipple/modules/tool/README.md`：
  - OpenAPI securitySchemes 写法
  - native tool manifest 写法
  - runtime slot resolve 写法
  - 禁止直接读取 credential source
- [x] 更新 `docs/lark-channel-guide.md`，改成 Access binding / OAuth account 写法。
- [x] 更新 `docs/webhook-channel-guide.md`，说明 webhook secret requirement。
- [x] 更新 `docs/ui/current-ui-design-functional-spec.md`：
  - Access 页面要显示 requirement catalog。
  - Tool/Channel Settings 只绑定 Access credential，不接收 raw secret。
- [x] 在 `docs/agents/hosted-agent-operating-contract.md` 增加约束：
  - 新增 Tool/Channel 时必须声明 credential requirements。
  - 不允许绕过 Access 读取外部凭证。

验收：

```bash
rg -n 'env:|file:|raw secret|os\\.environ|getenv' \
  docs src/crxzipple/modules/tool/README.md \
  | rg -v 'forbidden|禁止|deprecated|migration|archive'
```

## P7. 迁移与清理

- [x] 迁移 `config/tool_providers` / 内置 OpenAPI tool manifests 中的 direct source credential 到 Access credential binding id。
- [x] 迁移 `config/channel_profiles` 中的 direct source credential 到 Access credential binding id。
- [x] 创建必要的 Access binding seed：
  - OpenAI API key
  - Codex auth JSON
  - Brave Search API key
  - iTick API token
  - Lark app id
  - Lark app secret
  - Lark verification token
  - Lark encrypt key
  - Lark bot open id
  - webhook secret examples
- [x] 删除运行时代码中 direct source 解析分支，migration helper 除外。
- [x] 删除旧文档里鼓励 `env:` / `file:` 的配置示例。
- [ ] 保留历史兼容判断只允许出现在 migration / archive / deprecated note。
- [x] 数据库 migration 补齐 requirement binding 持久化：`access_consumer_bindings.credential_bindings` 保存 slot -> credential binding id；不复用 Authorization policy 表。
- [ ] OAuth account/provider 持久化随 P4 官方授权 Flow 落地，不混入 Authorization policy 表。

验收：

```bash
rg -n 'env:|file:|credential_binding_ref|auth_ref|username_source|password_source|source=' \
  src/crxzipple/modules/tool src/crxzipple/modules/channels config/tool_providers config/channel_profiles \
  | rg -v 'migration|deprecated|archive|test'
```

## P8. 端到端验收

- [ ] 注册一个 API key credential binding 后，OpenAPI tool provider 可选择该 binding 并执行成功。
- [x] 绑定错误 credential kind 时，保存被拒绝或执行前返回明确 mismatch。
- [x] 停用/注销 credential binding 后，Access Operations 显示 degraded/not ready，Tool/Channel 运行返回 access_not_ready。
- [x] Lark channel 缺 app secret 时，Access Requirements tab 显示对应 slot missing。
- [x] OAuth provider 未配置时，OAuth requirement 显示 setup provider missing，不显示假登录。
- [ ] OAuth provider 配置后，可发起 setup session，并在完成后绑定 OAuth account。
- [x] Workbench/Operations 中的错误文案能定位到 Access requirement，而不是裸露底层异常。
- [x] Access audit 能看到 bind/unbind/verify/setup/revoke/disable 记录。

验收命令：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_access_requirement_catalog.py \
  tests/unit/test_access_tool_requirements.py \
  tests/unit/test_access_channel_requirements.py \
  tests/unit/test_access_oauth.py \
  tests/unit/test_tool_openapi.py \
  tests/unit/test_channels.py

cd frontend && npm run typecheck && npm run build
```

## 推荐施工顺序

1. 先做 shared contract 与 architecture guard。
2. 再做 Tool OpenAPI requirement 自动上报，因为现有代码基础最接近。
3. 接 Access requirement catalog / read model，让 Access 面板先可见。
4. 再做 Channel profile slots 和 Lark 文档迁移。
5. 最后做 OAuth setup flow，因为它牵涉 provider config、callback/device-code、token refresh 和审计。
