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
  bootstrap/        # composition root
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

`bootstrap/container.py` 是装配点。新增服务、repository、adapter 时要在这里接线，但不要把业务逻辑塞进 container。

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
| `access` / `authorization` | readiness、credential/access inventory、policy、temporary grant | 被工具、LLM、前端自行推断权限 |
| `session` | conversation/session/message persistence and mutation | 路由 agent、tool、channel、queue policy |
| `agent` | agent profile、home/workspace config | 直接执行 run 或修改 runtime queue |
| `browser` / `mobile` / `ocr` | capability runtime、profile、device/host adapter | 绕过 daemon 维护长生命周期能力进程 |
| `artifacts` | artifact metadata、filesystem storage、preview/download surface | 把 artifact 内容长期塞在 tool run details 里 |

新增跨模块能力时优先加 application port 或 query service，不要跨模块 import 对方 domain entity 然后直接改状态。

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
- `.crxzipple/operations/observer_observation.json` 只保存轻量观察状态；页面 projection 在 Postgres。

### Operations 页面布局约束

- PC 端按全屏应用，不按文章页或移动优先卡片流。
- 顶部保留健康、角色、刷新、核心动作、关键指标。
- 主表格区域是主区，右侧是图表/摘要/风险/服务健康，不要让主表格被大量小卡片压缩。
- 每个模块的信息密度要按数据价值分配。高密度数据用表格、分页、筛选、右侧抽屉；不要塞进小卡片滚动。
- 卡片无数据时也保持稳定尺寸；空态居中展示短文案，不要用大色块填空。
- 详情和长错误放右侧 drawer/panel，不要撑高表格行。
- Tool / LLM / Orchestration 的设计稿是强约束；其他模块也按同样的全屏监控思路调整。

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
- 工具实现必须返回 `ToolRunResult`，不要返回裸 dict。
- 模型可见内容放 `ToolRunResult.content`；业务结构放 `details`；执行诊断放 `metadata`。
- image/file block 会外部化为 artifact ref，长期历史里应保存轻量 attachment ref。

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
- capability daemons such as Chrome MCP / OCR host

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
python -m crxzipple.main daemon run --service-set workers --service-set channels-stack
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
3. 在 `bootstrap/container.py` 注册 daemon service spec。
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
