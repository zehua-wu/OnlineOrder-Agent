# 中文学习路线

如果是第一次学习Agent，请先读 [从零理解OnlineOrder Agent V2](../doc/agent-v2-from-zero-zh.md)。它从整体责任讲到实际数据与代码；下面的文档适合作为进一步查阅材料。

之后可按顺序读，并在每一步对应运行代码。

|顺序|文档|你会解决的问题|
|---|---|---|
|1|[启动、API Key 与调试](quickstart-zh.md)|不花钱先演示；明天拿到 Key 改哪几行；如何接真实账户|
|2|[源码审查与真实 API 合同](api-contract-zh.md)|为什么这些工具可用；为什么购物车不能自动重试|
|3|[V2 架构、循环和可靠性](agent-v2-design-zh.md)|每个模块、方法、调用链、状态与记忆的责任|
|4|[完整 Session 演变](session-walkthrough-zh.md)|同一个对话每轮实际存了什么 JSON|
|5|[评测与性能](evaluation-zh.md)|成功率、完成率、召回、延迟和统计置信度怎么解释|
|6|[面试问答与继续追问](interview-zh.md)|如何用这份实现回答工程面试，并明确当前限制|

代码入口：`app/main.py:create_app` → `app/api/routes.py:chat` → `app/agent/orchestrator.py:AgentOrchestrator.chat`。

不要一开始就背框架名。先亲自跑通搜索、筛选、准备、确认、查看购物车，再用 `tests/test_harness_v2.py` 理解故障后为什么不能直接重试。

生成的完整工具 JSON 在 [examples/tools.json](examples/tools.json)。Session 示例由 `python -m app.evaluation.session_walkthrough` 从实际 Harness 和合成后端运行生成，包含完整字段而非示意伪代码。

交付验证与主要文件清单：[verification-zh.md](verification-zh.md)。
