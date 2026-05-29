# Skill Governance Redesign Checklist 2026-05-20

本文档是 Skill 模块治理重构的施工清单。目标不是给 Settings 增加一层 skill
代理，也不是把 skill 继续停留在“文件扫描 + Settings overlay”的中间态；目标是让
Skills 模块成为 skill 内容索引、来源、安装、启停、readiness 和审计的 owner。

当前口径：

- Skills 是 owner。
- Settings 是操作面和治理入口。
- Operations 是观察面。
- Orchestration 是运行时消费者。

后续 agent 维护 skill 的能力以
[Skill Authoring Meta-Skill Checklist 2026-05-21](skill-authoring-meta-skill-checklist-20260521.md)
为施工入口：生成 skill 本身应由 `skill-authoring` meta-skill 驱动，落地必须走
Skills owner 的 draft、validate、diff、approve、apply 链路。

不接受最小迁移后长期双轨。旧 Settings-owned skill enablement overlay、运行时额外
adapter 和 UI 中的“not exposed by Skills HTTP”中间态都应在 cutover 阶段删除。

## 参考扫描结论

对比本地参考项目后，三种形态可以作为边界参照：

- Claude Code 偏运行时文件发现：skill 是 `SKILL.md -> PromptCommand`，由
  managed/user/project/add-dir 多层目录加载，通过 `SkillTool` 按需读取和执行 prompt
  command。它轻量，但不适合作为 CRXZipple 控制台治理的完整 owner 模型。
- OpenClaw 偏配置驱动：`skills.entries.*` 维护 per-skill enabled/env/config，
  `skills.load` 管目录和 watch，`skills.limits` 管扫描上限，并有 bundled、managed、
  workspace、extra、plugin 等来源优先级。
- Hermes 最接近治理台：`skills_list`/`skill_view` 做渐进读取，`skill_manage`
  支持 create/edit/patch/delete/write_file/remove_file，启停支持全局和按平台禁用，
  hub 安装有安全扫描，并返回 required env / credential readiness。

CRXZipple 的目标不是照搬其中任何一套，而是吸收 OpenClaw 的 source/lifecycle
分层和 Hermes 的 owner CRUD/readiness 形态，同时保持 DDD 模块边界。

## 当前基线

- `src/crxzipple/modules/skills/application/manager.py` 当前提供：
  - list available skills
  - get selected skill
  - read `SKILL.md` or package file
  - validate skill package
  - install skill package
- `src/crxzipple/modules/skills/infrastructure/filesystem/repository.py` 当前以文件系统为主：
  - workspace roots: `.crxzipple/skills`, `skills`
  - global root: `~/.crxzipple/skills`
  - system root: repo bundled `skills`
  - 运行态解析 `SKILL.md` frontmatter；legacy `skill.yaml` 只作为 validate/install
    迁移输入
- `frontend/src/pages/settings/modules/SkillCatalogSettingsPage.vue` 已切到
  `/skills/*` owner API；旧 Settings overlay 和 coverage 中间态已删除。
- `src/crxzipple/modules/skills/application/settings_integration.py` 与
  `SkillEnablementManagerAdapter` 已退场，Settings materialized enablement 不再注入
  Skills runtime。
- Orchestration 已改为通过 `SkillCatalogPort.resolve_prompt_catalog(...)` 获取
  Skills owner 解析后的 prompt catalog；旧 `orchestration.application.resolve_skill`
  已删除。
- `tools/skills/tool.yaml` 暴露 `skill_read`，用于按需读取本次 run 可见的 skill 包内容。

## 冻结口径

- Skill 内容文件是真相载体，DB 存索引、治理态、readiness、安装记录和审计，不把
  `SKILL.md` 正文复制为主真相。
- Skills 模块拥有 skill source、package index、enablement、readiness、installation。
- Settings 不保存 skill enablement 真相，不直接绕过 Skills application 修改 skill。
- Operations 不写 skill 真相，只消费 skill 事件和 Skills query/read model。
- Orchestration 只消费 `SkillCatalogPort` / `SkillPromptResolver`，不关心文件扫描和
  governance 实现。
- Agent profile 不恢复 skill 弱绑定。若后续要限制某个 agent 可用哪些 skill，应通过
  authorization 或 resolution policy 做过滤。
- Skill 不授予权限，也不直接执行业务。真正执行仍由 Tool、Access、Authorization、
  Workspace、Memory 等模块负责。
- 被禁用、缺 readiness、surface 不匹配或 authorization 不允许的 skill 不进入 prompt，
  `skill_read` 也不能读取。

## 目标运行链路

```text
Agent / Run context
  -> Orchestration Prompt Assembler
  -> SkillPromptResolver
  -> Skills owner query/readiness
  -> Available Skills prompt block
  -> model decides
  -> skill_read(skill, path?)
  -> model follows guidance
  -> regular tools execute work
```

运行时只暴露 skill 的精简 catalog：名称、描述、适用条件、requirements、资源摘要。
完整 `SKILL.md` 和支持文件必须通过 `skill_read` 按需读取。

## 领域模型 Checklist

- [x] 新增 `SkillSource`：
  `source_id/root_path/source_kind/scope/priority/enabled/readonly/metadata`。
- [x] 新增 `SkillPackageIndex`：
  `package_id/name/source_id/root_path/manifest_path/instructions_path/version/fingerprint/status/indexed_at/updated_at`。
- [x] 新增 `SkillEnablementPolicy`：
  支持 global/source/skill/tag/surface 维度 enable/disable，记录 priority 和 reason。
- [x] 新增 `SkillReadiness`：
  `ready/setup_needed/unsupported/disabled/invalid`，记录 missing tools、missing access、
  unsupported platform、validation errors。
- [x] 新增 `SkillInstallation`：
  install/import/create/update/delete/sync 记录，包含 source、target、actor、reason。
- [x] 新增 skill operation event：
  已接通 `skills.package.created`、`skills.package.updated`、
  `skills.package.deleted`、`skills.package.enabled`、`skills.package.disabled`、
  `skills.package.validate_succeeded/failed`、`skills.package.install_succeeded/failed`、
  `skills.read.succeeded/failed`、`skills.source.created/updated/deleted/synced`、
  `skills.readiness.changed`。

## 数据库与仓储 Checklist

- [x] 新增 Postgres migration: `skill_sources`。
- [x] 新增 Postgres migration: `skill_packages`。
- [x] 新增 Postgres migration: `skill_enablement_policies`。
- [x] 新增 Postgres migration: `skill_readiness`。
- [x] 新增 Postgres migration: `skill_installations`。
- [x] 增加唯一约束：同一 source 下 skill name 唯一。
- [x] 增加 fingerprint，用于检测 `SKILL.md`、manifest 和支持文件变更。
  Filesystem repository 会基于 `SKILL.md`/manifest 和资源文件内容生成 package
  fingerprint，owner catalog 只保存索引摘要。
- [x] Repository 支持 source CRUD、package index CRUD、enablement query、readiness
  upsert、installation audit。
- [x] 文件内容仍由 source root 持有，DB 不作为 `SKILL.md` 正文主真相。

## 文件扫描与索引 Checklist

- [x] 统一以 `SKILL.md` frontmatter 为当前格式。
  `FilesystemSkillRepository.list/get/read/sync` 的运行态扫描只加载 `SKILL.md`
  frontmatter；测试 helper 也默认产出 current-format package。
- [x] `skill.yaml` 仅作为迁移输入保留，不继续扩展旧 schema。
  `validate/install` 明确允许读取 legacy sidecar；`install` 会把 legacy package
  物化为 `SKILL.md` frontmatter，并移除安装目标中的 `skill.yaml`。
- [x] 扫描时校验 path traversal、symlink escape、超大文件、缺 instructions、frontmatter
  必填字段。
- [x] 支持 source 优先级：workspace > global > managed/external > system。
- [x] readonly/system source 禁止编辑和删除。
- [x] sync 时能标记 missing/removed，不静默消失。
- [x] sync 后发布 `skills.source.synced` 事件。
- [x] 未实现 watcher 前不暴露 watch 配置，避免假功能。
  已移除 `watch_enabled` / `watch_debounce_ms` 的 domain、API、CLI、frontend type
  和新 migration 字段；后续若实现 watcher，需单独按 `SKILL.md` 与 resource 白名单
  设计事件源。

## Application 服务 Checklist

- [x] `SkillSourceService`：source CRUD、enabled/readonly 更新、sync/reindex。
  Source create/update/delete/sync 已从 `SkillManager` 拆出；source 启停通过 source
  update 的 enabled 字段治理，sync 后写 source/package index、readiness snapshot 和事件。
- [x] `SkillPackageService`：create/install/import/update/delete/read/validate。
  Package create/update/write/read/validate/install/delete 已从 `SkillManager` 拆出，统一处理
  package 事件、安装审计和 source reindex。
- [x] `SkillCatalogService`：list/get/build catalog/resolve prompt catalog。
  Catalog 查询和 prompt catalog 解析已从 `SkillManager` 拆出，运行时不再直接关心文件扫描。
- [x] `SkillGovernanceService`：enable/disable policy resolve。
  Skill enable/disable 已从 `SkillManager` 拆出，由 owner catalog policy 写入治理真相。
- [x] `SkillReadinessService`：owner readiness 查询和 snapshot 持久化。
  当前 run prompt readiness 仍由 `SkillPromptResolver` 聚合 Tool、Access、Authorization
  和 surface；owner readiness 查询与持久化已拆成独立 service。
- [x] `SkillPromptResolver`：输出本次 run 可见、可读、ready 的 skill catalog。
- [x] `SkillPromptResolver` 产出的 run readiness 会回写 owner readiness snapshot，并在
  语义变化时发布 `skills.readiness.changed`。
- [x] owner readiness 查询和删除 reconciliation 会回写 readiness snapshot，并在语义
  变化时发布 `skills.readiness.changed`，不再只等 run prompt resolve 才进入观察链路。
- [x] 移除 `SkillEnablementManagerAdapter` 和 Settings materialized enablement runtime
  注入。
- [x] 所有 mutate 操作写事件和 audit，不只更新文件。
  package create/update/write/delete、enable/disable 已写事件；audit 表与
  source 事件已接通；readiness 变化事件已接通；`skill_installations` 记录
  package/source create/update/delete/sync/install/enable/disable。

## HTTP / CLI API Checklist

- [x] `GET /skills` 支持
  `workspace_dir/surface/source/include_disabled/include_readiness/include_removed`。
- [x] `GET /skills/{name}` 返回详情、resources、readiness、enablement、source。
- [x] `POST /skills` 新建 skill package。
- [x] `PATCH /skills/{name}` 更新 manifest/frontmatter 元信息。
- [x] `PUT /skills/{name}/instructions` 更新 `SKILL.md` 正文。
- [x] `PUT /skills/{name}/files/{path}` 写支持文件。
- [x] `DELETE /skills/{name}/files/{path}` 删除支持文件。
- [x] `POST /skills/{name}/enable`。
- [x] `POST /skills/{name}/disable`。
- [x] `DELETE /skills/{name}`。
- [x] `POST /skills/install` 接入新 installation 记录。
- [x] `POST /skills/validate` 接入新 validator 和 readiness preview。
- [x] `POST /skills/sync`。
- [x] `GET /skills/sources`。
- [x] `POST /skills/sources`。
- [x] `PATCH /skills/sources/{source_id}`。
- [x] `DELETE /skills/sources/{source_id}`。
- [x] CLI 同步补齐 list/get/read/create/install/delete/enable/disable/sync/source。
  已接通 list/show/install/delete/enable/disable/sync/source/create/update/
  write-instructions/write-file/delete-file；source create/update/delete 已接通；
  `get` 与 `read` 已补齐。

## Runtime 接入 Checklist

- [x] Prompt assembler 不再手写 `list_available + ResolveSkill` 简化判断，改用
  `SkillPromptResolver`。
- [x] `SkillPromptResolver` 对接 Tool Function catalog，判断 required tools 是否存在且可用。
- [x] `SkillPromptResolver` 对接 Access readiness，判断 required access / credential 是否可用。
- [x] `SkillPromptResolver` 对接 Authorization，判断当前 run 是否允许使用该 skill
  声明的 required effects。
- [x] `SkillPromptResolver` 对接 surface 运行环境，surface 不匹配不进入 prompt。
- [x] `SkillPromptResolver` 对接 runtime platform，判断 `supported_platforms`
  是否匹配当前运行平台；不匹配时 readiness 为 `unsupported`，并写入
  `unsupported_platforms`、checks 和 readiness changed 事件。
- [x] `skill_read` 继续只允许读取本次 run 的 `available_skill_names`。
- [x] `skill_read` 返回 content、resources、readiness metadata。
- [x] `skill_read` 只能读 skill package 内文件，不能读任意路径。
- [x] 被禁用、未 ready、surface 不匹配或 authorization 不允许的 skill 不进入 prompt。
- [x] Skill catalog prompt 保持精简，完整内容必须按需读取。

## Settings UI Checklist

- [x] 移除 `skill-catalog` 的 Settings-owned enablement overlay。
- [x] Skill 页面只调用 `/skills/*` owner API。
- [x] 主表显示：Skill、Source、Enabled、Ready、Surface、Tools、Access、Updated。
- [x] 详情区显示：Instructions、Resources、Readiness、Source、Audit。
  Settings Skill 页面已接入 `/skills/installations`，详情侧展示 package/source/readiness/
  resources/audit，Instructions 通过 owner API 读取。
- [x] 新建/编辑使用表单和 markdown 编辑器，不让用户直接改 JSON。
  Skill 页面新增表单式 create/update 和 Instructions Markdown 编辑器，保存走
  `/skills`、`PATCH /skills/{name}`、`PUT /skills/{name}/instructions`。
- [x] Enable/Disable/Delete/Sync/Validate 全部接通真实 Skills API。
- [x] Source 管理放入 source tab 或右侧抽屉。
  Source 管理已放入右侧 Sources 面板，支持 create/update/delete/sync，全部调用
  Skills owner source API。
- [x] 删除 coverage 行中的 “not exposed by Skills HTTP” 中间态。
- [x] loading/empty/error 状态保持稳定布局。

## Operations Checklist

- [x] Operations Skills 页读取 Skills query/read model，不绕到 Settings。
- [x] 接入事件：sync、install、validate、enable、disable、readiness_changed、read。
  Skills owner 已发布 `skills.readiness.changed`；Operations Skills read model 已消费该事件
  修正状态和缺失项。Operations observer 静态订阅已包含 Skills 事件，
  materializer 已覆盖 `skills` 事件到 `skills`/`events` projection 的刷新映射。
  Skills Operations read model 直接读取 `SKILL_OPERATION_EVENT_NAMES` 声明 topic，不再扫描
  整条 event bus。
- [x] 展示 installed/ready/disabled/invalid/source 分布。
  Operations Skills 页的 readiness donut 已覆盖 ready/setup/unsupported/disabled/invalid，
  source 分布 chart 已接入 source 维度。
- [x] 展示缺失项：missing tools、missing access、unsupported platform、invalid package。
  Missing Capabilities、Capability Requirements、Resolver Detail 和 drawer requirements
  已消费 `unsupported_platforms`，同时保留 missing tool/access/effect 展示。
- [x] 展示最近 skill read、失败原因和耗时。
  Operations Skills 页新增 `Skill Reads` 表，单独展示 `skills.read.succeeded/failed`
  的 skill、path、surface、result、duration 和失败原因，不再只能混在通用解析日志里看。
- [x] Operations action 通过 Skills application action port 执行 validate/install/sync，不直接写文件。
  `/operations/skills/validate`、`/operations/skills/install`、`/operations/skills/sync`
  都通过 `OperationsActionService -> SkillManager` 调用 Skills application，并写
  Operations action audit。

## 安全与治理 Checklist

- [x] 禁止 skill 读取任意路径，只能读包内文件。
- [x] readonly/system skill 禁止 UI 编辑和删除。
- [x] 外部安装必须 validate 后才能入库。
- [x] required access 只引用 Access binding 或 requirement id，不接受明文 secret。
  `required_secrets` / `required_credential_files` / `required_auth` 已退场；
  `required_access` 拒绝 `env:`、`file:`、`codex_auth_json`、`auth_ref` 和本地路径。
- [x] required tools 只引用 ToolFunction id。
  `required_tools`/`optional_tools`/`suggested_tools` 拒绝 credential source 和路径形态。
- [x] source root 必须做 realpath containment 校验。
- [x] 所有 mutate 操作写 audit/event。
- [x] 删除 skill 时处理文件删除、index 状态、readiness 状态和事件一致性。
  `sync(source_id=...)` 会对 owner catalog 做差异 reconciliation：source 中消失的包标记为
  `removed`，对应 readiness 标记为 `invalid/removed`，删除动作继续发布
  `skills.package.deleted`。
- [x] readiness 不在前端推断，由后端给出。

## 清理 Checklist

- [x] 删除 Settings materializer 中 `skill_enablements` 对 runtime 的注入。
- [x] 删除 `SkillEnablementManagerAdapter`。
- [x] 删除 Settings Skill 页面中的 overlay resource 匹配逻辑。
- [x] 删除 Settings Skill 页面中 coverage “not exposed by Skills HTTP” 行。
- [x] 清理旧文档中 “Settings owns skill enablement” 的描述。
- [x] 更新 `docs/agents/hosted-agent-operating-contract.md`，写入 skill owner 边界。
- [x] 更新 `docs/README.md` 文档入口。

## 验证 Checklist

- [x] 单测：source sync、path safety、readonly、fingerprint、enablement resolve。
  已补 owner catalog 删除一致性回归：uninstall 后 package index 为 removed，
  readiness 为 invalid/removed；已补 fingerprint 内容变更、source precedence、
  resource symlink escape、prompt summary-only 回归。
- [x] 单测：owner readiness 查询和删除 reconciliation 发布 `skills.readiness.changed`。
- [x] 单测：prompt readiness 聚合 Tool / Access / Authorization / surface。
- [x] 单测：run prompt readiness 变化会持久化并发布 `skills.readiness.changed`。
- [x] 单测：`skill_read` 只能读本次 available skill。
- [x] API 测试：CRUD、enable/disable、delete、sync、source CRUD。
  已覆盖 list/show/validate/install/create/update/write-instructions/write-file/
  delete-file/enable/disable/delete/sync/sources/source CRUD。
- [x] CLI 测试：list/get/read/create/install/delete/enable/disable/sync/source。
  已覆盖 list/show/validate/install/create/update/write-instructions/write-file/
  delete-file/delete/enable/disable/sync/source/source CRUD。
- [x] Operations read model / event 测试。
  已覆盖 `skills.readiness.changed` 对 Skills read model 状态/缺失项的影响，
  以及 observer 静态订阅和 materializer projection 映射。
- [x] Settings Skill 页面 typecheck。
- [x] `frontend` build。
- [x] 迁移测试：现有 filesystem skill 可被重新索引并正常进入 prompt。
- [x] 架构守卫：禁止 Settings 重新注入 skill enablement runtime adapter。

## 迁移顺序

1. 新增 domain model、repository port 和 persistence migration。
2. 新增 source/package/readiness application services。
3. 把当前 filesystem scan 改为 `sync -> package index -> query`。
4. 补齐 owner HTTP / CLI API。
5. 切换 Orchestration 到 `SkillPromptResolver`。
6. 改造 `skill_read` 只依赖 resolver 产出的 available/readable 集合。
7. Settings Skill 页面改为纯 Skills owner API。
8. Operations 接入 skill query service 和 skill events。
9. 删除 Settings overlay、adapter 和旧文档口径。
10. 做全量验证和架构守卫。

## 完成定义

- Skills 模块能独立回答：有哪些 skill、来自哪里、是否启用、是否 ready、缺什么、能否读取、
  能否编辑、谁改过。
- Settings 不再持有 skill enablement 真相。
- Orchestration 不直接扫描文件，不直接推断治理态，只消费 Skills resolver。
- Operations 能展示 skill source、readiness、使用和失败事实。
- 旧 adapter 和兼容中间态已删除，而不是继续隐藏在装配层。
