# Agent Workspace Context

本文档记录当前 agent workspace bootstrap 的实现边界。它已经不是待施工 Phase 1 计划。

## 当前目标

`agent.runtime_preferences.workspace` 会参与 orchestration prompt construction：

1. `agent` 保存 workspace 偏好，但不读取文件。
2. `orchestration` 在 prompt assembly 中解析 workspace。
3. `workspace_context.py` 从 workspace 根目录加载受信任 bootstrap 文件。
4. `PromptAssembler` 把这些文件作为 system context block 注入。
5. session transcript、memory recall、skills catalog、tool schema 仍走各自 owner 模块。

## 代码入口

- `src/crxzipple/modules/orchestration/application/workspace_context.py`
- `src/crxzipple/modules/orchestration/application/prompt_assembler.py`
- `src/crxzipple/modules/orchestration/application/prompting/producers.py`
- `src/crxzipple/modules/orchestration/application/engine.py`
- `src/crxzipple/modules/agent/domain/value_objects.py`
- `src/crxzipple/modules/agent/infrastructure/home_config.py`

## 文件加载规则

当前固定 allowlist：

- `AGENT.md` / `AGENTS.md`
- `SOUL.md`
- `TOOLS.md`
- `IDENTITY.md`
- `USER.md`
- `BOOTSTRAP.md`
- `MEMORY.md` / `memory.md`

同一组内按顺序取第一个存在的文件，例如 `AGENT.md` 优先于 `AGENTS.md`。

## 安全与预算

loader 当前约束：

- workspace path 必须存在且是目录。
- 每个候选文件必须 resolve 到 workspace root 内部。
- 只加载 allowlist 中的根目录文件。
- 文件必须是 UTF-8 文本。
- 单文件最大 `2 MiB`。
- 单文件注入最多 `20_000` chars。
- 总注入最多 `80_000` chars。
- 超预算内容会截断，并带 `[...truncated...]` 标记。
- 文件内容按 path + stat identity 做进程内缓存。

## Prompt 注入位置

`PromptAssembler` 会在 system blocks 中加入 workspace context block。它和以下 block 一起接受统一 system prompt budget：

- agent instruction
- runtime context
- flow prompt
- available tools
- session tools
- workspace context
- recalled memory
- skills catalog

这意味着 workspace context 不是无限追加，也不会绕过 LLM context budget。

## 边界

- `agent` 只拥有 profile/home/workspace preference。
- `orchestration` 拥有 runtime prompt building。
- `session` 只拥有 transcript truth。
- `memory` 仍是 durable knowledge owner。
- `skills` 仍是 instruction asset/catalog owner。
- interface handler 不直接读取 `AGENTS.md` 或 workspace 文件。

## 后续改动规则

如果要扩展 workspace bootstrap：

1. 先确认是否属于 agent home、workspace context、memory、skills 还是 tool catalog。
2. 新文件名必须进入 allowlist，不要加 glob 扫描整个 workspace。
3. 新内容必须接受同一 budget 和 root-containment 检查。
4. 更新相关 prompt preview/debug metadata，方便 Workbench/Trace/Operations 定位。
5. 补 workspace 缺失、文件存在、越界路径、超预算截断的测试。
