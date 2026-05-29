# CRXZipple Agent Contract

本文件适用于整个仓库。托管 agent 接手任何开发任务前，必须先读完本文件；做较大改动时继续读 [docs/agents/hosted-agent-operating-contract.md](docs/agents/hosted-agent-operating-contract.md)。

## 项目方向

CRXZipple 是一个 DDD 风格的本地 Agent Runtime 控制台和运行时。当前主线不是补旧中间态，而是把系统收敛到清晰的模块边界、事件驱动运行、Operations 侧向观察 read model、`frontend` 全屏控制台。

如果旧文档、旧代码和当前约束冲突，优先级为：

1. 用户最新明确决策。
2. 本 `AGENTS.md` 和 `docs/agents/*`。
3. 当前代码中已经落地的目标结构。
4. 旧设计文档。

主文档入口是 [docs/README.md](docs/README.md)。`docs/archive/` 只保留历史背景，不能作为当前施工依据。

## 不可破坏的约束

- 不要回滚或覆盖用户已有改动；工作树经常是 dirty 的，只改任务相关文件。
- 不要为了兼容旧结构增加大段 shim；后续开发应服务重构后的目标结构。
- 不要复活已经退场的旧 orchestration facade，例如 `OrchestrationControlService`、`orchestration/application/services.py`、`orchestration/application/router.py`、旧 `session_resolver.py`。
- 不要把业务模块做成 Operations 页面的 owner-specific read model provider。业务模块提供通用 application/query service；`modules/operations` 通过 port/service 聚合运维 read model。
- 不要让前端直接调用 `/tools`、`/llms`、`/orchestration` 等模块 API 来拼 Operations 真相。Operations 页面消费 `/operations/{module}`。
- 不要把 `events` 模块写成业务决策中心。它只提供 topic、cursor、contract、publish/read/wait 基础能力。
- 不要让 `tool` 或 `llm` 完成 orchestration run。它们只拥有自己的生命周期事实；orchestration 观察事实并推进外层 run。
- 不要把树化 Prompt 再塞回 orchestration 内部拼装。`modules/context_workspace` 拥有 Context Tree、节点状态、render snapshot 和 agent-facing `context_tree.*` 工具；orchestration 只通过 `PromptSurfaceBuilder` 收集运行输入，并把 Context Workspace render snapshot 交给 LLM provider。
- 不要按 Browser profile 生成 Tool Source 或 daemon MCP service。Browser profile 是运行上下文；默认 browser capability 只有 `configured.browser` 和 `browser.*`，daemon 只保留 `host:browser:{profile}`。
- 长运行服务必须由 `daemon` 管理，使用 `daemon run/ensure` 或 `make dev-up`，不要手动启动一堆无归属 worker 作为常态。
- 本地完整运行默认使用 Docker Compose 中的 Postgres + Redis。SQLite 只作为显式 fallback 或测试轻量后端。
- `frontend` 是唯一当前 UI 主线；不要新增或恢复旧前端目录。

## 代码边界速记

- `src/crxzipple/app/assembly/*`：组合根，声明 module-local factories、integration factories 和 activation tasks。
- `src/crxzipple/app/container.py`：薄运行时查找句柄，只通过 `AppKey` 访问已装配 application。
- `src/crxzipple/interfaces/http`、`src/crxzipple/interfaces/cli`：薄接口层。
- `src/crxzipple/modules/*/domain`：纯领域模型，不依赖 FastAPI、SQLAlchemy、外部 IO。
- `src/crxzipple/modules/*/application`：用例、服务、ports、read/query surface。
- `src/crxzipple/modules/*/infrastructure`：持久化、外部系统、runtime adapter。
- `src/crxzipple/modules/operations`：运维面和 sidecar observer，读取事件和模块 query service，物化 read model。
- `src/crxzipple/modules/events`：通用事件总线，不拥有业务语义。
- `src/crxzipple/modules/context_workspace`：树化 Prompt / Context Tree owner，维护 session 绑定的上下文节点、展开折叠、估算、provider attachment mirror 和 render snapshot。
- `tools/context_tree`：agent-facing Context Tree 工具包，只通过 Context Workspace / Memory / Artifact application service 操作树，不直接读写 owner module 内部存储。
- `frontend/src/pages`：Workbench / Operations / Trace / Settings 页面。
- `frontend/src/shared`：API client、runtime contract、i18n、设计 token、通用 UI。

## 数据真相

- 业务事实由 owner module 持有：orchestration run、tool run、LLM invocation、channel runtime、daemon instance、memory/index 等。
- Prompt 上下文真相由 Context Workspace 持有：Context Tree 节点、节点状态、render snapshot 和 provider attachment mirror 落在 `context_workspace`。orchestration run 只记录 `context_render_snapshot_id` 等引用事实。
- 跨进程运行事实通过 events backend 流动。共享运行环境必须用 Redis backend，不要把 in-memory event backend 当跨进程方案。
- Operations read model 由独立 `operations-observer` 侧向消费事件并物化到 Postgres `operations_projections`。
- `/operations/*` API 优先读取 `operations_projection_store`。如果页面缺数据，应补事件、query service 或 projection materializer，而不是让前端绕路拼接。
- Operations observed events、observer heartbeat、projection 都在 Postgres；`.crxzipple/operations/observer_observation.json` 只能作为显式轻量 fallback 或测试状态。

## 前端约束

- 新页面先对齐 `docs/ui` 设计稿和 `docs/ui/current-ui-design-functional-spec.md`。
- PC 端按全屏应用设计，首屏尽量展示关键监控信息；不要用大量内部滚动小卡片偷懒。
- Operations 每个模块都应有自己的页面结构和数据重点，不能复用万能 overview。
- Skeleton/loading/error/empty 状态要保持稳定布局，避免数据加载前后大面积跳动。
- 所有用户可见固定文案进入 i18n；不要把事件 key、metric key 直接裸露给用户。
- API client 必须处理 HTML 错误页，`VITE_API_BASE` 默认 `/api`，Vite proxy 要返回 JSON。

## 常用命令

```bash
make dev-up
make dev-status
make dev-down

source scripts/dev/infra-env.sh
python -m crxzipple.main db upgrade head
python -m crxzipple.main daemon status

PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py
PYTHONPATH=src pytest -q tests/unit/test_tool_background.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_orchestration_context_workspace_snapshot.py

cd frontend
npm run typecheck
npm run build
npm run audit:operations-layout
```

按改动范围选择验证，不要用“没跑测试”糊弄过去；确实跑不了时说明原因。

## 必读文档

- [docs/README.md](docs/README.md)
- [docs/agents/hosted-agent-operating-contract.md](docs/agents/hosted-agent-operating-contract.md)
- [docs/orchestration-design.md](docs/orchestration-design.md)
- [docs/operations-data-truth-audit.md](docs/operations-data-truth-audit.md)
- [docs/context-workspace-prompt-tree-design.md](docs/context-workspace-prompt-tree-design.md)
- [docs/context-workspace-prompt-tree-development.md](docs/context-workspace-prompt-tree-development.md)
- [docs/ui/current-ui-design-functional-spec.md](docs/ui/current-ui-design-functional-spec.md)
- [docs/ui/runtime-ui-read-model-contracts.md](docs/ui/runtime-ui-read-model-contracts.md)
- [src/crxzipple/modules/tool/README.md](src/crxzipple/modules/tool/README.md)
- [src/crxzipple/modules/daemon/README.md](src/crxzipple/modules/daemon/README.md)
- [tests/unit/README.md](tests/unit/README.md)
