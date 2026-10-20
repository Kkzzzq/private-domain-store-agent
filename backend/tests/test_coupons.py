from merchant_fixture import authorize_merchant
from datetime import timedelta
import pytest
from sqlalchemy import select
from app.models.tables import Coupon, UserCoupon, Order, utcnow
from app.db.session import SessionLocal


def login(client, name="alice"):
    return {"Authorization": "Bearer " + client.post("/api/v1/auth/login", json={"username": name, "password": name + "123"}).json()["access_token"]}


def setup_coupon(client, **values):
    body = dict(name="测试满减券", threshold_cents=9900, amount_cents=1000, total_count=2,
        starts_at=(utcnow()-timedelta(days=1)).isoformat()+"Z", ends_at=(utcnow()+timedelta(days=1)).isoformat()+"Z")
    body.update(values)
    response = client.post("/api/v1/b/coupons", headers=login(client,"merchant"), json=body)
    assert response.status_code == 200, response.text
    return response.json()


def purchase(client, user_coupon_id=None, quantity=2):
    products = client.get("/api/v1/c/shops/nanzhi/products").json()
    sku = products[0]["skus"][0]
    body = dict(sku_id=sku["id"], quantity=quantity, address="测试地址一号", user_coupon_id=user_coupon_id)
    return client.post("/api/v1/c/shops/nanzhi/orders", headers=login(client), json=body)


def claim(client, coupon):
    response = client.post(f"/api/v1/c/shops/nanzhi/coupons/{coupon['id']}/claim", headers=login(client))
    assert response.status_code == 200, response.text
    return response.json()["user_coupon_id"]


def test_coupon_full_order_cancel_and_pay(client):
    coupon = setup_coupon(client, threshold_cents=0)
    owned = claim(client, coupon)
    order = purchase(client, owned).json()
    assert order["discount_yuan"] == 10
    assert order["total_yuan"] == order["goods_yuan"] + order["freight_yuan"] - 10
    assert purchase(client, owned).status_code == 400
    cancelled = client.post(f"/api/v1/c/orders/{order['order_no']}/cancel", headers=login(client))
    assert cancelled.status_code == 200
    second = purchase(client, owned).json()
    paid = client.post(f"/api/v1/c/orders/{second['order_no']}/pay", headers=login(client))
    assert paid.status_code == 200
    assert purchase(client, owned).status_code == 400
    merchant = client.get("/api/v1/b/coupons", headers=login(client,"merchant")).json()[0]
    assert merchant["used_count"] == 1
    b_orders = client.get("/api/v1/b/orders", headers=login(client,"merchant")).json()
    assert next(o for o in b_orders if o['order_no']==second['order_no'])["discount_yuan"] == 10


def test_duplicate_claim_does_not_consume_quota(client):
    coupon=setup_coupon(client)
    claim(client,coupon)
    response=client.post(f"/api/v1/c/shops/nanzhi/coupons/{coupon['id']}/claim",headers=login(client))
    assert response.status_code == 409
    assert client.get("/api/v1/b/coupons",headers=login(client,"merchant")).json()[0]["claimed_count"] == 1


def test_issuance_exhaustion_does_not_invalidate_claimed_coupon(client):
    coupon = setup_coupon(client, threshold_cents=0, total_count=1)
    owned = claim(client, coupon)
    merchant = login(client, "merchant")
    row = client.get("/api/v1/b/coupons", headers=merchant).json()[0]
    assert row["issuance_state"] == "exhausted"
    assert row["remaining_count"] == 0 and row["active"]
    assert row["unused_count"] == 1 and row["reserved_count"] == 0
    order = purchase(client, owned)
    assert order.status_code == 200, order.text
    row = client.get("/api/v1/b/coupons", headers=merchant).json()[0]
    assert row["reserved_count"] == 1 and row["unused_count"] == 0
    client.post(f"/api/v1/c/orders/{order.json()['order_no']}/cancel", headers=login(client))
    row = client.get("/api/v1/b/coupons", headers=merchant).json()[0]
    assert row["reserved_count"] == 0 and row["unused_count"] == 1
    assert row["claimed_count"] == 1 and row["issuance_state"] == "exhausted"


def test_coupon_issuance_state_distinguishes_time_and_disabling(client):
    from app.services.coupons import issuance_state
    from types import SimpleNamespace
    now = utcnow()
    row = SimpleNamespace(enabled=True, starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=1),
                          claimed_count=0, total_count=2)
    assert issuance_state(row) == "active"
    row.starts_at = now + timedelta(hours=1)
    assert issuance_state(row) == "scheduled"
    row.ends_at = now - timedelta(hours=1)
    row.starts_at = now - timedelta(days=2)
    assert issuance_state(row) == "expired"
    row.enabled = False
    assert issuance_state(row) == "disabled"


def test_scope_authentication_and_quota(client):
    coupon=setup_coupon(client,total_count=1)
    path=f"/api/v1/c/shops/nanzhi/coupons/{coupon['id']}/claim"
    assert client.post(path).status_code == 401
    assert client.post(path,headers=login(client,"merchant")).status_code == 403
    assert client.get("/api/v1/b/coupons",headers=login(client)).status_code == 403
    other = client.post('/api/v1/auth/register',json={'username':'coupon_other','password':'other123','role':'merchant'}).json()
    authorize_merchant(client, other)
    assert client.patch(f"/api/v1/b/coupons/{coupon['id']}",headers={'Authorization':'Bearer '+other['access_token']},json={"enabled":False}).status_code == 404
    assert client.post(path.replace("nanzhi","muguang"),headers=login(client)).status_code in (400,404)
    owned=claim(client,coupon)
    assert client.post(path,headers=login(client,"bob")).status_code == 400
    with SessionLocal() as db:
        row=db.get(UserCoupon,owned)
        row.user_id=99999
        db.commit()
    assert purchase(client,owned).status_code == 400


def test_invalid_threshold_disabled_and_expired_do_not_reserve_stock(client):
    coupon=setup_coupon(client,threshold_cents=10000000)
    owned=claim(client,coupon)
    assert purchase(client,owned).status_code == 400
    client.patch(f"/api/v1/b/coupons/{coupon['id']}",headers=login(client,"merchant"),json={"enabled":False})
    assert purchase(client,owned).status_code == 400
    with SessionLocal() as db:
        c=db.get(Coupon,coupon['id']);c.enabled=True;c.ends_at=utcnow()-timedelta(seconds=1);db.commit()
    assert purchase(client,owned).status_code == 400
    with SessionLocal() as db:
        assert db.scalar(select(Order).where(Order.user_id == db.get(UserCoupon, owned).user_id, Order.status == 'pending')) is None


def test_quote_caps_discount_and_shipping_threshold(client):
    coupon=setup_coupon(client,threshold_cents=0,amount_cents=1000000)
    owned=claim(client,coupon)
    products=client.get("/api/v1/c/shops/nanzhi/products").json()
    sku=products[0]["skus"][0]
    body={"items":[{"sku_id":sku['id'],"quantity":2}],"user_coupon_id":owned}
    quote=client.post("/api/v1/c/shops/nanzhi/coupon-quote",headers=login(client),json=body).json()
    assert quote["discount_yuan"] == quote["goods_yuan"]
    assert quote["total_yuan"] == quote["freight_yuan"]
    order=purchase(client,owned).json()
    assert order["total_yuan"] == quote["total_yuan"]


def test_expired_order_returns_coupon(client):
    owned=claim(client,setup_coupon(client,threshold_cents=0))
    order=purchase(client,owned).json()
    from app.services.orders import auto_cancel_expired
    with SessionLocal() as db:
        record=db.scalar(select(Order).where(Order.order_no==order['order_no']))
        record.expires_at=utcnow()-timedelta(minutes=1);db.commit()
        assert auto_cancel_expired(db)==1
        assert auto_cancel_expired(db)==0
        assert db.get(UserCoupon,owned).status == "available"
    assert purchase(client,owned).status_code == 200


def test_coupon_bad_input(client):
    headers=login(client,"merchant")
    assert client.post('/api/v1/b/coupons',headers=headers,json={}).status_code==422
    with pytest.raises(AssertionError):
        setup_coupon(client,amount_cents=0)


def test_cart_checkout_uses_same_discount(client):
    owned=claim(client,setup_coupon(client,threshold_cents=0))
    sku=client.get('/api/v1/c/shops/nanzhi/products').json()[0]['skus'][0]
    headers=login(client)
    cart=client.post('/api/v1/c/shops/nanzhi/cart',headers=headers,json={'sku_id':sku['id'],'quantity':2}).json()
    result=client.post('/api/v1/c/shops/nanzhi/cart/checkout',headers=headers,json={
        'cart_item_ids':[cart['items'][0]['id']], 'address':'测试收货地址', 'user_coupon_id':owned})
    assert result.status_code==200,result.text
    assert result.json()['discount_yuan']==10
    assert client.get('/api/v1/c/shops/nanzhi/cart',headers=headers).json()['items']==[]


def test_simultaneous_claims_and_redemption(client, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.base import Base
    from app.models.tables import User
    from app.seed import seed_if_empty
    from app.services.coupons import claim as claim_service, create, CouponIn
    from app.services.orders import create_order
    from app.schemas.dto import OrderCreate
    from fastapi import HTTPException
    engine=create_engine(f'sqlite:///{tmp_path / "concurrent.db"}',connect_args={'timeout':15})
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine)
    with sessions() as db:
        seed_if_empty(db)
        users={u.username:u.id for u in db.scalars(select(User)).all()}
        coupon=create(db,db.get(User,users['merchant']),CouponIn(name='限量券',threshold_cents=0,amount_cents=1000,total_count=1,
            starts_at=utcnow()-timedelta(days=1),ends_at=utcnow()+timedelta(days=1)))
    def take(username):
        with sessions() as db:
            try: return claim_service(db,db.get(User,users[username]),'nanzhi',coupon['id'])
            except HTTPException: return None
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(take,['alice','bob']))
    assert sum(r is not None for r in results)==1
    winner='alice' if results[0] else 'bob'
    owned=next(r['user_coupon_id'] for r in results if r)
    def redeem(_):
        with sessions() as db:
            try: return create_order(db,db.get(User,users[winner]),'nanzhi',OrderCreate(sku_id=1,quantity=1,address='并发测试地址',user_coupon_id=owned))
            except HTTPException:
                db.rollback(); return None
    with ThreadPoolExecutor(2) as pool:
        orders=list(pool.map(redeem,range(2)))
    assert sum(o is not None for o in orders)==1
    with sessions() as db:
        assert db.get(Coupon,coupon['id']).claimed_count==1
        assert db.get(UserCoupon,owned).status=='reserved'
    engine.dispose()
