import json

import pytest
from sqlalchemy import select

from app.agent.context import Actor, reset_actor, set_actor
from app.agent.guard import execute_tool
from app.db.session import SessionLocal
from app.models.tables import CartItem, Order, OrderItem, Product, Shop, Sku, User
from app.services.store_context import collect_records, query_store_data


@pytest.fixture()
def scoped_context(client):
    with SessionLocal() as db:
        buyer = db.scalar(select(User).where(User.username == "alice"))
        merchant = db.scalar(select(User).where(User.username == "merchant"))
        other = User(username="context-other", password_hash="not-for-login", role="customer")
        foreign = User(username="context-foreign", password_hash="not-for-login", role="merchant")
        db.add_all([other, foreign])
        db.flush()
        shop = Shop(merchant_id=foreign.id, name="其它店铺", share_code="context-other-shop")
        db.add(shop)
        db.flush()
        product = db.scalar(select(Product).where(Product.shop_id == 1))
        sku = product.skus[0]
        other_product = Product(shop_id=shop.id, name="外店机密商品", status="on", skus=[Sku(spec="外店规格", price_cents=100, stock=9)])
        db.add(other_product)
        db.flush()
        db.add_all([CartItem(user_id=buyer.id, shop_id=1, sku_id=sku.id, quantity=2),
                    CartItem(user_id=other.id, shop_id=1, sku_id=sku.id, quantity=7),
                    CartItem(user_id=buyer.id, shop_id=shop.id, sku_id=other_product.skus[0].id, quantity=9)])
        own = Order(shop_id=1, user_id=buyer.id, order_no="CTX-OWN", total_cents=100, address="绝不能向量化的地址", phone="13912345678",
                    items=[OrderItem(product_id=product.id, sku_id=sku.id, product_name="本人专属杯子", sku_spec="蓝色", price_cents=100, quantity=1)])
        other_order = Order(shop_id=1, user_id=other.id, order_no="CTX-OTHER", total_cents=200, address="另一位地址",
                            items=[OrderItem(product_id=product.id, sku_id=sku.id, product_name="其它买家的杯子", sku_spec="红色", price_cents=200, quantity=1)])
        foreign_order = Order(shop_id=shop.id, user_id=buyer.id, order_no="CTX-FOREIGN", total_cents=100, address="外店地址")
        db.add_all([own, other_order, foreign_order])
        db.commit()
        yield db, buyer, merchant, other, own


def test_cart_is_private_to_current_account_and_shop(scoped_context):
    db, buyer, merchant, other, own = scoped_context
    actor = Actor(buyer.id, "customer", buyer.username, 1)
    rows = collect_records(db, actor, "cart")
    assert len(rows) == 1 and rows[0]["data"]["数量"] == 2
    assert collect_records(db, Actor(merchant.id, "merchant", merchant.username, 1), "cart") == []
    token = set_actor(db, actor)
    try:
        assert "不允许指定其他身份" in execute_tool("query_store_data", {"topic": "cart", "user_id": other.id})
        result = json.loads(query_store_data("cart"))
        assert len(result["匹配记录"]) == 1
    finally:
        reset_actor(token)


def test_orders_filter_before_embedding_and_exclude_pii(scoped_context):
    db, buyer, merchant, other, own = scoped_context
    rows = collect_records(db, Actor(buyer.id, "customer", buyer.username, 1), "orders")
    own_rows = [row for row in rows if row["id"] == str(own.id)]
    assert own_rows
    text = json.dumps(rows, ensure_ascii=False)
    assert "CTX-OTHER" not in text and "CTX-FOREIGN" not in text
    assert "13912345678" not in text and "绝不能向量化的地址" not in text
    assert "CTX-OWN" not in own_rows[0]["text"]
    seller_rows = collect_records(db, Actor(merchant.id, "merchant", merchant.username, 1), "orders")
    text = json.dumps(seller_rows, ensure_ascii=False)
    assert "CTX-OTHER" in text and "CTX-FOREIGN" not in text
    from app.services.store_context import ranked_ids
    assert ranked_ids(rows, "请查PS209999999999", db, Actor(buyer.id, "customer", buyer.username, 1), "orders", 5) == []


def test_customer_cannot_use_merchant_manual(scoped_context):
    db, buyer, merchant, other, own = scoped_context
    token = set_actor(db, Actor(buyer.id, "customer", buyer.username, 1))
    try:
        assert "无权" in execute_tool("merchant_help", {"question": "如何发优惠券"})
        assert "后台操作" in query_store_data("merchant_help", "优惠券")
        assert "参数缺失或无效" in execute_tool("query_store_data", {"topic": "merchant_help"})
    finally:
        reset_actor(token)
    token = set_actor(db, Actor(merchant.id, "merchant", merchant.username, 1))
    try:
        help_text = execute_tool("merchant_help", {"question": "优惠券"})
        assert "优惠券管理" in help_text and "每单限用一张" in help_text
        assert ".md" not in help_text and "来源" not in help_text
    finally:
        reset_actor(token)


def test_hidden_decoration_and_style_are_merchant_only(scoped_context):
    from app.models.tables import Testimonial
    db, buyer, merchant, other, own = scoped_context
    db.add(Testimonial(shop_id=1, nickname="隐藏客户", content="未发布反馈", enabled=False))
    db.commit()
    customer = json.dumps(collect_records(db, Actor(buyer.id, "customer", buyer.username, 1), "settings"), ensure_ascii=False)
    seller = json.dumps(collect_records(db, Actor(merchant.id, "merchant", merchant.username, 1), "settings"), ensure_ascii=False)
    assert "未发布反馈" not in customer and "未发布反馈" in seller
    assert "background_color" not in customer and "background_color" in seller


def test_same_identity_sessions_and_recent_history_are_role_isolated(client):
    from app.services.session import SessionService
    service = SessionService()
    state = {"messages": [{"role": "assistant", "content": "商家经营信息"}]}
    service.save(42, 1, "same-id", state, "merchant")
    service.record_turn(42, 1, "same-id", "经营", "商家经营信息", [], "merchant")
    assert service.load(42, 1, "same-id", "customer")["messages"] == []
    assert service.recent(42, 1, "customer")["messages"] == []
    assert service.load(42, 1, "same-id", "merchant")["messages"] == state["messages"]


def test_reviews_are_linked_to_sku_and_not_identified_as_testimonials(scoped_context):
    from app.models.tables import Review
    db, buyer, merchant, other, own = scoped_context
    item = own.items[0]
    db.add(Review(user_id=buyer.id, product_id=item.product_id, order_item_id=item.id, rating=4, content="蓝色很喜欢，电话13912345678"))
    db.commit()
    review_id = db.scalar(select(Review.id).where(Review.order_item_id == item.id))
    rows = collect_records(db, Actor(buyer.id, "customer", buyer.username, 1), "reviews")
    review = next(row["data"] for row in rows if row["id"] == str(review_id))
    assert review["sku_id"] == item.sku_id
    assert "13912345678" not in json.dumps(review)
    assert "user_id" not in review and "订单号" not in review
    from app.models.governance import ReviewRestriction
    db.add(ReviewRestriction(review_id=review_id, hidden=True))
    db.commit()
    visible = collect_records(db, Actor(buyer.id, "customer", buyer.username, 1), "reviews")
    assert not any(row["id"] == str(review_id) for row in visible)


def test_customer_and_merchant_product_views_differ(scoped_context):
    from app.services.agent_queries import store_catalog
    db, buyer, merchant, other, own = scoped_context
    db.add(Product(shop_id=1, name="运营专属草稿", category="家居", status="draft", skus=[Sku(spec="未上架", price_cents=200, stock=5)]))
    db.commit()
    for role, user in (("customer", buyer), ("merchant", merchant)):
        token = set_actor(db, Actor(user.id, role, user.username, 1))
        try:
            text = store_catalog(limit=20)
            assert ("运营专属草稿" in text) is (role == "merchant")
        finally:
            reset_actor(token)
