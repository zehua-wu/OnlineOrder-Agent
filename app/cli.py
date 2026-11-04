"""Interactive client: python -m app.cli --demo (server must already be running)."""

import argparse
import json
import os
from uuid import uuid4

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--demo", action="store_true", help="Use the synthetic backend's demo-token"
    )
    parser.add_argument("--session-id")
    args = parser.parse_args()
    token = "demo-token" if args.demo else os.getenv("ONLINEORDER_CUSTOMER_TOKEN")
    if not token:
        parser.error(
            "Set ONLINEORDER_CUSTOMER_TOKEN to a CUSTOMER login JWT, or use --demo with the mock backend."
        )
    session_id = args.session_id
    pending_id = None
    with httpx.Client(
        base_url=args.url, headers={"Authorization": "Bearer " + token}, timeout=100
    ) as client:
        while True:
            try:
                message = input("你 > ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if message.lower() in {"exit", "quit"}:
                break
            if not message:
                continue
            body = {"message": message, "requestId": str(uuid4())}
            if session_id:
                body["sessionId"] = session_id
            if pending_id and message.lower().rstrip("。.!！") in {
                "确认",
                "确认添加",
                "确认加入",
                "确认加入购物车",
                "confirm",
                "confirm add",
            }:
                body["confirmActionId"] = pending_id
            try:
                response = client.post("/agent/chat", json=body)
            except httpx.RequestError:
                print(
                    f"请求未完成；requestId={body['requestId']}。不要盲目重复添加，请先查看购物车和已知 action。"
                )
                continue
            if not response.is_success:
                print(response.status_code, response.text)
                continue
            data = response.json()
            session_id = data["sessionId"]
            pending = data.get("pendingAction")
            pending_id = pending["action_id"] if pending else None
            print("助手 >", data["answer"])
            for card in data.get("cards", []):
                print(
                    f"  {card['position']}. {card['name']}  ${card.get('price')}  id={card['menuItemId']}"
                )
            if data.get("cart") is not None:
                print("购物车:", json.dumps(data["cart"], ensure_ascii=False))
            print(
                f"sessionId={session_id}  traceId={data.get('traceId')}  status={data.get('status')}"
            )
            if data.get("actionId"):
                print("actionId=" + data["actionId"])


if __name__ == "__main__":
    main()
