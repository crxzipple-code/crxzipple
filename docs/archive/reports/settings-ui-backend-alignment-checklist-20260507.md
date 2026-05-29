# Settings UI 与后台设计对齐清单 2026-05-07

> 2026-05-08 corrective note: 本文档仍可作为 Settings UI 接线历史和页面差异参考，
> 但其中把 Agent / LLM / Channel profile 视为 Settings-owned truth 的判断已经过期。
> 当前边界、风险和整改顺序以
> `docs/reports/settings-module-boundary-complexity-review-20260508.md` 为准。

本文档记录当前 Settings 前端模板与后台 Settings 治理设计的差异，并给出后续接入、滞后、移除的任务清单。它替代早期“Settings 只有静态 UI、后台缺 `/ui/settings`”的旧判断。

## 当前结论

Settings 后台已经不是只读 read model。当前设计是：Settings 模块持有配置资源、版本、覆盖、生效解析、快照和 Settings action audit；各业务模块在启动或同步阶段消费 Settings materializer 产出的 shared config。

施工前，Settings 前端没有跟上这个结构。`frontend/src/pages/settings/SettingsShell.vue` 已经有 13 个页面模板，但除 `AccessAssetsSettingsPage.vue` 外，大部分页面仍是静态数组和假操作。Access 页虽然接了真实接口，但接的是 `/ui/access`，不是 Settings-owned access config resources。

2026-05-07 本轮施工后，Settings UI 已建立 `/ui/settings*` API 层，并将 Overview、Audit、LLM、Tool、Memory、Runtime、Agent、Channel、Access、Skill Enablement、Environment、Event placeholder、Backup placeholder 页面改为 Settings 主数据源。Event Registry 与 Backup Restore 已从主导航移除，直达 URL 只显示只读 placeholder。

同日收尾追加：LLM、Tool、Memory、Runtime、Agent、Channel 资源页已接入通用 Settings 治理操作面板，当前只开放后台语义闭合的 `validate`、`dry-run`、`enable`、`disable`，写操作强制填写 reason 并走 Settings action audit；`create`、`update`、`publish`、`rollback` 仍需要专门表单/版本选择，不进入通用面板。Access migration plan 也已能导入为 Settings-owned `access-assets` 配置声明，`bootstrap-import` 会同时返回 core 与 access 两段导入结果。

当前本机 API 快照如下，资源数量只代表当前环境，不代表后台能力不存在：

| kind | 当前状态 | 当前资源数 | 结论 |
| --- | --- | ---: | --- |
| overview | warning | 11 total | 可接，缺失项需要在 UI 中真实展示 |
| agent-profiles | empty | 0 | 后台可接，当前环境无资源 |
| llm-profiles | ready | 6 | 优先接 |
| tool-catalog | ready | 2 | 优先接，但只接治理配置，不冒充运行工具目录 |
| skill-catalog | empty | 0 | 限域接，只接 skill enablement |
| memory-config | ready | 1 | 优先接 |
| access-assets | empty | 0 | 限域接，需要先把 Access 配置真相导入 Settings |
| channel-profiles | empty | 0 | 后台可接，当前环境无资源 |
| event-registry | empty | 0 | 滞后，当前只是 Settings placeholder |
| runtime-defaults | ready | 1 | 优先接 |
| environment | ready | 1 | 限域接，先修脱敏和只读解析 |
| audit-logs | ready | 0 | 优先接，当前为空态 |
| backup-restore | empty | 0 | 移除或隐藏 |

## 后台事实

- Settings HTTP 已注册在 `/settings` 和 `/ui/settings`，支持 overview、list、detail、action 与 bootstrap import。
- 当前统一 kind 包括 `agent-profiles`、`llm-profiles`、`tool-catalog`、`skill-catalog`、`memory-config`、`access-assets`、`channel-profiles`、`event-registry`、`runtime-defaults`、`environment`、`audit-logs`、`backup-restore`。
- 写操作支持 `create`、`update`、`publish`、`rollback`、`enable`、`disable`，并要求 `reason`。
- 启动 seed 目前只采集 agent、llm、tool、memory、channel、runtime、environment。没有自动 seed skill、access、event、backup。
- materializer 已支持 llm、agent、tool provider/root/enablement、skill enablement、channel、memory、runtime、access config。没有 event registry 和 backup restore materializer。
- 容器已经在模块启动前 materialize Settings，并把 LLM、Agent、Tool、Skill、Channel、Memory、Runtime、Authorization 等消费路径接到 Settings。
- Access 的运行时授权、readiness、setup、secret handling 仍由 Access 模块负责；Settings 只应该持有 access/authorization 的可治理配置真相。

## 施工前前端模板事实

- `SettingsShell.vue` 已有完整导航，但只负责本地路由和组件切换，没有数据加载。
- `OverviewSettingsPage.vue`、`AgentProfilesSettingsPage.vue`、`LlmProfilesSettingsPage.vue`、`ToolCatalogSettingsPage.vue`、`SkillCatalogSettingsPage.vue`、`MemoryConfigSettingsPage.vue`、`ChannelProfilesSettingsPage.vue`、`EventRegistrySettingsPage.vue`、`RuntimeDefaultsSettingsPage.vue`、`EnvironmentSettingsPage.vue`、`AuditLogsSettingsPage.vue`、`BackupRestoreSettingsPage.vue` 基本使用静态数组。
- `AccessAssetsSettingsPage.vue` 已用 `requestJson`，但读取 `/ui/access` 和 `/ui/access/assets/{id}`，它现在是 Access control plane snapshot，不是 Settings 配置治理真相。
- `frontend/src/shared/runtime/contracts.ts` 中 SettingsResourceId 仍保留 `event-contracts`，而后台与 Shell 使用 `event-registry`。Shell 虽做了 alias，但共享契约需要统一。
- i18n 仍显示 `Event Contracts`，与后台 `Event Registry` 命名不一致。
- 侧边栏 `settings.documentation` 当前链接到 `/settings/audit-logs`，不是文档页，应移除或改为真实帮助入口。

## 接入决策

| UI 模块 | 决策 | 原因与边界 |
| --- | --- | --- |
| Overview | P0 立即接 | `/ui/settings` 已能返回 counts、health、issues、recent changes。需要替换全部静态指标。 |
| Audit Logs | P0 立即接 | `/ui/settings/audit-logs` 已有分页 list/detail。当前为空也要真实空态，不能继续显示 2025 假日志。 |
| LLM Profiles | P0 立即接 | 当前已有 6 个 Settings 资源，且 LLM runtime 已从 Settings materializer 消费。Provider health、capability test 不属于 Settings 真相，先隐藏或链接到 Operations/LLM。 |
| Memory Config | P0 立即接 | 当前已有 default 资源，页面应展示生效值、解析来源、版本和 validation。 |
| Runtime Defaults | P0 立即接 | 当前已有 defaults 资源，且 orchestration/tool worker/daemon 已消费 materialized config。 |
| Tool Catalog | P0 限边界接 | 当前后台资源是 provider/root/enablement，不是运行时 discovered tool 目录。UI 要改成“工具配置治理”，运行统计与工具执行状态留在 Operations/Tool。 |
| Agent Profiles | P0 可接 | 后台、shared contract、materializer、模块消费路径都已具备。当前环境资源数为 0，所以先接真实空态、创建/导入动作和 detail 骨架。 |
| Channel Profiles | P0 可接 | 后台和 channel profile parser 已具备。当前环境资源数为 0，所以先接真实空态与资源 action。 |
| Access Assets | P1 限域接 | 现有 UI 接的是 `/ui/access`。需要先把 access asset、credential binding、consumer binding、authorization policy 等配置声明导入 Settings，再合并 Access readiness。 |
| Skill Catalog | P1 已切 owner API | Settings 作为治理入口调用 `/skills/*`。技能包发现、安装、manifest、启停、readiness、source、read/catalog 真相均属于 Skills 模块，不能恢复 Settings-owned overlay。 |
| Environment | P1 限域接 | 后台有 environment resource，但模板里的 variables/secrets/groups 没有对应治理模型。先只做 read-only 生效解析，并加强敏感字段脱敏。 |
| Event Registry | P2 滞后 | 后台只是 placeholder；event contract/definition 真相还在 Events registry。Settings 页面先隐藏写操作，或只链接到 Operations/Events。 |
| Backup Restore | P3 移除或隐藏 | 当前无 backup/restore 应用服务、存储策略、dry-run、restore workflow。保留页面会误导。 |
| Settings Documentation | P3 移除 | 当前链接到 audit logs，不是真文档入口。 |
| 静态 Quick Actions | P3 隐藏 | New Agent/Add LLM/Register Tool/Create Skill/Add Channel/Define Event 等按钮不能在 action form 和 reason/audit 没闭合前展示为可用。 |

## 必须先清的差异

- 前端共享类型统一为 `event-registry`，清理 `event-contracts` 的 Settings resource id。
- i18n 统一命名，避免 UI 显示 Event Contracts、后台返回 Event Registry。
- 新增 Settings 前端 API 层，不能每个页面手写 `requestJson`：
  - `getSettingsOverview()`
  - `listSettingsResources(kind, pagination)`
  - `getSettingsResource(kind, resourceId)`
  - `runSettingsAction(kind, resourceId, action, payload, reason)`
- 增加通用 Settings 页面状态：loading、error、empty、stale、pagination、selected detail。
- 写操作必须弹出 reason 输入，后端已经要求 reason。
- 环境资源展示前先修敏感值脱敏。当前 key-based redaction 不会因为字段名 `database_url` 自动隐藏连接串中的密码。
- 移除静态 mock 数字、假日期、假用户、假 provider health、假 backup size。

## 施工清单

### S0. 文档与边界

- [x] 建立本对齐清单。
- [x] 将旧的 Settings 接入文档标注为过期，并指向本文档。
- [x] 在 agent 约束文档中补充：Settings UI 只能消费 `/ui/settings*`，Access runtime readiness 作为辅助事实，不作为配置真相。

### S1. 前端基础接入

- [x] 新增 `frontend/src/pages/settings/api.ts`，封装 `/ui/settings*`。
- [x] 补齐 Settings TypeScript 类型，或把 `frontend/src/shared/runtime/contracts.ts` 的 Settings 类型改到与后端字段一致。
- [x] 清理 `event-contracts` 和 `event-registry` 的命名冲突。
- [x] 抽一个轻量 composable，例如 `useSettingsPage(kind)`，统一加载、分页、错误和选中资源。
- [ ] SettingsShell 传入 active kind，不再让子页各自维护静态数据源。

### S2. 优先接 P0 页面

- [x] Overview 接 `/ui/settings`：resource counts、missing kinds、health、recent changes、issues、distribution、useful links。
- [x] Audit Logs 接 `/ui/settings/audit-logs`：分页表格、详情抽屉、真实空态。
- [x] LLM Profiles 接 `/ui/settings/llm-profiles`：列表、detail、effective config、versions、audit、治理操作 reason 表单。
- [x] Memory Config 接 `/ui/settings/memory-config`：default config、resolution trace、validation、versions、治理操作 reason 表单。
- [x] Runtime Defaults 接 `/ui/settings/runtime-defaults`：orchestration/tool/daemon 分组展示、治理操作 reason 表单。
- [x] Tool Catalog 接 `/ui/settings/tool-catalog`：provider/root/enablement 三类资源，不展示运行时调用统计，接入治理操作 reason 表单。
- [x] Agent Profiles 接 `/ui/settings/agent-profiles`：真实空态、导入/创建入口、detail 骨架；有资源时显示治理操作 reason 表单。
- [x] Channel Profiles 接 `/ui/settings/channel-profiles`：真实空态、导入/创建入口、detail 骨架；有资源时显示治理操作 reason 表单。

### S3. Access 限域接入

- [x] 定义 access Settings resource import：asset、credential binding、consumer binding、authorization policy、provider scope enablement、permission enablement。
- [x] Access Settings 页主数据源改为 `/ui/settings/access-assets`。
- [x] Access runtime readiness 从 `/ui/access` 或后端组合层作为辅助状态合入，不再作为配置真相。
- [x] Secret 原值永不出现在 Settings UI，只显示 binding、masked preview、readiness、setup availability。
- [x] Access 配置写动作通过 AccessActionService -> AccessSettingsActionAdapter -> Settings action audit；Access runtime audit 不吞并 Settings 配置审计边界。

### S4. P1/P2 页面收缩

- [x] Skill Catalog 改名或限域为 Skill Enablement，隐藏 create skill package、manifest 编辑、包安装等未接后台能力。
- [x] Environment 先改成 read-only effective environment，隐藏 secrets/groups/import/export 编辑器。
- [x] Event Registry 暂时从主导航移除，或显示 read-only “由 Events registry 提供”并链接到 Operations/Events。
- [x] Backup Restore 从主导航移除，后续等 backup service、storage policy、dry-run 和 restore workflow 成型后再恢复。
- [x] 移除 Settings Documentation 到 audit logs 的伪链接。

### S5. 后台补强

- [x] Settings HTTP 红线：`database_url`、URL 内嵌密码、DSN、authorization path 等敏感字段统一脱敏。
- [x] 修正 `get_settings_resource_detail` 中重复 `return _resource_detail_payload(...)`。
- [x] 增加 `/ui/settings` 响应模型测试，覆盖 kind alias、分页、detail、reason required、audit 空态。
- [x] 增加 access config import/materialization 测试，确认 Access runtime readiness 不反向成为 Settings truth。
- [x] 明确 event-registry 和 backup-restore 在后台中的 placeholder 状态，避免 UI 误判为可编辑模块。

### S6. 验收

- [x] `pytest tests/unit/test_settings_http.py tests/unit/test_settings_module.py tests/unit/test_settings_contracts.py`
- [x] `cd frontend && npm run typecheck`
- [x] `cd frontend && npm run build`
- [x] Playwright 检查 `/settings`、`/settings/llm-profiles`、`/settings/tool-catalog`、`/settings/audit-logs`、`/settings/access-assets`。
- [ ] Playwright 验收 skeleton 与真实数据布局高度稳定，无假数据闪烁。当前只完成真实数据/空态截图冒烟，尚未做 loading skeleton 差分。
- [x] 用真实 API 快照验证空态：agent/channel/skill/access/event/backup 为空时页面不显示假卡片。
