# Skill Authoring Meta-Skill Checklist 2026-05-21

本文档是 Skill 模块 authoring / meta-skill 升级的施工与收口记录。目标是让 agent
在完成任务后，能够把
可复用经验沉淀为 skill；同时保持 Skill 模块作为 owner，确保创建、校验、授权、
审阅和落盘都在受控链路里完成。

核心判断：

- 生成 skill 本身应该是一种 skill，而不是散落在 Settings 表单、临时 prompt 或
  orchestration 特例里的功能。
- `skill-authoring` 负责教 agent 如何提炼经验、组织 instructions、声明依赖和生成
  draft。
- Skills module 负责 owner truth、校验、diff、apply、sync、readiness 和 audit。
- Tool function 只是 agent 调用 Skills application 的受控执行面。
- UI 是审阅和治理台，不是唯一作者。

不接受把 agent 直接放开去写文件；也不接受绕过 Skills owner API 的兼容通道。

## 公开生态参考

可参考但不照搬：

- Anthropic `anthropics/skills`：skill 以 `SKILL.md` 为核心，强调自包含目录和
  frontmatter 触发语义。
- OpenAI `openai/skills` 的 `skill-creator`：把创建和更新 skill 本身设计为
  meta-skill，强调精简、渐进披露、resources/scripts/assets 的分层。
- Microsoft `microsoft/skills` 的 `skill-creator`：强调通过文档来源、校验和测试
  场景来生产可维护 skill。
- 社区 skill 仓库普遍采用“meta skill + package validation + examples”的模式，而
  不是把创建过程写死在产品表单中。

CRXZipple 的落地方式应符合本仓库 DDD 边界：meta-skill 提供生成方法，Skills
application 提供治理用例，Access/Tool/Authorization 提供依赖真相。

## 目标用户故事

用户在一个 agent 任务完成后说：

> 把这次处理经验转成一个 skill。

系统应支持以下链路：

1. Orchestration 根据用户意图把 `skill-authoring` 放进可用 skill。
2. LLM 读取 `skill-authoring`，总结本次任务经验。
3. LLM 调用 agent-facing skill authoring tools 创建 draft。
4. Skills module 校验 draft 的 `SKILL.md`、frontmatter、resources 和 requirements。
5. Draft readiness 查询 Tool、Access、Authorization 的 owner API，返回缺失依赖。
6. 前端或 approval 面板展示 diff、readiness 和风险。
7. 用户确认后，系统 apply 到可写 source，写 audit，发布事件，触发 sync/readiness。

这条链路必须支持新建 skill 和更新已有 skill。

## 边界决策

- `skill-authoring` 是系统内置 skill，放在 repo bundled skill source 下，例如
  `skills/skill-authoring/SKILL.md`。
- `skill-authoring` 不直接写文件，不携带私有凭证，不声明越权行为。
- `skill-authoring` 的职责是指导 LLM 产出结构化 draft，不是把 Skills application
  的校验逻辑复制一份。
- Skills module 新增 authoring application service，统一处理 draft 生命周期。
- Agent-facing tool function 只调用 Skills application，不直接访问 filesystem。
- `apply` 必须经过 authorization effect 和用户确认，不能让 agent 静默写入。
- Settings 可以人工编辑 skill，但 agent 维护主路径应是
  `draft -> validate -> diff -> approve -> apply`。
- Operations 只观察 authoring 事件和 readiness，不参与决策。

## 目标架构

```text
User request
  -> Orchestration
  -> skill-authoring meta-skill enters prompt
  -> model summarizes reusable experience
  -> skill_draft_create / skill_draft_update
  -> Skills Authoring Service
  -> validate requirements through Tool / Access / Authorization ports
  -> skill_draft_diff
  -> approval / Settings review
  -> skill_draft_apply
  -> Skills Package Service writes owner truth
  -> sync package index + readiness
  -> events + audit
```

## System Skill Contract

新增内置 skill：`skill-authoring`。

建议结构：

```text
skills/skill-authoring/
├── SKILL.md
└── references/
    ├── skill-quality-checklist.md
    ├── requirement-mapping.md
    └── examples.md
```

`SKILL.md` 应保持短而可执行：

- 什么时候触发：
  用户要求把经验、流程、踩坑、领域知识、工具用法沉淀为 skill。
- 如何提炼：
  从任务目标、约束、有效步骤、失败模式、工具依赖、验收方式中抽取。
- 如何判断是否应该创建 skill：
  可复用、边界清晰、能降低未来上下文成本、不是一次性对话总结。
- 如何组织内容：
  `name`、`description`、`when_to_use`、`anti_patterns`、instructions、references、
  resources。
- 如何声明 requirements：
  只能引用 Tool Function ID、Access requirement/binding、Authorization effect、
  surface、platform；不能写 env、文件路径或凭证值。
- 如何验证：
  生成 draft 后必须调用 validate/diff，不直接 apply。

`references/skill-quality-checklist.md` 放质量规则：

- skill 是否过宽或过窄。
- description 是否能准确触发。
- instructions 是否给模型保留合理自由度。
- 是否把大段参考移动到 references。
- 是否没有泄露用户敏感信息。
- 是否包含验收 prompt 或 failure examples。

`references/requirement-mapping.md` 放依赖映射规则：

- 从任务中识别可能需要的 Tool Function。
- 从外部服务识别 Access requirement。
- 从写入、网络、文件、远程执行识别 Authorization effect。
- 无法确认时标记为 suggested，不写成 required。

## Domain / Application Model

新增或扩展以下 application model：

- `SkillDraft`
  - `draft_id`
  - `status`: `draft | validated | invalid | applied | rejected | expired`
  - `intent`: `create | update`
  - `skill_name`
  - `target_source_id`
  - `target_scope`: `workspace | global`
  - `workspace_dir`
  - `base_fingerprint`
  - `manifest`
  - `instructions_body`
  - `support_files`
  - `requirements`
  - `validation`
  - `diff`
  - `created_by_run_id`
  - `created_by_turn_id`
  - `actor`
  - `reason`
  - `created_at / updated_at / expires_at`

- `SkillDraftValidation`
  - `errors`
  - `warnings`
  - `missing_tools`
  - `missing_access`
  - `missing_effects`
  - `unsupported_surfaces`
  - `unsupported_platforms`
  - `readiness_status`

- `SkillDraftDiff`
  - `manifest_diff`
  - `instructions_diff`
  - `file_diffs`
  - `summary`

新增 application service：

- `SkillAuthoringService`
  - `create_draft`
  - `update_draft`
  - `validate_draft`
  - `build_diff`
  - `apply_draft`
  - `reject_draft`
  - `list_drafts`
  - `get_draft`
  - `delete_draft`

`SkillAuthoringService` 可以组合现有 `SkillPackageService`、`SkillReadinessService`、
`SkillCatalogService` 和 integration ports，但不能绕过它们直接写 owner truth。

## Persistence

建议新增 Postgres 表：

- `skill_authoring_drafts`
  - 保存 draft metadata、manifest payload、instructions body、support file payload、
    validation snapshot、diff snapshot。
- `skill_authoring_audit`
  - 保存 create/update/validate/diff/apply/reject/delete 操作记录。

持久化 draft 的原因：

- agent 生成 draft 后需要给前端或 approval 面板审阅。
- 用户可能隔一段时间再确认。
- diff 和 validation 需要可追踪。
- Operations 需要观察 authoring backlog 和失败原因。

不把 draft 表作为最终 truth。`apply` 后最终 truth 仍然是 skill package 文件和 Skills
owner catalog。

## HTTP API

新增 Skills owner API：

- `POST /skills/drafts`
  创建 draft。支持从经验总结创建新 skill，或基于已有 skill 创建更新 draft。
- `GET /skills/drafts`
  查询 draft 列表，支持 status、skill_name、run_id、workspace_dir 过滤。
- `GET /skills/drafts/{draft_id}`
  获取 draft 详情、validation、diff、audit。
- `PATCH /skills/drafts/{draft_id}`
  更新 draft 内容。
- `POST /skills/drafts/{draft_id}/validate`
  校验 manifest、instructions、files、requirements 和 readiness。
- `POST /skills/drafts/{draft_id}/diff`
  生成或刷新 diff。
- `POST /skills/drafts/{draft_id}/apply`
  应用 draft 到 owner truth。必须校验 authorization effect 和 source writability。
- `POST /skills/drafts/{draft_id}/reject`
  标记 draft 被拒绝。
- `DELETE /skills/drafts/{draft_id}`
  删除未应用 draft。

API 不接受裸 JSON 手写配置作为主用户体验，但可以传输结构化 payload。

## Agent-Facing Tool Functions

在 `tools/skills/tool.yaml` 中新增受控 authoring tools。

建议 tool function：

- `skill_draft_create`
  - 输入：`intent`、`skill_name`、`summary`、`target_source_id`、`workspace_dir`、
    `manifest`、`instructions_body`、`support_files`、`reason`。
  - 输出：`draft_id`、摘要、下一步。

- `skill_draft_update`
  - 输入：`draft_id` 和 patch。
  - 输出：更新后的 draft 摘要。

- `skill_draft_validate`
  - 输入：`draft_id`。
  - 输出：validation errors/warnings、missing dependencies、readiness。

- `skill_draft_diff`
  - 输入：`draft_id`。
  - 输出：human-readable diff summary 和结构化 diff。

- `skill_draft_apply`
  - 输入：`draft_id`、`reason`。
  - 输出：applied skill、source、fingerprint、sync/readiness result。
  - 要求：用户确认 + authorization effect。

- `skill_draft_reject`
  - 输入：`draft_id`、`reason`。
  - 输出：rejected status。

保留现有 `skill_read`。不要让 `skill_read` 兼任写入能力。

## Authorization Effects

建议新增 effects：

- `skill_authoring.create`
- `skill_authoring.update`
- `skill_authoring.validate`
- `skill_authoring.diff`
- `skill_authoring.apply`
- `skill_authoring.reject`
- `skill.package.write`

默认策略：

- validate/diff 可以低风险允许。
- create/update draft 需要记录 actor/run/turn，但不直接改变 owner truth。
- apply 必须显式确认。
- system/readonly source 永远不能 apply。
- workspace source 需要 workspace boundary 校验。

## Requirement Resolution

Draft validation 必须使用 owner API / application port 获取候选真相：

- Tool requirements 来自 Tool Function catalog。
- Access requirements 来自 Access assets / credential requirements。
- Authorization effects 来自 Authorization policy/effect surface。
- Surface/platform 来自 runtime context 和 Skills module 支持列表。

LLM 不应该凭空发明 requirement。如果识别到不确定依赖：

- 放入 `suggested_tools` 或 validation warning。
- 不放入 `required_tools`。
- 在 diff summary 中提示用户确认。

## UI / Approval Flow

Settings Skill 页面新增 authoring 审阅能力：

- 顶部或侧栏显示 Drafts 队列。
- 选中 draft 后展示：
  - 目标 skill / source / scope
  - manifest 摘要
  - instructions preview
  - requirements readiness
  - diff
  - validation errors/warnings
  - audit
- 用户可以：
  - edit draft
  - validate
  - apply
  - reject
  - delete

Workbench / Approval 面板：

- 当 agent 调用 `skill_draft_apply` 时展示 approval card。
- Card 必须展示 diff summary、目标 source、风险、缺失依赖。
- 用户确认后再执行 apply。

不要把“创建 skill”做成要求用户手写 JSON 的页面。人工编辑可以存在，但应该是结构化
表单和 markdown 编辑器。

## Events / Operations

新增事件：

- `skills.authoring.draft.created`
- `skills.authoring.draft.updated`
- `skills.authoring.draft.validated`
- `skills.authoring.draft.diff_built`
- `skills.authoring.draft.apply_failed`
- `skills.authoring.draft.applied`
- `skills.authoring.draft.rejected`
- `skills.authoring.draft.deleted`

Operations Skills 页面应观察：

- 待审 draft 数量。
- invalid draft 数量。
- 最近 apply 的 skill。
- readiness 失败原因。
- authoring 失败事件。

Operations 不写 draft，不参与 apply 决策。

## Checklist

### 1. Contract / Documentation

- [x] 新增 `skills/skill-authoring/SKILL.md`。
- [x] 新增 `skills/skill-authoring/references/skill-quality-checklist.md`。
- [x] 新增 `skills/skill-authoring/references/requirement-mapping.md`。
- [x] 新增 `skills/skill-authoring/references/examples.md`。
- [x] 在 Skills governance 文档中链接本清单。
- [x] 在 `docs/ui/current-ui-design-functional-spec.md` 中补 Settings Skill Draft 审阅区。
- [x] 在 `tools/skills/tool.yaml` 中说明读写工具边界，并把 `skill.read` 与
  `skill.authoring` capability 分离。

### 2. Application Service

- [x] 新增 `SkillAuthoringService`。
- [x] 新增 draft request/response application models。
- [x] 新增 draft validation model。
- [x] 新增 draft diff model。
- [x] `SkillManager` 暴露 authoring facade 方法，但不吞掉 service 边界。
- [x] `SkillAuthoringService` 创建 draft 时不写 owner package truth。
- [x] `apply_draft` 只通过 `SkillPackageService` 写入 package。
- [x] `apply_draft` 后通过既有 package service 触发 package sync、readiness 和
  installation audit。
- [x] `apply_draft` 对 update draft 做 base fingerprint 冲突校验，目标变更后拒绝覆盖。
- [x] Owner readiness 和 draft validation 已通过 Tool Source Query 解析可用 Tool Function，
  不再把已注册的 `skill_draft_*` 工具误判为缺失。

### 3. Persistence / Migration

- [x] 新增 migration: `skill_authoring_drafts`。
- [x] 新增 migration: `skill_authoring_audit`。
- [x] Repository 支持 draft CRUD。
- [x] Repository 支持 draft audit append/list。
- [x] Draft payload 保存结构化 manifest、instructions、files、validation、diff。
- [x] Draft 过期策略明确，不把长期历史塞满 active query。

### 4. HTTP / CLI

- [x] `POST /skills/drafts`。
- [x] `GET /skills/drafts`。
- [x] `GET /skills/drafts/{draft_id}`。
- [x] `PATCH /skills/drafts/{draft_id}`。
- [x] `POST /skills/drafts/{draft_id}/validate`。
- [x] `POST /skills/drafts/{draft_id}/diff`。
- [x] `POST /skills/drafts/{draft_id}/apply`。
- [x] `POST /skills/drafts/{draft_id}/reject`。
- [x] `DELETE /skills/drafts/{draft_id}`。
- [x] CLI 补齐 draft list/show/create/update/validate/diff/apply/reject/delete。

### 5. Tool Functions

- [x] 扩展 `tools/skills/tool.yaml`，新增 authoring tools。
- [x] 新增 handler，调用 Skills application，不直接写 filesystem。
- [x] `skill_draft_apply` 声明 `requires_confirmation`、`mutates_state` 和
  `skill_authoring.apply` required effect。
- [x] Tool result 返回结构化 metadata，方便前端和 Operations 观察。
- [x] 保证 `skill_read` 仍只负责读取。

### 6. Authorization / Approval

- [x] 新增 `skill_authoring.*` 和 `skill.package.write` effects。
- [x] 默认策略允许 create/update/validate/diff/reject，限制 apply。
- [x] Workbench approval card 支持 skill draft apply。
- [x] Apply 前校验 readonly/system source 和 base fingerprint。
- [x] Apply 冲突时返回错误，不静默覆盖。

### 7. UI

- [x] Settings Skill 页面新增 Drafts 队列。
- [x] Draft 详情展示 diff、validation、summary 和目标写入信息。
- [x] 支持 validate、diff、apply、reject、delete。
- [x] Workbench 展示 skill apply approval。
- [x] 所有固定文案进入 i18n。
- [x] Loading/empty/error 状态保持稳定布局。

### 8. Events / Operations

- [x] 新增 authoring event contract。
- [x] Authoring service 发布 draft lifecycle events。
- [x] Operations observer 消费 authoring events。
- [x] Operations Skills 页面展示 authoring backlog 和失败原因。

### 9. Tests

- [x] Unit/HTTP: `SkillAuthoringService.create_draft`。
- [x] Unit/HTTP: `SkillAuthoringService.validate_draft`。
- [x] Unit/HTTP: `SkillAuthoringService.apply_draft`。
- [x] Unit: readonly/system source apply 被拒绝。
- [x] Unit: owner readiness 使用运行时 Tool Function catalog。
- [x] Unit: draft validation 使用 Tool / Access / Authorization readiness ports。
- [x] Unit: authoring draft lifecycle events。
- [x] Unit/HTTP: base fingerprint conflict。
- [x] Unit: tool handler 不直接写 filesystem。
- [x] HTTP: draft CRUD / validate / diff / apply。
- [x] CLI: draft lifecycle。
- [x] Frontend: typecheck/build。

## Construction Closure

- Draft validation has structured fields and Tool / Access / Authorization readiness ports wired.
- Draft lifecycle events are projected into first-class Operations Skills authoring backlog and
  failure panels.
- Draft-specific audit persistence is implemented and exposed through owner HTTP/CLI flows.
- CLI draft lifecycle is implemented.
- Settings Skill page includes the Draft review surface and consumes owner APIs.

## Acceptance Criteria

本轮完成后必须满足：

- 用户可以让 agent 把一次任务经验生成 skill draft。
- Agent 可以调用受控 tool 创建、校验和生成 diff。
- Apply 前用户能看到 diff、readiness 和风险。
- Apply 后 skill 出现在 Skills catalog，且能被下一次 run 按 readiness 使用。
- 没有 agent 直接写 skill 文件的通道。
- 没有 Settings-owned skill 真相。
- 没有绕过 Skill owner 的兼容路径。
- 缺 Tool/Access/Authorization 依赖时，系统返回结构化原因，而不是生成不可用 skill。

## Suggested Verification

按改动范围选择验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_skills_http.py
PYTHONPATH=src pytest -q tests/unit/test_skills_owner_catalog_persistence.py
PYTHONPATH=src pytest -q tests/unit/test_skills_context.py

cd frontend
npm run typecheck
npm run build
```

新增实现时应补专门的 authoring 测试，不把现有 owner catalog 测试当作替代。
