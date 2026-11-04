"""Tiny deterministic demo policy; no inference quality claim and no network."""

import json
import re
from uuid import uuid4

from app.llm.base import ModelTurn, ToolCall


class MockOrderingModel:
    async def respond(self, *, input_items, tools, instructions):
        def call(name, args):
            tool = ToolCall(str(uuid4()), name, json.dumps(args, ensure_ascii=False))
            return ModelTurn(
                tool_calls=[tool],
                output_items=[
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": tool.call_id,
                                "type": "function",
                                "function": {"name": name, "arguments": tool.arguments},
                            }
                        ],
                    }
                ],
            )

        message = next(
            (
                i["content"]
                for i in reversed(input_items)
                if isinstance(i, dict) and i.get("role") == "user"
            ),
            "",
        ).lower()
        if (
            input_items
            and isinstance(input_items[-1], dict)
            and input_items[-1].get("type") == "function_call_output"
        ):
            output = json.loads(input_items[-1]["output"])
            if "restaurants" in output and ("菜单" in message or "menu" in message):
                return call("get_menu", {"restaurant_id": output["restaurants"][0]["id"]})
            return ModelTurn(
                text="已查询到工具返回的数据。"
                if output.get("ok")
                else "这次操作未成功，请检查条件后继续。"
            )
        if (
            "购物车" in message
            and any(w in message for w in ("查看", "看看", "有什么"))
            or "show cart" in message
        ):
            return call("get_cart", {})
        positions = {"一": 1, "二": 2, "三": 3}
        matched = re.search(r"第([一二三123])", message)
        position = (
            positions.get(matched[1], int(matched[1]) if matched and matched[1].isdigit() else None)
            if matched
            else None
        )
        if "second" in message:
            position = 2
        if "first" in message:
            position = 1
        if any(w in message for w in ("加入", "加到", "add")):
            qty = re.search(r"([1-9][0-9]*)\s*(?:份|units?)", message)
            quantity = (
                int(qty[1])
                if qty
                else (2 if any(w in message for w in ("两份", "二份", "two")) else 1)
            )
            return call("add_to_cart", {"position": position, "quantity": quantity})
        if position and any(w in message for w in ("不错", "选", "looks good", "choose")):
            return call("select_search_result", {"position": position})
        if any(w in message for w in ("餐厅", "菜单", "restaurant", "menu")):
            return call("list_restaurants", {})
        if any(
            w in message
            for w in ("鸡", "chicken", "avocado", "牛油果", "素食", "vegetarian", "找", "find")
        ):
            args = {}
            if "鸡" in message or "chicken" in message:
                args["primary_protein"] = "CHICKEN"
            if "素食" in message or "vegetarian" in message:
                args["vegetarian"] = True
            if "avocado" in message or "牛油果" in message:
                args["keyword"] = "avocado"
            if "不辣" in message or "不太辣" in message or "mild" in message:
                args["max_spicy_level"] = 1
            if "15" in message:
                args["max_price"] = 15
            if "取消预算" in message:
                args["clear_filters"] = ["max_price"]
            return call("search_menu", args)
        return ModelTurn(
            text="演示模式支持：找15美元以内不太辣的鸡肉、最好有avocado、第二个不错、把第二个加入两份、确认、查看购物车、看看菜单。"
        )
