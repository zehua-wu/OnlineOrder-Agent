"""Contract-shaped synthetic fixtures. Never point this transport at a real cart."""

import json

import httpx

USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"
RESTAURANT_ID = "a3000000-0000-0000-0000-000000000001"
ITEM_1 = "a4000000-0000-0000-0000-000000000001"
ITEM_2 = "a4000000-0000-0000-0000-000000000002"
ITEM_3 = "a4000000-0000-0000-0000-000000000003"
ITEM_4 = "a4000000-0000-0000-0000-000000000004"
CATALOG = [
    {
        "menuItemId": ITEM_1,
        "menuItemName": "Avocado Chicken Bowl",
        "price": 12.0,
        "primaryProtein": "CHICKEN",
        "spicyLevel": 1,
        "vegetarian": False,
        "availableQuantity": 10,
        "ingredientSummary": "chicken avocado rice",
        "servingTemperature": "HOT",
        "caffeinated": False,
    },
    {
        "menuItemId": ITEM_2,
        "menuItemName": "Avocado Chicken Wrap",
        "price": 14.0,
        "primaryProtein": "CHICKEN",
        "spicyLevel": 0,
        "vegetarian": False,
        "availableQuantity": 5,
        "ingredientSummary": "chicken avocado tortilla",
        "servingTemperature": "HOT",
        "caffeinated": False,
    },
    {
        "menuItemId": ITEM_3,
        "menuItemName": "Tofu Salad",
        "price": 9.0,
        "primaryProtein": "TOFU",
        "spicyLevel": 0,
        "vegetarian": True,
        "availableQuantity": 8,
        "ingredientSummary": "tofu greens",
        "servingTemperature": "COLD",
        "caffeinated": False,
    },
    {
        "menuItemId": ITEM_4,
        "menuItemName": "Hot Chicken",
        "price": 18.0,
        "primaryProtein": "CHICKEN",
        "spicyLevel": 4,
        "vegetarian": False,
        "availableQuantity": 0,
        "ingredientSummary": "chicken chili",
        "servingTemperature": "HOT",
        "caffeinated": False,
    },
]
CATALOG = [
    {
        **item,
        "restaurantId": RESTAURANT_ID,
        "restaurantName": "Fixture Kitchen",
        "cuisineType": "AMERICAN",
        "category": "MAIN",
        "sweetnessLevel": 0,
        "imageUrl": None,
        "description": "Synthetic offline fixture",
    }
    for item in CATALOG
]


class DemoBackend:
    def __init__(self):
        self.quantities: dict[str, dict[str, int]] = {}
        self.memories: dict[str, dict[str, str]] = {}
        self.calls: list[tuple[str, str, dict | None]] = []
        self.next_cart_write_error: str | None = None
        self.write_count = 0

    def cart(self, user=USER_ID):
        items = []
        for item_id, quantity in self.quantities.get(user, {}).items():
            item = next(i for i in CATALOG if i["menuItemId"] == item_id)
            items.append(
                {
                    "id": item_id,
                    "menuItemId": item_id,
                    "name": item["menuItemName"],
                    "price": item["price"],
                    "imageUrl": None,
                    "quantity": quantity,
                    "subtotal": round(item["price"] * quantity, 2),
                }
            )
        return {
            "id": "a5000000-0000-0000-0000-000000000001" if items else None,
            "userId": user,
            "status": "ACTIVE",
            "items": items,
            "totalAmount": round(sum(i["subtotal"] for i in items), 2),
        }

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, path, body))
        token = request.headers.get("Authorization")
        user = OTHER_USER_ID if token == "Bearer other-demo-token" else USER_ID
        if (
            path != "/api/search"
            and not path.startswith("/api/restaurants")
            and token not in {"Bearer demo-token", "Bearer other-demo-token"}
        ):
            return httpx.Response(401, json={"message": "Login required"})
        if path == "/api/users/me":
            return httpx.Response(200, json={"id": user, "role": "CUSTOMER"})
        if path == "/api/search":
            items = [i for i in CATALOG if i["availableQuantity"] > 0]
            for key, value in body.items():
                if value is None or key == "limit":
                    continue
                if key == "keyword":
                    items = [
                        i
                        for i in items
                        if str(value).lower()
                        in (i["menuItemName"] + " " + i["ingredientSummary"]).lower()
                    ]
                elif key in {"maxPrice", "minPrice", "maxSpicyLevel", "maxSweetnessLevel"}:
                    field = {
                        "maxPrice": "price",
                        "minPrice": "price",
                        "maxSpicyLevel": "spicyLevel",
                        "maxSweetnessLevel": "sweetnessLevel",
                    }[key]
                    items = [
                        i
                        for i in items
                        if (i[field] >= value if key == "minPrice" else i[field] <= value)
                    ]
                else:
                    items = [i for i in items if i.get(key) == value]
            return httpx.Response(
                200,
                json=sorted(items, key=lambda i: (i["price"], i["menuItemName"]))[
                    : body.get("limit", 20)
                ],
            )
        if path == "/api/restaurants":
            return httpx.Response(
                200, json=[{"id": RESTAURANT_ID, "name": "Fixture Kitchen", "status": "OPEN"}]
            )
        if path == f"/api/restaurants/{RESTAURANT_ID}/menu":
            return httpx.Response(
                200,
                json=[
                    {
                        **i,
                        "id": i["menuItemId"],
                        "name": i["menuItemName"],
                        "available": True,
                        "sellable": i["availableQuantity"] > 0,
                        "reservedQuantity": 0,
                        "stockStatus": "AVAILABLE" if i["availableQuantity"] else "SOLD_OUT",
                    }
                    for i in CATALOG
                ],
            )
        if path == "/api/cart" and request.method == "GET":
            return httpx.Response(200, json=self.cart(user))
        if path == "/api/cart/items" and request.method == "POST":
            self.write_count += 1
            fault, self.next_cart_write_error = self.next_cart_write_error, None
            if fault == "conflict":
                return httpx.Response(409, json={"message": "Item unavailable"})
            quantities = self.quantities.setdefault(user, {})
            quantities[body["menuItemId"]] = (
                quantities.get(body["menuItemId"], 0) + body["quantity"]
            )
            if fault == "timeout_after_commit":
                raise httpx.ReadTimeout("Simulated lost response", request=request)
            if fault == "500_after_commit":
                return httpx.Response(500, json={"message": "Uncertain commit"})
            if fault == "invalid_json":
                return httpx.Response(200, text="<html>Bad upstream body</html>")
            return httpx.Response(200, json=self.cart(user))
        if path == "/api/agent/memories/mutations":
            memory = self.memories.setdefault(user, {})
            for mutation in body["mutations"]:
                if mutation["operation"] == "DELETE":
                    memory.pop(mutation["key"], None)
                else:
                    memory[mutation["key"]] = mutation["value"]
            return httpx.Response(200, json=[{"key": k, "value": v} for k, v in memory.items()])
        if path == "/api/agent/memories":
            return httpx.Response(
                200,
                json=[{"key": k, "value": v} for k, v in self.memories.get(user, {}).items()][
                    : int(request.url.params.get("limit", 50))
                ],
            )
        return httpx.Response(404, json={"message": "No such fixture endpoint"})
