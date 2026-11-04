# 评测、工具成功率、任务完成率、召回与性能

## 1. 先区分你在测哪一层

能跑过测试，只说明已覆盖的程序行为符合预期；能通过 Mock 对话，也不证明真实模型理解能力好。V2 将测试分为四层：

|层|方式|能证明什么|不能证明什么|
|---|---|---|---|
|程序/状态测试|假模型 + 实际 orchestrator/executor|状态转换、参数边界、幂等、异常路径|真实模型选工具能力|
|HTTP 与 provider 协议|TestClient、OpenAI SDK + MockTransport|真实 JSON、鉴权、assistant/tool 消息序列|平台 Key 和服务可用性|
|共享 Redis 语义|fakeredis + Lua、两个独立 client/coordinator|共享日志、锁、NX 与重复确认逻辑|真实集群的 failover、eviction、网络分区|
|评测场景|8 个带标签的多轮任务 + 合成后端|回归、指标定义、故障注入安全终止|生产流量上的模型质量/延迟|

没有真实 Key，因此本次没有向 Qwen/DeepSeek 发送真实推理请求；也没有为了测试而修改或写入真实 OnlineOrder-Dev 数据。

## 2. 运行方式

```bash
pytest --cov=app --cov-report=term-missing -q
ruff check app tests
ruff format --check app tests
python -m app.evaluation.run --output work/evaluation.json
```

`app/evaluation/cases.json` 是可阅读的标签集。每个场景定义 messages、预期工具顺序、有效筛选、相关商品 ID、期望 cart、写入次数和可选故障。其中6个是业务/取消任务，2个是安全故障场景；两类分开统计，避免把正确拒绝误计为成功加购。任务判定读取实际保存的状态和 Mock 后端，不用模型自己说“完成了”作为成功依据。

拿到 Key 后评测真实 LLM：

```bash
python -m app.evaluation.run --model configured --repeats 3 --output work/qwen-evaluation.json
```

这个模式读取 `.env` 的真实 provider/model，但仍使用进程内合成后端，因此不会改你的真实购物车。CLI 返回非零表示至少一个标签任务不满足；报告仍保存。缺失或不可用 Key 会使相应任务失败，不会伪装成 mock 结果。

重复 3 次只检验一定程度的稳定性，不能把同一批样例重复当作 24 个独立用户任务。温度为 0 也不能保证所有 provider 完全确定。

## 3. 指标定义与分母

|指标|定义|本实现的判定边界|
|---|---|---|
|tool_success_rate|所有 `ok=true` 工具尝试 / 所有工具尝试|包括内部 commit；准备添加成功不等于已写入|
|tool_argument_validity_rate|非 INVALID_TOOL_ARGUMENTS 的工具尝试 / 全部尝试|只衡量 schema 合法性；未知工具和错误选择另看 selection；不能单独证明语义正确|
|tool_selection_exact_rate|实际工具序列完全等于标签序列的场景 / 场景数|故意严格，合理额外读工具也可能被扣分，需人工分析|
|search_argument_accuracy|最终有效筛选符合全部标注条件的场景 / 有筛选标签的场景|检查多轮合并后的实际 state，额外未标注条件不在这个子指标中|
|write_success_rate|commit 得到合法成功响应的次数 / commit 次数|UNKNOWN 计失败；不能推断实际未提交|
|task_completion_rate|达到标签目标的业务场景 / 全部业务场景|仅6个搜索、浏览、加购、取消任务；故障安全样例不混入这个分母|
|safety_case_pass_rate|正确安全停止的故障场景 / 安全场景|2个缺少引用/写入不确定场景；通过不等于业务加购完成|
|expected_outcome_pass_rate|符合全部预期的场景 / 全部8个场景|用于整个回归集是否通过|
|menu_recall_at_3_macro|每个检索样例的 `相关∩前三结果 / 全部相关`，再宏平均|gold ID 来自人工标签；没有相关标注的样例不进分母|
|memory_recall_at_8|一个标注记忆样例中，检索到的 gold key / 全部 gold key|仅 1 个 smoke case；安全约束保留可能让实际返回数超过 8|
|turn_latency_p50/p95/p99|按样本排序、nearest-rank 分位数|内部 turn 计时，排除鉴权/锁等待等，不是公网请求 p95|
|input_tokens/output_tokens|主循环 provider 返回的 usage 累计|Mock 为 0；当前不含独立 memory 抽取调用|

分母为 0 时输出 null，不把“没有测到”包装成 100%。task completion 附带 Wilson 95% 区间，但仅在样例近似独立时有统计解释；小合成集和重复样例存在偏差。

schema 合法性与语义正确性必须分开。例如 `get_cart({})` 是合法调用，却不能完成用户“找鸡肉”；`quantity=99` 合法但不一定是用户要的数量。需要工具选择、参数语义、后端执行、目标状态一起判断。

## 4. 本次运行的基线含义

在此次开发环境中，Mock suite：8/8 个场景符合标签；17 次工具尝试中 15 次 ok，tool_success_rate=88.2353%；参数合法率和工具选择序列匹配率 100%；两次 commit 中，一次正常成功，一次故意响应丢失，所以 write_success_rate=50%。两类检索的 smoke recall 都为 100%。

6/6 个业务任务通过，另有2/2安全场景通过。业务任务的 Wilson 下界约为 61.0%，已经说明小样本不能承诺稳定的 99% 完成率。真实模型还会面对省略、指代、多语言、冲突偏好、长对话和不可用服务，不能使用这些 Mock 数字向面试官声称真实模型达到相同结果。

Mock 的内部延迟通常为毫秒以内到数毫秒，token 为 0，因为没有网络推理。它只说明回归路径没有异常阻塞，不能用来推算真实 QPS、真实 p95 或费用。运行生成的 [基线报告](examples/evaluation-baseline.json) 保存了该次样本和限制说明；不同机器/运行的时间会不同。

## 5. 如何建立可用于面试答辩的真实质量评测

从现有 8 例起步，扩为独立任务集，按用户而非单条消息划分开发集/测试集，避免相似对话泄漏。固定菜单快照与故障配置，保存 prompt/schema/model 版本；模型名字若是平台可变 alias，报告同时记录平台版本信息（如果可获取）。

建议至少覆盖：

- 单条件、中英混合、同义食材、大小写、多个筛选与无匹配。
- “加 avocado / 不限预算 / 重新找饮料 / 第二个 / 刚才选的”及跨轮约束矛盾。
- 过敏与口味冲突、当天例外、撤回记忆、另一个用户、过期 JWT/Session。
- 数量模糊、菜名重名、候选刷新后位置改变、选择但不加购、取消/过期确认。
- tool schema 错误、重复调用、provider 截断/429/超时、backend 409/429/5xx。
- 后端已提交响应丢失、结果日志失败、同 action 两 worker 确认、外部 UI 并发修改。
- tool result/菜单描述中的提示注入，确认程序不会因数据中的“请忽略限制”而写购物车。

每类错误单独分层报告，不能只给总平均。对自然语言答案增加人工评分：真实性、可理解性、无依据成功声明、是否正确澄清、是否保持用户约束。LLM-as-judge 可辅助筛选，但应盲评、固定 rubric，并抽样核验与人工一致率；绝不能让同一个 Agent 自评成功。

若要衡量 memory extraction，另外标注 should_write、key/value、evidence、UPSERT/DELETE，分别测写入 precision/recall、撤回成功率和跨用户隔离。当前证据门控偏向 precision，会牺牲 recall；本分支的测试验证了若干门控行为，但尚没有大规模标注集证明抽取质量。

检索进一步报告 precision@k、MRR、nDCG、条件保持率及 no-answer 样例误召回率；分开“后端候选集合是否包含 gold”和“候选内 rerank 是否取到 gold”，以定位 recall 丢失在哪一层。

## 6. 性能怎样测才诚实

当前 `TurnMetrics.duration_ms` 从请求日志预留之后计到最终 Session save，包含模型、工具和记忆处理；不含 HTTP 鉴权、用户锁等待、首次 Session/journal 读取和最后缓存 request response。工具耗时包含 client 的读重试与退避；commit 事件的计时不包含其前置 cart/menu 检查。模型 metrics 记录逻辑调用，SDK 实际 HTTP 重试次数没有独立计数。独立 memory 抽取费用没有汇总。

因此上线前需增加 HTTP 外层 span、鉴权/排队/存储/记忆分段 span、provider usage 和请求次数归因，才能分析真正 p95 与成本。

负载测试至少分三组：

1. 固定无延迟假模型，测 Harness 的 CPU、锁、Session/journal Redis 开销。
2. 具有可控延迟/429/timeout 的 provider stub，测排队、超时、连接池和失败恢复。
3. 小额度真实模型 + 隔离真实 Spring 测试账户，测网络、token、工具命中及端到端延迟；涉及加购必须清楚隔离数据，不在真实用户购物车上压测。

测试时报告并发数、任务混合比例、硬件、连接池、Python worker 数、缓存冷热、样本量和失败率。按不同用户分布发压；同用户串行锁的吞吐和多用户吞吐是两件事。用开放到达率模型观察排队，否则闭环压测可能掩盖过载。

单次任务成本 = 主循环输入/输出 token 费用 + 记忆抽取费用 + 重试消耗 + 工具/存储成本。优化先看最大贡献项：减少重复模型轮次、跳过无用抽取、缩短 tool output、精简记忆、适当缓存只读结果。不能缓存实时 cart 或无限放大重试来提高表面成功率。

## 7. 自动化覆盖与仍待验证的范围

测试包括正常多轮、schema 错误、跨用户隔离、时间期限、重复确认、未知写入、日志写失败、Redis 两 worker、真实 SDK wire 格式和 API 层流程。运行结果与最终 PR 记录一致时再引用测试数量和覆盖率，后续新增测试会改变数字。

当前未进行真实 Qwen/DeepSeek 调用、真实 Redis 集群故障测试或真实 Spring 数据库端到端写入测试。CI workflow 会在 Python 3.11/3.12 运行离线测试、覆盖率门槛 85%、ruff 和评测，并保存报告；是否在 GitHub 运行成功，应查看实际 Actions 状态，不能仅凭提交了 YAML 认定通过。
