# 源码审查与真实 API 合同

审查日期：2026-11-05（Asia/Shanghai）。Agent 起点为 `975aee9f976e3e02b60da2bedd857494d4b231f3`，Backend 起点为 `15d42405ec0e35d48bb3c1259e864f0b47411cbc`。本地 OnlineOrder-Dev 的工作区保持干净，V2 不包含任何该仓库改动。

## 1. 审查了什么

Agent：routes、orchestrator、prompt、模型封装、ToolExecutor、工具 schema、搜索状态、InMemory/Redis store、进程内锁、长期记忆读写与抽取、现有测试和 README。

Backend：Cart/Restaurant/Search/User/AgentMemory 的 Controller 和 DTO、CartService、SearchService、MenuItemSearchRepository、MenuService、SecurityConfig、ApiExceptionHandler；同时检查前端 agentClient、apiClient、AgentChat 和 Vite 代理。

原实现已经具备搜索筛选合并、结果位置映射、选中状态和 PostgreSQL 长期记忆。主要缺口：只有搜索/选择工具；模型依赖 Responses API；Redis 存储并未配套跨进程锁；未知 sessionId 会隐式新建；最近消息直接截断；没有请求重放、购物车写日志、评测与菜单/购物车调用链。

V2 建立在这些现有能力上，不另造数据库或后端路由。

## 2. 采用的真实后端端点

以下链接固定在被审查的 commit，而非会继续变化的 main。

|Agent 用途|真实 HTTP|请求|后端返回|源码证据|
|---|---|---|---|---|
|鉴权|`GET /api/users/me`|Bearer JWT|`id`、`role` 等|[UserController](https://github.com/zehua-wu/OnlineOrder-Dev/blob/15d42405ec0e35d48bb3c1259e864f0b47411cbc/backend/src/main/java/com/zehua/onlineorder/user/controller/UserController.java)|
|搜索|`POST /api/search`|搜索 DTO|`MenuItemSearchResponse[]`|[Search Controller](https://github.com/zehua-wu/OnlineOrder-Dev/blob/15d42405ec0e35d48bb3c1259e864f0b47411cbc/backend/src/main/java/com/zehua/onlineorder/menu/controller/CatalogSearchController.java)|
|餐厅列表|`GET /api/restaurants`|无业务参数|`RestaurantResponse[]`|[RestaurantController](https://github.com/zehua-wu/OnlineOrder-Dev/blob/15d42405ec0e35d48bb3c1259e864f0b47411cbc/backend/src/main/java/com/zehua/onlineorder/restaurant/controller/RestaurantController.java#L28)|
|餐厅菜单|`GET /api/restaurants/{restaurantId}/menu`|真实 UUID|`MenuItemResponse[]`，`X-Menu-Cache` header|[RestaurantController](https://github.com/zehua-wu/OnlineOrder-Dev/blob/15d42405ec0e35d48bb3c1259e864f0b47411cbc/backend/src/main/java/com/zehua/onlineorder/restaurant/controller/RestaurantController.java#L38)|
|当前购物车|`GET /api/cart`|Bearer JWT|`CartResponse`|[CartController](https://github.com/zehua-wu/OnlineOrder-Dev/blob/15d42405ec0e35d48bb3c1259e864f0b47411cbc/backend/src/main/java/com/zehua/onlineorder/cart/controller/CartController.java#L39)|
|添加|`POST /api/cart/items`|`menuItemId`、`quantity`|添加后的完整 `CartResponse`|[CartController](https://github.com/zehua-wu/OnlineOrder-Dev/blob/15d42405ec0e35d48bb3c1259e864f0b47411cbc/backend/src/main/java/com/zehua/onlineorder/cart/controller/CartController.java#L44)|
|长期记忆读取|`GET /api/agent/memories?limit=50`|JWT；limit 1..100|memory 数组|[MemoryController](https://github.com/zehua-wu/OnlineOrder-Dev/blob/15d42405ec0e35d48bb3c1259e864f0b47411cbc/backend/src/main/java/com/zehua/onlineorder/agent/memory/controller/AgentUserMemoryController.java)|
|长期记忆变更|`POST /api/agent/memories/mutations`|mutations 数组，最多 10|最新最多 50 条 memory|同上|

没有调用 `/api/menu`、`/api/cart/add`、`/api/memories/search` 或虚构的单商品查询/向量检索接口。`/agent/actions/...` 是本分支新增的 **Agent 服务接口**，不是声称 Spring 已经存在的接口。

## 3. 搜索合同：结构筛选 + SQL 子串匹配

`MenuItemSearchRequest` 的真实字段：

```json
{
  "keyword": "avocado",
  "primaryProtein": "CHICKEN",
  "maxSpicyLevel": 1,
  "maxPrice": 15,
  "limit": 10
}
```

其他可选字段为 `cuisineType/category/maxSweetnessLevel/vegetarian/caffeinated/servingTemperature/minPrice`。辣度和甜度 0..4；limit 1..100；keyword 最长 100，category 最长 50。枚举以 `app/models/tools.py` 对齐的后端 Enum 为准。

Agent 工具采用 snake_case，client 转换成上述 camelCase。`start_new_search`、`clear_filters` 只供 Harness 合并状态，不会发给 Spring。

[MenuItemSearchRepository](https://github.com/zehua-wu/OnlineOrder-Dev/blob/15d42405ec0e35d48bb3c1259e864f0b47411cbc/backend/src/main/java/com/zehua/onlineorder/menu/repository/MenuItemSearchRepository.java) 的实际行为：

- 仅返回 OPEN 餐厅、已上架且 `availableQuantity > 0` 的商品。
- keyword 在 name/description/ingredientSummary 上作不区分大小写的连续子串匹配；它不是多词分词、embedding 或语义搜索。
- 结构条件以 AND 合并；按价格升序、名称升序排序。
- Backend 缺省 limit 为 20，Agent 主动传 10。响应为数组，没有总数、cursor 或 offset。

因此 Agent 将“牛油果”翻译为 `avocado`，并避免把 chicken 再拼入 keyword。多轮“再加 avocado”会继承原价格、蛋白质和辣度条件，而不要求后端懂对话。

搜索返回的商品 ID 字段为 `menuItemId`，名称为 `menuItemName`；菜单接口则是 `id`、`name`。两种响应在 ToolExecutor 中归一成 `SearchResultReference`，卡片和后续 position 都引用真实返回值。

`totalResults` 和“更多卡片”只基于本轮保存的数组。达到 limit 不能证明数据库没有更多结果，V2 不伪造服务端分页。

## 4. 菜单与库存的不同含义

菜单接口通过 `MenuService.viewAvailableMenuWithCacheStatus` 使用 Redis cache，返回上架菜单项，包括可能 `sellable=false` 的缺货项，包含 `availableQuantity/reservedQuantity/stockStatus`。

菜单不提供搜索 DTO 中所有营养/口味元数据。V2 不凭空补出 vegetarian、过敏原、蛋白质等未知值。

确认添加前会读取购物车，再通过实际餐厅菜单核对上架、sellable 和库存快照，比较“已有数量 + 本次数量”。但是菜单可能命中 cache，读取后也会发生并发变化，因此这个校验不能预留库存、不能替代结账。最终库存与支付一致性仍属于现有 Spring 流程。

## 5. 购物车合同和关键可靠性事实

真实添加请求只接受：

```json
{"menuItemId":"a4000000-0000-0000-0000-000000000001","quantity":2}
```

DTO 要求 UUID 非空、数量至少为 1。V2 为单次操作增加 99 的上限，这是 Harness 策略，不是虚构的后端约束。

实际响应形状：

```json
{
  "id":"a5000000-0000-0000-0000-000000000001",
  "userId":"11111111-1111-1111-1111-111111111111",
  "status":"ACTIVE",
  "items":[{
    "id":"a6000000-0000-0000-0000-000000000001",
    "menuItemId":"a4000000-0000-0000-0000-000000000001",
    "name":"Avocado Chicken Bowl",
    "price":12.0,
    "imageUrl":null,
    "quantity":2,
    "subtotal":24.0
  }],
  "totalAmount":24.0
}
```

没有 active cart 时，`id=null/items=[]/totalAmount=0` 是合法响应。金额由 Spring BigDecimal 计算，Agent 只展示返回值，不负责财务结算。

[CartService.addItem](https://github.com/zehua-wu/OnlineOrder-Dev/blob/15d42405ec0e35d48bb3c1259e864f0b47411cbc/backend/src/main/java/com/zehua/onlineorder/cart/service/CartService.java#L53) 对已有项调用 `increaseQuantity`，因此请求两次就会累加两次。Controller **不接收或使用 Idempotency-Key**。原系统结账接口的幂等设计不能套用到这个端点。

CartService 检查用户、商品上架、餐厅营业；add 本身没有原子预留库存。V2 不把“加入购物车”描述为“库存已锁定”或“订单已完成”。

400、401、403、404、409、429 和 5xx 依据 SecurityConfig、ApiExceptionHandler 处理。添加返回明确 4xx 时不自动重试；网络异常、5xx、无效的成功响应均保守标记 UNKNOWN。更多理由见架构文档的崩溃窗口表。

## 6. 长期记忆真实合同

Backend 已有 `agent_user_memories` 表与用户级 UPSERT/DELETE 接口；Agent 不直接连接 PostgreSQL，也不创建额外迁移。

```json
{"mutations":[
  {"operation":"UPSERT","key":"spice.preference","value":"Usually prefers mild food"},
  {"operation":"DELETE","key":"ingredient.dislike:cilantro","value":null}
]}
```

存储隔离键是 `(user_id, memory_key)`，user_id 从 JWT 得到。列表按更新时间倒序，最多读取最近 100 条；V2 默认 50。响应的 key/value 被 Agent 使用，后端还会返回 id/createdAt/updatedAt，但当前检索模型不使用这些额外元数据。

V2 没有声称它提供向量数据库、全量历史查询、持久化 evidence、版本冲突检测或可证明的过敏原安全。证据引用只用于抽取时校验，不会发送给不支持这个字段的 Backend。

## 7. 前端兼容性与未改变的范围

`frontend/src/services/agentClient.js` 现有聊天请求只发送 message/sessionId，V2 继续接受。新增 requestId 是可选增强；不修改前端就不能保证浏览器重复发送同一句消息时做请求级去重。

现有“卡片添加”按钮本来通过原 API 修改购物车，它不经过 Agent 的操作日志。Agent 用户锁也不能锁住用户在原 UI 或别的客户端发起的并发购物车变更。V2 因此不根据购物车数量差自动推断某个 UNKNOWN action 是否成功。

源码合同的 Mock 并不等同于运行中服务合同测试。本次运行的测试以 MockTransport、SDK wire Mock 和 fakeredis 验证，未对真实数据库或真实模型执行端到端写入。
