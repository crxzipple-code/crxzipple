# Settings / Module Boundary Complexity Review 2026-05-08

本文档是当前额外复杂度审查和后续修复任务清单。它优先级高于
`settings-integration-dev-checklist-20260506.md`、`settings-governance-construction-checklist-20260507.md`
和 `settings-ui-backend-alignment-checklist-20260507.md` 中关于 profile 真相源迁移的旧判断。

## 结论

Settings 应该是配置治理模块，不应该默认成为各业务模块实体的最终真相源。

当前额外复杂度主要来自把 Agent / LLM / Channel 等 profile 类模块实体搬进
Settings，再通过 materializer 同步回模块 runtime。这样会产生两套入口、两套读模型、
一次额外投影和同步时序风险。

新的边界原则：

- 模块实体真相归 owner module。Agent profile 归 Agent/backbone/home registry；
  LLM profile 归 LLM；Channel profile 归 Channels。例外必须在当前架构文档中明确写出。
- Settings 归治理：配置资源目录、版本、覆盖、审计、启停策略、环境覆盖、导入导出、
  validation、dry run、impact preview。
- Settings 可以提供只读索引或治理 overlay，但不能绕过 owner application service 修改模块实体。
- Settings 通用 action 只适用于 Settings-owned resource。模块实体动作必须 dispatch 到 owner
  application service，并由 owner module 负责落真相、发事件、更新运行索引。
- shared settings contracts 只放跨模块治理协议和窄配置契约，不能复制完整模块 domain entity。

2026-05-08 整改记录：

- module-owned profiles（Agent / LLM / Channel）和 readonly placeholders（Event / Environment）
  已停止暴露 Settings 通用 `dry-run` / `validate` 动作；这些 kind 在接 owner dispatcher
  前只保留治理读面。
- LLM `/llms/sync-profiles` 与 CLI `llm sync-profiles` 已停止读取 Settings legacy
  `llm-profiles` resource；正常同步只读取 LLM bootstrap/config 输入。
- Access 配置写 intent 已统一经 `AccessSettingsActionAdapter` 写 Settings-backed access
  declarations；adapter 缺失时直接失败，不再回落到 Access repository 旧写路径。
- Settings bootstrap setup 中未调用的 Agent / LLM / Channel profile seed helpers 已删除，避免后续误判
  Settings 仍可 seed profile truth。

## 审查发现

### R1. Agent Profile 形成双真相链路

当前 Agent 本身已经有实体、home registry 和 `agent.json` 读写链路：

- `src/crxzipple/modules/agent/domain/entities.py`
- `src/crxzipple/modules/agent/application/services.py`
- `src/crxzipple/modules/agent/infrastructure/home_config.py`
- `src/crxzipple/modules/agent/infrastructure/home_registry.py`

但 `/agents` 创建现在先写 Settings `agent-profiles`，再同步回 Agent runtime：

- `src/crxzipple/modules/agent/interfaces/http.py`
- `src/crxzipple/modules/agent/interfaces/cli.py`
- `src/crxzipple/modules/agent/application/settings_integration.py`

风险：

- Settings UI 可直接 enable/disable Settings resource，但不会触发 Agent runtime sync。
- `/agents` 读的是 Agent service，`/ui/settings/agent-profiles` 读的是 Settings resource。
- Agent home 文件、registry、Settings resource 和 runtime index 可能出现漂移。

### R2. shared/settings.py 复制模块业务 schema

已处理：`src/crxzipple/shared/settings.py` 不再定义 Agent / LLM / Channel 完整 profile
config DTO。显式迁移入口使用 legacy mapping payload，由 owner module 自己解析为领域输入。

风险：

- shared 层从协议层膨胀成业务模型镜像。
- 模块 schema 改动需要同步改 shared、materializer、settings UI、module integration。
- 后续 agent 容易误以为 Settings 才是 profile owner。

### R3. Settings 通用 action 绕过模块应用语义

`src/crxzipple/modules/settings/interfaces/http.py` 的通用 action dispatcher 对所有 kind
执行 `create/update/enable/disable`。这对 Settings-owned resource 合理，但对 Agent/LLM/Channel
profile 这类模块实体会绕过 owner module。

当前状态：已收口第一层。module-owned profiles 与 readonly placeholders 不再允许 Settings 通用
`dry-run` / `validate` / 写动作；后续如果要在 Settings 页面发起 profile 写动作，必须接 owner
dispatcher。

风险：

- Settings action audit 显示成功，但模块 runtime 未应用。
- 模块事件、领域校验、sidecar/home 文件更新没有发生。
- 前端同一个按钮对不同 resource kind 的真实效果不一致。

### R4. 启动链路有导入、materialize、再 sync 的额外循环

当前 container 构建阶段会 seed Settings，再 materialize profile/config，再同步回模块。

风险：

- 启动时职责不清：Settings bootstrap、运行真相恢复、模块 runtime index 重建混在一起。
- 每个模块都需要一个 settings_integration 转换器。
- 对 Agent profile 这类已经有自身持久化的模块，启动路径变成多余且易错。

### R5. Access 有可接受但需要收边界的双层结构

Access 拥有 secret/setup/readiness/runtime grant/audit，同时 Settings 中出现
`access-assets` 和 import/action adapter。

这不是完全错误，但必须收紧：

- Access runtime 生命周期继续归 Access。
- Settings 可以治理 policy、enablement、binding declaration，但写入必须通过明确的 Access
  application command 或 Settings-to-Access dispatcher。
- 从 LLM/tool/channel profile 反推 access inventory 只能标记为 inferred/read-only，不能冒充
  Access 真相。

### R6. Operations read model 装配面偏宽

Operations 当前通过大 context 注入大量模块 service，再由 provider 拼页面 read model。
这是运维面可接受的过渡复杂度，但长期应收为明确 query ports。

风险：

- `Any`/反射式 provider 让 read model 契约不稳定。
- 后续页面优化容易直接读模块内部服务。

### R7. 旧文档仍会把 agent 带回错误方向

旧 Settings checklist 中存在“移除运行时私有 profile 真相”“Settings 拥有 Agent profile”
等判断。这些必须标记为过期，否则托管 agent 会继续补缝。

### R8. LLM Profile 也形成 Settings 写入后同步 runtime 的链路

当前 LLM 有自己的 domain entity、repository 和 application service：

- `src/crxzipple/modules/llm/domain/entities.py`
- `src/crxzipple/modules/llm/application/services.py`

历史问题是 `/llms` 创建先写 Settings `llm-profiles`，再调用 `llm_service.sync_profiles(...)`：

- `src/crxzipple/modules/llm/interfaces/http.py`
- `src/crxzipple/modules/llm/interfaces/cli.py`

当前状态：已收口。`/llms` HTTP/CLI 写路径回到 LLM service/repository；
`sync-profiles` 不再读取 Settings legacy `llm-profiles` resource，legacy materializer 仅保留为显式
migration/import 候选。

风险：

- `/llms` 读 LLM service，`/ui/settings/llm-profiles` 读 Settings resource。
- Settings 通用 enable/disable 只改 Settings resource，不更新 LLM profile repository。
- LLM invocation 使用 LLM service 中的 enabled/profile 信息，可能与 Settings 页面显示不一致。

结论：

- LLM profile 需要重新分类。若保留 Settings governance，写动作必须 dispatch 到
  `LlmApplicationService`，不能由 Settings 通用 action 直接改 payload。

### R9. Channel Profile 有 Settings bootstrap 与 Channel system config 两层真相

Channels 已有 `ChannelProfileApplicationService` 和 file-backed `ChannelSystemConfigStore`：

- `src/crxzipple/modules/channels/application/services.py`
- `src/crxzipple/modules/channels/infrastructure/stores.py`
- `src/crxzipple/modules/channels/infrastructure/state_root.py`

启动时 Settings materializer 产出 channel payload，再转成 `ChannelProfile`，写入
Channel system config：

- `src/crxzipple/bootstrap/container.py`
- `src/crxzipple/modules/channels/application/settings_integration.py`

风险：

- `/ui/settings/channel-profiles` 改 Settings resource 后，不会自动更新 channel system config。
- Lark/Webhook 运行时读取 `channel_profile_service.get_profile(...)`，不是直接读 Settings。
- Channel runtime、daemon spec、connection binding 的启停和 profile 修改需要 owner module 应用语义。

结论：

- Channel profile 默认应归 Channels profile service/store。Settings 可做治理 overlay 或配置导入入口，
  但不能成为唯一写入口。

### R10. Tool Catalog 是 mixed kind，provider/root/enablement 混在一个 Settings kind 中

Tool 的 Settings materializer 从同一个 `tool-catalog` kind 中解析三类资源：

- provider：`tool_providers()`
- root：`tool_roots()`
- enablement：`tool_enablements()`

相关代码：

- `src/crxzipple/modules/settings/application/materialization.py`
- `src/crxzipple/modules/settings/application/setup.py`
- `src/crxzipple/modules/tool/application/settings_integration.py`
- `src/crxzipple/bootstrap/container.py`

风险：

- 一个 kind 承载 provider/root/enablement，UI/action/validation 很难知道 resource 的真实 subtype。
- provider/root 在 container build 时注册 discovery/runtime handler；Settings action 改 payload 后不会重建
  discovery registry、remote handler 或 worker runtime gateway。
- enablement 在 `ToolEnablementService` 构建时生效；通用 Settings enable/disable 后当前进程不热更新。
- Tool worker CLI 的 `--max-in-flight` 由 daemon spec 注入时使用 runtime materializer，但手动启动时仍从
  `core.config.Settings` 读取 `tool_worker_max_in_flight`，不是 Settings effective config。

结论：

- Tool provider/root 是配置治理项，但需要明确 `config_subkind` 和 apply policy。
- Tool enablement 可以 Settings-owned，但必须定义 hot reload 或 `requires_restart`。

### R11. Skill Enablement 是合理治理项，但与 Skills runtime catalog 边界要写死

Skill enablement 当前通过 `SkillEnablementManagerAdapter` 包裹 `SkillManager`，只过滤可用 skill：

- `src/crxzipple/modules/skills/application/settings_integration.py`

风险：

- Settings `skill-catalog` 只有 enablement，不是完整 skill package/catalog 真相。
- 通用 Settings action 改 enablement 后，已构建的 `SkillEnablementService` 不热更新。
- UI 如果展示安装、manifest、运行能力，就会把 Skills module 的职责搬到 Settings。

结论：

- `skill-catalog` 应拆名或加 subtype：`skill-enablement`。
- skill package discovery/install/validate/read 继续归 Skills。

### R12. Memory Config / Runtime Defaults 是较合理的 Settings-owned config，但热应用边界不清

Memory 和 Runtime defaults 当前是启动期 bootstrap config：

- `src/crxzipple/modules/memory/application/settings_integration.py`
- `src/crxzipple/modules/orchestration/application/settings_integration.py`
- `src/crxzipple/bootstrap/container.py`

风险：

- Settings action 修改 `memory-config` 后，当前 `FileMemoryContextResolver`、embedding provider、
  watcher interval 不会自动重建。
- Settings action 修改 `runtime-defaults` 后，orchestration lease、tool worker lease、tool worker
  concurrency、daemon specs 不会自动应用到已运行进程。
- UI 没有明确展示哪些字段 hot apply、哪些字段 requires restart / daemon restart / worker restart。

结论：

- Memory/Runtime 可以保持 Settings-owned，但必须补 apply policy 和 runtime applied status。

### R13. Environment resource 存在把运行环境和敏感连接信息落入 Settings payload 的风险

`environment` seed 会把 `database_url`、events backend、sandbox backend、authorization path
写入 Settings resource payload：

- `src/crxzipple/modules/settings/application/setup.py`

HTTP/UI read model 做了脱敏：

- `src/crxzipple/modules/settings/interfaces/http.py`
- `frontend/src/pages/settings/modules/EnvironmentSettingsPage.vue`

但 Settings resource/version payload 本身仍可能保存原始 `database_url`。audit metadata 有 `_redact(...)`，
不等于 resource payload 已被脱敏。

风险：

- 如果 `database_url` 含用户名密码，Settings repository 会成为额外敏感信息存储点。
- Environment 更像 runtime/bootstrap fact + override target，不应该默认可写完整环境快照。

结论：

- Environment 页面先保持 read-only。
- Settings 中保存环境信息要使用 redacted snapshot 或 secret ref，不保存原始 secret-bearing URL。

### R14. Access 已经有专用 action adapter，但 Settings 与 Access repository 的边界仍混合

Access 的配置写 intent 会由 `AccessActionService` 转给 `AccessSettingsActionAdapter`：

- `src/crxzipple/modules/access/application/actions.py`
- `src/crxzipple/modules/access/application/settings_integration.py`

Access bootstrap importer 又会从 migration plan 写 `access-assets`：

- `src/crxzipple/modules/access/application/importer.py`

风险：

- Access repository、Settings `access-assets`、从 LLM/tool/channel 推断出的 inferred inventory 三种来源并存。
- Authorization policy 的 enable/disable/delete 当前本质是 Settings payload 状态更新，是否同步到
  Authorization runtime/evaluator 需要明确。
- Access config view 只 materialize Settings configs；Access runtime readiness 另走 Access。

结论：

- Access 不是要回滚，而是要更明确分类：declaration/policy 归 Settings governance，
  secret/setup/readiness/grant/evaluator runtime 归 Access/Authorization。

### R15. Settings UI 的通用 action 面板对不同 ownership 的资源表现不一致

通用 `SettingsActionPanel` 对所有 kind 都开放 validate/dry-run/enable/disable：

- `frontend/src/pages/settings/components/SettingsActionPanel.vue`

风险：

- 对 Settings-owned config，它只是配置变更。
- 对 module-owned entity，它可能不会影响 owner module runtime。
- 对需要 restart 的 config，它没有告诉用户只是“已保存未生效”。

结论：

- action availability 必须来自后台 action metadata。
- UI 需要显示 `owner_module`、`truth_source`、`apply_policy`、`runtime_applied`。

## 整改任务清单

### C0. 文档护栏

状态：进行中。

- [x] 新增本复杂度审查和整改任务清单。
- [x] 更新 `docs/README.md`，把本文档列为当前 Settings 边界依据。
- [x] 更新托管 agent 约束，明确 Settings 与模块实体边界。
- [x] 给旧 Settings 开发清单加 superseded/corrective note。
- [ ] 后续施工完成后，把已废弃的旧 Settings checklist 归档或压缩成历史背景。

验收：

```bash
rg -n "移除运行时私有 profile 真相|Settings 必须拥有受治理配置的真相|Settings-owned agent profile" docs
```

结果中只能出现在明确标注为 superseded 的历史段落。

### C1. 配置资源分类表

状态：进行中。

产出一个当前有效分类表，至少包含：

- `settings-owned-config`：Settings 是真相源，可直接通用 action。
- `module-owned-entity`：模块是真相源，Settings 只做索引/overlay/治理入口。
- `module-owned-runtime-fact`：运行事实，只能进 Operations/Trace，不进 Settings 写面。
- `placeholder`：当前无后台 workflow，不展示可编辑入口。

初始建议：

| kind | 分类 | owner | 处理方向 |
| --- | --- | --- | --- |
| agent-profiles | module-owned-entity | Agent | 真相回到 Agent/backbone；Settings 只读索引和治理入口 |
| llm-profiles | module-owned-entity | LLM | 真相回到 LLM profile service；Settings 只做治理 overlay，不暴露通用写动作 |
| channel-profiles | module-owned-entity | Channels | 真相回到 Channel profile service/store；Settings 只做治理 overlay，不暴露通用写动作 |
| tool-catalog | mixed | Tool / Settings | provider/root/enablement 可治理；必须补 subtype 和 apply policy；discovered tool/runtime 不归 Settings |
| skill-catalog | mixed | Skills / Settings | enablement 可治理；skill package/catalog runtime 归 Skills |
| access-assets | mixed | Access / Settings | policy/binding declaration 可治理；secret/setup/readiness/runtime grant 归 Access |
| memory-config | settings-owned-config | Settings | 保持治理配置，Memory 消费；必须标注 hot/restart 生效边界 |
| runtime-defaults | settings-owned-config | Settings | 保持治理配置，标注 daemon/worker restart 或 hot apply |
| environment | settings-owned-config | Settings | 只读/脱敏/覆盖治理；禁止保存 secret-bearing raw values |
| event-registry | placeholder | Events | 先只读链接，不做 Settings 写面 |
| backup-restore | placeholder | Settings | 无 workflow 前隐藏 |

验收：

- 文档中每个 Settings kind 都能追到 owner、写入口和生效方式。
- 前端页面文案不再把 module-owned entity 称为 Settings-owned truth。

### C2. Agent Profile 回收

状态：基本完成，剩余仅为可选 owner dispatcher 设计。

- [x] `/agents` create/update/enable/disable/delete 重新以 `AgentApplicationService` 为唯一写入口。
- [x] `/agents` update/delete owner API 按 Agent domain 语义补齐；delete 移除 registry 和
  `agent.json` profile truth，但保留 home 下的用户资产文件。
- [x] Agent home registry / `agent.json` / Agent service runtime index 作为 Agent profile 真相。
- [x] Settings 不再 seed 完整 `agent-profiles` 作为运行真相。
- [x] 移除 shared `AgentProfileConfig` / `LlmProfileConfig` / `ChannelProfileConfig`；
  显式迁移入口降为 legacy mapping payload，由 owner module 解析。
- [x] 移除 `agent_profile_input_from_settings` 作为启动和 HTTP/CLI 日常写主路径；保留仅用于显式
  `sync-profiles` 兼容导入。
- [x] Settings Agent 页面改为读取 Agent owner API / Settings overlay 的组合 read model，不直接修改完整 profile payload。
- [x] Settings Agent enable/disable 在未接 dispatcher 前禁用，不再走通用 Settings action。
- [x] `sync-profiles` 明确成为迁移/恢复命令，不是日常写路径。
- [x] Agent owner API 增加 `GET /agents/{agent_id}/resolution` 只读解析预览；它通过 Agent owner
  profile、LLM/Tool/Skill/Access 公开 query surface 组合运行前事实，不写 Settings resource，也不从
  Operations projection 反推 profile 真相。

验收：

```bash
rg -n "agent_profile_input_from_settings|agent-profiles" src/crxzipple/modules/agent src/crxzipple/modules/settings frontend/src/pages/settings
```

不应再出现“Settings 写完整 Agent profile 后再 sync runtime”的主路径。

### C3. LLM 与 Channel Profile 复核

状态：基本完成，剩余仅为可选 owner dispatcher 设计。

- [x] 复核并落地：LLM profile 由 LLM service/repository 作为真相源。
- [x] 复核并落地：Channel profile 由 Channels profile service/store 作为真相源。
- [x] LLM 正常 `sync-profiles` 停止读取 Settings legacy `llm-profiles` resource。
- [ ] 如果后续要在 Settings 页面直接执行 profile 写动作，必须建立 per-kind owner dispatcher；当前先禁用通用动作。
- [x] shared 中移除 Agent/LLM/Channel 完整 profile schema，避免复制完整 entity。
- [x] 更新 `/llms`、channel profile CLI/HTTP 的写路径和测试。
- [x] 禁止 Settings 通用 enable/disable 直接改 `llm-profiles`、`channel-profiles` 后不触发 owner module。
- [x] 为 LLM/Channel profile 页面展示 owner、truth source 和 runtime apply status 的基础表达。
- [x] LLM/Channel profile 页面主列表与详情改读 owner API：`/llms`、`/channels/profiles`；Settings 只作为治理 overlay。

验收：

- LLM/Channel 的创建、更新、启停事件由 owner module 发出。
- Settings 页面展示清楚“治理配置 / 模块实体 / runtime 状态”的区别。

### C3A. Tool Catalog 拆 subtype 和生效策略

状态：未处理。

- [ ] 给 `tool-catalog` 资源增加明确 subtype：`provider`、`root`、`enablement`。
- [ ] provider/root action 不能只改 Settings payload；必须显示 `requires_tool_runtime_rebuild`
  或接 Tool application service 的 reload/apply workflow。
- [ ] enablement action 要么热更新 `ToolEnablementService`，要么明确 requires worker/API restart。
- [ ] 手动 `tool-worker run` 的 `max_in_flight` 也改为读取 materialized runtime defaults，或文档标注
  CLI 参数优先、core env fallback。
- [ ] Tool Settings UI 不展示 discovered tool/runtime state；这些继续归 Operations/Tool。

验收：

```bash
rg -n "tool-catalog|ToolEnablementService|tool_worker_max_in_flight" src/crxzipple/modules src/crxzipple/bootstrap
```

每条写路径都能说明 subtype 和生效时机。

### C3B. Skill Enablement 限域

状态：未处理。

- [ ] 将 `skill-catalog` 页面和资源文案限定为 skill enablement。
- [ ] 安装、validate、manifest、read、package catalog 继续走 Skills module。
- [ ] Settings action 修改 skill enablement 后补 hot reload 或 requires restart 标记。
- [ ] 前端隐藏任何未闭合的完整 skill catalog/create/install 假入口。

验收：

- Settings 不再自称拥有 skill package/catalog truth。
- Skills runtime usage 仍只从 Operations/Skills 观察。

### C4. Settings action dispatcher 收口

状态：基本完成，剩余 owner dispatcher / migration command 收口。

- [x] 为 Settings action 增加 kind ownership registry。
- [x] `settings-owned-config` 继续走 Settings action service。
- [ ] `module-owned-entity` 动作 dispatch 到 owner module application service。
- [x] `module-owned-entity` 在 dispatcher 接通前禁止通用 create/update/publish/rollback/enable/disable。
- [x] `module-owned-entity` 在 dispatcher 接通前也禁止通用 dry-run/validate，避免假成功。
- [x] `placeholder` 禁止 create/update/enable/disable/dry-run/validate。
- [x] action response 和 list/detail response 返回 `ownership`、`action_policy`、`apply_policy`。
- [x] 通用 `SettingsActionPanel` 使用集中 action policy，不再本地泛化推断 enable/disable。
- [ ] 通用 `SettingsActionPanel` 后续改为完全使用后台 action metadata，而不是前端薄 policy map。
- [ ] 每个 module-dispatched action 同时记录 Settings governance audit 和 owner module event/audit。

验收：

- 对 Agent/LLM/Channel profile 不能再只改 Settings resource 而不影响 runtime。
- Settings action 响应包含 `applied_by`、`owner_module`、`requires_restart` 或 `runtime_applied`。

### C5. Bootstrap 与 materializer 拆分

状态：部分完成。

- [x] 区分启动默认 seed 和 owner module bootstrap：profile 不再经 Settings materializer 进入运行真相。
- [x] module-owned profile 不参与 Settings materializer 的启动主链路。
- [x] `collect_core_settings_resources` 不再默认把 Agent profile 当 Settings-owned resource。
- [x] 停止默认 seed LLM profile 和 Channel profile 为 Settings-owned truth。
- [x] 删除 Settings setup 中未调用的 Agent / LLM / Channel profile seed helpers，避免误用。
- [x] materializer 启动主链路保留 Settings-owned config；module-owned profile helper 仅保留显式兼容导入。
- [x] module-owned entity 的 Settings UI read model 改走 owner query service / overlay，而不是历史 Settings resource。
- [ ] 对需要迁移的旧资源提供显式 migration command，不在每次启动静默搬家。

验收：

- container build 不再为了 Agent profile 执行 Settings -> Agent sync。
- 启动日志能区分 Settings config materialization 与 module runtime recovery。

### C6. Access 边界收紧

状态：部分完成。

- [ ] 明确 access setting 的资源分类：policy、binding declaration、provider scope enablement、
  permission enablement、redaction/export policy。
- [ ] Access action command 作为 secret/setup/readiness/grant 的唯一执行入口。
- [x] Access 配置写 intent 只通过 `AccessSettingsActionAdapter` 写 Settings-backed access declarations；
  adapter 缺失时直接失败，不再回落到 Access repository 旧写路径。
- [ ] 后续把 Settings-to-Access dispatcher 抽成更明确的 command port，避免 adapter 名义继续膨胀。
- [ ] `collect_access_inventory` 中 inferred 来源显式标注，不能和 Access repository truth 混淆。
- [ ] Settings Access 页面区分 configured、inferred、runtime readiness、secret material missing。
- [ ] Authorization runtime/evaluator 读取 policy 的生效路径必须明确：Settings payload、Access repository、
  Authorization repository 三者只能有一个 active source 或有清晰同步边界。

验收：

- Access runtime readiness 不写入 Settings resource。
- Secret 原值仍不进入 Settings payload、audit、projection。

### C6A. Memory / Runtime Defaults 生效策略

状态：未处理。

- [ ] 为 `memory-config` 每个字段标注 `hot_apply`、`requires_api_restart`、
  `requires_worker_restart` 或 `requires_reindex`。
- [ ] 为 `runtime-defaults` 每个字段标注影响范围：orchestration executor、tool scheduler、
  tool worker、daemon spec、current process only。
- [ ] Settings action 响应返回 apply policy 和 runtime applied status。
- [ ] Operations 页面显示当前进程/worker 实际使用的 runtime config snapshot，避免 Settings 显示与运行现场不一致。

验收：

- 修改 Settings 后，UI 不再暗示所有字段已经在线生效。
- Tool worker、orchestration executor、memory watcher 的实际配置能从 Operations 看到。

### C6B. Environment 敏感值与只读边界

状态：完成首轮收口。

- [x] `environment` resource 不保存原始 secret-bearing `database_url`；改为 redacted value、driver/host
  summary 或 secret ref。
- [x] Environment Settings action 在 backend 和 UI 均保持 validation-only，直到有完整 override workflow。
- [x] Settings resource/version payload 层不再由 bootstrap seed 写入 raw `database_url`。
- [x] 增加测试覆盖 `database_url` 中的用户名密码不会出现在 Settings version payload、audit、UI response。

验收：

```bash
rg -n "database_url" src/crxzipple/modules/settings tests/unit
```

能证明保存和返回路径都不会泄漏敏感连接信息。

### C7. Operations query port 化

状态：未处理。

- [ ] 为 Operations source provider 定义正式 query port/protocol，替代大 context + `Any`。
- [ ] 每个 provider 只依赖 owner module 暴露的通用 query service。
- [ ] 保留 observer/projection/event-driven 侧向结构，不回到前端拼 raw module API。
- [ ] 缺口继续落在 `docs/operations-data-truth-audit.md`。

验收：

- `modules/operations/application/read_models/factory.py` 不再直接传入大量模块内部服务。
- Operations 页面请求仍只读 projection/read model，不扫全库全 topic。

### C8. Settings UI 收口

状态：部分完成。

- [ ] Settings 子页复用 `useSettingsPage` 或统一 page adapter，不再每页复制 payload 类型和 loader。
- [x] 移除“Settings-owned agent profile”等错误文案。
- [ ] 隐藏未闭合的创建按钮，或接到 owner module action flow。
- [ ] action panel 从后台 action metadata 渲染；当前已集中为薄 policy map，等待后台 metadata 全量接入。
- [x] module-owned entity 页展示 owner、truth source、governance overlay、runtime apply status 的基础表达。
- [x] Agent Profiles 页接入 owner `resolution` 读面，新增 Resolve 标签展示 LLM/Tool/Skill/Access/Validation/Trace
  解析预览；列表分页改为真实 `pageSize/currentPage`，不再显示假分页控件。
- [ ] Tool/Skill/Access 这类 mixed kind 页面展示 subtype，不再把不同资源塞成同一种编辑/动作模型。
- [ ] Memory/Runtime/Environment 页面展示 apply policy，避免“保存即运行生效”的错觉。

验收：

```bash
rg -n "Settings-owned|New Agent Profile|runSettingsAction\\(" frontend/src/pages/settings
```

残留必须是有意设计，并能说明 owner module 生效路径。

## 推荐施工顺序

1. C0 文档护栏。
2. C1 资源分类表。
3. C4 action dispatcher 收口，先阻止继续绕写。
4. C2 Agent Profile 回收。
5. C3 LLM / Channel Profile 复核。
6. C5 Bootstrap / materializer 拆分。
7. C6 Access 边界收紧。
8. C8 Settings UI 收口。
9. C7 Operations query port 化。

不要并行改同一条写路径。Agent / LLM / Channel 可以并行审查，但落代码时每个模块要有清晰 owner 和测试边界。
