# Access Governance Redesign Checklist 2026-05-06

本文档记录 2026-05-06 阶段把 Access 从 LLM / Tool / Channel / Agent / env / YAML 等分散真相中剥离出来的重构。2026-05-08 起，Authorization / Access 边界已重新收口：内部 ABAC policy、evaluator、run/session/agent grant 归 `authorization`；外部 provider/account/credential、readiness、setup、租用/停用/注销/审计归 `access`。后续以 `authorization-access-boundary-remediation-checklist-20260508.md` 为准。

> 过时说明：本文中 “Access owns authorization policy / temporary grant / evaluator adapter”
> 是阶段性判断，已经废弃。不要继续按该方向新增代码。

不要继续把 Access 扩展成独立 settings 真相源；后续 access asset、credential binding 声明、consumer binding、authorization policy、permission enable/disable、rotation/export/redaction policy 的配置真相应迁入 `modules/settings`。

## 结论

当前 Access 已有 `check`、`setup`、`inventory` 和基础 credential resolver，但还不是完整访问治理面：

- `AccessApplicationService` 主要解析 `env:`、`file:`、`codex_auth_json` 绑定，没有持久化的 access asset / credential binding / setup session 真相。
- `collect_access_inventory()` 通过扫描 `llm_service`、`tool_service`、`channel_profile_service` 反向发现访问需求，Access 不是需求和资产的 source of truth。
- Authorization policy 由 `authorization` 模块、YAML loader、runtime managed path、repository 分散持有，Access 不能完整治理权限策略。
- 前端/Operations/Settings 能看到 readiness，但没有统一的 access control plane、审计、版本、影响分析、导入导出和安全写入流程。

阶段性目标关系（已完成）：

```text
Access temporarily centralizes access governance truth
shared owns access protocol
modules consume injected effective access
Settings references Access assets, not secret values
Operations observes access runtime/readiness facts
```

新的目标关系：

```text
Settings owns access/authorization configuration truth
Access owns runtime credential resolution, setup, readiness and secret handling
Authorization owns evaluator/runtime decision execution
shared owns effective settings/access protocols
modules consume injected effective settings and access
Operations observes runtime/readiness facts only
```

## 施工原则

- Access 是运行时访问能力模块，不是“检查 env 是否存在”的工具函数集合，也不是长期 settings 真相源。
- 阶段性 Access tables 可以继续服务 runtime/readiness/setup，但可配置访问真相必须向 Settings 迁移：access assets、credential binding 声明、consumer bindings、authorization policies、permission enable/disable、rotation/export/redaction policy。
- `src/crxzipple/shared/` 放访问协议、决策对象、asset ref、credential binding ref、redaction model、consumer protocol；业务模块依赖 shared 协议，不依赖 Access 内部实现。
- Access 通过 container 注入各模块。LLM / Tool / Channel / Agent / Memory 只能消费 `EffectiveAccessProvider`、`CredentialProvider`、`AuthorizationDecisionProvider` 等窄协议；这些 provider 后续应读取 Settings effective config，再执行 Access runtime resolution。
- 业务模块可以声明“我需要什么访问能力”，但不能成为访问资产、凭据、授权策略或 secret 原值的治理者。
- Authorization 不再作为并列治理真相源。它保留为 evaluator/runtime decision engine；policy source of truth 归 Settings。
- 所有 secret material capture 必须走 Access setup/secret-store flow；配置声明和启停动作走 Settings action；HTTP/UI 只返回 binding、状态、来源、校验和 masked preview，不返回原值。
- 不做长期兼容 shim。现有 env/YAML/config 和阶段性 Access governance tables 只能作为迁移输入、bootstrap import 或 runtime 状态来源。

## P0. 边界、协议与迁移设计

### A0.1 定义 Access 治理真相

状态：已处理（已新增 shared/domain 资源治理模型；业务模块切换仍按 P3 推进）。

目标：

- 新增 Access resource registry，至少覆盖：
  - `credential_binding`
  - `secret_asset`
  - `connection_asset`
  - `oauth_provider`
  - `oauth_account`
  - `authorization_policy`
  - `temporary_grant`
  - `setup_session`
  - `access_requirement`
  - `consumer_binding`
- 每个 resource 至少声明：
  - `resource_id`
  - `resource_kind`
  - `governance_scope`
  - `secret_policy`
  - `storage_key`
  - `consumer_modules`
  - `readiness_policy`
  - `authorization_policy`
  - `rotation_policy`
  - `audit_required`
  - `export_policy`
  - `degraded_reason`

建议位置：

- `src/crxzipple/modules/access/domain/resources.py`
- `src/crxzipple/modules/access/application/registry.py`

验收：

```bash
rg -n 'AccessResource|resource_kind|credential_binding|secret_policy|rotation_policy|consumer_modules' \
  src/crxzipple/modules/access src/crxzipple/shared
```

### A0.2 定义 shared 访问协议

状态：已处理（已新增 `src/crxzipple/shared/access.py` 协议）。

目标：

- 在 `src/crxzipple/shared/` 定义访问消费协议和值对象：
  - `AccessAssetRef`
  - `CredentialBindingRef`
  - `SecretBindingRef`
  - `AccessRequirementRef`
  - `AccessConsumerRef`
  - `AccessReadiness`
  - `AccessDecision`
  - `AuthorizationPolicySpec`
  - `TemporaryGrantSpec`
  - `EffectiveAccessProvider`
  - `CredentialProvider`
  - `AuthorizationDecisionProvider`
- 协议必须表达：
  - asset identity
  - consumer identity
  - required scopes/effects
  - readiness status
  - setup action metadata
  - masked preview
  - decision reason/code/obligations
  - audit/trace context

验收：

```bash
rg -n 'EffectiveAccessProvider|CredentialProvider|AuthorizationDecisionProvider|AccessAssetRef|CredentialBindingRef' \
  src/crxzipple/shared src/crxzipple/modules
```

### A0.3 统一 Access 与 Authorization 边界

状态：已处理（架构文档与 shared 决策协议已更新；Authorization 运行时 policy truth 已由 Access-backed repository 提供，Authorization 仅作为 evaluator/service 执行引擎保留）。

目标：

- 明确 `authorization` 不再是独立治理模块。
- 选择一种落地方式：
  - 推荐：保留 `modules/authorization` 作为 evaluator engine，policy repository 和 temporary grant repository 由 Access 拥有并注入。
  - 后续可选：将 authorization evaluator/domain 合并到 `modules/access/authorization/*`，删除并列模块。
- Access 拥有 policy source of truth、policy import/export、policy action、policy audit。
- Authorization evaluator 只负责纯决策，不扫描 YAML、不持久化、不暴露治理 HTTP。

验收：

```bash
rg -n 'authorization_policy|TemporaryAuthorizationGrant|AuthorizationPolicyRepository' \
  src/crxzipple/modules/access src/crxzipple/modules/authorization src/crxzipple/shared
```

### A0.4 设计 Access 持久化模型

状态：已处理（已新增 ORM、repository、audit repository 和 Alembic `0042`）。

目标：

- 新增持久化表/仓储：
  - `access_assets`
  - `access_credential_bindings`
  - `access_secret_bindings`
  - `access_connection_profiles`
  - `access_authorization_policies`
  - `access_setup_sessions`
  - `access_temporary_grants`
  - `access_readiness_snapshots`
  - `access_action_audits`
- secret 原值不能明文入库。第一阶段可只保存 binding 和 source；后续接本地 keychain/vault。
- 所有 sensitive 字段必须有 redaction policy。

验收：

```bash
rg -n 'access_assets|access_credential_bindings|access_authorization_policies|access_action_audits' \
  src/crxzipple alembic tests
```

### A0.5 迁移输入清单

状态：已处理（已新增纯 application 迁移输入扫描/导入器；旧 env/YAML/config/requirement 声明只作为 Access bootstrap import 输入，业务模块消费方已按 P3 切到注入的 Access/shared provider）。

目标：

- 把现有散落配置作为迁移输入，而不是长期真相：
  - `container.settings.llm_profiles[*].credential_binding`
  - tool `access_requirement_sets`
  - channel profile account/webhook/token/signing secret requirements
  - `CRXZIPPLE_READY_AUTH_REQUIREMENTS`
  - `authorization_policy_paths`
  - `authorization_runtime_policy_path`
  - env/file/codex auth json bindings
- 迁移必须生成 Access resources 和 consumer bindings。
- 迁移后业务模块从 Access provider 读取，不再自行解析这些字段。

验收：

```bash
rg -n 'AccessMigration|authorization_policy_paths|CRXZIPPLE_READY_AUTH_REQUIREMENTS|llm_profiles.*credential_binding' \
  src/crxzipple tests
PYTHONPATH=src pytest -q tests/unit/test_access_migration.py
```

## P1. Access Query / Control API

### A1.1 新增 Access control-plane read model

状态：已处理（已新增 control-plane read model；HTTP control surface 仍按 A1.2 推进）。

目标：

- 新增后端 read model：
  - `AccessOverviewReadModel`
  - `AccessAssetListReadModel`
  - `AccessAssetDetailReadModel`
  - `CredentialBindingReadModel`
  - `AuthorizationPolicyReadModel`
  - `AccessConsumerBindingReadModel`
  - `AccessReadinessReadModel`
  - `AccessSetupSessionReadModel`
  - `AccessAuditReadModel`
- read model 只能返回 masked / redacted 数据。

验收：

```bash
rg -n 'AccessOverviewReadModel|AccessAssetDetail|CredentialBindingReadModel|AccessAuditReadModel' \
  src/crxzipple/modules/access src/crxzipple/interfaces/http
```

### A1.2 新增 `/ui/access*` 或 `/ui/settings/access-assets` 的真实治理模型

状态：已处理（`/ui/access*` control-plane HTTP 读面已接入路由；`/ui/settings/access-assets` 已作为同一 Access read model 的 Settings 别名；Settings 前端不再使用静态资产/消费者/使用样例）。

目标：

- 至少提供：
  - `GET /ui/access`
  - `GET /ui/access/assets`
  - `GET /ui/access/assets/{asset_id}`
  - `GET /ui/access/policies`
  - `GET /ui/access/consumers`
  - `GET /ui/access/audits`
- Settings 的 `/ui/settings/access-assets` 读取 Access read model，不自己扫模块。
- Operations 的 Access 页面读取 readiness/runtime 摘要，不成为配置治理入口。

验收：

```bash
curl -fsS http://127.0.0.1:8000/ui/access | jq .
curl -fsS http://127.0.0.1:8000/ui/settings/access-assets | jq '.summary'
```

### A1.3 替换 inventory 反向扫描

状态：已处理（inventory 聚合只从 Access governance repository/read model 与 consumer bindings 生成；旧 `collect_access_inventory(container, ...)` 入口保留为 HTTP/CLI 兼容入口，但不再反向扫描 LLM / Tool / Channel 私有服务）。

当前问题：

- `src/crxzipple/modules/access/interfaces/inventory.py` 直接扫描 LLM / Tool / Channel。

目标：

- inventory 从 Access resource registry 和 consumer bindings 生成。
- LLM / Tool / Channel 等模块启动或配置变更时，只注册/消费 Access consumer binding。
- `include_disabled` 由 Access 记录的 consumer state 决定，不调用模块私有服务。

验收：

```bash
rg -n 'container\\.(llm_service|tool_service|channel_profile_service)' src/crxzipple/modules/access/interfaces/inventory.py || true
PYTHONPATH=src pytest -q tests/unit/test_access_inventory.py
```

## P2. 写操作、权限与审计

### A2.1 Access action 契约

状态：已处理（已新增 `AccessActionRequest` / `AccessActionResult`、应用服务骨架和 `POST /access/actions`）。

目标：

- 新增统一 Access action 入口：
  - `POST /access/actions`
  - 或纳入统一 console action dispatcher，但 action owner 是 Access。
- action payload 至少包含：
  - `action_id`
  - `resource_kind`
  - `target_id`
  - `intent`
  - `changes`
  - `reason`
  - `confirmation`
  - `risk_acknowledged`
  - `actor`
  - `trace_context`
- action response 至少包含：
  - `status`
  - `asset`
  - `audit_ref`
  - `validation`
  - `readiness`
  - `warnings`

验收：

```bash
rg -n 'AccessAction|risk_acknowledged|audit_ref|trace_context' src/crxzipple/modules/access tests
PYTHONPATH=src pytest -q tests/unit/test_access_actions.py
```

### A2.2 Credential / secret setup flow

状态：已处理（Access action 已支持 register env/file/codex binding 与 begin setup session；setup session/action audit 记录 actor/resource/action/reason/before/after/permission_decision/result；raw secret input 在审计前拒绝，旧 `/access/setup` 仅保留为只读提示型 readiness 辅助入口）。

目标：

- `begin_setup()` 不再只返回“请设置 env/file”的提示。
- Access 创建真实 setup session：
  - target asset
  - expected binding kind
  - secret capture policy
  - expiry
  - actor
  - validation state
  - audit ref
- 支持第一阶段安全动作：
  - register env binding
  - register file binding
  - register codex auth json binding
  - verify binding readiness
  - rotate binding metadata
- 不接收或回显 secret 原值，除非后续明确引入受保护 secret store。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_access_actions.py
rg -n 'secret_value|api_key|token' src/crxzipple/modules/access | rg -v 'masked|redact|binding|metadata' || true
```

### A2.3 Authorization policy 写入归 Access

状态：已处理（`POST /access/actions` 已支持 create/update/enable/disable/delete policy、YAML import、bundle export、dry-run decision 与 impact preview；运行时 policy truth 已切到 Access-backed repository，YAML 只作为 import/export 格式）。

目标：

- Access action 支持：
  - create/update/enable/disable/delete policy
  - import YAML policy
  - export policy bundle
  - dry-run policy decision
  - impact preview
- `authorization/interfaces/http.py` 的治理写入口退役；保留 check only 或迁到 Access。
- `YamlAuthorizationPolicyLoader` 只作为 import helper。

验收：

```bash
rg -n '@router\\.(post|put|patch|delete).*polic' src/crxzipple/modules/authorization src/crxzipple/modules/access
PYTHONPATH=src pytest -q tests/unit/test_authorization.py tests/unit/test_access_policies.py
```

### A2.4 Access 审计

状态：已处理（Access action/setup session 与 authorization policy 写动作均记录 actor/resource/action/reason/before_redacted/after_redacted/permission_decision/result；审计 request/result 统一脱敏，raw secret input 在审计前拒绝）。

目标：

- 所有 Access 写操作必须记录：
  - actor
  - resource_kind
  - target_id
  - action
  - reason
  - before/after redacted diff
  - permission decision
  - setup session id
  - trace/request id
  - result
- 审计不能记录 secret 原值。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_access_actions.py tests/unit/test_access_persistence.py
rg -n 'access_action_audits|before_redacted|after_redacted|permission_decision' src/crxzipple tests
```

## P3. 模块消费方切换

### A3.1 LLM 切换为 Access credential consumer

状态：已处理（`LlmApplicationService` 注入 shared `CredentialProvider`，adapter request 携带调用前解析出的 `resolved_credential`；`llm/infrastructure/adapters/common.py` 已退役私有 `CredentialResolver` / Codex auth json fallback，直接 adapter 单测改为显式传 resolved credential；HTTP/DTO 输出只显示 public binding label）。

目标：

- LLM profile 中只保留 `CredentialBindingRef` 或由 Settings profile 引用 Access asset。
- LLM adapter 调用前通过注入的 `CredentialProvider` 获取 credential。
- LLM 模块不解析 env/file/codex auth json。

落地说明：

- LLM adapter 不再私自解析 env/file/codex auth json；调用前由 `LlmApplicationService` 经注入的 Access/shared credential provider 解析。
- `LlmAdapterRequest.resolved_credential` 是 adapter 获取凭据的唯一入口；无凭据 profile 必须显式表达。
- `tests/unit/test_access_llm_integration.py` 覆盖 env/file/codex binding 经 Access provider 注入 LLM adapter，HTTP/DTO/read model 不回显 secret。

验收：

```bash
rg -n 'os\\.environ|getenv|read_text\\(|credential_binding' src/crxzipple/modules/llm
PYTHONPATH=src pytest -q tests/unit/test_llm.py tests/unit/test_access_llm_integration.py
```

### A3.2 Tool 切换为 Access requirement consumer

状态：已处理（OpenAPI remote runtime 已改为注入 shared `CredentialProvider`；Tool package/OpenAPI provider 构建链路已接 `access_service`；OpenAPI query credential 在 run metadata 中脱敏；Tool catalog `access_requirement_sets` 只作为 Access migration/import 的 consumer declaration 输入，readiness/binding 由 Access consumer bindings/read model 生成）。

目标：

- Tool catalog 声明 requirements/effects，但 Access 持有 requirement readiness 和 credential mapping。
- Tool run 前使用 Access decision/readiness provider。
- Authorization effect/tool decision 由 Access 统一入口提供。

落地说明：

- OpenAPI remote runtime 通过注入的 Access credential provider 获取 OpenAPI credential。
- `tool.access_requirement_sets` 不再是 Tool readiness/binding 真相，只作为 Access migration/import 的 consumer declaration。
- Orchestration approval/temporary grants 已写入 Access temporary grants；Authorization 保留 evaluator，policy/grant truth 由 Access-backed repository 提供。

验收：

```bash
rg -n 'check_tool_execution|check_requirement|access_requirement_sets' src/crxzipple/modules/tool src/crxzipple/modules/orchestration
PYTHONPATH=src pytest -q tests/unit/test_tool_background.py tests/unit/test_access_tool_integration.py
```

### A3.3 Channel 切换为 Access connection consumer

状态：已处理（Channel binding resolver 已移除模块内 `CredentialResolver` 单例，Lark/Webhook runtime 和 HTTP entrypoints 通过注入的 Access credential provider 解析 token/signing secret/open id；runtime binding metadata 只暴露 binding/ref/masked preview）。

目标：

- Channel profile 不持有 secret 原值。
- Webhook signing secret、Lark token、account credential 等全部引用 Access asset/binding。
- Channel runtime 启动时从 Access provider 取 effective connection credential。

落地说明：

- Channel binding resolver 消费注入的 Access credential provider，不再持有模块内 `CredentialResolver` 单例。
- Lark/Webhook runtime 与 HTTP entrypoints 通过 Access provider 解析 token/signing secret/open id。
- Channel runtime binding metadata 只返回 binding/ref/masked preview，不返回 secret 原值。

验收：

```bash
rg -n 'signing_secret|token|credential|password' src/crxzipple/modules/channels | rg -v 'binding|redact|masked' || true
PYTHONPATH=src pytest -q tests/unit/test_channels.py tests/unit/test_access_channels_integration.py
```

### A3.4 Agent / Orchestration 切换为 Access decision consumer

状态：已处理（approval 的 run/session temporary grants 已写入 `access_temporary_grants`，Authorization evaluator 通过 Access-backed temporary grant repository 读取；`ALWAYS_FOR_AGENT` 写入 Access-owned authorization policy；orchestration approval port 不再向调用方暴露 `TemporaryAuthorizationGrant` / `AuthorizationPolicy` 返回类型）。

目标：

- Orchestration approval 和 temporary grants 归 Access governance。
- Agent profile 可以作为 subject dimension，但不持有权限真相。
- Run/session grant 写入 Access temporary grant store。

落地说明：

- Orchestration approval port 不再向调用方暴露 `TemporaryAuthorizationGrant` / `AuthorizationPolicy` 返回类型。
- Run/session temporary grants 写入 Access temporary grant repository，再由 authorization evaluator 读取 effective grants。
- `container._build_authorization_service()` 已改为 Access-backed policy/grant repositories；YAML/runtime policy path 仅作为 bootstrap import 输入。

验收：

```bash
rg -n 'TemporaryAuthorizationGrant|grant_run_access|grant_session_access' \
  src/crxzipple/modules/orchestration src/crxzipple/modules/authorization src/crxzipple/modules/access
PYTHONPATH=src pytest -q tests/unit/test_orchestration_approval.py tests/unit/test_access_grants.py
```

## P4. UI / Operations / Settings 对齐

### A4.1 Settings Access Assets 页面

状态：已处理（阶段性：`/settings/access-assets` 已读取 `/ui/access` control-plane 数据；静态资产、静态消费者/使用样例和假写动作已移除；凭据预览只显示 `masked_preview` 或 server-side-only 文案，`storage_key` 不回显原值。下一阶段按 Settings 统一配置治理口径迁入 Settings-owned access config resources）。

目标：

- `/settings/access-assets` 当前展示阶段性 Access read model，下一阶段展示 Settings-owned access config truth 并合并 Access runtime readiness：
  - assets
  - bindings
  - consumers
  - policies
  - readiness
  - setup sessions
  - audits
- 不再展示由前端静态编造的 asset/consumer/usage。
- 不显示 secret 原值。

验收：

```bash
rg -n 'const (assets|consumerRows|usageRows) = \\[' frontend/src/pages/settings/modules/AccessAssetsSettingsPage.vue || true
cd frontend && npm run typecheck
```

### A4.2 Operations Access 页面

状态：已处理（Operations Access 页面只保留 readiness/runtime 观察、刷新和跳转 Settings/Trace；已移除 check/setup/inventory 执行动作、prompt 和治理写入口；raw drawer 对 Access payload 做递归脱敏）。

目标：

- Operations 只展示运行健康和 readiness 摘要：
  - blocked assets
  - expired sessions
  - failed setup
  - policy denial rate
  - recent access events
- 治理动作跳转 Settings/Access control surface，不在 Operations 里编辑策略。

验收：

```bash
curl -fsS http://127.0.0.1:8000/operations/access | jq '.summary'
```

### A4.3 i18n 与脱敏扫描

状态：已处理（Access 固定文案已补入 `frontend/src/shared/i18n/messages/{zh-CN,en-US}.ts`；前端构建/typecheck 通过；Settings/Operations Access 页的 secret/source_ref/storage_key 展示路径已做静态扫描）。

目标：

- Access UI 文案进 `frontend/src/shared/i18n/messages/{zh-CN,en-US}.ts`。
- 后端返回稳定 enum/status id，前端映射文案。
- 全仓 secret 泄露扫描。

验收：

```bash
rg -n 'access\\.[a-zA-Z0-9_.-]+' frontend/src/pages frontend/src/shared/i18n
rg -n '(sk-[A-Za-z0-9]|api_key=.*[A-Za-z0-9]{8}|token=.*[A-Za-z0-9]{8}|secret=.*[A-Za-z0-9]{8})' \
  src frontend docs | rg -v 'masked|redact|example|placeholder|binding' || true
cd frontend && npm run typecheck
```

## P5. 退役旧真相源

### A5.1 退役 authorization YAML/runtime policy 真相

状态：已处理（`AuthorizationApplicationService` 现在使用 Access-backed policy repository；YAML/runtime policy path 只作为 bootstrap import 输入，运行时 list/check/upsert 读取或写入 `access_authorization_policies`，旧 in-memory runtime YAML 写盘已退役）。

目标：

- YAML policy 只作为 import/export 格式。
- `authorization_runtime_policy_path` 不再是运行时治理真相。
- Access DB/repository 是 policy source of truth。

验收：

```bash
rg -n 'authorization_policy_paths|authorization_runtime_policy_path|YamlAuthorizationPolicyLoader' src/crxzipple
```

### A5.2 退役模块私有 credential parsing

状态：已处理（LLM adapter common、Tool OpenAPI remote runtime、Channel binding/runtime 均已退役私有 `CredentialResolver` / codex auth json helper；业务模块通过注入的 Access/shared credential provider 获取 resolved credential。剩余 `env:` / `file:` / `codex_auth_json` 字符串只作为 binding declaration、测试输入或 Access migration/readiness 语义出现）。

目标：

- 业务模块不直接读取 credential source。
- `CredentialResolver` 保留在 Access 内部。
- env/file/codex auth json 只由 Access 解析。

验收：

```bash
rg -n 'env:|file:|codex_auth_json|CredentialResolver|resolve_credential' src/crxzipple/modules \
  | rg -v 'modules/access|tests' || true
```

### A5.3 更新当前架构文档

状态：已处理（文档边界已更新；代码迁移仍按 A0-A5 推进）。

目标：

- 更新 `docs/instruction-assets-memory-auth-design.md`：
  - Access owns governance truth。
  - Authorization is evaluator/decision protocol, not separate governance owner。
  - Modules declare requirements but consume Access effective decisions/bindings。
  - Settings references Access assets/bindings, not secret values。
- 旧的“authorization owns long-term rules”表述需要替换。
- 新增轻量文档约束测试，防止旧口径继续作为当前约束出现：
  - `authorization belongs to ABAC`
  - `Authorization policy` 作为并列治理真相源
  - `ABAC` 作为唯一最终权限决策点
  - Settings 保存或展示 secret 原值

验收：

```bash
rg -n 'authorization owns|authorization belongs|Access owns|EffectiveAccessProvider' docs/instruction-assets-memory-auth-design.md
PYTHONPATH=src pytest -q tests/unit/test_access_architecture_docs.py
```

## 建议落地顺序

1. A0.1-A0.3：先定 Access 真相、shared 协议、Access/Authorization 边界。
2. A0.4：建 Access 持久化和审计表。
3. A0.5：写迁移输入扫描和导入器。
4. A1.1-A1.3：读侧先从 Access 真相生成，不再反扫业务模块。
5. A2.1-A2.4：打开 Access actions、setup session、policy 写入和审计。
6. A3.1-A3.4：按 LLM、Tool、Channel、Agent/Orchestration 顺序切换消费方。
7. A4.1-A4.3：Settings/Operations/UI 对齐和脱敏扫描。
8. A5.1-A5.3：退役旧真相源并更新架构文档。

## 最小验证集

```bash
PYTHONPATH=src pytest -q tests/unit/test_access.py tests/unit/test_authorization.py
PYTHONPATH=src pytest -q tests/unit/test_access_inventory.py tests/unit/test_access_policies.py
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py tests/unit/test_operations_observation.py
cd frontend && npm run typecheck
cd frontend && npm run build
```

## 完成定义

- 阶段性 Access 已集中访问资产、credential bindings、connection profiles、authorization policies、setup sessions、temporary grants 和 access audit，消除了业务模块分散真相；下一阶段配置真相迁入 Settings。
- shared 提供访问协议，业务模块只消费注入 provider。
- LLM / Tool / Channel / Agent / Orchestration 不再直接解析 env/file/codex credential 或持有权限策略真相。
- Settings 统一管理 access/authorization 可配置真相，但不保存 secret 原值。
- Operations 只观察 access readiness/runtime，不编辑治理配置。
- `/access/check`、`/access/setup`、`/access/inventory` 均由 Access 真相生成。
- Authorization policy 不再由 YAML/runtime path 或 Access 独立表作为长期配置真相，目标迁入 Settings。
- 所有 secret/token/API key 不出现在 HTTP response、日志、审计 diff、前端静态数据或文档示例中。
