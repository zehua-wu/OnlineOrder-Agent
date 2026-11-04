# 启动、替换 API Key 与调试

## 1. 环境准备

Python 3.11 或 3.12。在 OnlineOrder-Agent 的 `feat/agent-harness-v2` 分支执行：

```bash
git switch feat/agent-harness-v2
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

Windows PowerShell：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

如果使用 uv：`uv sync --frozen --extra dev`；后面的 Python、pytest、uvicorn 命令前加 `uv run`，无需手动激活。`uv.lock` 固定了依赖解析结果；pip 的 editable 安装则按 pyproject 的兼容范围解析。

## 2. 无密钥完整演示

`.env`：

```dotenv
APP_ENV=development
LLM_PROVIDER=mock
DEMO_BACKEND=true
SESSION_BACKEND=memory
```

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另一个终端：

```bash
python -m app.cli --demo
```

按 README 的六句话体验多轮、选中、准备和确认。`mock` 是小型确定性策略，只识别少量示例表达，不是一个可自由对话的语言模型。演示后端有独立的合成菜单和虚拟购物车，不会请求 Spring。`demo-token` 只在演示模式有效，不是实际登录凭据。重启会丢失内存状态。

浏览 <http://127.0.0.1:8000/docs> 也能测试 API；每个需要身份的接口在 `authorization` 参数填 `Bearer demo-token`。

## 3. 明天拿到模型 Key 后只需替换这里

Qwen 中国区：

```dotenv
LLM_PROVIDER=qwen
LLM_API_KEY=你在阿里云百炼获得的Key
LLM_MODEL=qwen-plus
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DEMO_BACKEND=false
```

DeepSeek：

```dotenv
LLM_PROVIDER=deepseek
LLM_API_KEY=你在DeepSeek获得的Key
LLM_MODEL=deepseek-chat
LLM_BASE_URL=https://api.deepseek.com/v1
DEMO_BACKEND=false
```

`LLM_MODEL`、`LLM_BASE_URL` 可以留空，会根据 provider 选择上述默认值。Qwen 国际区域的账号要使用该账号文档对应的兼容地址和模型权限；不要将不同区域的 Key 与端点混用。选支持 function/tool calling 的模型；不要先换成未验证的推理模型或自行添加 reasoning 参数。

读取优先级：`LLM_API_KEY` → 当前 provider 对应的 `QWEN_API_KEY` / `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`。因此切换 provider 时必须同步更换通用 Key，避免旧 Key 覆盖新 provider 的专用 Key。

Key 存本地 `.env`，已在 `.gitignore` 排除。不要写进 Python、README、前端、截图或 git。修改后重启 uvicorn；配置使用进程内缓存。缺少 Key 时 `/health` 仍可用，聊天返回 503 `AGENT_NOT_CONFIGURED`。

想先测真实模型、继续使用虚拟购物车：保留真实 provider 和 Key，设置 `DEMO_BACKEND=true`，CLI 仍用 `--demo`。生产环境禁止 mock 模型、演示后端和内存 Session。

## 4. 接真实 OnlineOrder-Dev

按原项目现有说明启动 Spring 与它所需的数据库等服务；**V2 不修改它的源码、迁移或前端**。

```dotenv
DEMO_BACKEND=false
ONLINEORDER_BACKEND_URL=http://localhost:8080
CORS_ORIGINS=http://localhost:3000
```

在原前端注册/登录 CUSTOMER。拿到登录接口返回的用户 JWT，用它调用 Agent。模型 API Key 发给模型平台，用户 JWT 发给 Spring；这两种凭据完全不同。

CLI 的 Bash 配置：

```bash
read -s ONLINEORDER_CUSTOMER_TOKEN
export ONLINEORDER_CUSTOMER_TOKEN
python -m app.cli
```

PowerShell 可在本地设置 `$env:ONLINEORDER_CUSTOMER_TOKEN` 后运行 CLI，不要把实际 Token 写入项目文件或提交。CLI 的 Token 只存于该进程内存。

现有前端已经把 `/agent-api` 代理到 `127.0.0.1:8000`，并把 `sessionId` 带入后续消息，因此无需改前端就能聊天。添加工具的准备信息会显示为普通回复；输入“确认”即可继续。现有界面不会自动根据 V2 新的 `cart` 字段刷新独立购物车面板，应使用原面板的刷新/查询或 CLI/Swagger 核对。我们没有修改 OnlineOrder-Dev 来补这个 UI 行为。

## 5. HTTP 合同与客户端重试

```http
POST /agent/chat
Authorization: Bearer <CUSTOMER-JWT>
Content-Type: application/json

{"message":"找15美元以内不太辣的鸡肉","requestId":"8cadca59-d254-4684-8290-d2a9871fd7c2"}
```

服务生成新的 `sessionId`，后续请求携带它。每个新的用户意图生成新的 UUID `requestId`；**网络重试同一请求时保留原 requestId 和完全相同的消息、sessionId、confirmActionId**。首次请求即使没有 sessionId，也可通过同一 requestId 获取原响应。旧客户端不传该字段仍可用，但无法获得 HTTP 层的重复消息消除能力。

`add_to_cart` 不执行写入，响应中的待确认动作示例：

```json
{
  "pendingAction": {
    "action_id": "7480b80a-2289-45e7-82d6-daa103b3462d",
    "kind": "ADD_TO_CART",
    "menu_item_id": "a4000000-0000-0000-0000-000000000001",
    "restaurant_id": "a3000000-0000-0000-0000-000000000001",
    "name": "Avocado Chicken Bowl",
    "quantity": 1,
    "created_at": "2026-11-04T17:00:00Z",
    "expires_at": "2026-11-04T17:05:00Z"
  }
}
```

确认采用新的 requestId：

```json
{
  "message": "确认",
  "sessionId": "上一轮返回的sessionId",
  "requestId": "5b80ab0a-5d3b-49ee-8728-9c6c4a7a1187",
  "confirmActionId": "7480b80a-2289-45e7-82d6-daa103b3462d"
}
```

使用实际返回的 UUID，示例中的文字占位不能直接发送。也兼容仅携带 sessionId 的“确认/确认添加/确认加入/确认加入购物车/confirm/confirm add”。不会把“好吧你看着办”当成程序确认。带 `confirmActionId` 时，消息也必须明确确认；“取消”加确认 ID 会被拒绝。取消消息支持“取消/取消添加/cancel/cancel add”。

Response 中保留原有 `answer/cards/totalResults/hasMore/toolSteps`，新增 `requestId/traceId/status/errorCode/pendingAction/actionId/cart/metrics`。`pendingAction` 的内部字段采用 snake_case，与 Session 中保持一致。`cart` 只有本轮读到或成功动作回执时返回；重复确认返回的是原动作回执，想看当前购物车请再调用 get_cart。

`GET /agent/sessions/{sessionId}/cards?offset=3&limit=3` 从保存的候选快照分页，不再消耗模型调用。`totalResults` 仅代表保存的候选数，不是数据库全量命中数。

## 6. 结果未知时如何恢复

收到 `WRITE_OUTCOME_UNKNOWN` / `TURN_TIMEOUT`，或确认请求断网后，**不要直接说“再加一次”**。

1. 使用原 sessionId 发送“查看购物车”，或用原购物车界面核对商品和数量。
2. 用已显示的 action ID 调 `GET /agent/actions/{actionId}`。日志是用户级的，即使 Session 已过期，保留期内仍可查询。
3. 用户实际核对后，可调用以下 Agent 自己的接口解除写入隔离：

```http
POST /agent/actions/{actionId}/acknowledge
Authorization: Bearer <CUSTOMER-JWT>
Content-Type: application/json

{"acknowledgement":"I_CHECKED_THE_CART"}
```

该接口会再读一次真实 cart，保存核对回执并解除该 action 的隔离；**不会重发旧的添加操作**。它只表达“用户已经检查，允许继续”，不证明原动作究竟成功还是失败。需要补加时，由用户重新明确提出新的添加请求并确认。成功或明确失败的 action 不需要 acknowledge，重复请求返回 409。

## 7. Redis 与运行参数

```dotenv
SESSION_BACKEND=redis
REDIS_URL=redis://localhost:6379/0
SESSION_TTL_SECONDS=14400
ACTION_TTL_SECONDS=604800
APP_ENV=production
```

复用现有 Redis 服务即可，不修改原 Compose。请确认该 Redis 对 Agent 日志具备需要的持久化、备份和内存策略：TTL 仍在并不意味着不会被 eviction 驱逐。生产不应依赖会随时淘汰的动作日志。用户锁 lease = 整轮模型/工具期限 + 30 秒；Redis 连接/命令超时 5 秒。对停机、分区、主从切换和数据丢失的极限见架构文档。

## 8. 常见错误

|现象|处理|
|---|---|
|401 / 403|确认使用 CUSTOMER JWT；不是模型 Key；过期则重新登录|
|404 SESSION_NOT_FOUND|原 Session 已过期；去掉 sessionId 新开对话，不沿用“第二个”|
|409 TURN_BUSY|另一个同用户请求在执行；稍后用同 requestId 重试|
|409 REQUEST_ID_REUSED|同一 requestId 对应了不同输入；新意图必须使用新 ID|
|409 REQUEST_INTERRUPTED|该请求被保留为未完成；先核对 Session/action，再发新请求，不自动重跑|
|503 SESSION_STORE_UNAVAILABLE|存储不可用；已发送的购物车写入要先检查，不能当作没有发生|
|模型 401/404|检查 Key、区域、模型权限和 Base URL 的 `/v1`，避免重复 `/v1/v1`|
|status=degraded|读取 errorCode 和 metrics.tools；已完成的状态仍被保留|
|不能结账|Agent 尚未开放此工具；使用原系统的结账流程|

本次自动化验证没有调用真实 Qwen/DeepSeek；Key 可用性、配额和真实语言表现需按以上步骤验证。
