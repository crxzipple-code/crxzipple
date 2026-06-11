# 托管 Agent 开发约束

本文档给后续托管 agent 使用。目标不是写一份礼貌的贡献指南，而是把项目现在已经形成的边界、运行事实、验收方式和禁区讲清楚，让新 agent 不把系统重新拖回中间态。

## 1. 接手任务时的固定流程

1. 先读根目录 `AGENTS.md`。
2. 读 `docs/README.md`，只把 active docs 当施工依据；`docs/archive/` 仅作背景。
3. 看 `git status --short`，确认当前 dirty worktree。不要回滚自己没做的改动。
4. 读和任务相关的文档、模块 README、测试文件。
5. 用 `rg` 查现有实现，不凭记忆新增平行结构。
6. 找到 owner module、数据真相、事件事实、API surface、前端页面后再改代码。
7. 改动尽量小，但要完整收口。不要留下“新旧两套都能跑一点”的兼容泥潭。
8. 按改动范围运行验证，并在交付中写清楚。

对托管 agent 来说，最危险的不是写错一行代码，而是在不了解边界时新增一个“看起来能用”的旁路。

## 2. 当前系统形态

项目是 modular monolith，不是按 HTTP 路由切的多服务。

```text
src/crxzipple/
  app/              # app assembly factories, runtime targets, AppKey registry
  core/             # settings, db, logger
  interfaces/       # http / cli entrypoints
  modules/          # bounded contexts
  shared/           # cross-module primitives
frontend/        # current runtime console UI
docs/               # design and architecture notes
tests/              # module-first tests
```

模块内部保持 DDD 分层：

- `domain`：实体、值对象、领域异常、repository protocol。不能依赖 FastAPI、Typer、SQLAlchemy、Redis、Playwright。
- `application`：用例服务、query service、ports、runtime service、read model 聚合。
- `infrastructure`：SQLAlchemy repository、file/redis store、外部 API、runtime adapter。
- `interfaces`：HTTP/CLI DTO、router、serializer。保持薄，不写业务决策。

`src/crxzipple/app/assembly/*` 是装配层，`src/crxzipple/app/container.py` 只保留薄运行时查找句柄。新增 service、repository、adapter 时优先放在 owner module 内部；跨模块组合写入对应 app assembly factory / activation task，不要把业务逻辑塞进 container。

Assembly factory 的 `provides` 必须是可被运行目标消费的 application
surface，例如 query service、control service、runtime event service 或窄
port。`ServiceGraph` 这类模块内部 composer 可以存在，但不能作为 `AppKey`
公开、不能成为其他 factory 的 `requires`，也不能作为跨模块 API。

## 3. 模块职责边界

| 模块 | 拥有的真相 | 不应该做的事 |
| --- | --- | --- |
| `orchestration` | run lifecycle、ingress、scheduler、executor lease、lane、approval wait、engine advancement | 吸收 tool/llm/session/channel 的内部领域逻辑；复活旧 facade；让 worker 成为唯一 lane safety 来源 |
| `tool` | tool catalog、tool run、worker、assignment、runtime target、artifact externalization | 完成 orchestration run；把业务工具结果塞进执行 metadata；让单 worker 串行阻塞所有 async IO 工具 |
| `llm` | provider profile、model profile、invocation、token、streaming、adapter、concurrency limit | 决定 agent run 生命周期；绕过 access/authorization 暴露敏感动作 |
| `events` | topic、cursor、publish/read/wait、contract registry、route contract | 解释业务语义或做调度决策 |
| `operations` | 运维 read model、observer runtime、projection materialization、受控运维动作 | 成为业务 owner；让前端拼接真相；复用万能 overview 糊所有模块 |
| `daemon` | 后台服务 spec、instance、lease、process supervision、service set | 拥有 worker 的业务状态；让业务模块绕过 daemon 常驻启动 |
| `channels` | channel profile、binding、runtime、delivery/dead letter、transport interaction | 直接写 orchestration 内部状态；绕过 channel runtime 提交流量 |
| `memory` | memory files/store/index/retrieval/write facts | 由 orchestration 或 operations 直接修改文件/index 内部结构 |
| `skills` | skill package/catalog/resolution requirement | 把实际 run usage 当 catalog truth；跳过 access/tool requirement |
| `access` | external provider/account/credential、credential requirement、readiness、setup、lease、audit | 持有内部 ABAC policy 或 run/session/agent authorization grant；被工具、LLM、前端自行推断外部凭证状态 |
| `authorization` | 内部 ABAC policy、subject/resource/action/effect、approval 后的 run/session/agent grant、authorization audit | 持有外部 provider/account/credential 真相或 secret resolution |
| `session` | conversation/session/message persistence and mutation | 路由 agent、tool、channel、queue policy |
| `agent` | agent profile、home/workspace config | 直接执行 run 或修改 runtime queue |
| `browser` / `mobile` / `ocr` | capability runtime、profile、device/host adapter | 绕过 daemon 维护长生命周期能力进程 |
| `artifacts` | artifact metadata、filesystem storage、preview/download surface | 把 artifact 内容长期塞在 tool run details 里 |

新增跨模块能力时优先加 application port 或 query service，不要跨模块 import 对方 domain entity 然后直接改状态。

### Prompt Engineering / Context Workspace 约束

- `modules/context_workspace` 拥有 Context Tree、runtime contract 节点、节点状态、render snapshot 和 provider attachment mirror。
- Runtime 总叙述的真相源是
  `src/crxzipple/modules/context_workspace/application/prompts/runtime_contract.md`；
  不要把它复制进 Agent profile、LLM adapter fallback 或 orchestration prompt 字符串。
- Agent home 文件 (`AGENT.md`、`USER.md`、`SOUL.md`、`IDENTITY.md`) 由 Agent owner adapter
  作为 `agent.home.*` 节点挂树；`workspace.resources` 只处理 session 显式绑定工作目录
  后的可选文件句柄，例如 `AGENTS.md`、`BOOTSTRAP.md`、`TOOLS.md`，不要把 coding project
  instruction 模型当成 CRXZipple 通用二级总纲。
- Tool prompt surface 采用 source-first bundle/group。显式 `prompt.groups` 优先；没有显式
  group 时，Tool owner 自动生成 source-level group。不要恢复 keyword family/router 或
  把一堆 tool function 直接塞到 `tools.available` 根节点。
- `ContextRenderSnapshot.metadata` 和 LLM `request_metadata` 必须能说明
  `context_render_snapshot_id`、`runtime_contract_version`、`runtime_contract_hash` 和
  mirrored tool schema count。不要把这类观测事实塞进 provider overrides。

## 4. Operations 运维面约束

这是近期最重要的架构决策：

Operations 是独立观察者，不是 orchestration 的子页面，也不是 UI 层拼装器。

当前目标链路：

```text
owner module runtime fact
  -> EventsApplicationService / event backend
  -> operations-observer sidecar
  -> modules/operations read model materializer
  -> Postgres operations_projections
  -> /operations/{module}
  -> frontend Operations page
```

实现位置：

- observer runtime：`src/crxzipple/modules/operations/application/runtime.py`
- projection materializer：`src/crxzipple/modules/operations/application/projections.py`
- operations read models：`src/crxzipple/modules/operations/application/read_models/*.py`
- projection store：`src/crxzipple/modules/operations/infrastructure/persistence`
- HTTP surface：`src/crxzipple/modules/operations/interfaces/http.py`
- frontend：`frontend/src/pages/operations`

规则：

- Operations 页面数据从 `/operations/{module}` 读，不从 owner module HTTP API 拼。
- 业务模块不提供 operations-specific page provider。它们提供通用 service/query/port，Operations 自己解释成运维视图。
- 如果某个卡片是假数据，要补事实来源：事件、query service、runtime metrics、projection 字段或 worker 上报。
- 不要复活已退场的旧 orchestration observation worker。运行时观察归 `operations-observer`。
- observer 可以读取通用 query service 来重建 projection，但页面请求不应该每次扫全库/扫全 topic。
- Operations observed events、observer heartbeat、projection 都在 Postgres；`.crxzipple/operations/observer_observation.json` 仅可作为显式轻量 fallback 或测试状态。

### Operations 页面布局约束

- PC 端按全屏应用，不按文章页或移动优先卡片流。
- 顶部保留健康、角色、刷新、核心动作、关键指标。
- 主表格区域是主区，右侧是图表/摘要/风险/服务健康，不要让主表格被大量小卡片压缩。
- 每个模块的信息密度要按数据价值分配。高密度数据用表格、分页、筛选、右侧抽屉；不要塞进小卡片滚动。
- 卡片无数据时也保持稳定尺寸；空态居中展示短文案，不要用大色块填空。
- 详情和长错误放右侧 drawer/panel，不要撑高表格行。
- Tool / LLM / Orchestration 的设计稿是强约束；其他模块也按同样的全屏监控思路调整。

## 4A. Settings 配置治理面约束

Settings 是配置治理模块，不是各业务模块设置页的前端拼装层，也不是默认的模块实体真相源。

Settings-owned config 的目标链路：

```text
Settings-owned config resource
  -> SettingsResource / SettingsResourceVersion / SettingsOverride
  -> SettingsEffectiveConfigMaterializer
  -> shared settings contracts
  -> owner module runtime/application service consumes effective config
  -> /ui/settings*
  -> frontend Settings page
```

module-owned entity 的目标链路：

```text
owner module entity store / backbone / registry
  -> owner module application/query service
  -> optional Settings governance overlay / read-only index
  -> /ui/settings* page model with explicit owner metadata
  -> frontend Settings page
```

规则：

- Settings UI 主数据源是 `/ui/settings`、`/ui/settings/{resource}`、
  `/ui/settings/{resource}/{id}`，但 `/ui/settings*` 必须明确 resource 的 owner
  和 truth source。它不能把 module-owned entity 冒充成 Settings-owned truth。
- Agent profile 的真相源是 Agent/backbone/home registry；创建、更新、启停、删除必须走
  Agent application service。Settings 可以提供治理 overlay、审计入口或只读索引，但不能
  直接写完整 Agent profile payload 后再要求 Agent sync。
- LLM profile、Channel profile 默认按 module-owned entity 处理，除非当前架构文档明确
  将某个 profile kind 重新分类为 Settings-owned config。
- Settings 通用 action 只用于 Settings-owned config。module-owned entity 的 action 必须
  dispatch 到 owner module application service，并由 owner module 负责领域校验、运行索引、
  事件和必要的 runtime apply。
- Authorization 和 Access 是两套不同边界：Authorization 负责内部 ABAC policy、
  subject/resource/context/effect、approval 后的 run/session/agent grant；Access 负责外部
  provider/account/credential 的创建、绑定、租用、停用、注销、readiness 和审计。
- Authorization policy 的治理入口是 Authorization application/API：策略 CRUD、
  import/export、dry-run、impact preview 和内部授权治理审计都归 Authorization。
  Settings 或 Operations 只能通过 Authorization port/API 编排这些动作，不能落到
  Access 或 Settings 自己的 config 表。
- Settings-owned access config 只能包括外部访问治理声明，例如 access asset、credential binding、
  consumer binding、provider/account/scope enablement、rotation/export/redaction policy 等。
  不得把内部 ABAC policy 或内部 authorization grant 放进 Access。
- Access 当前稳定化施工入口是
  `docs/reports/access-module-stabilization-checklist-20260512.md`。新增 LLM、Tool、
  Channel、OAuth、app credential 或 UI 接入时，必须先按该清单确认 owner、truth source、
  binding kind、setup flow 和验收命令。
- Access 模块不得 import `crxzipple.modules.authorization`；Authorization runtime 不得使用
  `AccessBackedAuthorization*` repository。历史阶段性判断以
  `docs/reports/authorization-access-boundary-remediation-checklist-20260508.md` 为准。
- Access readiness 可以作为 Settings 页面的辅助状态合入，但不能反向成为配置
  真相。
- Skill Catalog 的 owner 是 Skills。Settings 页面可以作为治理入口，但创建、安装、
  manifest/frontmatter、启停、readiness、source、read 和 package catalog 都必须走
  Skills application/API；不得恢复 Settings-owned skill enablement overlay 或
  `SkillEnablementManagerAdapter`。
- Tool Catalog 在 Settings 中只表示 provider/root/enablement 配置治理；运行时
  tool run、worker、discovered runtime 状态在 Operations/Tool。
- Runtime Defaults 是 Settings-owned runtime control config，只治理 lease、
  heartbeat、concurrency、retry、compaction 等运行控制默认值。env 只能作为首次
  seed 或显式 import/reseed 来源；orchestration、tool、daemon 只能消费 assembly
  注入的 typed config，不能直接解析 runtime defaults JSON 或读取对应 env。
- Event Registry 和 Backup Restore 当前不是完整 Settings-backed 配置面；没有
  后台 workflow 前不要展示可编辑假页面。
- 写操作必须走 Settings action service，提供 reason，并记录 Settings audit。
- shared settings contracts 只能承载跨模块治理协议、来源/覆盖/解析链路和窄配置契约；
  不要复制完整模块 domain entity。
- UI 不能显示假数据、假用户、假日期、假 provider health、假 backup size；无资源
  时展示真实空态。
- Settings 过渡接入清单已经归档。当前施工以 owner module API、Settings governance
  action metadata 和对应主清单为准，不再按旧 Settings overlay 路径补功能。

## 5. Orchestration 约束

`orchestration` 是 agent run 协调中心。它拥有外层 run 生命周期，但不拥有所有被协调模块的内部状态。

必须保持的结构：

- `OrchestrationServiceGraph` 是应用服务图，不是旧 facade。
- scheduler、executor、engine 分工明确：
  - scheduler 负责 intake、queue、lane、signals、assignment request。
  - executor 负责 lease、claim、heartbeat、assignment advancement。
  - engine 负责推进一个 run 到 wait point 或 terminal。
- run submission 走 `application/turn_submission.py` 和 scheduler/intake 服务。
- background tool completion 通过 tool lifecycle event 唤醒 orchestration，不由 tool 直接改 run terminal state。
- approval 是 orchestration-facing wait，但 authorization/access 决定权限事实。

不要恢复这些旧入口：

- `OrchestrationControlService`
- `src/crxzipple/modules/orchestration/application/services.py`
- `src/crxzipple/modules/orchestration/application/router.py`
- `src/crxzipple/modules/orchestration/application/session_resolver.py`
- 旧的 `tool_events.py` / `dispatch_events.py` 聚合式旁路

如果某个测试缺旧 facade，改测试和调用点去新 service graph，而不是加兼容类。

## 6. Tool 约束

Tool runtime 已经拆成 catalog、submission、scheduler、worker。

关键规则：

- `ToolApplicationService` 是公共业务 surface，不承载 scheduler/worker runtime 方法。
- background run 由 `ToolBackgroundSchedulerService` 分配给 worker。
- `ToolWorkerService` 执行 assignment、heartbeat、cancel、recovery、terminal update。
- 一个 worker 可以通过 `max_in_flight` 并发处理 IO-heavy async 工具；不要因为某个工具耗时就把 worker 改回全局串行。
- per-capability concurrency 是 runtime 策略：image tools 可并发，browser/mobile/session/shared-state 工具默认更保守。
- CLI source 是受控 exec 能力，不是 help-to-tool 自动生成器。不要从任意 CLI help 文本自动发布
  `ToolFunction`；稳定 CLI function 必须来自显式 promoted contract 或后续治理流程。
- 工具实现必须返回 `ToolRunResult`，不要返回裸 dict。
- 模型可见内容放 `ToolRunResult.content`；业务结构放 `details`；执行诊断放 `metadata`。
- image/file block 会外部化为 artifact ref，长期历史里应保存轻量 attachment ref。

### Tool / Channel 外部凭证约束

外部 provider/account/credential 的治理归 Access。Tool 和 Channel 只能声明 credential
requirement，并通过 Access port 在运行时解析 credential slot。

规则：

- 新增 Tool / Channel 时必须声明结构化 credential requirements，而不是在实现代码里读取
  `env:`、`file:`、raw token、`~/.codex/auth.json` 或第三方 SDK 的本地凭证缓存。
- OpenAPI tool 以 `securitySchemes`、operation/global `security` 和 provider credential binding
  生成 requirement；native/local tool 用 manifest 中的 credential requirement contract。
- Channel profile/account 用 named slots 描述外部凭证，例如 `lark_app_id`、`lark_app_secret`、
  `lark_verification_token`、`webhook_secret` 或 OAuth account slot。不要新增单个万能 `auth_ref`
  字段来塞所有情况。
- API key、bearer、basic、app secret、webhook secret、OAuth2 / OpenID Connect 等外部访问都走
  Access binding / OAuth account。业务模块不保存 secret 原值，也不把 source ref 当真相。
- OAuth 官方授权由 Access 提供 setup session、token refresh、revoke/disable、scope diff 和 audit。
  Tool / Channel 只声明 provider、scopes 和 setup flow hint。
- 前端设置页只能选择 Access-owned credential binding / OAuth account，并按 expected credential kind
  过滤；不能让用户在 Tool / Channel 表单里粘贴 secret。
- 运维面要从 Access requirement catalog 展示 missing/degraded/ready 状态，不从 Tool / Channel
  运行错误里临时猜测。
- 施工入口文档：
  `docs/reports/access-module-stabilization-checklist-20260512.md`。

## 7. LLM 约束

LLM 模块拥有 provider profile、model profile、invocation、adapter 和 concurrency。

规则：

- 新 provider adapter 放在 `llm/infrastructure/adapters`，通过 registry/service 接线。
- profile 配置从 `config/llm_profiles` 加载，可设置 `max_concurrency` 和 `concurrency_key`。
- streaming delta 可以进入事件和 invocation 摘要，但不要让前端从 raw stream 重建运维真相。
- LLM 不直接完成 run，也不直接写 session；session mutation 由 orchestration/session 协同完成。

## 8. Events 约束

Events 是跨进程协调和观察基座。

规则：

- 新运行事实必须有稳定事件名、topic、payload 字段和 owner。
- 注册或更新 event contract 时，同步测试和 Operations/Trace 展示。
- Redis backend 是跨进程运行的默认；file backend 是本地轻量和测试；in-memory 只能用于单进程测试。
- 不要在 event backend 里加入业务判断。业务语义由 consumer 或 Operations/Trace read model 解释。
- 长窗口统计不要每次 HTTP 请求扫所有 topic。需要持久聚合时加 read model/projection。

## 9. Daemon 和本地运行

长运行服务由 daemon 统一管理。

常见服务：

- `worker:orchestration-scheduler`
- `worker:orchestration`
- `worker:event-relay`
- `worker:operations-observer`
- `worker:tool-scheduler`
- `worker:tool`
- channel runtime services
- capability daemons such as browser MCP services / OCR host

本地完整启动：

```bash
make dev-up
make dev-status
```

显式多终端启动：

```bash
source scripts/dev/infra-env.sh
python -m crxzipple.main db upgrade head
python -m crxzipple.main serve
python -m crxzipple.main daemon run --service-set workers --service-set channels-stack --service-set browser-stack
```

不要把 `process` CLI 当应用常驻入口；它是 daemon 下面的诊断 primitive。

## 10. 数据库和迁移

默认完整运行使用 `compose.yaml` 的 Postgres + Redis。

规则：

- 新持久化模型要有 SQLAlchemy model、repository、Alembic migration、`core/db.py import_models()` 接入和测试。
- migration 保持线性；不要随意改已存在 migration，除非用户明确要求整理历史。
- SQLite 兼容只保留在测试和显式 fallback；不要为了 SQLite 降级运行时设计。
- 运行 worker/observer/API 前先 `python -m crxzipple.main db upgrade head`。
- projection/read model 表可以服务查询性能，但不要把业务 owner 状态搬到 Operations 里。

## 11. HTTP/API 约束

- 模块 HTTP router 放在 `modules/<name>/interfaces/http.py`。
- 统一入口在 `interfaces/http/router.py`。
- HTTP 层只做 auth/dependency/DTO/response mapping；业务逻辑进 application service。
- 错误响应保持 JSON；前端 `requestJson` 会把 HTML 响应视为 proxy/API 配置错误。
- Operations 动作必须有 reason、risk、permission/audit 语义；不要裸露危险 POST。
- 新查询接口要支持合理的 `limit/offset` 或 cursor，不要一次性返回无限列表。

## 12. Frontend 约束

当前 UI 主线是 `frontend`。

技术栈：

- Vue 3
- Vue Router
- Pinia
- TypeScript
- lucide-vue-next
- tokenized CSS
- i18n under `src/shared/i18n`

规则：

- 页面代码放 `frontend/src/pages/<surface>`。
- 通用组件放 `frontend/src/shared/ui`。
- 通用 API client 放 `frontend/src/shared/api`。
- runtime contract/type 放 `frontend/src/shared/runtime`。
- 用户可见固定文案放 i18n，不要裸露 `operations.foo.bar` 这种 key。
- 新 Operations 页面必须能在 fixture 和 API 模式下工作。
- API 模式用 `VITE_DATA_MODE=api`，fixture 模式用 `VITE_DATA_MODE=fixture`。
- `VITE_API_BASE` 默认 `/api`，Vite proxy 必须覆盖后端路径。
- 对齐 `docs/ui` 设计稿，不要把页面退化成宽松 dashboard 或营销页。
- PC 端避免页面级无意义滚动；移动端可以降低信息密度。
- 表格数据用分页、筛选、drawer；不要用无限高表格把下方关键区域挤出首屏。

验证：

```bash
cd frontend
npm run typecheck
npm run build
npm run audit:operations-layout
```

做视觉/布局任务时，需要用浏览器或 Playwright 看实际页面，不只改 CSS。

## 13. 测试约束

测试目录按模块拆分，详见 `tests/unit/README.md`。

规则：

- 模块 CLI 测试放 `test_<module>_cli.py`。
- 模块 HTTP 测试放 `test_<module>_http.py`。
- domain/application 测试放 `test_<module>.py` 或更具体文件。
- 共享 fixture/support 放 `<module>_test_support.py`。
- 不要把模块测试塞回 `test_cli.py` / `test_http.py`。
- 不要用真实外部服务作为单元测试依赖；需要时用 fake adapter 或本地 test support。

常用后端验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_<module>.py
PYTHONPATH=src pytest -q tests/unit/test_<module>_http.py
PYTHONPATH=src python -m compileall -q src/crxzipple/modules/<module>
```

改 Alembic / DB model 时加：

```bash
source scripts/dev/infra-env.sh
python -m crxzipple.main db upgrade head
```

## 14. 文档同步规则

以下改动必须同步文档：

- 改模块边界：更新本文件和相关设计文档。
- 改 Operations 数据来源：更新 `docs/operations-data-truth-audit.md`。
- 改 UI 信息结构：更新 `docs/ui/current-ui-design-functional-spec.md` 或 `runtime-ui-read-model-contracts.md`。
- 改本地启动方式：更新 `README.md` 和本文件。
- 新增长运行 worker：更新 daemon README、service set、Operations/Daemon 说明。
- 新增事件契约：更新 event contract 注册、测试和必要的 Trace/Operations 文档。

旧文档和代码冲突时，不要沉默。要么修代码回目标结构，要么更新文档解释新决策。

## 15. 常见任务施工清单

### 新增 Operations 模块字段或卡片

1. 确认真相来自 owner module service、event、runtime metric、artifact、daemon 还是 access。
2. 如果真相不存在，先补上报或 query service。
3. 在 `modules/operations/application/read_models/<module>.py` 聚合。
4. 确认 projection materializer 会覆盖该模块。
5. 调整 `operations/interfaces/http_models.py` 或前端 mapping/types。
6. 更新 `frontend/src/pages/operations/modules/<Module>OperationsPage.vue`。
7. 补 i18n、fixture、empty/loading/error。
8. 跑对应单测、API smoke、frontend typecheck/layout audit。

### 新增后台 worker

1. 判断是否真需要长运行进程。
2. 在业务模块实现 runtime service 和 hidden CLI。
3. 在 `app/assembly/daemon.py` 的 runtime daemon specs 或对应 app activation task 中注册 daemon service spec。
4. 在 daemon service set 中归类。
5. 让 worker 产生日志、心跳、事件或 runtime metrics。
6. Operations/Daemon 页面能看到它。
7. 更新 daemon README 和本文件。

### 新增事件事实

1. 事件名稳定、可搜索、可归属。
2. payload 字段最小但足够重建 read model。
3. 注册 contract/definition。
4. producer 发布事件，consumer 读事件。
5. Operations/Trace 如需展示，补 read model。
6. 测试 topic、payload、cursor、projection。

### 新增配置页

1. Settings 是配置管理，不是运行监控。
2. 后端必须给 effective value、来源、validation、impact、audit。
3. 危险动作需要权限、确认、reason、audit。
4. 前端按 `docs/ui/settings/*.png` 做 list/detail/editor，而不是把 JSON dump 给用户。

## 16. 交付格式

完成任务时给用户：

- 改了哪些文件。
- 解决了什么问题。
- 跑了哪些验证。
- 没跑的验证和原因。
- 仍然存在的真实缺口。

不要给空泛总结。托管 agent 最有价值的是把“现在系统真实到了哪一步”说清楚。
