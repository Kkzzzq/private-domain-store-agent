from app.services.session import SessionService, compact_messages


def login(client, username="alice"):
    token = client.post("/api/v1/auth/login", json={"username": username, "password": username + "123"}).json()["access_token"]
    return {"Authorization": "Bearer " + token}


def test_recent_requires_customer_and_isolates_account_and_shop(client):
    path = "/api/v1/c/shops/nanzhi/chat/recent"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=login(client, "merchant")).status_code == 403
    from app.models.tables import User, Shop
    from app.db.session import SessionLocal
    with SessionLocal() as db:
        alice = db.query(User).filter_by(username="alice").one()
        shop = db.query(Shop).filter_by(share_code="nanzhi").one()
        service = SessionService()
        service.record_turn(alice.id, shop.id, "latest", "私有问题", "私有回答", [])
        assert service.recent(alice.id + 999, shop.id)["messages"] == []
        assert service.recent(alice.id, shop.id + 999)["messages"] == []
    result = client.get(path, headers=login(client)).json()
    assert result["session_id"] == "latest"
    assert len(result["messages"]) == 2
    assert client.get("/api/v1/c/shops/missing/chat/recent", headers=login(client)).status_code == 404


def test_recent_keeps_five_complete_turns_independent_of_compaction(client):
    service = SessionService()
    for i in range(7):
        service.record_turn(100, 200, f"s{i}", f"q{i}", "answer" * 100, [{"id": i}])
    recent = service.recent(100, 200)
    assert recent["session_id"] == "s6"
    assert len(recent["messages"]) == 10
    assert recent["messages"][0]["content"] == "q2"
    assert recent["messages"][-1]["products"] == [{"id": 6}]
    compact_messages({"messages": recent["messages"]}, 100)
    assert len(service.recent(100, 200)["messages"]) == 10


def test_successful_chat_is_restored_with_session_for_followup(client):
    headers = login(client)
    base = "/api/v1/c/shops/nanzhi"
    assert client.get(base + "/chat/recent", headers=headers).json()["messages"] == []
    first = client.post(base + "/chat", headers=headers, json={"message": "抱枕有货吗"}).json()
    recent = client.get(base + "/chat/recent", headers=headers).json()
    assert recent["session_id"] == first["session_id"]
    assert recent["messages"][-1]["content"] == first["answer"]
    second = client.post(base + "/chat", headers=headers, json={"message": "这个多少钱", "session_id": recent["session_id"]}).json()
    assert second["session_id"] == first["session_id"]
    assert len(client.get(base + "/chat/recent", headers=headers).json()["messages"]) == 4
