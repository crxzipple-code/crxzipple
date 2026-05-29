# Settings Integration Development Checklist 2026-05-06

> Superseded: 本文档的“当前状态”已经过期。Settings 后台、`/settings` 与
> `/ui/settings`、持久化和模块 materializer 已在 2026-05-07 的施工中落地。
> 后续 Settings UI 接入以
> `docs/reports/settings-ui-backend-alignment-checklist-20260507.md` 为参考；
> Settings 与模块实体 ownership 以
> `docs/reports/settings-module-boundary-complexity-review-20260508.md` 为准。
> 本文中“移除运行时私有 profile 真相”“Settings 必须拥有 Agent/LLM/Channel
> profile 最终真相”等方向不得作为新施工依据。

本文档基于当前前后端代码审阅，作为后续托管 agent 接手 Settings 面板接通工作的任务清单。

## 结论

当前 Settings 面板大部分只有路由、导航、静态 UI 和部分 i18n 接通；Access Assets 目前已经通过 Access control plane 得到阶段性真实 read model，但仍未纳入 Settings 统一配置治理真相。

Settings 不只是 read model。它应该是配置管理控制台，至少包含：

- 配置资源目录、治理边界和配置真相。
- 页面级 query/read model。
- 配置来源和生效值解析。
- validation / dry run / impact preview。
- 受控写操作、权限、确认和审计。
- secret 脱敏、导入导出、备份恢复能力边界。
- 向各模块注入有效配置的 shared 协议。

- 前端入口：`frontend/src/pages/settings/SettingsShell.vue`
- Settings 子页：`frontend/src/pages/settings/modules/*.vue`
- 设计稿：`docs/ui/settings/*.png`
- 目标契约：`docs/ui/runtime-ui-read-model-contracts.md` 的 Settings 章节

代码证据：

- `frontend/src/pages/settings` 下没有 `fetch`、`requestJson`、`onMounted` 或 settings API composable。
- 13 个子页都使用 `const rows = [...]`、`const tools = [...]`、`const profiles = [...]` 等硬编码数据。
- 后端已经有 `/ui/access*` 和 `/ui/settings/access-assets`，但还没有通用 `/ui/settings`、`/ui/settings/{resource}`、`/ui/settings/{resource}/{id}`。
- `/ui/bootstrap` routes 仍需要补 `/ui/settings`、`/ui/settings/{resource}`、`/ui/settings/{resource}/{id}`。
- 后端已有部分模块原始接口，例如 `/agents`、`/llms`、`/tools`、`/skills`、`/events/contracts`、`/access/inventory`，但这些接口不是统一配置治理面，也没有让 Settings 成为配置真相源。

## 施工原则

- Settings 是配置治理模块，不是 Operations 运维面，也不是各模块 UI 入口的拼装层。
- Settings 是统一配置治理模块。Access、Authorization、Agent、LLM、Tool、Channel 等都是配置使用者或运行时执行者，不因安全敏感而绕过 Settings。
- Settings 必须拥有受治理配置的真相，包括 LLM profile、Agent profile、Channel profile、Tool provider/catalog 配置、Skill enablement、Memory defaults、runtime defaults、environment overrides、Access asset/binding 配置、Authorization policy 配置和配置变更审计。
- Access 不特殊对待：access asset、credential binding 声明、consumer binding、authorization policy、permission enable/disable、rotation/export/redaction policy 等可配置治理项归 Settings；Access 只保留运行时 credential resolution、readiness observation、setup execution、secret store/vault port 和 runtime grant/evaluator adapter。
- `src/crxzipple/shared/` 放配置协议、值对象契约、有效配置 provider protocol、脱敏/来源/解析链路模型；业务模块依赖 shared 协议，不反向依赖 Settings 实现。
- Settings 通过 container 注入到各模块：模块消费 `EffectiveSettingsProvider` 或更窄的 profile provider，不自己读取散落配置源。
- 前端 Settings 不直接拼各模块 API。读侧通过 `/ui/settings*` 获取页面级模型；写侧通过受控 Settings action 入口发起。
- `/ui/settings*` 是 Settings query surface，负责页面级组合、权限过滤、脱敏、validation summary、action metadata 和 HTTP mapping。
- 业务模块负责使用配置后的领域行为、运行时应用和必要的领域校验函数，但不拥有受治理配置的最终真相。
- 不新增兼容 shim，不保留静态假数据与真实数据两套长期并存。
- 所有 secret、token、API key、connection string 必须脱敏；Settings 页面只显示存在性、来源、状态和可操作动作。
- 第一阶段可以先落读端点，但 P0 必须先定义 Settings 真相源、shared 协议、写操作和审计边界，避免后面补丁式加动作。

## 新 Settings 接入方式

目标结构：

```text
Settings owns configuration governance truth
Settings also owns access/authorization configuration truth
Access owns runtime access execution and secret handling ports
Authorization owns evaluator/runtime decision execution
shared owns effective config / access protocols
modules consume injected effective settings and access refs
Operations observes runtime facts only
```

具体接法：

1. 新增 `modules/settings`，持有配置资源 registry、配置资源仓库、版本、来源、覆盖、生效解析、validation、impact、action audit。
2. 新增 `shared/settings.py`，定义 `SettingsResourceRef`、`EffectiveSettingsProvider`、`ConfigResolution`、`LlmProfileConfig`、`AgentProfileConfig`、`ChannelProfileConfig`、`ToolProviderConfig`、`RuntimeDefaultsConfig` 等消费协议。
3. `core.config.Settings` 和当前 YAML/env/module repositories 只作为 bootstrap/import 输入；长期运行真相必须落到 Settings repository。
4. `container` 构建 Settings application/query/action/provider，并把窄 provider 注入 Agent / LLM / Tool / Channel / Memory / Runtime 相关服务。
5. `/ui/settings*` 只读 Settings query provider 的页面模型；Settings 子页不直接打 `/agents`、`/llms`、`/tools`、`/channels`、`/access` 等模块私有接口。
6. Settings action 写配置资源，包括 Access/Authorization 的可配置资源。涉及 secret material capture、credential verification、temporary runtime grant 的运行时动作由 Settings action 编排 Access/Authorization runtime service，但配置真相仍归 Settings。
7. 业务模块可以提供 validator、runtime summary、package manifest reader、credential readiness probe，但不能提供 Settings 专用 read model，也不能拥有配置治理最终真相。

## P0. 配置控制面、契约与边界

### S0.0 定义 Settings 配置真相与治理面

状态：未处理。

目标：

- 新增长期 Settings 模块，作为受治理配置的 source of truth，而不是只定义页面 read model。
- Settings 管理配置资源目录、配置存储、版本/来源、生效值解析、变更工作流、审计和导入导出。
- Settings resource 至少覆盖：
  - `agent-profile`
  - `llm-profile`
  - `tool-provider`
  - `tool-root`
  - `tool-enablement`
  - `skill-enablement`
  - `channel-profile`
  - `memory-config`
  - `access-asset`
  - `credential-binding`
  - `access-consumer-binding`
  - `access-requirement-binding`
  - `authorization-policy`
  - `runtime-defaults`
  - `environment-override`
  - `backup-policy`
- 每个 resource 至少声明：
  - `resource_id`
  - `resource_kind`
  - `governance_scope`
  - `config_contract`
  - `storage_key`
  - `consumer_modules`
  - `resolution_policy`
  - `supports_create/update/delete/enable/disable/import/export`
  - `validation_policy`
  - `dry_run_policy`
  - `audit_required`
  - `secret_policy`
  - `degraded_reason`
- 明确 Settings 自己可以拥有：
  - 配置资源目录。
  - 受治理配置真相。
  - 配置版本、来源、覆盖和生效值。
  - 配置 action workflow。
  - 配置变更 audit。
  - cross-resource validation / impact preview。
- 明确 Settings 不拥有：
  - Operations 运行态。
  - LLM 调用记录、Tool run、Channel runtime、Memory index 等业务运行事实。
  - access credential secret 原值、可逆 token、private key material。
  - runtime readiness snapshots、setup session 执行过程、临时 runtime grant 执行事实；这些是 Access/Authorization/Operations 的运行事实，但对应的策略和默认行为配置仍归 Settings。

建议位置：

- `src/crxzipple/modules/settings/domain/*`
- `src/crxzipple/modules/settings/application/*`
- `src/crxzipple/modules/settings/infrastructure/persistence/*`
- `src/crxzipple/modules/settings/interfaces/http.py`

验收：

```bash
rg -n 'SettingsResource|resource_id|governance_scope|config_contract|secret_policy|audit_required' \
  src/crxzipple docs/reports/settings-integration-dev-checklist-20260506.md
```

### S0.1 定义 shared 配置协议

状态：未处理。

目标：

- 在 `src/crxzipple/shared/` 定义配置消费协议和配置值对象契约，避免业务模块依赖 Settings 模块实现。
- 至少包含：
  - `EffectiveSettingsProvider`
  - `SettingsProviderForAgent`
  - `SettingsProviderForLlm`
  - `SettingsProviderForTool`
  - `SettingsProviderForChannel`
  - `SettingsResourceRef`
  - `ConfigResolution`
  - `ConfigSource`
  - `SecretBindingRef`
  - `ValidationIssue`
  - `SettingsChangeSet`
  - `LlmProfileConfig`
  - `AgentProfileConfig`
  - `ChannelProfileConfig`
  - `ToolProviderConfig`
  - `RuntimeDefaultsConfig`
- 业务模块只能消费 shared 协议下发的已解析/有效配置，不能自行扫描 Settings 存储或私有文件。
- shared config 可以引用 `shared.access.CredentialBindingRef` / `AccessAssetRef`，但不能包含 secret 原值。

验收：

```bash
rg -n 'EffectiveSettingsProvider|LlmProfileConfig|AgentProfileConfig|ChannelProfileConfig|SecretBindingRef' \
  src/crxzipple/shared src/crxzipple/modules
```

### S0.2 定义 Settings 前后端共享 query/read model

状态：未处理。

目标：

- 新增后端响应模型。注意：这些是 Settings query/read model，不是 Settings 的全部职责。覆盖：
  - `SettingsOverviewReadModel`
  - `SettingsResourcePageReadModel`
  - `SettingsList`
  - `SettingsDetail`
  - `SettingsSummary`
  - `SettingsValidation`
  - `SettingsImpact`
  - `SettingsAudit`
  - `SettingsAction`
  - `ConfigResolution`
- 新增前端 TypeScript 类型，与后端字段一一对应。

建议写入：

- `src/crxzipple/interfaces/http/ui_settings_models.py` 或并入 `ui_models.py`
- `frontend/src/pages/settings/api.ts`

验收：

```bash
rg -n 'SettingsOverview|SettingsResource|SettingsAction|ConfigResolution' \
  src/crxzipple/interfaces/http frontend/src/pages/settings
cd frontend && npm run typecheck
```

### S0.3 新增 `/ui/settings*` read endpoints

状态：未处理。

目标：

- `GET /ui/settings`
- `GET /ui/settings/{resource}`
- `GET /ui/settings/{resource}/{id}`
- `/ui/bootstrap` routes 增加上述 endpoint。
- `GET /ui/settings/access-assets` 目标上读取 Settings-owned access config resources，并合并 Access runtime readiness/secret setup 状态。当前直接复用 Access control-plane read model 只能作为阶段性过渡，不是最终边界。

规则：

- resource id 使用当前前端路由 id：
  - `overview`
  - `agent-profiles`
  - `llm-profiles`
  - `tool-catalog`
  - `skill-catalog`
  - `memory-config`
  - `access-assets`
  - `channel-profiles`
  - `event-registry`
  - `runtime-defaults`
  - `environment`
  - `audit-logs`
  - `backup-restore`
- 未支持资源返回稳定 JSON error 或 degraded read model，不返回 HTML。

验收：

```bash
curl -fsS http://127.0.0.1:8000/ui/settings >/tmp/settings-overview.json
curl -fsS http://127.0.0.1:8000/ui/settings/tool-catalog >/tmp/settings-tool.json
curl -fsS http://127.0.0.1:8000/ui/bootstrap | jq '.routes[]' | rg '/ui/settings'
PYTHONPATH=src pytest -q tests/unit/test_ui_settings_http.py
```

### S0.4 建立 Settings query provider

状态：未处理。

目标：

- 添加一个 Settings query provider，负责从 Settings resource registry、Settings 配置真相和必要的运行摘要生成页面模型。
- 不要在 FastAPI router 函数里写复杂组合逻辑。
- 运行摘要只能作为状态引用或健康摘要，不反向成为配置真相。
- Access Assets resource 通过 Settings query provider 读取 access config resources，并通过 Access runtime service 合并 readiness/setup/audit link；不要从 `/access/inventory` 或模块服务反向扫描。

建议位置：

- `src/crxzipple/modules/settings/application/query.py`
- `src/crxzipple/modules/settings/interfaces/http.py`

验收：

```bash
python -m py_compile src/crxzipple/interfaces/http/ui.py src/crxzipple/interfaces/http/ui_settings*.py
PYTHONPATH=src pytest -q tests/unit/test_ui_settings_http.py
```

### S0.5 定义 Settings command/action 契约

状态：未处理。

目标：

- 在接页面数据前，先定义每个资源允许的 command 形态，避免后续前端绕过 Settings 治理。
- action payload 至少包含：
  - `action_id`
  - `resource_id`
  - `target_id`
  - `intent`
  - `changes`
  - `reason`
  - `confirmation`
  - `risk_acknowledged`
  - `trace_context`
- action response 至少包含：
  - `status`
  - `resource`
  - `audit_ref`
  - `validation`
  - `effective_configuration`
  - `warnings`

规则：

- Settings action 是配置写入统一入口；实际持久化进入 Settings 配置仓库。
- 写入成功后由 Settings 生成新的 effective configuration，并通过 shared provider 被各模块消费。
- 所有写操作默认需要 authorization decision 和 audit。
- Secret 写入只能走受控 secret binding/setup flow，不允许 echo 原值。
- 涉及 access asset、credential binding 声明、consumer binding、authorization policy、permission enable/disable、rotation/export/redaction policy 的写操作必须是 Settings action。
- 涉及 secret material capture、credential verification、runtime setup session、temporary runtime grant 的动作由 Settings action 编排 Access/Authorization runtime service；运行时事实可落 Access/Authorization，但配置真相不外放。

验收：

```bash
rg -n 'SettingsAction|audit_ref|risk_acknowledged|trace_context|secret' \
  src/crxzipple/interfaces src/crxzipple/modules/settings frontend/src/pages/settings || true
```

### S0.6 新增 Settings 持久化模型

状态：未处理。

目标：

- 新增 Settings 持久化表/仓储：
  - `settings_resources`
  - `settings_resource_versions`
  - `settings_effective_snapshots`
  - `settings_overrides`
  - `settings_validation_results`
  - `settings_action_audits`
- 所有 resource payload 都必须经过 schema/version/redaction policy。
- secret-like 字段只能保存 Access ref 或 masked metadata。

验收：

```bash
rg -n 'settings_resources|settings_resource_versions|settings_action_audits' src/crxzipple alembic tests
```

### S0.7 新增 Settings bootstrap / migration importer

状态：未处理。

目标：

- 把现有散落配置作为迁移输入：
  - `container.settings.agent_profiles`
  - `container.settings.llm_profiles`
  - `container.settings.tool_local_paths`
  - `container.settings.tool_mcp_providers`
  - `container.settings.tool_openapi_providers`
  - `container.settings.channel_profiles`
  - memory/runtime/environment 相关 env/config 字段
  - 当前 agent/llm/tool/channel 模块 repository 中已注册配置
- importer 生成 Settings resource + version + effective snapshot。
- import 后业务模块从 Settings shared provider 读取，不再把旧配置源当长期真相。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_settings_migration.py
rg -n 'from_legacy_container|SettingsBootstrapImporter' src/crxzipple/modules/settings tests
```

### S0.8 Container 注入与消费方边界

状态：未处理。

目标：

- `AppContainer` 构建：
  - `settings_governance_repository`
  - `settings_query_provider`
  - `settings_action_service`
  - `effective_settings_provider`
- Agent / LLM / Tool / Channel / Memory 等模块只接收窄 shared provider 或 Settings-backed repository adapter。
- 不允许业务模块直接 import `modules.settings` 内部实现。

验收：

```bash
rg -n 'EffectiveSettingsProvider|SettingsProviderFor' src/crxzipple/bootstrap src/crxzipple/modules src/crxzipple/shared
rg -n 'modules.settings' src/crxzipple/modules/agent src/crxzipple/modules/llm src/crxzipple/modules/tool src/crxzipple/modules/channels || true
```

## P1. 先接真实读侧数据

### S1.1 Settings Overview 接真实聚合

状态：未处理。

当前假数据：

- `frontend/src/pages/settings/modules/OverviewSettingsPage.vue`
- `metrics`、`healthRows`、`recentChanges`、`issueRows`、`quickActions` 全部静态。

配置真相：

- agent count：Settings 中的 `agent-profile` 配置资源。
- llm count：Settings 中的 `llm-profile` 配置资源。
- tool count：Settings 中的 `tool` / `tool-provider` 配置资源。
- skill count：Settings 中的 `skill` 配置资源。
- event count：`event_definition_registry.list_definitions()`
- access readiness：Access control-plane read model 的健康摘要，不从模块反向扫描
- channel count：Settings 中的 `channel-profile` 配置资源。
- runtime defaults：Settings 中的 `runtime-defaults` 配置资源。
- recent changes：第一阶段可为空态；不要继续造 Jane Doe/John Smith 假审计
- issues：从 validation summary 聚合；没有检查结果时返回空态

验收：

```bash
curl -fsS http://127.0.0.1:8000/ui/settings | jq '{resource_counts, configuration_health}'
rg -n 'Jane Doe|John Smith|Research Assistant|browser_control|2 hours ago|5 hours ago' \
  frontend/src/pages/settings/modules/OverviewSettingsPage.vue || true
```

### S1.2 Agent Profiles 页面接 `/ui/settings/agent-profiles`

状态：未处理。

当前假数据：

- `rows`、`traceRows`、`skillRows` 静态。
- 表单值硬编码 `General Assistant`。

配置真相：

- Settings repository 中的 `agent-profile` 资源。
- shared `AgentProfileConfig` effective configuration。
- agent home snapshot 只能作为关联文件/工作区状态 tab，不是 profile 配置真相。

后端缺口：

- 需要在 read model 中补 effective configuration、resolution trace、validation summary。
- 需要把现有 agent profile 配置迁入 Settings，agent 模块改为消费注入的 effective config。
- 不能把 agent profile 写成 orchestration、session 或 agent 模块私有配置真相。

验收：

```bash
curl -fsS http://127.0.0.1:8000/ui/settings/agent-profiles | jq '.list.total'
curl -fsS http://127.0.0.1:8000/ui/settings/agent-profiles/{agent_id} | jq '.detail'
rg -n 'General Assistant|Research Agent|Code Agent|Data Analyst' frontend/src/pages/settings/modules/AgentProfilesSettingsPage.vue || true
```

### S1.3 LLM Profiles 页面接 `/ui/settings/llm-profiles`

状态：未处理。

当前假数据：

- `profiles`、`capabilityRows` 静态。
- 表单值硬编码模型和 provider。

配置真相：

- Settings repository 中的 `llm-profile` 资源。
- shared `LlmProfileConfig` effective configuration。
- invocation summary 只能作为轻量 usage link/last used 摘要，真实运维图表归 Operations LLM。

后端缺口：

- 需要 provider/model availability、source、default/concurrency/timeout 的脱敏 read model。
- LLM 模块需要从 shared Settings provider 读取 profile；`container.settings.llm_profiles` 和 LLM 私有 repository 只能作为 bootstrap/import 或运行缓存。

验收：

```bash
curl -fsS http://127.0.0.1:8000/ui/settings/llm-profiles | jq '.list.total'
curl -fsS http://127.0.0.1:8000/llms | jq 'length'
rg -n 'gpt-4o|Claude|Gemini|Jane Doe' frontend/src/pages/settings/modules/LlmProfilesSettingsPage.vue || true
```

### S1.4 Tool Catalog 页面接 `/ui/settings/tool-catalog`

状态：未处理。

当前假数据：

- `tools`、`accessRows`、`testRows` 静态。
- 示例写死 `web_search`、`serpapi.com/openapi.yaml`。

配置真相：

- Settings repository 中的 `tool-provider`、`tool-root`、`tool-enablement` 配置资源。
- Tool package / manifest / OpenAPI spec 是工具内容契约输入；Settings 治理 provider/root/enablement/策略覆盖，不复制工具运行事实。
- shared `ToolProviderConfig` / tool catalog effective configuration。
- tool domain fields：parameters、required effects、access requirements、execution policy、execution support、runtime key、enabled。

后端缺口：

- detail 必须包含 input schema、output/result contract、runtime strategy、access/effects、artifact output、contract validation。
- access requirement 显示应来自 Tool declaration + Access consumer binding/readiness，不要前端编造 `serpapi_api`。

验收：

```bash
curl -fsS http://127.0.0.1:8000/ui/settings/tool-catalog | jq '.list.total'
curl -fsS http://127.0.0.1:8000/tools | jq 'length'
rg -n 'serpapi|web_search|send_email|sql_query' frontend/src/pages/settings/modules/ToolCatalogSettingsPage.vue || true
```

### S1.5 Skill Catalog 页面接 `/ui/settings/skill-catalog`

状态：未处理。

当前假数据：

- `skills`、`capabilityRows`、`accessRows`、`contractRows` 静态。

配置真相：

- `skill_manager.list_skills()`
- `skill_manager.get_skill(...)`
- `skills` HTTP detail serializer 可复用，但 Settings read model 需要按设计稿组织。
- Skill package manifest 是技能内容契约输入；Settings 治理 enablement、surface binding、capability mapping 和策略覆盖。

后端缺口：

- required files/resources、capability requirements、access requirements、supported surfaces、contract validation 要从 skill manifest/package 真相生成。

验收：

```bash
curl -fsS http://127.0.0.1:8000/ui/settings/skill-catalog | jq '.list.total'
curl -fsS http://127.0.0.1:8000/skills | jq 'length'
rg -n 'Search Knowledge Base|Data Analysis|Email Processing|Web Research' frontend/src/pages/settings/modules/SkillCatalogSettingsPage.vue || true
```

### S1.6 Event Registry 页面接 `/ui/settings/event-registry`

状态：未处理。

当前假数据：

- `events`、`cards` 静态。

配置真相：

- `event_definition_registry.to_payload()` 作为 contract/import 输入；Settings 治理可配置的 surface、durability、compatibility policy 和 enablement。
- `events_service` topic/subscription diagnostics
- `EventSurface` / observer coverage。

后端缺口：

- 页面 detail 要展示 payload schema、publication mode、durability、producer/consumer、surface、observer route。

验收：

```bash
curl -fsS http://127.0.0.1:8000/ui/settings/event-registry | jq '.list.total'
curl -fsS http://127.0.0.1:8000/events/contracts | jq '.definition_count'
rg -n 'run.created|tool.started|memory.updated|source' frontend/src/pages/settings/modules/EventRegistrySettingsPage.vue || true
```

### S1.7 Access Assets 页面接 `/ui/settings/access-assets`

状态：部分处理（当前已由 Access control-plane read model 提供 `/ui/settings/access-assets` 阶段性别名；目标仍需迁到 Settings-owned access config resources，并合并 Access runtime readiness/setup 状态）。

当前假数据：

- `assets`、`consumerRows`、`usageRows` 静态。

目标配置真相：

- Settings repository 中的 `access-asset`、`credential-binding`、`access-consumer-binding`、`access-requirement-binding`、`authorization-policy` 配置资源。
- Access runtime service 提供 readiness、credential verification、setup session 状态、masked preview 和 runtime audit link。
- Authorization evaluator 提供策略 dry-run / impact preview 的执行结果，但 policy 配置由 Settings 持有。

规则：

- 只展示凭据存在性、来源、目标、readiness、缺失项和 setup action。
- 不展示 secret 原文或可逆 token。
- 不再调用 `/access/inventory` 作为 Settings 页面真相，也不从 Tool / LLM / Agent 反向索引。
- 权限启停、policy enable/disable、access asset enable/disable 都是 Settings action，不是 Access 特例。

验收：

```bash
curl -fsS http://127.0.0.1:8000/ui/settings/access-assets | jq '.summary'
curl -fsS http://127.0.0.1:8000/ui/access | jq '.counts'
rg -n 'sk-|token|secret|api_key=.*[A-Za-z0-9]{8}' frontend/src/pages/settings src/crxzipple/interfaces/http || true
```

### S1.8 Channel Profiles 页面接 `/ui/settings/channel-profiles`

状态：未处理。

当前假数据：

- `channels` 静态，表单和 sample payload 硬编码。

配置真相：

- Settings repository 中的 `channel-profile` 配置资源。
- shared `ChannelProfileConfig` effective configuration。
- `channel_runtime_manager.list_runtimes()` 只能作为关联运行状态摘要。
- dead letter summary 链接 Operations，不在 Settings 内做运维主视图。

后端缺口：

- 当前 channels 配置真相还在 channel system config store，需要迁移到 Settings；旧 store 只能作为 bootstrap/import 输入。
- Channels 模块应消费注入的 effective channel profiles；runtime/dead-letter/transport endpoint 不参与配置治理写入。

验收：

```bash
curl -fsS http://127.0.0.1:8000/ui/settings/channel-profiles | jq '.list.total'
rg -n 'Web Chat|Slack|Lark|Test with Sample Payload' frontend/src/pages/settings/modules/ChannelProfilesSettingsPage.vue || true
```

### S1.9 Memory Config 页面接 `/ui/settings/memory-config`

状态：未处理。

当前假数据：

- `stores`、`consumerRows`、`lifecycleRows` 静态。

配置真相：

- Settings repository 中的 `memory-config` 配置资源。
- `memory_context_resolver`、`file_memory_service`、memory overview/search/index service 只能提供 validation/runtime summary。
- agent profiles 的 memory/workspace preference。

后端缺口：

- Memory config 真相目前分散在启动 settings、agent profile/home、memory index context；需要收敛到 Settings，并在 read model 中显式标出来源、生效路径和不可热更新项。

验收：

```bash
curl -fsS http://127.0.0.1:8000/ui/settings/memory-config | jq '.summary'
curl -fsS http://127.0.0.1:8000/memory/overview | jq .
rg -n 'Agent Memory|Vector Store|Redis Cache' frontend/src/pages/settings/modules/MemoryConfigSettingsPage.vue || true
```

### S1.10 Runtime Defaults 页面接 `/ui/settings/runtime-defaults`

状态：未处理。

当前假数据：

- 表单值和 `impactRows` 静态。

配置真相：

- Settings 中的 `runtime-defaults` 配置资源：
  - orchestration lease/heartbeat/timeout
  - tool worker max in flight / heartbeat / lease
  - LLM default timeout/concurrency
  - operations projection/observer settings
  - events backend/database backend 类型
- 配置来源：default/env/config file/imported settings；env/config file 只作为 Settings source metadata 或 bootstrap input，secret value 必须脱敏。

后端缺口：

- 需要 settings metadata/resolution helper，至少能标出 default/env/imported/overridden。
- dry run 和 change impact 可先返回 unsupported/degraded 状态，不继续显示假结果。

验收：

```bash
curl -fsS http://127.0.0.1:8000/ui/settings/runtime-defaults | jq '.effective_configuration'
rg -n '1024|gpt-4o-mini|claude-3.5-haiku|90 seconds|5 seconds' frontend/src/pages/settings/modules/RuntimeDefaultsSettingsPage.vue || true
```

### S1.11 Environment 页面接 `/ui/settings/environment`

状态：未处理。

当前假数据：

- `environments`、`variables`、`secrets`、`groups` 静态。

配置真相：

- Settings 中的 environment override 配置资源和当前 runtime environment 摘要。
- DB/Redis readiness 可链接 Operations runtime，不在 Settings 再实现运维探测。
- 安全的 env key inventory：只返回 key、source、required/optional、configured/missing、masked preview；secret material 继续归 Access。

后端缺口：

- 需要统一 safe settings/env inventory，避免到处手写脱敏。

验收：

```bash
curl -fsS http://127.0.0.1:8000/ui/settings/environment | jq '.summary'
rg -n 'prod-us-east-1|staging|Jane Doe|SECRET_VALUE|sk-' frontend/src/pages/settings/modules/EnvironmentSettingsPage.vue || true
```

### S1.12 Audit Logs 页面接真实审计源

状态：未处理。

当前假数据：

- `logs` 静态。

数据源：

- Settings 自己的 `settings_action_audits`。
- Access Assets 页可链接 Access runtime audit；配置变更审计必须进入 Settings audit。
- 第一阶段若借用 `operations_action_audits`，必须标注范围是 operations actions，不能伪装成配置审计。

后端缺口：

- 当前缺 Settings config audit read endpoint。
- 需要统一 `AuditRef` 模型，包含 actor、resource、action、reason、diff、trace。

验收：

```bash
curl -fsS http://127.0.0.1:8000/ui/settings/audit-logs | jq '.list.total'
rg -n 'Jane Doe|Mike Lee|Filter saved locally|Production environment' frontend/src/pages/settings/modules/AuditLogsSettingsPage.vue || true
```

### S1.13 Backup Restore 页面先降级为明确未接通

状态：未处理。

当前假数据：

- `backups`、`restoreAudit`、`scopeItems` 静态。

目标：

- 如果没有 backup service，不继续展示虚构备份。
- 返回 degraded/unsupported read model：
  - title/description
  - capability missing
  - required Settings backup capability
  - disabled actions
  - implementation notes

验收：

```bash
curl -fsS http://127.0.0.1:8000/ui/settings/backup-restore | jq '.health'
rg -n 'backup-2025|48.7 GB|Scheduled backup|Download / Restore' frontend/src/pages/settings/modules/BackupRestoreSettingsPage.vue || true
```

## P2. 前端替换静态页面

### S2.1 新增 settings API composable

状态：未处理。

目标：

- `frontend/src/pages/settings/api.ts` 使用 `requestJson`。
- 暴露：
  - `loadSettingsOverview()`
  - `loadSettingsResource(resource)`
  - `loadSettingsResourceDetail(resource, id)`
- 支持 loading/error/retry。

验收：

```bash
rg -n 'requestJson<.*>\\("/ui/settings' frontend/src/pages/settings
cd frontend && npm run typecheck
```

### S2.2 所有 Settings 子页从 props/read model 渲染

状态：未处理。

目标：

- `SettingsShell` 负责加载当前 resource read model。
- 子页接收 read model props，不自己写静态 rows。
- list/detail/filter/tab 使用统一字段结构。
- 无数据时展示后端返回的 empty state，不造默认条目。

验收：

```bash
rg -n 'const (rows|profiles|tools|skills|assets|events|channels|stores|logs|backups|environments|variables|secrets) = \\[' \
  frontend/src/pages/settings/modules || true
cd frontend && npm run typecheck
```

### S2.3 页面保持设计稿信息架构

状态：未处理。

目标：

- 不把 Settings 简化成 generic table。
- 每个资源仍按 `docs/ui/settings/*.png` 保留：
  - 左侧资源/列表
  - 中间详情/编辑面板
  - 右侧 summary/validation/effective/audit
  - 底部或 header actions
- PC 端按全屏配置管理台，不用大量空白卡片糊布局。

验收：

```bash
cd frontend && npm run build
```

人工验收：

- `/settings`
- `/settings/agent-profiles`
- `/settings/llm-profiles`
- `/settings/tool-catalog`
- `/settings/access-assets`
- `/settings/event-registry`

至少这 6 页首屏不能出现明显静态假数据、硬编码人名或示例服务名。

### S2.4 i18n 覆盖

状态：未处理。

目标：

- Settings 页面新增文案进入 `frontend/src/shared/i18n/messages/{zh-CN,en-US}.ts`。
- 后端返回的 enum/status 使用稳定 id，前端映射显示文案。
- 不暴露 `settings.*`、`operations.*` 这种裸 key。

验收：

```bash
rg -n 'settings\\.[a-zA-Z0-9_.-]+' frontend/src/pages/settings
cd frontend && npm run typecheck
```

## P3. 写操作、权限和审计

### S3.1 落地 Settings action dispatcher

状态：未处理。

目标：

- action 契约必须在 P0 定义；实际写入可以在读侧稳定后逐资源打开。
- 动作入口遵循 `docs/ui/runtime-ui-read-model-contracts.md`：
  - `POST /ui/actions/{action_id}` 或等价 console action dispatcher
  - payload 必须包含 resource、target id、reason、confirmation、risk acknowledgement、trace context
- action dispatcher 负责权限、审计、validation、dry run、持久化 Settings 变更和刷新 effective configuration。
- dispatcher 路由规则：
  - Settings-owned config resource 写入 Settings action service。
  - Access/Authorization 的可配置资源也写入 Settings action service。
  - Access runtime action 只处理 secret material capture、credential verification、runtime setup session、temporary runtime grant 等运行时事实。
  - Operations runtime action 写入 Operations action service。
  - 业务模块只提供 validator/runtime apply hook，不成为配置治理写入口。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_ui_settings_actions_http.py
rg -n 'endpoint="/(agents|llms|tools|skills|channels|access|memory)' frontend/src/pages/settings || true
```

### S3.2 各模块切换为 Settings 配置消费方

状态：未处理。

按 consumer 拆：

- Agent：从 shared `AgentProfileConfig` / effective provider 读取 profile；移除运行时私有 profile 真相。
- LLM：从 shared `LlmProfileConfig` / effective provider 读取 profile；`container.settings.llm_profiles` 降级为迁移输入。
- Tool：从 Settings 读取 provider/root/catalog 配置；工具运行服务只消费 effective tool catalog。
- Skill：当前执行口径已变更为 Skills owner。Settings 不再保存 skill enablement 真相；
  skill package、source、enable/disable、readiness、manifest、read/catalog 均走
  Skills application/API。
- Access：当前已接 Access control plane；目标是把 access/authorization 可配置真相迁入 Settings，Access 消费 effective access config 并负责 secret/runtime/readiness/temporary grant 执行。
- Channels：从 shared `ChannelProfileConfig` / effective provider 读取 profile；channel system config store 退化或迁移。
- Memory：从 Settings 读取 memory defaults、store binding、retention/index policy；避免直接写 agent home 或文件 index 内部。
- Runtime Defaults / Environment：由 Settings 管理可治理配置；不可热更新项必须标记 requires restart，不假装在线生效。
- Backup Restore：需要先定义 Settings 自己的 backup/restore 边界。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_ui_settings_actions_http.py tests/unit/test_authorization.py
```

### S3.3 配置变更审计

状态：未处理。

目标：

- 所有 Settings 写操作必须产出审计事实：
  - actor
  - resource
  - resource_kind
  - consumer_modules
  - action
  - reason
  - before/after diff
  - trace/request id
  - permission decision
- Audit Logs 页面从真实 audit source 读取。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_ui_settings_actions_http.py
curl -fsS http://127.0.0.1:8000/ui/settings/audit-logs | jq '.list.rows[0]'
```

## 建议落地顺序

1. S0.0-S0.8：先定 Settings 配置真相、shared 协议、持久化、bootstrap/import、container 注入、query model 和 action 契约。
2. S1.7：把 Access Assets 从阶段性 Access control-plane 别名迁到 Settings-owned access config resources，作为“不特殊对待 Access”的边界样板。
3. S1.1：Overview 接 Settings resource counts/health，去掉明显假数据。
4. S1.2-S1.4：Agent / LLM / Tool 三个配置消费者先迁到 Settings effective provider。
5. S2.1-S2.2：前端改成统一 settings API + query model props。
6. S1.5-S1.6：Skill / Event 接真实契约和 Settings enablement。
7. S1.8-S1.11：Channel / Memory / Runtime Defaults / Environment 接通，并处理脱敏和 requires restart。
8. S1.12-S1.13：Audit / Backup 明确真实源或降级空态。
9. S2.3-S2.4：按设计稿重新压紧布局和 i18n。
10. S3.*：逐资源打开写操作、权限和审计。

## 最小验证集

```bash
PYTHONPATH=src pytest -q tests/unit/test_ui_settings_http.py
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py tests/unit/test_events.py
cd frontend && npm run typecheck
cd frontend && npm run build
```

## 完成定义

- `/settings` 和 12 个 resource 页不再依赖静态假数据。
- `/ui/settings*` 返回稳定 JSON，字段满足当前 Settings 设计稿。
- 前端 Settings 不直接调用模块私有写接口。
- Agent / LLM / Tool / Channel 等配置消费者从 shared Settings provider 读取 effective config。
- Access Assets 页由 Settings read model 提供配置真相，并合并 Access runtime readiness/setup 状态。
- 所有 secret 均脱敏。
- 未实现能力以 degraded/unsupported 空态呈现，不虚构成功备份、审计、人名或配置。
- 新增/修改功能有单元测试或明确扫描命令。
