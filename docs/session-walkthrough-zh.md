# 同一个 Session 的完整 JSON 演变

以下内容由 `python -m app.evaluation.session_walkthrough` 执行真实 Harness 和合成 Mock 后端生成。商品、用户、时间和 UUID 是演示数据；没有真实凭据。时间戳使用 UTC（Z），展示时可换成你的本地时区。

每个 JSON 块都是该轮**完整 Session 文档**，没有省略字段。单独的 [JSON 文件](examples/session-evolution.json) 还保存了每步真实 Mock cart 与累计写入次数，方便 diff。模型不会保存完整 tool transcript，而是由工作状态恢复下一轮的引用。

观察重点：前两轮 search 的条件合并；第三轮 selected_item；第四轮 pending_action 出现但 cart 仍空；第五轮仅经用户确认才有后端写入；第六轮 cart 快照来自 get_cart。


## 第 1 轮：找15美元以内不太辣的鸡肉

搜索成功：CHICKEN、价格和辣度进入 search，真实 UUID 和 position 进入候选映射。没有购物车写入。

后端累计写入次数：0。

```json
{
  "schema_version": 2,
  "session_id": "d6b76614-60ec-476b-ba0f-0d29880655a2",
  "revision": 1,
  "turn_count": 1,
  "user_id": "11111111-1111-1111-1111-111111111111",
  "owner_fingerprint": null,
  "messages": [
    {
      "role": "user",
      "content": "找15美元以内不太辣的鸡肉"
    },
    {
      "role": "assistant",
      "content": "已查询到工具返回的数据。"
    }
  ],
  "state": {
    "current_task": "MENU_SEARCH",
    "search": {
      "keyword": null,
      "cuisine_type": null,
      "category": null,
      "primary_protein": "CHICKEN",
      "max_spicy_level": 1,
      "max_sweetness_level": null,
      "vegetarian": null,
      "caffeinated": null,
      "serving_temperature": null,
      "min_price": null,
      "max_price": 15.0,
      "limit": 10
    },
    "last_search_results": [
      {
        "position": 1,
        "menu_item_id": "a4000000-0000-0000-0000-000000000001",
        "name": "Avocado Chicken Bowl",
        "description": "Synthetic offline fixture",
        "ingredient_summary": "chicken avocado rice",
        "restaurant_name": "Fixture Kitchen",
        "restaurant_id": "a3000000-0000-0000-0000-000000000001",
        "price": 12.0,
        "image_url": null,
        "category": "MAIN",
        "cuisine_type": "AMERICAN",
        "available_quantity": 10,
        "primary_protein": "CHICKEN",
        "spicy_level": 1,
        "sweetness_level": 0,
        "vegetarian": false,
        "caffeinated": false,
        "serving_temperature": "HOT"
      },
      {
        "position": 2,
        "menu_item_id": "a4000000-0000-0000-0000-000000000002",
        "name": "Avocado Chicken Wrap",
        "description": "Synthetic offline fixture",
        "ingredient_summary": "chicken avocado tortilla",
        "restaurant_name": "Fixture Kitchen",
        "restaurant_id": "a3000000-0000-0000-0000-000000000001",
        "price": 14.0,
        "image_url": null,
        "category": "MAIN",
        "cuisine_type": "AMERICAN",
        "available_quantity": 5,
        "primary_protein": "CHICKEN",
        "spicy_level": 0,
        "sweetness_level": 0,
        "vegetarian": false,
        "caffeinated": false,
        "serving_temperature": "HOT"
      }
    ],
    "selected_item": null,
    "phase": "CHAT",
    "pending_action": null,
    "cart": null,
    "last_restaurants": [],
    "results_updated_at": "2026-11-04T17:48:43.288072Z"
  },
  "summary": null,
  "created_at": "2026-11-04T17:48:43.285284Z",
  "updated_at": "2026-11-04T17:48:43.288214Z"
}
```


## 第 2 轮：最好有avocado

补充 avocado：继承原条件，只更新 keyword，候选替换。messages 保留前一轮对话。

后端累计写入次数：0。

```json
{
  "schema_version": 2,
  "session_id": "d6b76614-60ec-476b-ba0f-0d29880655a2",
  "revision": 2,
  "turn_count": 2,
  "user_id": "11111111-1111-1111-1111-111111111111",
  "owner_fingerprint": null,
  "messages": [
    {
      "role": "user",
      "content": "找15美元以内不太辣的鸡肉"
    },
    {
      "role": "assistant",
      "content": "已查询到工具返回的数据。"
    },
    {
      "role": "user",
      "content": "最好有avocado"
    },
    {
      "role": "assistant",
      "content": "已查询到工具返回的数据。"
    }
  ],
  "state": {
    "current_task": "MENU_SEARCH",
    "search": {
      "keyword": "avocado",
      "cuisine_type": null,
      "category": null,
      "primary_protein": "CHICKEN",
      "max_spicy_level": 1,
      "max_sweetness_level": null,
      "vegetarian": null,
      "caffeinated": null,
      "serving_temperature": null,
      "min_price": null,
      "max_price": 15.0,
      "limit": 10
    },
    "last_search_results": [
      {
        "position": 1,
        "menu_item_id": "a4000000-0000-0000-0000-000000000001",
        "name": "Avocado Chicken Bowl",
        "description": "Synthetic offline fixture",
        "ingredient_summary": "chicken avocado rice",
        "restaurant_name": "Fixture Kitchen",
        "restaurant_id": "a3000000-0000-0000-0000-000000000001",
        "price": 12.0,
        "image_url": null,
        "category": "MAIN",
        "cuisine_type": "AMERICAN",
        "available_quantity": 10,
        "primary_protein": "CHICKEN",
        "spicy_level": 1,
        "sweetness_level": 0,
        "vegetarian": false,
        "caffeinated": false,
        "serving_temperature": "HOT"
      },
      {
        "position": 2,
        "menu_item_id": "a4000000-0000-0000-0000-000000000002",
        "name": "Avocado Chicken Wrap",
        "description": "Synthetic offline fixture",
        "ingredient_summary": "chicken avocado tortilla",
        "restaurant_name": "Fixture Kitchen",
        "restaurant_id": "a3000000-0000-0000-0000-000000000001",
        "price": 14.0,
        "image_url": null,
        "category": "MAIN",
        "cuisine_type": "AMERICAN",
        "available_quantity": 5,
        "primary_protein": "CHICKEN",
        "spicy_level": 0,
        "sweetness_level": 0,
        "vegetarian": false,
        "caffeinated": false,
        "serving_temperature": "HOT"
      }
    ],
    "selected_item": null,
    "phase": "CHAT",
    "pending_action": null,
    "cart": null,
    "last_restaurants": [],
    "results_updated_at": "2026-11-04T17:48:43.289656Z"
  },
  "summary": null,
  "created_at": "2026-11-04T17:48:43.285284Z",
  "updated_at": "2026-11-04T17:48:43.289740Z"
}
```


## 第 3 轮：第二个不错

明确选中第二个：selected_item 来自 position 2；选择本身不会修改 cart。

后端累计写入次数：0。

```json
{
  "schema_version": 2,
  "session_id": "d6b76614-60ec-476b-ba0f-0d29880655a2",
  "revision": 3,
  "turn_count": 3,
  "user_id": "11111111-1111-1111-1111-111111111111",
  "owner_fingerprint": null,
  "messages": [
    {
      "role": "user",
      "content": "找15美元以内不太辣的鸡肉"
    },
    {
      "role": "assistant",
      "content": "已查询到工具返回的数据。"
    },
    {
      "role": "user",
      "content": "最好有avocado"
    },
    {
      "role": "assistant",
      "content": "已查询到工具返回的数据。"
    },
    {
      "role": "user",
      "content": "第二个不错"
    },
    {
      "role": "assistant",
      "content": "已查询到工具返回的数据。"
    }
  ],
  "state": {
    "current_task": "MENU_SEARCH",
    "search": {
      "keyword": "avocado",
      "cuisine_type": null,
      "category": null,
      "primary_protein": "CHICKEN",
      "max_spicy_level": 1,
      "max_sweetness_level": null,
      "vegetarian": null,
      "caffeinated": null,
      "serving_temperature": null,
      "min_price": null,
      "max_price": 15.0,
      "limit": 10
    },
    "last_search_results": [
      {
        "position": 1,
        "menu_item_id": "a4000000-0000-0000-0000-000000000001",
        "name": "Avocado Chicken Bowl",
        "description": "Synthetic offline fixture",
        "ingredient_summary": "chicken avocado rice",
        "restaurant_name": "Fixture Kitchen",
        "restaurant_id": "a3000000-0000-0000-0000-000000000001",
        "price": 12.0,
        "image_url": null,
        "category": "MAIN",
        "cuisine_type": "AMERICAN",
        "available_quantity": 10,
        "primary_protein": "CHICKEN",
        "spicy_level": 1,
        "sweetness_level": 0,
        "vegetarian": false,
        "caffeinated": false,
        "serving_temperature": "HOT"
      },
      {
        "position": 2,
        "menu_item_id": "a4000000-0000-0000-0000-000000000002",
        "name": "Avocado Chicken Wrap",
        "description": "Synthetic offline fixture",
        "ingredient_summary": "chicken avocado tortilla",
        "restaurant_name": "Fixture Kitchen",
        "restaurant_id": "a3000000-0000-0000-0000-000000000001",
        "price": 14.0,
        "image_url": null,
        "category": "MAIN",
        "cuisine_type": "AMERICAN",
        "available_quantity": 5,
        "primary_protein": "CHICKEN",
        "spicy_level": 0,
        "sweetness_level": 0,
        "vegetarian": false,
        "caffeinated": false,
        "serving_temperature": "HOT"
      }
    ],
    "selected_item": {
      "menu_item_id": "a4000000-0000-0000-0000-000000000002",
      "name": "Avocado Chicken Wrap",
      "restaurant_name": "Fixture Kitchen",
      "price": 14.0
    },
    "phase": "CHAT",
    "pending_action": null,
    "cart": null,
    "last_restaurants": [],
    "results_updated_at": "2026-11-04T17:48:43.289656Z"
  },
  "summary": null,
  "created_at": "2026-11-04T17:48:43.285284Z",
  "updated_at": "2026-11-04T17:48:43.290290Z"
}
```


## 第 4 轮：把第二个加入两份

准备添加两份：phase=AWAITING_CONFIRMATION；action_id 由应用生成，带有效期；写入次数仍然为 0。

后端累计写入次数：0。

```json
{
  "schema_version": 2,
  "session_id": "d6b76614-60ec-476b-ba0f-0d29880655a2",
  "revision": 4,
  "turn_count": 4,
  "user_id": "11111111-1111-1111-1111-111111111111",
  "owner_fingerprint": null,
  "messages": [
    {
      "role": "user",
      "content": "找15美元以内不太辣的鸡肉"
    },
    {
      "role": "assistant",
      "content": "已查询到工具返回的数据。"
    },
    {
      "role": "user",
      "content": "最好有avocado"
    },
    {
      "role": "assistant",
      "content": "已查询到工具返回的数据。"
    },
    {
      "role": "user",
      "content": "第二个不错"
    },
    {
      "role": "assistant",
      "content": "已查询到工具返回的数据。"
    },
    {
      "role": "user",
      "content": "把第二个加入两份"
    },
    {
      "role": "assistant",
      "content": "准备将 Avocado Chicken Wrap × 2 加入购物车。请回复“确认”或“取消”（5 分钟内有效）。"
    }
  ],
  "state": {
    "current_task": "MENU_SEARCH",
    "search": {
      "keyword": "avocado",
      "cuisine_type": null,
      "category": null,
      "primary_protein": "CHICKEN",
      "max_spicy_level": 1,
      "max_sweetness_level": null,
      "vegetarian": null,
      "caffeinated": null,
      "serving_temperature": null,
      "min_price": null,
      "max_price": 15.0,
      "limit": 10
    },
    "last_search_results": [
      {
        "position": 1,
        "menu_item_id": "a4000000-0000-0000-0000-000000000001",
        "name": "Avocado Chicken Bowl",
        "description": "Synthetic offline fixture",
        "ingredient_summary": "chicken avocado rice",
        "restaurant_name": "Fixture Kitchen",
        "restaurant_id": "a3000000-0000-0000-0000-000000000001",
        "price": 12.0,
        "image_url": null,
        "category": "MAIN",
        "cuisine_type": "AMERICAN",
        "available_quantity": 10,
        "primary_protein": "CHICKEN",
        "spicy_level": 1,
        "sweetness_level": 0,
        "vegetarian": false,
        "caffeinated": false,
        "serving_temperature": "HOT"
      },
      {
        "position": 2,
        "menu_item_id": "a4000000-0000-0000-0000-000000000002",
        "name": "Avocado Chicken Wrap",
        "description": "Synthetic offline fixture",
        "ingredient_summary": "chicken avocado tortilla",
        "restaurant_name": "Fixture Kitchen",
        "restaurant_id": "a3000000-0000-0000-0000-000000000001",
        "price": 14.0,
        "image_url": null,
        "category": "MAIN",
        "cuisine_type": "AMERICAN",
        "available_quantity": 5,
        "primary_protein": "CHICKEN",
        "spicy_level": 0,
        "sweetness_level": 0,
        "vegetarian": false,
        "caffeinated": false,
        "serving_temperature": "HOT"
      }
    ],
    "selected_item": {
      "menu_item_id": "a4000000-0000-0000-0000-000000000002",
      "name": "Avocado Chicken Wrap",
      "restaurant_name": "Fixture Kitchen",
      "price": 14.0
    },
    "phase": "AWAITING_CONFIRMATION",
    "pending_action": {
      "action_id": "7d51a8f4-4cae-4190-9068-33a839342898",
      "kind": "ADD_TO_CART",
      "menu_item_id": "a4000000-0000-0000-0000-000000000002",
      "restaurant_id": "a3000000-0000-0000-0000-000000000001",
      "name": "Avocado Chicken Wrap",
      "quantity": 2,
      "created_at": "2026-11-04T17:48:43.290816Z",
      "expires_at": "2026-11-04T17:53:43.290734Z"
    },
    "cart": null,
    "last_restaurants": [],
    "results_updated_at": "2026-11-04T17:48:43.289656Z"
  },
  "summary": null,
  "created_at": "2026-11-04T17:48:43.285284Z",
  "updated_at": "2026-11-04T17:48:43.290923Z"
}
```


## 第 5 轮：确认

下一条用户消息确认：程序分支创建写前日志、单次提交。pending_action 清空，phase 回到 CHAT，cart 使用成功响应。

后端累计写入次数：1。

```json
{
  "schema_version": 2,
  "session_id": "d6b76614-60ec-476b-ba0f-0d29880655a2",
  "revision": 5,
  "turn_count": 5,
  "user_id": "11111111-1111-1111-1111-111111111111",
  "owner_fingerprint": null,
  "messages": [
    {
      "role": "user",
      "content": "找15美元以内不太辣的鸡肉"
    },
    {
      "role": "assistant",
      "content": "已查询到工具返回的数据。"
    },
    {
      "role": "user",
      "content": "最好有avocado"
    },
    {
      "role": "assistant",
      "content": "已查询到工具返回的数据。"
    },
    {
      "role": "user",
      "content": "第二个不错"
    },
    {
      "role": "assistant",
      "content": "已查询到工具返回的数据。"
    },
    {
      "role": "user",
      "content": "把第二个加入两份"
    },
    {
      "role": "assistant",
      "content": "准备将 Avocado Chicken Wrap × 2 加入购物车。请回复“确认”或“取消”（5 分钟内有效）。"
    },
    {
      "role": "user",
      "content": "确认"
    },
    {
      "role": "assistant",
      "content": "已将 Avocado Chicken Wrap × 2 加入购物车。"
    }
  ],
  "state": {
    "current_task": "MENU_SEARCH",
    "search": {
      "keyword": "avocado",
      "cuisine_type": null,
      "category": null,
      "primary_protein": "CHICKEN",
      "max_spicy_level": 1,
      "max_sweetness_level": null,
      "vegetarian": null,
      "caffeinated": null,
      "serving_temperature": null,
      "min_price": null,
      "max_price": 15.0,
      "limit": 10
    },
    "last_search_results": [
      {
        "position": 1,
        "menu_item_id": "a4000000-0000-0000-0000-000000000001",
        "name": "Avocado Chicken Bowl",
        "description": "Synthetic offline fixture",
        "ingredient_summary": "chicken avocado rice",
        "restaurant_name": "Fixture Kitchen",
        "restaurant_id": "a3000000-0000-0000-0000-000000000001",
        "price": 12.0,
        "image_url": null,
        "category": "MAIN",
        "cuisine_type": "AMERICAN",
        "available_quantity": 10,
        "primary_protein": "CHICKEN",
        "spicy_level": 1,
        "sweetness_level": 0,
        "vegetarian": false,
        "caffeinated": false,
        "serving_temperature": "HOT"
      },
      {
        "position": 2,
        "menu_item_id": "a4000000-0000-0000-0000-000000000002",
        "name": "Avocado Chicken Wrap",
        "description": "Synthetic offline fixture",
        "ingredient_summary": "chicken avocado tortilla",
        "restaurant_name": "Fixture Kitchen",
        "restaurant_id": "a3000000-0000-0000-0000-000000000001",
        "price": 14.0,
        "image_url": null,
        "category": "MAIN",
        "cuisine_type": "AMERICAN",
        "available_quantity": 5,
        "primary_protein": "CHICKEN",
        "spicy_level": 0,
        "sweetness_level": 0,
        "vegetarian": false,
        "caffeinated": false,
        "serving_temperature": "HOT"
      }
    ],
    "selected_item": {
      "menu_item_id": "a4000000-0000-0000-0000-000000000002",
      "name": "Avocado Chicken Wrap",
      "restaurant_name": "Fixture Kitchen",
      "price": 14.0
    },
    "phase": "CHAT",
    "pending_action": null,
    "cart": {
      "id": "a5000000-0000-0000-0000-000000000001",
      "userId": "11111111-1111-1111-1111-111111111111",
      "status": "ACTIVE",
      "items": [
        {
          "id": "a4000000-0000-0000-0000-000000000002",
          "menuItemId": "a4000000-0000-0000-0000-000000000002",
          "name": "Avocado Chicken Wrap",
          "price": 14.0,
          "imageUrl": null,
          "quantity": 2,
          "subtotal": 28.0
        }
      ],
      "totalAmount": 28.0
    },
    "last_restaurants": [],
    "results_updated_at": "2026-11-04T17:48:43.289656Z"
  },
  "summary": null,
  "created_at": "2026-11-04T17:48:43.285284Z",
  "updated_at": "2026-11-04T17:48:43.291979Z"
}
```


## 第 6 轮：查看购物车

再查购物车：调用 GET /api/cart，验证当前实际数量。messages 刚好为 6 对，再继续对话才会触发默认压缩。

后端累计写入次数：1。

```json
{
  "schema_version": 2,
  "session_id": "d6b76614-60ec-476b-ba0f-0d29880655a2",
  "revision": 6,
  "turn_count": 6,
  "user_id": "11111111-1111-1111-1111-111111111111",
  "owner_fingerprint": null,
  "messages": [
    {
      "role": "user",
      "content": "找15美元以内不太辣的鸡肉"
    },
    {
      "role": "assistant",
      "content": "已查询到工具返回的数据。"
    },
    {
      "role": "user",
      "content": "最好有avocado"
    },
    {
      "role": "assistant",
      "content": "已查询到工具返回的数据。"
    },
    {
      "role": "user",
      "content": "第二个不错"
    },
    {
      "role": "assistant",
      "content": "已查询到工具返回的数据。"
    },
    {
      "role": "user",
      "content": "把第二个加入两份"
    },
    {
      "role": "assistant",
      "content": "准备将 Avocado Chicken Wrap × 2 加入购物车。请回复“确认”或“取消”（5 分钟内有效）。"
    },
    {
      "role": "user",
      "content": "确认"
    },
    {
      "role": "assistant",
      "content": "已将 Avocado Chicken Wrap × 2 加入购物车。"
    },
    {
      "role": "user",
      "content": "查看购物车"
    },
    {
      "role": "assistant",
      "content": "已查询到工具返回的数据。"
    }
  ],
  "state": {
    "current_task": "CART",
    "search": {
      "keyword": "avocado",
      "cuisine_type": null,
      "category": null,
      "primary_protein": "CHICKEN",
      "max_spicy_level": 1,
      "max_sweetness_level": null,
      "vegetarian": null,
      "caffeinated": null,
      "serving_temperature": null,
      "min_price": null,
      "max_price": 15.0,
      "limit": 10
    },
    "last_search_results": [
      {
        "position": 1,
        "menu_item_id": "a4000000-0000-0000-0000-000000000001",
        "name": "Avocado Chicken Bowl",
        "description": "Synthetic offline fixture",
        "ingredient_summary": "chicken avocado rice",
        "restaurant_name": "Fixture Kitchen",
        "restaurant_id": "a3000000-0000-0000-0000-000000000001",
        "price": 12.0,
        "image_url": null,
        "category": "MAIN",
        "cuisine_type": "AMERICAN",
        "available_quantity": 10,
        "primary_protein": "CHICKEN",
        "spicy_level": 1,
        "sweetness_level": 0,
        "vegetarian": false,
        "caffeinated": false,
        "serving_temperature": "HOT"
      },
      {
        "position": 2,
        "menu_item_id": "a4000000-0000-0000-0000-000000000002",
        "name": "Avocado Chicken Wrap",
        "description": "Synthetic offline fixture",
        "ingredient_summary": "chicken avocado tortilla",
        "restaurant_name": "Fixture Kitchen",
        "restaurant_id": "a3000000-0000-0000-0000-000000000001",
        "price": 14.0,
        "image_url": null,
        "category": "MAIN",
        "cuisine_type": "AMERICAN",
        "available_quantity": 5,
        "primary_protein": "CHICKEN",
        "spicy_level": 0,
        "sweetness_level": 0,
        "vegetarian": false,
        "caffeinated": false,
        "serving_temperature": "HOT"
      }
    ],
    "selected_item": {
      "menu_item_id": "a4000000-0000-0000-0000-000000000002",
      "name": "Avocado Chicken Wrap",
      "restaurant_name": "Fixture Kitchen",
      "price": 14.0
    },
    "phase": "CHAT",
    "pending_action": null,
    "cart": {
      "id": "a5000000-0000-0000-0000-000000000001",
      "userId": "11111111-1111-1111-1111-111111111111",
      "status": "ACTIVE",
      "items": [
        {
          "id": "a4000000-0000-0000-0000-000000000002",
          "menuItemId": "a4000000-0000-0000-0000-000000000002",
          "name": "Avocado Chicken Wrap",
          "price": 14.0,
          "imageUrl": null,
          "quantity": 2,
          "subtotal": 28.0
        }
      ],
      "totalAmount": 28.0
    },
    "last_restaurants": [],
    "results_updated_at": "2026-11-04T17:48:43.289656Z"
  },
  "summary": null,
  "created_at": "2026-11-04T17:48:43.285284Z",
  "updated_at": "2026-11-04T17:48:43.292867Z"
}
```


## Session 之外的动作日志

这份记录属于用户级 journal，生命周期可以长于 Session。即使另一个 HTTP 请求确认同一个 action，也只返回此回执，不重复 POST。

```json
{
  "action": {
    "action_id": "7d51a8f4-4cae-4190-9068-33a839342898",
    "kind": "ADD_TO_CART",
    "menu_item_id": "a4000000-0000-0000-0000-000000000002",
    "restaurant_id": "a3000000-0000-0000-0000-000000000001",
    "name": "Avocado Chicken Wrap",
    "quantity": 2,
    "created_at": "2026-11-04T17:48:43.290816Z",
    "expires_at": "2026-11-04T17:53:43.290734Z"
  },
  "status": "SUCCEEDED",
  "cart": {
    "id": "a5000000-0000-0000-0000-000000000001",
    "userId": "11111111-1111-1111-1111-111111111111",
    "status": "ACTIVE",
    "items": [
      {
        "id": "a4000000-0000-0000-0000-000000000002",
        "menuItemId": "a4000000-0000-0000-0000-000000000002",
        "name": "Avocado Chicken Wrap",
        "price": 14.0,
        "imageUrl": null,
        "quantity": 2,
        "subtotal": 28.0
      }
    ],
    "totalAmount": 28.0
  },
  "error_code": null,
  "updated_at": "2026-11-04T17:48:43.291937Z"
}
```


## 接下来自己做两个实验

将 `SESSION_RECENT_MESSAGE_LIMIT=4`，继续发送普通消息，观察 messages 只保留两对，summary 变成更早用户原话的有界 JSON 引用列表；search、selected_item 不靠 summary 恢复，所以不会跟着旧消息一起丢失。

运行 `pytest tests/test_harness_v2.py -q`，阅读 `test_unknown_write_blocks_new_writes_until_explicit_review`：模拟后端已加购但响应丢失，观察 action=UNKNOWN、用户屏障保留、再次确认没有第二次 POST；核对后 acknowledge 才允许新动作。取消/过期流程则完全没有写入。

Session 里的 cart 只是最近一次读取；不要拿它推断未来库存、支付状态或未知操作的因果关系。request/action 的其他存储 JSON 类型见 `app/models/harness.py` 和架构文档。
