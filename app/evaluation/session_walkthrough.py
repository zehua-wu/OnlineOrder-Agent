"""Generate complete, synthetic Session snapshots for the Chinese tutorial."""

import asyncio
import json
from pathlib import Path

import httpx

from app.agent.orchestrator import AgentOrchestrator
from app.clients.onlineorder_backend import OnlineOrderBackendClient
from app.evaluation.mock_backend import USER_ID, DemoBackend
from app.llm.mock import MockOrderingModel
from app.memory.coordinator import SessionCoordinator
from app.memory.in_memory import InMemorySessionStore
from app.tools.definitions import AGENT_TOOLS
from app.tools.executor import ToolExecutor


async def main():
    backend = DemoBackend()
    store = InMemorySessionStore()
    snapshots = []
    action_id = None
    async with httpx.AsyncClient(
        base_url="http://fixture.test", transport=httpx.MockTransport(backend.handle)
    ) as http:
        agent = AgentOrchestrator(
            model=MockOrderingModel(),
            tool_executor=ToolExecutor(OnlineOrderBackendClient(http)),
            session_store=store,
            coordinator=SessionCoordinator(),
            session_ttl_seconds=3600,
            recent_message_limit=12,
            max_tool_steps=5,
        )
        session_id = None
        for message in (
            "找15美元以内不太辣的鸡肉",
            "最好有avocado",
            "第二个不错",
            "把第二个加入两份",
            "确认",
            "查看购物车",
        ):
            response = await agent.chat(
                message=message,
                session_id=session_id,
                user_id=USER_ID,
                authorization="Bearer demo-token",
            )
            session_id = response.session_id
            if response.pending_action:
                action_id = response.pending_action.action_id
            saved = await store.get(session_id)
            snapshots.append(
                {
                    "user_message": message,
                    "session": saved.model_dump(mode="json"),
                    "backend_cart": backend.cart(),
                    "write_count": backend.write_count,
                }
            )
        action = await agent.get_action(user_id=USER_ID, action_id=action_id)
    target = Path("docs")
    (target / "examples").mkdir(parents=True, exist_ok=True)
    (target / "examples/session-evolution.json").write_text(
        json.dumps(snapshots, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (target / "examples/tools.json").write_text(
        json.dumps(AGENT_TOOLS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    paragraphs = [
        """# 同一个 Session 的完整 JSON 演变

以下内容由 `python -m app.evaluation.session_walkthrough` 执行真实 Harness 和合成 Mock 后端生成。商品、用户、时间和 UUID 是演示数据；没有真实凭据。时间戳使用 UTC（Z），展示时可换成你的本地时区。

每个 JSON 块都是该轮**完整 Session 文档**，没有省略字段。单独的 [JSON 文件](examples/session-evolution.json) 还保存了每步真实 Mock cart 与累计写入次数，方便 diff。模型不会保存完整 tool transcript，而是由工作状态恢复下一轮的引用。

观察重点：前两轮 search 的条件合并；第三轮 selected_item；第四轮 pending_action 出现但 cart 仍空；第五轮仅经用户确认才有后端写入；第六轮 cart 快照来自 get_cart。
"""
    ]
    explanations = [
        "搜索成功：CHICKEN、价格和辣度进入 search，真实 UUID 和 position 进入候选映射。没有购物车写入。",
        "补充 avocado：继承原条件，只更新 keyword，候选替换。messages 保留前一轮对话。",
        "明确选中第二个：selected_item 来自 position 2；选择本身不会修改 cart。",
        "准备添加两份：phase=AWAITING_CONFIRMATION；action_id 由应用生成，带有效期；写入次数仍然为 0。",
        "下一条用户消息确认：程序分支创建写前日志、单次提交。pending_action 清空，phase 回到 CHAT，cart 使用成功响应。",
        "再查购物车：调用 GET /api/cart，验证当前实际数量。messages 刚好为 6 对，再继续对话才会触发默认压缩。",
    ]
    for index, (snapshot, explanation) in enumerate(
        zip(snapshots, explanations, strict=True), start=1
    ):
        paragraphs.append(
            f"\n## 第 {index} 轮：{snapshot['user_message']}\n\n{explanation}\n\n后端累计写入次数：{snapshot['write_count']}。\n\n```json\n"
            + json.dumps(snapshot["session"], ensure_ascii=False, indent=2)
            + "\n```\n"
        )
    paragraphs.append(
        "\n## Session 之外的动作日志\n\n这份记录属于用户级 journal，生命周期可以长于 Session。即使另一个 HTTP 请求确认同一个 action，也只返回此回执，不重复 POST。\n\n```json\n"
        + action.model_dump_json(indent=2)
        + "\n```\n"
    )
    paragraphs.append("""
## 接下来自己做两个实验

将 `SESSION_RECENT_MESSAGE_LIMIT=4`，继续发送普通消息，观察 messages 只保留两对，summary 变成更早用户原话的有界 JSON 引用列表；search、selected_item 不靠 summary 恢复，所以不会跟着旧消息一起丢失。

运行 `pytest tests/test_harness_v2.py -q`，阅读 `test_unknown_write_blocks_new_writes_until_explicit_review`：模拟后端已加购但响应丢失，观察 action=UNKNOWN、用户屏障保留、再次确认没有第二次 POST；核对后 acknowledge 才允许新动作。取消/过期流程则完全没有写入。

Session 里的 cart 只是最近一次读取；不要拿它推断未来库存、支付状态或未知操作的因果关系。request/action 的其他存储 JSON 类型见 `app/models/harness.py` 和架构文档。
""")
    (target / "session-walkthrough-zh.md").write_text("\n".join(paragraphs), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
