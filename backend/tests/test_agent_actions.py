import json
from datetime import datetime, timedelta
from unittest.mock import Mock
import pytest
from sqlalchemy import select, func
from app.agent.context import Actor, set_actor, reset_actor
from app.agent.guard import execute_tool
from app.agent.product_actions import ProductProposal, prepare_product_draft
from app.db.session import SessionLocal
from app.models.tables import User, Product
from test_bc_link import login


def prepare(client, **kwargs):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "merchant"))
        token = set_actor(db, Actor(user.id, user.role, user.username, 1, session_id="test-action-session"))
        try:
            result = execute_tool("prepare_product_draft", kwargs or {"name":"新款杯子", "category":"杯子",
                "skus":[{"spec":"红色", "price_yuan":37, "stock":12}]})
            return json.loads(result)["proposal_id"]
        finally:
            reset_actor(token)


def product_count():
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(Product))


def test_proposal_preview_confirm_idempotent_and_not_visible_to_buyer(client):
    headers = login(client, "merchant")
    before = product_count()
    pid = prepare(client)
    assert product_count() == before
    url = f"/api/v1/b/agent/product-proposals/{pid}"
    preview = client.get(url, headers=headers).json()
    assert preview["payload"]["skus"][0]["stock"] == 12
    saved = client.post(url + "/confirm", headers=headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()["status"] == "completed"
    product_id = saved.json()["product_id"]
    assert client.post(url + "/confirm", headers=headers).json()["product_id"] == product_id
    assert product_count() == before + 1
    products = client.get("/api/v1/b/products", headers=headers).json()
    row = next(p for p in products if p["id"] == product_id)
    assert row["status"] == "draft" and row["skus"][0]["price_yuan"] == 37
    assert client.get(f"/api/v1/c/shops/nanzhi/products/{product_id}").status_code == 404
    assert client.post(url + "/cancel", headers=headers).status_code == 409


def test_cancel_expiration_and_auth(client):
    headers = login(client, "merchant")
    pid = prepare(client)
    url = f"/api/v1/b/agent/product-proposals/{pid}"
    assert client.post(url + "/confirm").status_code == 401
    assert client.get(url, headers=login(client,"alice")).status_code == 403
    for action in ("cancel", "cancel"):
        assert client.post(url + "/" + action, headers=headers).status_code == 200
    assert client.post(url + "/confirm", headers=headers).status_code == 409
    expired = prepare(client)
    with SessionLocal() as db:
        db.get(ProductProposal, expired).expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.post(f"/api/v1/b/agent/product-proposals/{expired}/confirm", headers=headers).status_code == 409


def test_foreign_owner_cannot_read_confirm_cancel(client):
    headers = login(client,"merchant")
    pid = prepare(client)
    with SessionLocal() as db:
        proposal = db.get(ProductProposal,pid)
        proposal.user_id = db.scalar(select(User.id).where(User.username == "bob"))
        db.commit()
    url = f"/api/v1/b/agent/product-proposals/{pid}"
    assert client.get(url,headers=headers).status_code == 404
    assert client.post(url+"/confirm",headers=headers).status_code == 404
    assert client.post(url+"/cancel",headers=headers).status_code == 404


def test_clone_is_new_draft_and_source_unchanged(client):
    headers = login(client,"merchant")
    source = client.get("/api/v1/b/products",headers=headers).json()[0]
    pid = prepare(client,source_product_id=source["id"],name="复制款")
    saved = client.post(f"/api/v1/b/agent/product-proposals/{pid}/confirm",headers=headers).json()
    assert saved["product_id"] != source["id"]
    rows = client.get("/api/v1/b/products",headers=headers).json()
    original = next(p for p in rows if p["id"] == source["id"])
    assert original == source
    clone = next(p for p in rows if p["id"] == saved["product_id"])
    assert clone["skus"][0]["price_yuan"] == source["skus"][0]["price_yuan"]


def test_tool_rejects_invalid_identity_price_and_buyer(client):
    with SessionLocal() as db:
        for username, args, expected in [("alice", {}, "无权"), ("merchant", {"shop_id":2}, "身份"),
            ("merchant", {"name":"x", "skus":[{"spec":"s","price_yuan":-1,"stock":2}]}, "参数")]:
            user=db.scalar(select(User).where(User.username==username))
            token=set_actor(db,Actor(user.id,user.role,user.username,1))
            try: assert expected in execute_tool("prepare_product_draft", args)
            finally: reset_actor(token)
        user=db.scalar(select(User).where(User.username=="merchant"))
        token=set_actor(db,Actor(user.id,user.role,user.username,1))
        try:
            assert "先向商家确认" in execute_tool("prepare_product_draft", {"name":"只有名字"})
            assert "没有找到本店可访问的资源" in execute_tool("prepare_product_draft", {"source_product_id":999999})
        finally:reset_actor(token)


def test_confirmation_failure_rolls_back_product_and_claim(client,monkeypatch):
    headers=login(client,"merchant")
    pid=prepare(client)
    before=product_count()
    import app.agent.product_actions as module
    real=module._sku_row
    monkeypatch.setattr(module,"_sku_row",Mock(side_effect=RuntimeError("injected")))
    with pytest.raises(RuntimeError):
        client.post(f"/api/v1/b/agent/product-proposals/{pid}/confirm",headers=headers)
    assert product_count()==before
    with SessionLocal() as db: assert db.get(ProductProposal,pid).status=="pending"
    monkeypatch.setattr(module,"_sku_row",real)
    assert client.post(f"/api/v1/b/agent/product-proposals/{pid}/confirm",headers=headers).status_code==200


def test_model_tool_loop_creates_only_pending_proposal(client):
    from langchain_core.messages import AIMessage
    from app.agent.assistant import assistant
    from app.core.config import settings
    user_model=Mock()
    user_model.bind_tools.return_value=user_model
    user_model.invoke.side_effect=[AIMessage(content="",tool_calls=[{"name":"prepare_product_draft",
        "args":{"name":"测试新商品","skus":[{"spec":"单个","price_yuan":12,"stock":4}]},"id":"p1"}]),
        AIMessage(content="已生成配置提案，请点击预览确认。")]
    before=product_count()
    old=settings.agent_mode
    settings.agent_mode="auto"
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.username=="merchant"))
        token=set_actor(db,Actor(user.id,user.role,user.username,1))
        try:
            response=assistant.chat(user_id=user.id,shop_id=1,session_id=None,message="配置商品",llm=user_model)
            assert response["tools"][0]["tool"]=="prepare_product_draft"
            assert response["mode"]=="llm"
        finally: reset_actor(token);settings.agent_mode=old
    assert product_count()==before


def test_parallel_confirm_creates_one_product(client,tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.base import Base
    from app.models.tables import Shop
    from app.agent.product_actions import confirm_proposal
    engine=create_engine("sqlite:///"+str(tmp_path/"parallel.db"),connect_args={"check_same_thread":False})
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine,autoflush=False)
    with SessionLocal() as db:
        merchant=db.scalar(select(User).where(User.username=="merchant"))
        shop=db.scalar(select(Shop).where(Shop.merchant_id==merchant.id))
        user_values={c.name:getattr(merchant,c.name) for c in User.__table__.columns}
        shop_values={c.name:getattr(shop,c.name) for c in Shop.__table__.columns}
    with engine.begin() as connection:
        connection.execute(User.__table__.insert().values(**user_values))
        connection.execute(Shop.__table__.insert().values(**shop_values))
    with sessions() as db:
        db.add(ProductProposal(id="parallel",user_id=merchant.id,shop_id=shop.id,session_id="parallel",
            payload={"name":"并发款","skus":[{"spec":"默认","price_yuan":10,"stock":3}]},
            expires_at=datetime.utcnow()+timedelta(minutes=10)))
        db.commit()
    barrier=Barrier(2)
    def confirm_once(_):
        with sessions() as db:
            user=db.get(User,merchant.id)
            barrier.wait(timeout=5)
            return confirm_proposal(db,user,"parallel")["product_id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(confirm_once,range(2)))
    assert results[0]==results[1]
    with sessions() as db:assert db.scalar(select(func.count()).select_from(Product))==1
    engine.dispose()
