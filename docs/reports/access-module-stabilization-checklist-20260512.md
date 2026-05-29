# Access Module Stabilization Checklist 2026-05-12

本文档作为 Access 模块稳定化主清单，覆盖 LLM、Tool、Channel、Settings、
Operations 的外部访问治理收口。它接续并收拢：

- `docs/archive/reports/access-governance-redesign-checklist-20260506.md`
- `docs/reports/authorization-access-boundary-remediation-checklist-20260508.md`
- `docs/archive/reports/tool-channel-access-credential-requirements-checklist-20260511.md`

其中 Access governance 和 Tool/Channel credential requirements 两份过渡清单已归档到
`docs/archive/reports/`；当前施工只以本文和 agent contract 为准。

## 冻结口径

- Access 是外部访问治理模块：OAuth account、API key、app credential、bot token、
  webhook secret、QR/session asset、credential binding、readiness、setup、lease、audit。
- Authorization 是内部 ABAC/approval 模块：subject/resource/action/effect/policy/grant。
- Settings 是业务配置治理入口：只保存 owner module 的业务配置，以及指向 Access 的 binding id。
- LLM/Tool/Channel/Agent 只能声明 requirement 或保存 binding id，运行时通过 Access port 解析。
- 业务模块不得直接读取 raw secret、`env:`、`file:`、`codex_auth_json` 或本地 auth 文件。
- 长期兼容路径不保留；旧配置只允许出现在 migration、archive、deprecated note、测试 fixture。

## 当前事实

- LLM profile 已使用 `credential_binding_id`，OpenAI API key 与 Codex OAuth 均有配置示例。
- Tool / Channel 已有 credential requirement contract、slot binding、Access read model 和 UI 投影。
- Access 已有 assets、credential bindings、consumer bindings、setup sessions、OAuth providers/accounts、
  action audit 的 persistence/read model。
- Codex OAuth 已有本地 browser callback 闭环；飞书/企业微信应归为 app credential binding，
  不是 OAuth login。
- Access UI 仍存在 Codex 特例、generic OAuth/provider setup 不完整、CRUD 表单空间和动作闭环待收。
- `env:` / `file:` 仍作为 Access 自身的 credential source 类型存在，业务侧必须只持有 binding id。

## 2026-05-12 施工记录

- 已组织 Worker A/B/C 并行施工：
  - Worker A 收 Access backend/OAuth/action/readiness。
  - Worker B 收 LLM/Tool/Channel direct credential source guard。
  - Worker C 收 Access Settings/Operations UI。
- 已补 Access readiness/runtime resolve 的 `credential_kind_mismatch` 与
  `credential_source_kind_mismatch`，OAuth source 只能服务 OAuth/OIDC binding kind。
- 已补 `register_app_credential_binding` 后端 action，与前端 app credential binding modal 对齐。
- 已补 Generic browser OAuth setup session、scope diff payload、device-code 结构化入口。
- 已补 Access action raw secret 拒收覆盖 nested payload、setup/OAuth metadata 和 trace context。
- 已补 LLM/Tool/Channel guard：业务 profile/config 拒绝 `env:`、`file:`、`codex_auth_json`、
  `auth_ref` 作为 credential binding id。
- 已调整 Access Assets UI：主表筛选、binding modal、provider-specific OAuth action、Operations
  audit detail；Codex 登录不再在任意 Access asset 上触发。
- 已更新 active docs：`docs/README.md`、`docs/agents/hosted-agent-operating-contract.md`、
  `docs/instruction-assets-memory-auth-design.md`。
- 已完成本轮集成验收：
  - `git diff --check` 通过。
  - `PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py tests/unit/test_access_actions.py tests/unit/test_access_http.py tests/unit/test_access_read_models.py tests/unit/test_access.py` 通过，51 passed。
  - `PYTHONPATH=src pytest -q tests/unit/test_llm.py tests/unit/test_llm_http.py tests/unit/test_llm_settings_integration.py tests/unit/test_access_llm_integration.py tests/unit/test_orchestration_llm_resolver.py` 通过，31 passed。
  - `PYTHONPATH=src pytest -q tests/unit/test_access_tool_integration.py tests/unit/test_tool_access_architecture.py tests/unit/test_tool_settings_integration.py tests/unit/test_openapi_access.py tests/unit/test_openai_image_tool.py` 通过，26 passed。
  - `PYTHONPATH=src pytest -q tests/unit/test_access_channel_requirements.py tests/unit/test_channel_access_architecture.py tests/unit/test_channel_bindings.py tests/unit/test_channels.py tests/unit/test_channels_http.py` 通过，86 passed。
  - `PYTHONPATH=src pytest -q tests/unit/test_access_architecture_docs.py tests/unit/test_authorization_access_boundary.py` 通过，6 passed。
  - `cd frontend && npm run typecheck` 通过。
  - `cd frontend && npm run build` 通过。

## 2026-05-21 P0 边界收口记录

- 已加严 `tests/unit/test_authorization_access_boundary.py`：
  - Access 不得 import `modules.authorization` 或内部 ABAC runtime 类型。
  - Authorization 不得 import Access credential/readiness/binding 类型。
  - LLM/Tool/Channel runtime 不得通过 `os.environ[...]`、`os.environ.get(...)`、
    `os.getenv(...)` 或 `getenv(...)` 读取业务凭证。
  - `config/llm_profiles` 不得包含 `env:`、`file:`、`codex_auth_json`、`auth_ref`
    direct credential source。
- 已清理 active docs 中 “Access owns authorization policy/grant” 的旧口径：
  `docs/instruction-assets-memory-auth-design.md` 与 `docs/orchestration-design.md`
  均改为 Access 管外部访问事实、Authorization 管内部 ABAC policy/grant。
- 验证通过：
  - `PYTHONPATH=src pytest -q tests/unit/test_authorization_access_boundary.py tests/unit/test_channel_access_architecture.py tests/unit/test_tool_access_architecture.py tests/unit/test_llm_settings_integration.py -q`
  - `PYTHONPATH=src ruff check tests/unit/test_authorization_access_boundary.py tests/unit/test_channel_access_architecture.py tests/unit/test_tool_access_architecture.py`

## 2026-05-21 P1 模型/API 收口记录

- 已移除 `credential_file` 作为 credential binding kind 的旧尾巴。文件路径现在只表达为
  `source_kind=file`，凭证类型仍使用 `api_key`、`bearer_token`、`basic`、
  `oauth2_account`、`openid_connect`、`app_secret`、`webhook_secret`、`certificate`。
- 已补 `AccessCredentialKind` 合约测试，防止 `codex_auth_json`、`credential_file`
  等旧 kind 回流。
- 已同步 LLM/Channel/Access Settings 前端兼容判断，不再把 `credential_file` 当成可选 kind。
- 已补 `AccessResolvedCredential`：`resolve_credential()` 返回 `str` 子类，调用方仍可按
  普通 secret 字符串使用，同时携带不含 secret value 的 `audit_context`，包含 binding、
  source metadata、consumer 和脱敏 trace context。
- 已把 Operations Access 的 credential requirements / audit summary 收进
  `/operations/access` read model；前端不再从 Operations 页面绕到
  `/ui/access/credential-requirements` 或 `/ui/access/audits`。
- 已移除 Settings Access 独立 audit/credential-requirements UI route；`/ui/access`
  保留管理页需要的配置总览，审计展示回到 Operations。
- 验证通过：
  - `PYTHONPATH=src pytest -q tests/unit/test_access.py tests/unit/test_access_actions.py tests/unit/test_access_http.py tests/unit/test_access_read_models.py tests/unit/test_access_persistence.py tests/unit/test_access_governance_contracts.py -q`
  - `PYTHONPATH=src pytest -q tests/unit/test_access.py tests/unit/test_access_oauth.py tests/unit/test_access_llm_integration.py tests/unit/test_llm.py tests/unit/test_channel_bindings.py tests/unit/test_openapi_access.py tests/unit/test_openai_image_tool.py -q`
  - `PYTHONPATH=src pytest -q tests/unit/test_access.py tests/unit/test_access_actions.py tests/unit/test_access_http.py tests/unit/test_access_read_models.py tests/unit/test_access_persistence.py tests/unit/test_access_governance_contracts.py tests/unit/test_ui_access_http.py tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_operations_access_page_uses_access_inventory_state -q`
  - `cd frontend && npm run typecheck`
  - `cd frontend && npm run build`

## P0. 边界守卫

- [x] 新增或加严 architecture guard：`modules/access` 不 import `modules.authorization`。
- [x] 新增或加严 architecture guard：`modules/authorization` 不 import Access credential/readiness。
- [x] 新增或加严 architecture guard：LLM/Tool/Channel runtime 不直接调用 `os.environ` 获取业务凭证。
- [x] 新增或加严 architecture guard：业务 profile/config 不接受 `env:` / `file:` /
  `codex_auth_json` 作为 credential binding id。
- [x] 保留 `env:` / `file:` 仅限 Access credential binding source、migration、tests。
- [x] 清理文档中“Access 管内部授权”的旧口径，只留下边界说明或 archive。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_authorization_access_boundary.py
rg -n 'modules.authorization|AuthorizationPolicy|AbacAuthorizationEvaluator' src/crxzipple/modules/access
rg -n 'os\\.environ|getenv|read_text\\(.*credential|codex_auth_json|auth_ref' \
  src/crxzipple/modules/llm src/crxzipple/modules/tool src/crxzipple/modules/channels \
  | rg -v 'migration|deprecated|test|forbidden|reject'
```

## P1. Access 模型与 API 收口

- [x] `AccessCredentialKind` 不再包含 `codex_auth_json`，旧值只允许 migration 识别。
- [x] `AccessCredentialBindingRecord` 明确支持 `api_key`、`bearer_token`、`basic`、
  `oauth2_account`、`openid_connect`、`app_secret`、`webhook_secret`、`certificate`。
- [x] 增加 credential kind compatibility check：requirement expected kind 与 binding kind 不一致时
  readiness 返回 `credential_kind_mismatch`，运行时拒绝解析。
- [x] 增加 source kind compatibility check：`oauth_account` source 只能服务 OAuth/OIDC binding kind。
- [x] Access resolve 返回审计上下文，但不记录 secret value。
- [x] `describe_credential_binding` 不泄露 `source_ref` 明文，只返回 masked/source metadata。
- [x] Access action 的 raw secret 拒收规则覆盖 nested payload、trace context、metadata。
- [x] 删除未使用或不请求的 Access UI/API 查询，避免加载慢和假面板。

验收：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_access.py \
  tests/unit/test_access_actions.py \
  tests/unit/test_access_http.py \
  tests/unit/test_access_read_models.py \
  tests/unit/test_access_persistence.py
```

## P2. OAuth / Setup Flow 完整化

2026-05-21 收口：OAuth setup flow 统一由 Access action 发起和审计；
browser/device-code completion 都落 OAuth account + credential binding，session read model
只暴露状态和脱敏 metadata。

- [x] Codex OAuth 保持 Access-owned：浏览器打开、local callback、manual code fallback、
  token store、OAuth account、credential binding 一次闭环。
- [x] Generic browser OAuth 支持从 provider config 发起 setup session，完成后写 OAuth account
  和 credential binding。
- [x] Device code flow 作为 Access setup session 的正式 flow kind。
- [x] OAuth scope diff 可见：declared/requested/granted/missing scopes。
- [x] OAuth account `disable` / `revoke` / `refresh` / `rotate` 动作统一走 Access action/audit。
- [x] OAuth setup session 在 UI 上展示 `waiting_for_user`、`completed`、`failed`、`expired`。
- [x] Token store 只保存到 Access runtime state；DB 只存 metadata/storage key/masked preview。
- [x] 不再导入或借用其他软件的 Codex auth json；相关 migration 只负责清理旧数据。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_access_oauth.py tests/unit/test_access_actions.py
```

## P3. App Credential / Channel Credential

2026-05-21 收口：Channel account 以 `credential_bindings` 声明 app credential slots；
Lark/Webhook/WeCom 均输出 owner credential requirements，Settings Channel 页面可基于
slot/expected kind 选择兼容 Access binding。Webhook profile-level secret 字段被拒收。

- [x] 飞书/Lark 按 app credential binding 建模：`app_id`、`app_secret`、
  `verification_token`、`encrypt_key`、`bot_open_id`。
- [x] 企业微信/WeCom 预留 app credential slots：`corp_id`、`agent_id`、`corp_secret`、
  `token`、`encoding_aes_key`；不误建成用户 OAuth login。
- [x] Webhook secret 只从 Access binding 读取，不允许 profile-level secret fallback。
- [x] Channel profile/account detail 展示 slot、expected kind、binding、readiness、setup 入口。
- [x] Channel runtime 缺凭证时返回 `access_not_ready`，不裸露底层异常。
- [x] Channel developer guide 给出 app credential 与 OAuth account 的差异。

验收：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_access_channel_requirements.py \
  tests/unit/test_channel_access_architecture.py \
  tests/unit/test_channel_bindings.py \
  tests/unit/test_channels.py \
  tests/unit/test_channels_http.py
```

## P4. LLM 接入收口

2026-05-21 收口：LLM profile 只持有 Access `credential_binding_id`；
OpenAI API 只接受 `api_key` binding，OpenAI Codex 只接受 OAuth account binding。
Settings 的 Direct LLM Test 改为 `/llms/test` transient profile probe，可在保存前用当前表单
真实调用后端 adapter，且不写入 profile/invocation 真相。

- [x] LLM profile 只保存 `credential_binding_id`，不保存 env/file/raw token。
- [x] Provider/model profile 的 credential expectation 用 Access kind 表达，OpenAI API key 与
  OpenAI Codex OAuth 不能互相误选。
- [x] LLM settings 页面新增“直接测试”只调用后端测试接口，不做前端假成功。
- [x] LLM adapter 统一通过 Access resolve credential；OAuth refresh 由 Access 完成。
- [x] LLM operations 的 provider access health 使用 Access readiness，不额外扫描本地文件。
- [x] 新增模型流程：创建 profile -> 选择 provider -> 选择兼容 Access binding -> 测试 -> 保存。

验收：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_llm.py \
  tests/unit/test_llm_http.py \
  tests/unit/test_llm_settings_integration.py \
  tests/unit/test_access_llm_integration.py \
  tests/unit/test_orchestration_llm_resolver.py
```

## P5. Tool 接入收口

2026-05-21 收口：Tool source/provider/local manifest 只接受 Access binding ID，
拒绝 `env:`、`file:`、`codex_auth_json`、`auth_ref` 等 direct source；OpenAPI/local/CLI
credential requirement 都走 Access readiness 和 runtime resolve，提交前失败统一为
`access_not_ready`。

- [x] OpenAPI `securitySchemes` 继续自动投影 credential requirements。
- [x] Native/local tool manifest 继续支持 `credential_requirements`。
- [x] Tool provider/detail 只选择 Access binding，不接受 direct source。
- [x] Tool runtime 按 slot resolve credential，kind mismatch / missing / disabled / revoked 都返回结构化
  `access_not_ready`。
- [x] Tool request/trace/audit 不记录 secret value，query/header credential 必须 redacted。
- [x] 工具开发文档明确官方 OAuth/API key/app secret 的写法和 setup handler 边界。

验收：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_access_tool_integration.py \
  tests/unit/test_tool_access_architecture.py \
  tests/unit/test_tool_settings_integration.py \
  tests/unit/test_openapi_access.py \
  tests/unit/test_openai_image_tool.py \
  tests/unit/test_tool_providers.py \
  tests/unit/test_tool_source_service.py \
  tests/unit/test_tool_http.py
```

## P6. Access Settings UI

2026-05-21 收口：Access Assets Settings 改为全屏应用式主表 + 右侧详情；
筛选置于表格顶部，注册/编辑/撤销 credential binding 通过 modal 完成。OAuth 动作按
provider 分流，Codex 只在 OpenAI Codex binding/account 上出现。

- [x] Access Assets 首屏为全屏应用布局：左侧主表沉底，右侧详情同高，注册/编辑使用 modal。
- [x] 顶部表格可筛选：kind、provider、status、readiness、consumer module。
- [x] 右侧详情展示 asset、credential binding、readiness、consumers、可用动作。
- [x] 新建 credential binding modal 按 source kind 切换表单：env、file、oauth account、app credential。
- [x] OAuth 登录按钮按 provider 显示，不再选任何 asset 都触发 Codex login。
- [x] Provider/type 不匹配时 option 有提示且不能保存。
- [x] 删除重复或无操作价值的面板；Audit Logs 移到 Operation，不在 Settings 首屏占位。
- [x] 空态、skeleton、实际数据保持相同布局高度，避免加载前后跳动。

验收：

```bash
cd frontend && npm run typecheck && npm run build
```

## P7. Access Operations / Observation

2026-05-21 收口：Access service/action service 现在把凭证 resolve、credential lease、
setup/action 结果作为 `access.*` 事件发布到 event bus；Operations Access 页面继续侧向读取
event bus / observer 事件并关联 target detail，不在 Settings 内做审计主表。

- [x] Operations Access 面板展示 runtime readiness、lease、setup session、resolve failure、audit summary。
- [x] 外部凭证使用事件进入 event bus：resolve requested/succeeded/failed、lease granted/denied、
  setup started/completed/failed、credential disabled/revoked。
- [x] Access audit detail 在 Operations 右侧面板展开，不在 Settings 内做审计主表。
- [x] Access Operations 不重复 Settings 管理动作，只提供运维动作与跳转。
- [x] read model 只从 event/Access query port 投影，不绕业务模块扫文件。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_access_read_models.py tests/unit/test_ui_access_http.py
cd frontend && npm run typecheck
```

## P8. Migration / Cleanup

2026-05-21 收口：旧 Codex auth json 清理已由 `0048` / `0049` migration 覆盖；
业务配置侧继续拒绝旧 direct credential source。Memory vector provider 也已改为
`vector_credential_binding_id` + Access credential provider，不再通过 LLM adapter 或环境变量
解析外部凭证。Operations Access read model 只接收 `access.*` 事件，不再把内部
`authorization.*` / `auth.*` 事件混入外部访问运维面。

- [x] 旧 `codex_auth_json` asset、setup session、binding 数据通过 migration 清理。
- [x] 旧 `auth_ref`、`credential_binding`、`*_source` 只允许在 migration/deprecated note/test
  或 reject/forbidden guard 中出现。
- [x] Access/Settings/Authorization 命名混淆清理：内部授权一律叫 authorization，外部访问一律叫 access。
- [x] README、hosted agent contract、developer guide 与当前唯一主路径一致。
- [x] 删除过时 checklist 中已完成或已废弃任务，避免 agent 被旧口径带偏。

验收：

```bash
rg -n 'access.*authorization|authorization.*access|codex_auth_json|auth_ref|credential_binding:' \
  docs src config tools frontend/src \
  | rg -v 'archive|migration|deprecated|test|forbidden|reject|202605'
```

补充验证：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_operations_access_page_uses_access_inventory_state \
  tests/unit/test_access_read_models.py \
  tests/unit/test_file_backed_memory.py \
  tests/unit/test_channel_memory_runtime_settings_integration.py \
  tests/unit/test_settings_contracts.py \
  tests/unit/test_logger.py \
  tests/unit/test_access.py \
  tests/unit/test_access_actions.py

PYTHONPATH=src ruff check \
  src/crxzipple/modules/memory/infrastructure/indexing/embeddings.py \
  src/crxzipple/modules/operations/application/read_models/access.py \
  src/crxzipple/modules/access/interfaces/cli.py

cd frontend && npm run typecheck
```

## Agent 施工拆分

- Worker A：Access backend/OAuth/action/readiness。写入范围：
  `src/crxzipple/modules/access/**`、`src/crxzipple/shared/access.py`、
  `alembic/versions/**access**`、`tests/unit/test_access*.py`。
- Worker B：LLM/Tool/Channel runtime contract guards。写入范围：
  `src/crxzipple/modules/llm/**`、`src/crxzipple/modules/tool/**`、
  `src/crxzipple/modules/channels/**`、`config/**`、`tools/**`、
  相关 `tests/unit/test_*access*.py`。
- Worker C：Access Settings/Operations UI。写入范围：
  `frontend/src/pages/settings/modules/AccessAssetsSettingsPage.vue`,
  `frontend/src/pages/settings/ownerApis/accessAssets.ts`,
  `frontend/src/pages/operations/modules/AccessOperationsPage.vue`,
  i18n 与 shared UI 相关文件。
- Worker D：文档、agent 约束、旧 checklist 清理。写入范围：
  `docs/**`、`README.md`、`tests/unit/test_access_architecture_docs.py`。

## 总体验收

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_access*.py \
  tests/unit/test_authorization_access_boundary.py \
  tests/unit/test_llm*.py \
  tests/unit/test_tool*access*.py \
  tests/unit/test_channel*access*.py \
  tests/unit/test_orchestration_llm_resolver.py

cd frontend && npm run typecheck && npm run build
```
