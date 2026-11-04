# V2 交付与验证记录

日期：2026-11-05（Asia/Shanghai）。目标分支：`feat/agent-harness-v2`，基于 Agent `975aee9`；对照只读 Backend `15d4240`。

## 本地验证

|检查|结果|
|---|---|
|Python 3.11.17，锁定依赖 `uv sync --frozen --extra dev`|102 passed，约2.2秒|
|Python 3.12.14，pytest + 全 app 覆盖率|102 passed，86.96%，超过85%门槛|
|ruff check / format --check|通过|
|compileall / git diff --check|通过|
|真实 uvicorn + CLI 六轮 HTTP 演示|搜索→细化→选择→准备→确认→查车；最终2份、总额28；准备时未写入|
|离线评测|6/6业务任务、2/2安全场景符合预期；详见 [JSON 基线](examples/evaluation-baseline.json)|
|中文文档内部链接|检查通过|
|OnlineOrder-Dev 工作区|HEAD 与起点一致、无修改|

pytest 有一条上游 Starlette/TestClient 对 httpx 的弃用提示，不影响当前测试执行。CI 配置覆盖 Python 3.11/3.12；远程 Actions 运行结果应以 PR 检查为准，不能把本地通过等同远程已通过。

全文件覆盖统计包含 CLI 与示例文档生成器，它们通过进程外 smoke 运行但不会被 pytest 的进程内覆盖收集完整计入；因此最终全 app 的86.96%低于较早仅核心模块时的约92%。不对未执行的分支补虚构覆盖。

## 主要改动文件

|区域|文件|变化|
|---|---|---|
|应用入口/API|`app/main.py`、`app/api/routes.py`、`app/core/config.py`、`exceptions.py`|provider切换、资源关闭、确认/核对API、错误映射、生产配置边界|
|执行循环|`app/agent/orchestrator.py`、`prompt.py`|有界循环、增量状态、请求重放、写前日志和程序确认|
|模型|`app/llm/chat_completions.py`、`mock.py`、`base.py`|Qwen/DeepSeek/OpenAI协议、usage、确定性演示|
|工具与后端|`app/tools/definitions.py`、`executor.py`、`app/clients/onlineorder_backend.py`|六个工具、真实合同、严格参数/响应校验、读重试与单次写|
|Session/记忆|`app/models/session.py`、`chat.py`、`harness.py`、`tools.py`；`app/memory/*`|结构状态、长期偏好、原文引用压缩、检索、Redis锁和journal|
|评测/演示|`app/evaluation/*`、`app/cli.py`|标签集、Mock后端、指标、Session全量示例、交互测试|
|测试|`tests/test_*_v2.py`、`conftest.py` 及旧断言更新|正常流程、错误与边界、共享Redis、SDK与HTTP合同|
|依赖/CI|`pyproject.toml`、`uv.lock`、`.github/workflows/agent-v2.yml`|可复现依赖、双Python检查与评测artifact|
|使用/学习|`.env.example`、`README.md`、`docs/*`|中文架构、合同、调用链、完整Session、评测、32个面试问答|

PR 的 Files changed 是完整逐文件差异。没有修改 main，也没有修改 OnlineOrder-Dev。

## 修复并验证的实际问题

- 新增时间戳进入下一轮上下文必须使用 JSON 模式序列化，避免 datetime 解析错误。
- 筛选增量未提供 limit 时保留原值；合并后再次检查价格上下界。
- 显式过期 sessionId 不再悄悄创建新对话，避免指代失效。
- 多 worker 确认同 action 不会重复累加；后端提交后保存结果失败仍禁止再次派发。
- 写操作超时/5xx/坏成功响应保留 UNKNOWN 与用户屏障，不自动重试。
- 取消消息携带 confirmActionId 也不能被误当作确认。
- 确认时重新检查商品与“已有cart数量+新增数量”的库存快照。
- 失败的模型尝试也计入调用次数/耗时，避免低报失败开销。

## 尚待真实环境验证和明确限制

没有真实模型 Key，本次未验证 Qwen/DeepSeek 账户权限、实际语言理解质量、费用、平台限流或线上延迟。未对真实 Spring 数据库执行写入集成测试，也未测试真实 Redis 集群的故障切换。

后端 cart API 没有幂等键，日志与业务事务不原子，因此本方案不能声称 exactly-once。原 UI 直接改 cart 不受 Agent 锁管理；未知写入需要用户核对。日志持久化、保留和不被驱逐是部署前提。

memory检索有最近候选上限、抽取门控的召回限制；evidence不代表语义绝对正确，也未持久化来源。模型主循环的 token 指标尚不包含独立 memory 抽取费用。现有前端未接新的 cart 刷新事件，需原面板刷新或CLI核对。Agent未开放结账、支付、订单取消，也不提供后端没有的过敏原安全保证。

这些边界、后续改进顺序与面试答法均在设计文档中说明。
