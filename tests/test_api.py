from fastapi.testclient import TestClient

from app.main import create_app
from app.models.chat import ChatResponse, MenuItemCard, SearchCardsResponse


class FakeOrchestrator:
    async def chat(self, *, message, session_id, authorization):
        assert message == "chicken"
        assert authorization == "Bearer test-token"
        return ChatResponse(
            sessionId=session_id or "7adf472e-2d2e-4d72-a962-2584cd1549f9",
            answer="result",
            toolSteps=1,
        )

    async def get_search_cards(self, *, session_id, authorization, offset, limit):
        assert session_id == "7adf472e-2d2e-4d72-a962-2584cd1549f9"
        assert authorization == "Bearer test-token"
        assert offset == 3
        assert limit == 3
        return SearchCardsResponse(
            cards=[
                MenuItemCard(
                    position=4,
                    menuItemId="item-4",
                    name="Chicken Wrap",
                    price=11.49,
                )
            ],
            totalResults=4,
            nextOffset=4,
            hasMore=False,
        )


class FakeBackendClient:
    def __init__(self, role="CUSTOMER"):
        self.role = role

    async def get_current_user(self, *, authorization):
        assert authorization == "Bearer test-token"
        return {"id": "customer-1", "role": self.role}


def test_health() -> None:
    with TestClient(create_app(orchestrator=FakeOrchestrator(), backend_client=FakeBackendClient())) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_contract() -> None:
    with TestClient(create_app(orchestrator=FakeOrchestrator(), backend_client=FakeBackendClient())) as client:
        response = client.post(
            "/agent/chat",
            headers={"Authorization": "Bearer test-token"},
            json={"message": "chicken"},
        )
    assert response.status_code == 200
    assert response.json() == {
        "sessionId": "7adf472e-2d2e-4d72-a962-2584cd1549f9",
        "answer": "result",
        "toolSteps": 1,
        "cards": [],
        "totalResults": 0,
        "hasMore": False,
    }


def test_search_cards_contract() -> None:
    with TestClient(
        create_app(orchestrator=FakeOrchestrator(), backend_client=FakeBackendClient())
    ) as client:
        response = client.get(
            "/agent/sessions/7adf472e-2d2e-4d72-a962-2584cd1549f9/cards?offset=3&limit=3",
            headers={"Authorization": "Bearer test-token"},
        )
    assert response.status_code == 200
    assert response.json()["cards"][0] == {
        "position": 4,
        "menuItemId": "item-4",
        "name": "Chicken Wrap",
        "description": None,
        "ingredientSummary": None,
        "restaurantId": None,
        "restaurantName": None,
        "price": 11.49,
        "imageUrl": None,
        "category": None,
        "cuisineType": None,
        "availableQuantity": None,
        "primaryProtein": None,
        "spicyLevel": None,
        "sweetnessLevel": None,
        "vegetarian": None,
        "caffeinated": None,
        "servingTemperature": None,
    }
    assert response.json()["hasMore"] is False


def test_chat_rejects_invalid_session_id() -> None:
    with TestClient(create_app(orchestrator=FakeOrchestrator(), backend_client=FakeBackendClient())) as client:
        response = client.post(
            "/agent/chat",
            json={"message": "chicken", "sessionId": "not-a-uuid"},
        )
    assert response.status_code == 422


def test_chat_rejects_blank_message() -> None:
    with TestClient(create_app(orchestrator=FakeOrchestrator(), backend_client=FakeBackendClient())) as client:
        response = client.post("/agent/chat", json={"message": "   "})
    assert response.status_code == 422


def test_chat_requires_login() -> None:
    with TestClient(create_app(orchestrator=FakeOrchestrator(), backend_client=FakeBackendClient())) as client:
        response = client.post("/agent/chat", json={"message": "chicken"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Customer login is required to use the ordering assistant."


def test_chat_rejects_non_customer_account() -> None:
    with TestClient(
        create_app(orchestrator=FakeOrchestrator(), backend_client=FakeBackendClient(role="MERCHANT"))
    ) as client:
        response = client.post(
            "/agent/chat",
            headers={"Authorization": "Bearer test-token"},
            json={"message": "chicken"},
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "Only customer accounts can use the ordering assistant."
