# OnlineOrder Agent V2

基于 FastAPI 的点单 Agent。LLM 负责理解意图和提出工具调用，Harness 负责 Session、参数校验、记忆、执行边界与评测，OnlineOrder-Dev 的 Spring 服务继续负责身份、商品、购物车和订单。

**本分支只修改 OnlineOrder-Agent；没有修改 OnlineOrder-Dev。** 后端合同以 `15d4240` 的 Controller、DTO 和 Service 为准。

已实现：

- 有工具次数、上下文大小和总时限的完整循环；错误时保留已取得的结果。
- 多轮筛选合并、候选商品位置映射、选择、过期检查和短期记忆压缩。
- 通过现有 Spring API 读取/写入长期偏好；保守抽取、证据引用、删除与检索。
- `search_menu`、`list_restaurants`、`get_menu`、`select_search_result`、`get_cart`、`add_to_cart`。
- 添加商品采用应用管理的两轮确认；请求重放、操作日志、未知写入隔离及人工核对恢复。
- Qwen / DeepSeek / OpenAI 的 Chat Completions 适配；环境变量切换。
- 不需要真实密钥的完整演示、自动化测试和离线评测；可用真实 LLM 对同一 Mock 后端评测。

## 第一次学习Agent，先读这里

[从零理解这版Agent：整体思路、逐步调用、Session、记忆、工具与加购恢复](doc/agent-v2-from-zero-zh.md)。这份教程从具体点单问题讲到实际代码，不要求先熟悉Agent框架。

## 十分钟开始

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
cp .env.example .env
```

先在 `.env` 修改两行，**不用 API Key、Spring 或 Redis**：

```dotenv
LLM_PROVIDER=mock
DEMO_BACKEND=true
```

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
# 另开终端，激活同一虚拟环境：
python -m app.cli --demo
```

依次输入：`找15美元以内不太辣的鸡肉` → `最好有avocado` → `第二个不错` → `把第二个加入两份` → `确认` → `查看购物车`。

真实测试时，把 `.env` 改为：

```dotenv
LLM_PROVIDER=qwen
LLM_API_KEY=替换成你注册获得的Key
DEMO_BACKEND=false
ONLINEORDER_BACKEND_URL=http://localhost:8080
```

DeepSeek 只需换成 `LLM_PROVIDER=deepseek` 并填该平台的 Key；模型和地址留空会选用 provider 默认值。重启服务后生效。API Key **不是**用户 JWT；接真实后端还要用 CUSTOMER 登录 Token。完整说明见[启动与密钥指南](docs/quickstart-zh.md)。

## 验证与学习

```bash
pytest --cov=app --cov-report=term-missing -q
python -m app.evaluation.run --output work/evaluation.json
ruff check app tests
ruff format --check app tests
```

若安装了 uv，优先使用已锁定依赖：`uv sync --frozen --extra dev`，随后 `uv run pytest`。

从[中文文档导航](docs/README.md)开始，包括真实 API 审查、架构与调用链、完整 Session JSON 演变、指标定义和面试追问。API 在线文档：<http://127.0.0.1:8000/docs>。

## 需要理解的边界

Spring 的 `POST /api/cart/items` 会累加数量，**没有幂等键合同**。V2 对同一 action 保守地至多发送一次；超时或结果不确定时停止自动写入并要求核对，不声称端到端 exactly-once。Redis 模式需要持久化、不驱逐日志和适当运维；内存模式仅供单进程开发。详情见[可靠性设计](docs/agent-v2-design-zh.md)。

当前没有 Agent 结账、支付、取消订单工具，也没有后端不支持的向量检索或过敏原保证。Mock 分数只用于回归，真实模型效果与线上性能需要拿到 Key 后实测。
