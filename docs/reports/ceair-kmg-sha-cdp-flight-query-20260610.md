# 东航官网昆明到上海机票 CDP 查询记录 2026-06-10

## 查询范围

- 官网：中国东方航空官网 `https://www.ceair.com/`
- 查询日期：2026-06-10
- 航程：昆明 -> 上海
- 类型：单程，1 成人，现金价格
- 页面结果 URL：
  `https://www.ceair.com/zh/cny/shopping/oneway/KMG,KMM(R),KOM(R),SYM(R),SVM(R)-SHA,PVG,ASH(R),SNH(R),IMH(R),AXU(R),AOH(R),LTU(R),EGH(R)/2026-06-10`

## 页面可见结果摘要

东航官网低价日历显示 2026-06-10 昆明到上海最低价为 `¥470`。

直飞 / 经停主列表中页面可见航班如下：

| 航班 | 起飞 | 到达 | 航程 | 到达机场 | 页面可见现金含税价 |
| --- | --- | --- | --- | --- | --- |
| MU5807 | 12:15 长水 | 15:15 | 直达，3小时 | 虹桥 T2 | ¥1,196 |
| FM9452 | 14:05 长水 | 17:15 | 直达，3小时10分 | 虹桥 T2 | ¥810 |
| MU8504 | 14:05 长水 | 17:15 | 共享，直达，3小时10分 | 虹桥 T2 | ¥810 |
| MU5817 | 14:30 长水 | 17:45 | 直达，3小时15分 | 浦东 T1 | ¥550 |
| FM9454 | 16:00 长水 | 18:55 | 直达，2小时55分 | 虹桥 T2 | ¥1,012 |
| MU8500 | 16:00 长水 | 18:55 | 共享，直达，2小时55分 | 虹桥 T2 | ¥1,012 |
| MU5506 | 16:05 长水 | 21:55 | 经停福州，5小时50分 | 浦东 T1 | ¥550 |
| MU5324 | 16:25 长水 | 21:25 | 经停长沙，5小时 | 虹桥 T2 | ¥810 |
| MU5811 | 17:00 长水 | 20:15 | 直达，3小时15分 | 虹桥 T2 | ¥810 |
| FM9430 | 18:10 长水 | 23:20 | 经停衡阳，5小时10分 | 浦东 T1 | ¥550 |
| MU8488 | 18:10 长水 | 23:20 | 共享，经停衡阳，5小时10分 | 浦东 T1 | ¥810 |
| MU5813 | 20:30 长水 | 23:25 | 直达，2小时55分 | 虹桥 T2 | ¥1,196 |
| FM9466 | 22:05 长水 | 01:10 +1 天 | 直达，3小时5分 | 浦东 T1 | ¥470 |
| MU8580 | 22:05 长水 | 01:10 +1 天 | 共享，直达，3小时5分 | 浦东 T1 | ¥810 |

页面还展示了南航、吉祥航等联运/同页售卖结果，以及“更多出行方案推荐”的中转方案；上表只记录东航官网主列表中与东上航相关的可见航班。

## 工程路径

1. 先尝试使用 Codex Browser 插件的 in-app browser，目标 browser id 为 `iab`。
2. in-app browser 返回 `Browser is not available: iab`，因此改用本机 Python Playwright 的 Chromium。
3. 通过 Playwright 启动 Chromium，并创建 CDP session：
   - `context.new_cdp_session(page)`
   - `Network.enable`
4. 打开官网首页：
   - `https://www.ceair.com/zh/cny/home`
5. 通过页面控件操作，而不是直接拼接口：
   - 接受 Cookie。
   - 定位第一个 `input[aria-label="出发"]`，输入并选择 `城市 昆明 中国 KMG`。
   - 定位第一个 `input[aria-label="到达"]`，输入并选择 `城市 上海 中国 SHA`。
   - 打开日期控件，选择 `2026-06-10`。
   - 点击航班搜索。
6. 记录关键官网网络请求：
   - `POST /portal/v3/shopping/airport/search`
     - keyword: `昆明`
     - keyword: `上海`
   - `POST /portal/v3/shopping/briefInfo`
     - `depCityCode=KMG`
     - `arrCityCode=SHA`
     - `depDate=2026-06-10`
     - `routeType=OW`
   - `POST /portal/v3/shopping/querySummaryPrice`
     - `depDt=2026-06-10`
     - `depCode=KMG`
     - `arrCode=SHA,PVG`
7. 从官网渲染后的结果页读取页面可见航班、时间、机场、经停/直达和价格。

## 现场产物

- 搜索前截图：`tmp/ceair-before-search.png`
- 搜索结果截图：`tmp/ceair-after-search.png`

## 注意事项

- 本次查询没有绕过验证码，也没有登录或提交购买。
- 机票价格实时变化，以上结果只代表本次官网页面加载时的可见价格。
- 官网 Access 层面含阿里云验证码脚本；后续产品化时应把验证码识别为人工接管点，不应绕过。

## 与项目内会话实现方式对比

### 本次外部 CDP 查询路径

本次报告使用的是项目运行时之外的直接自动化路径：

```text
Python Playwright
-> Chromium page
-> CDP session Network.enable
-> DOM locator/fill/click
-> 读取渲染后页面文本
-> 人工整理报告
```

这个路径没有进入 CRXZipple 的 orchestration、Context Workspace、tool source、daemon allocation 或 Operations projection。优点是控制面短、步骤确定、便于针对官网页面写临时选择器；缺点是项目内部不可观测，也不会沉淀为 CRXZipple agent-facing browser 能力。

### 当前项目内会话路径

项目内发起的会话走的是完整 agent runtime：

```text
Workbench 用户输入
-> orchestration run
-> Context Workspace / Context Tree render
-> LLM openai_codex.gpt-5.4 决策下一步
-> context_tree.update_plan / expand / enable_tool_schema
-> browser.navigate / browser.network.start_capture / browser.observe / browser.form.fill / browser.overlay.select
-> daemon 管理的 browser profile crxzipple
-> Browser module 通过 CDP endpoint 操作页面
-> Tool run / LLM invocation / browser network capture 写入运行事实
-> Operations observer 侧向物化 read model
```

从 Operations 侧看到的浏览器运行时是 daemon 托管的 `crxzipple` profile，driver 为 `managed`，CDP endpoint 为 `http://127.0.0.1:18800`。它已经附着到东航官网 target，并记录了东航官网请求，例如：

- `POST https://www.ceair.com/portal/v3/shopping/querySummaryPrice`
- capture id 包括 `ceair_home` / `trace-...`

这说明项目内路径确实进入了官网，并且 browser module 的 network capture 已经捕获到票价摘要相关接口。

### 行为差异

| 维度 | 外部 Playwright/CDP 路径 | 项目内会话路径 |
| --- | --- | --- |
| 入口 | 本地脚本直接启动 Chromium | Workbench 创建 orchestration run |
| 浏览器控制 | 直接用 Playwright locator 和 CDP session | 通过 browser tool source，由 LLM 逐步调用工具 |
| 状态管理 | 脚本内临时状态 | orchestration run、tool run、browser allocation、Context Tree、Operations projection |
| 决策方式 | 人直接写死页面操作步骤 | LLM 根据 observe 结果决定下一步 |
| 可观测性 | 只有截图和手工记录 | Tool/LLM/browser/network/diagnostics 都进入运行事实和 Operations |
| 成本 | 少量脚本步骤 | 多轮 LLM、多次 observe、多次 tool schema/context 操作 |
| 稳定性 | 对当前页面结构更确定 | 更通用，但表单/弹层/日期控件容易反复尝试 |
| 结果 | 已到结果页并提取航班价格 | 到达官网并捕获价格摘要请求，但后续被取消，未形成最终航班列表答复 |

### 项目内会话的关键不同点

1. 第一轮用户只说“去东航官网查询昆明到上海的机票”，没有给日期；项目内 agent 先打开官网观察后，选择向用户追问日期。这是合理的 agent 行为。
2. 第二轮用户补充“今天的”后，agent 将今天解析为 `2026-06-10`，继续在东航官网表单里填写昆明、上海和日期。
3. 项目内会话多次调用 `browser.form.fill` 填写相同字段，尤其是目的地和日期字段。这和外部脚本一次性锁定 DOM/弹层选项的方式不同。
4. 项目内会话在 Workbench 中被停止，run 状态为 cancelled；因此没有走到读取结果页并总结航班价格的 final response。
5. Operations 中还能看到一个 browser/form 相关 tool run 长时间处于 Running/高进度状态，说明取消 orchestration run 后，异步 browser tool run 的终态清理可能还有缺口。

### 工程结论

外部路径证明东航官网的页面链路和关键网络请求可以跑通；项目内路径证明 CRXZipple 的 browser tool、daemon 托管浏览器、network capture 和 Operations 观测链路也能触达官网。但项目内实现更依赖 LLM 分步操作复杂表单，容易出现重复 fill、日期控件未稳定提交、取消后 tool run 残留等问题。

后续如果要让项目内这类任务稳定产品化，优先改进点是：

- 为 browser module 增加更强的结构化表单事务能力，例如一次工具调用内完成填值、选择弹层候选、提交搜索。
- 对日期/城市选择这类组合控件提供 browser-side evaluate/locator 级别的确定性动作，而不是完全依赖多轮 observe 后的文本填充。
- 在 orchestration cancel 时强制终止或收敛正在运行的 browser tool run，避免 Operations 里残留 Running 状态。
- 对 network capture 暴露更直接的 request/response 摘要读取能力，让 agent 在页面交互成功后能优先基于官网接口事实提取结果，再用页面文本做校验。
- 控制 Context Tree 和 browser observe 的重复上下文，降低同一页面状态被反复送入 LLM 的 token 成本。

## 项目内对齐改动

为让项目 agent 能更接近本次命令行 Playwright/CDP 临时脚本的操作方式，新增了 `browser.native.run` 作为 Browser source 下的原生脚本式入口。

实现方式不是开放任意命令行 Python，而是复用 browser action engine 里已有的 `batch` 能力：

```text
browser.native.run
-> browser runtime handler wrapper
-> kind=batch
-> daemon 托管 browser profile / target
-> Playwright-backed action engine 顺序执行 actions
-> Tool run / Browser runtime metadata / Operations 继续可观测
```

agent 后续可以用一次工具调用表达类似脚本的事务：

```json
{
  "actions": [
    {"kind": "fill", "selector": "input[aria-label='出发']", "text": "昆明"},
    {"kind": "wait", "text": "昆明 中国 KMG", "timeout_ms": 5000},
    {"kind": "click", "selector": "text=昆明 中国 KMG"},
    {"kind": "fill", "selector": "input[aria-label='到达']", "text": "上海"},
    {"kind": "wait", "text": "上海 中国 SHA", "timeout_ms": 5000},
    {"kind": "click", "selector": "text=上海 中国 SHA"}
  ],
  "stop_on_error": true
}
```

这条路径与本次外部脚本的差异是：浏览器不再由临时 Python 自己启动，而是使用项目 daemon 管理的 browser profile；执行日志和结果仍回到 Tool / Browser / Operations 体系。
