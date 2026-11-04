from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def demo_app():
    return create_app(settings=Settings(_env_file=None, llm_provider="mock", demo_backend=True))


def test_full_http_api_without_api_key():
    headers = {"Authorization": "Bearer demo-token"}
    with TestClient(demo_app()) as client:
        search = client.post(
            "/agent/chat", headers=headers, json={"message": "找鸡肉", "requestId": str(uuid4())}
        )
        assert search.status_code == 200
        session_id = search.json()["sessionId"]
        assert (
            client.get(f"/agent/sessions/{session_id}/cards?limit=1", headers=headers).json()[
                "nextOffset"
            ]
            == 1
        )
        staged = client.post(
            "/agent/chat",
            headers=headers,
            json={"sessionId": session_id, "message": "把第一个加入一份"},
        ).json()
        action_id = staged["pendingAction"]["action_id"]
        assert client.get(f"/agent/actions/{action_id}", headers=headers).status_code == 404
        committed = client.post(
            "/agent/chat",
            headers=headers,
            json={"sessionId": session_id, "message": "确认", "confirmActionId": action_id},
        )
        assert committed.status_code == 200
        assert committed.json()["cart"]["items"][0]["quantity"] == 1
        assert committed.json()["toolSteps"] == 1
        assert (
            client.get(f"/agent/actions/{action_id}", headers=headers).json()["status"]
            == "SUCCEEDED"
        )
        assert (
            client.get(
                f"/agent/actions/{action_id}", headers={"Authorization": "Bearer other-demo-token"}
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/agent/actions/{action_id}/acknowledge",
                headers=headers,
                json={"acknowledgement": "yes"},
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/agent/actions/{action_id}/acknowledge",
                headers=headers,
                json={"acknowledgement": "I_CHECKED_THE_CART"},
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/agent/chat",
                headers={"Authorization": "Bearer other-demo-token"},
                json={"message": "查看购物车", "sessionId": session_id},
            ).status_code
            == 403
        )


def test_http_request_replay_and_expired_session_contract():
    headers = {"Authorization": "Bearer demo-token"}
    body = {"message": "找鸡肉", "requestId": str(uuid4())}
    with TestClient(demo_app()) as client:
        first = client.post("/agent/chat", headers=headers, json=body)
        assert client.post("/agent/chat", headers=headers, json=body).json() == first.json()
        assert (
            client.post(
                "/agent/chat", headers=headers, json={**body, "message": "找素食"}
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/agent/chat", headers=headers, json={"message": "继续", "sessionId": str(uuid4())}
            ).status_code
            == 404
        )
        assert client.post("/agent/chat", json={"message": "找鸡肉"}).status_code == 401


def test_mismatched_confirmation_text_cannot_authorize_write():
    headers = {"Authorization": "Bearer demo-token"}
    with TestClient(demo_app()) as client:
        session = client.post("/agent/chat", headers=headers, json={"message": "找鸡肉"}).json()[
            "sessionId"
        ]
        action = client.post(
            "/agent/chat",
            headers=headers,
            json={"message": "把第一个加入一份", "sessionId": session},
        ).json()["pendingAction"]["action_id"]
        response = client.post(
            "/agent/chat",
            headers=headers,
            json={"message": "取消", "sessionId": session, "confirmActionId": action},
        )
        assert response.status_code == 409
        assert response.json()["code"] == "CONFIRMATION_TEXT_MISMATCH"
        cart = client.post(
            "/agent/chat", headers=headers, json={"message": "查看购物车", "sessionId": session}
        )
        assert cart.json()["cart"]["items"] == []
