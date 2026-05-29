# Pytest Runtime Governance Checklist 2026-05-18

## 当前结论

`tests/unit` 当前可单进程稳定跑完，但仍偏 runtime-heavy。2026-05-18 治理后最新验证结果为
`PYTHONPATH=src pytest -q -o faulthandler_timeout=120 tests/unit --durations=120 --durations-min=0.2`
通过，`1414 passed in 180.79s`。治理前同等全量约 `386.33s`，且在 61%/99% 区间存在卡死风险。

本轮已处理几类不应留在默认 unit 热路径里的问题：

- [x] `benchmark-tool-io` CLI 单测不再真实拉起 scheduler/executor 双线程并发跑 SQLite。测试改为端口级 fake service，保留 CLI 参数、输出结构、端口调用断言。
- [x] Operations observer 首次处理事件不再同步 materialize 全部 Operations 模块。全量状态投影推迟到维护节奏，事件批处理热路径只负责观察事件和到期定向投影。

同时修正了本轮暴露出的测试边界漂移：

- [x] HTTP/API 目标测试不再直取旧 `ORCHESTRATION_SCHEDULER_SERVICE` / `ORCHESTRATION_EXECUTOR_SERVICE` broad key，改用 `ORCHESTRATION_SCHEDULER_MAINTENANCE_SERVICE` 和 `ORCHESTRATION_EXECUTOR_CONTROL_SERVICE`。
- [x] OpenAI LLM profile 测试按 Access credential binding 约束显式传入 `openai-api-key`。
- [x] Settings materialization 测试按当前 Access 默认声明更新断言。
- [x] 大测试文件预算恢复通过，拆出 `test_ui_operations_orchestration_http.py` 和 `test_browser_tool_profile_http.py`。
- [x] 建立 pytest marker 分层：`fast`、`runtime`、`integration`、`live`、`benchmark`、`slow`，集中规则位于 `tests/conftest.py`，marker 声明位于 `pyproject.toml`。
- [x] `SqliteTestHarness` 使用进程内 schema template 复制，避免每个测试重复执行全量 DDL，同时保持每个测试独立 SQLite 文件。
- [x] 测试进程强制隔离事件后端环境：`tests/conftest.py` 将 `APP_EVENTS_BACKEND` 固定为 `file`，清理 Redis 连接相关环境变量，避免本机 dev stack 环境污染 unit。
- [x] SQLite file backend 不再使用 `NullPool` 高频 open/close 文件连接；连接复用后 executor 并发测试不再卡在 macOS SQLite 文件互斥上。WAL 初始化也改为每个数据库文件只执行一次。
- [x] `RedisEventsBackend` 增加 `close()`，`EventsApplicationService` / `AppContainer.close()` 会释放 topic listener 线程；Redis backend 单测也显式 close service。
- [x] Channel SSE 测试不再强制等待 1 秒 timeout；`/channels/web/events` 支持小数 timeout，测试等待降到 50/200ms。
- [x] `channel-runtime run --max-cycles 1` 测试显式使用短 poll interval，避免默认 5s 空闲等待混入单测热路径。
- [x] HTTP 公共测试基类使用持久 `TestClient` 上下文，并在测试装配中关闭 memory watcher，减少每个 request 重复创建 AnyIO portal 和 watcher 关闭等待。
- [x] `crxzipple ask/chat` 主 CLI 测试改为 fake turn submission，不再启动真实 sample LLM server 与 daemon ensure。
- [x] CLI 公共测试基类在默认 `self.env` 下复用 test-level runtime container，并确保 container 在同一套测试 env 中构建；自定义 env 或显式 `obj` 的测试仍走原始路径。
- [x] `process` CLI 与 workspace process 工具不再使用固定 200/400ms sleep 等待子进程完成，改为短轮询；`ProcessSupervisor` 终止轮询间隔从 100ms 降到 20ms。
- [x] Browser CDP host daemon 测试的假 managed process 补齐 `--remote-allow-origins`，避免生产逻辑误判并等待假 PID 退出；测试结束前显式关闭 `CdpControlEngine` HTTP session。
- [x] `Makefile` 增加 `test-unit-fast`、`test-unit-runtime`、`test-unit`、`test-live`，后续 agent 需要按任务风险选择测试层级。

当前分层采样：

- 2026-05-18 baseline:
  - `PYTHONPATH=src pytest --collect-only -q tests/unit -m fast`：702 tests。
  - `PYTHONPATH=src pytest --collect-only -q tests/unit -m runtime`：712 tests。
  - `PYTHONPATH=src pytest --collect-only -q tests -m live`：3 tests。
  - `make test-unit-fast`：702 passed, 712 deselected, 70.78s。
  - `make test-live`：3/1417 tests collected, 1414 deselected, 1.48s。
  - `PYTHONPATH=src pytest -q -o faulthandler_timeout=120 tests/unit --durations=120 --durations-min=0.2`：1414 passed, 180.79s。
- 2026-05-25 current sample:
  - `PYTHONPATH=src pytest --collect-only -q tests/unit -m fast`：846/1596 tests collected。
  - `PYTHONPATH=src pytest --collect-only -q tests/unit -m runtime`：750/1596 tests collected。
  - `PYTHONPATH=src pytest --collect-only -q tests -m live`：5/1601 tests collected。
  - `make test-unit-fast`：846 passed, 750 deselected, 64.15s。
  - `make test-unit-runtime`：750 passed, 846 deselected, 246.96s。
  - `make test-live`：5/1601 tests collected, 1596 deselected, 1.67s。
  - `make test-unit`：1596 passed, 314.76s。
  - `tests/unit/test_browser_tool_http.py` split out runtime HTTP wiring tests into
    `tests/unit/test_browser_tool_http_runtime.py`; file budget guard passes again.
  - Runtime layer assertions updated for the current Access inventory, Browser tool catalog,
    Alembic head, Event stream bootstrap, and Daemon missing-process projection semantics.

## 后续治理清单

- [x] 建立 pytest 分层口径：`unit-fast`、`unit-runtime`、`integration`、`live`、`benchmark`。默认开发命令应明确跑哪一层，benchmark/live 不应混入日常全量 unit。
- [x] 给 SQLite 测试库建立 schema template，减少每个用例重复 full schema 初始化。
- [x] 治理 SQLite 连接池策略，避免 unit 并发测试在 file-backed SQLite 上高频建连/关连。
- [x] 为 Redis events listener 建立可关闭生命周期，避免单测残留 daemon listener 线程。
- [x] 强制 unit 测试环境不继承本机 Redis event backend。
- [x] 给 HTTP heavy tests 抽公共轻量 fixture，避免每个 request 重复创建 `TestClient` portal；API 测试默认关闭 memory watcher。
- [x] 第一批 CLI heavy tests 改 fake runtime/port：root ask/chat 与 orchestration benchmark-tool-io。
- [x] 继续给 CLI heavy tests 抽公共轻量 fixture，减少每个用例重复 full runtime container 初始化。
- [x] 把剩余 1.5s 以上用例逐个归类：真实端到端价值保留；只验证接口 wiring 的改为 fake port；只验证序列化的下沉到 application/service 测试。
  当前慢用例列表已降到约 1.0-1.4s，剩余项均属于 runtime/process/browser/CLI
  生命周期类验证，继续保留在 `runtime` 分层，不再混入 fakeable wiring。
- [x] 为 Operations observer 增加专项性能守卫：单个事件批处理不能触发全模块 projection；全模块 projection 只能在明确 maintenance/rebuild 路径中发生。
  已补 `test_observer_runtime_event_driven_wakeup_does_not_scan_all_topics`，锁住
  event-driven wakeup 只处理被唤醒 topic 的行为，避免单事件批处理退回全订阅扫描。
- [x] 为 orchestration runtime benchmark 保留 Postgres/Redis 集成测试入口，避免用 SQLite 验证多 worker 并发语义。
  已新增 `make test-orchestration-benchmark-integration` 和
  `tests/integration/test_orchestration_runtime_benchmark_postgres_redis.py`，
  显式使用 dev infra 的 Postgres/Redis；默认不进入日常 unit。

## 当前最慢用例

全量通过后前几名仍是 runtime/process 端到端型测试：

- `test_tool_background_process_run_eventually_succeeds`：约 1.4s。
- `test_ui_operations_daemon_page_reports_missing_process_sessions`：约 1.4s。
- `test_workspace_exec_can_start_background_process_and_manage_it`：约 1.4s。
- `test_tool_runtime_endpoint_executes_sandbox_adapter`：约 1.3s。
- `test_process_cli_starts_lists_reads_and_removes_processes`：约 1.2s。
- `test_create_image_artifact_generates_preview_and_llm_variants`：约 1.2s。
- `test_orchestration_executor_and_scheduler_commands_drive_run_lifecycle`：约 1.0s。

这些不是卡死风险，但说明当前 `tests/unit` 里仍有 runtime/integration 风格验证。后续继续压全量耗时时，优先治理真实 process 生命周期测试、browser host daemon 测试、CLI 端到端测试分层。

## 已确认根因

- 全量卡在 61%/99% 的直接原因不是 pytest 本身，而是 unit 进程继承了本机 Redis event backend 环境，加上 Redis listener / memory watcher 等后台线程未完全释放。
- executor 并发测试的卡死直接落在 macOS SQLite 的文件连接互斥上。`NullPool` 让每个 unit UoW 都打开/关闭 SQLite 文件连接，在 async scheduler/executor 并发测试中会放大为连接层阻塞。
- SSE 测试慢的直接原因是测试为了等待 `event: timeout` 使用了 1 秒 timeout，而生产默认其实可以保留长连接；单测只需要证明流协议和 wakeup 行为。
