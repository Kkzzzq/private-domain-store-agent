from datetime import timedelta
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.tables import User, Shop, Order, Product, utcnow
from app.models.support import Shipment
from app.models.account import can_manage_store
from test_operations import operator


def test_scoped_orders_and_history(client):
    h=operator(client)
    for url in ['/api/v1/op/platform/orders','/api/v1/op/records/orders']:
        d=client.get(url,headers=h).json()
        assert d['needs_filter'] and d['items']==[]
    with SessionLocal() as db:
        row=db.scalar(select(Order)); sid,num=row.shop_id,row.order_no
        row.created_at=utcnow()-timedelta(days=40);db.commit()
    assert num not in [r['order_no'] for r in client.get(f'/api/v1/op/platform/orders?shop_id={sid}',headers=h).json()['items']]
    assert client.get(f'/api/v1/op/platform/orders?q={num}',headers=h).json()['items'][0]['order_no']==num
    assert client.get('/api/v1/op/platform/orders?days=0',headers=h).status_code==422
    assert client.get('/api/v1/op/platform/orders?size=101',headers=h).status_code==422
    assert client.get('/api/v1/op/platform/orders?shop_id=999999',headers=h).json()['items']==[]
    assert client.get(f'/api/v1/op/platform/orders?shop_id=999999&q={num}',headers=h).json()['items']==[]


def test_purchase_shipping_and_permissions(client):
    h=operator(client)
    with SessionLocal() as db:
        row=db.scalar(select(Order)); oid=row.id
        row.receiver='测试买家';row.phone='13800000000';row.address='测试地址'
        db.add(Shipment(order_id=oid,carrier='测试承运',tracking_number='SHIP-TEST-001',events=[{'at':'2026-10-20T01:00:00Z','text':'测试揽收'}]));db.commit()
    rows=client.get('/api/v1/op/platform/orders?q=SHIP-TEST-001&shipped_only=true',headers=h).json()['items']
    assert rows[0]['id']==oid and 'phone' not in rows[0]
    detail=client.get(f'/api/v1/op/platform/orders/{oid}',headers=h).json()
    assert detail['phone']=='13800000000' and detail['items'] and detail['shipment']['events'][0]['text']=='测试揽收'
    assert 'password_hash' not in str(detail)
    assert client.get(f'/api/v1/op/platform/orders/{oid}').status_code==401
    plain=client.post('/api/v1/auth/register',json={'username':'platform_plain','password':'test-password'}).json()
    denied={'Authorization':'Bearer '+plain['access_token']}
    assert client.get(f'/api/v1/op/platform/orders/{oid}',headers=denied).status_code==403
    assert client.patch(f'/api/v1/op/platform/accounts/{plain["user"]["id"]}',headers=denied,json={'merchant_enabled':True,'reason':'不能自授权'}).status_code==403
    assert client.get('/api/v1/op/platform/orders/999999',headers=h).status_code==404


def test_account_access_and_audit(client):
    h=operator(client)
    d=client.post('/api/v1/auth/register',json={'username':'new_store_user','password':'test-password'}).json();uid=d['user']['id']
    for enabled in [True,False]:
        r=client.patch(f'/api/v1/op/platform/accounts/{uid}',headers=h,json={'nickname':'更新昵称','merchant_enabled':enabled,'reason':'核验授权'})
        assert r.status_code==200 and r.json()['merchant_enabled']==enabled
        with SessionLocal() as db:
            assert can_manage_store(db,db.get(User,uid))==enabled
            assert db.scalar(select(Shop).where(Shop.merchant_id==uid)) is None
    d=client.get('/api/v1/op/platform/accounts?q=new_store_user',headers=h).json()
    assert d['total']==1 and 'password_hash' not in str(d)
    assert client.get('/api/v1/op/platform/audits',headers=h).json()['total']==2


def test_shop_and_product_management(client):
    h=operator(client)
    rows=client.get('/api/v1/op/platform/shops',headers=h).json()['items'];sid=rows[0]['id']
    assert 'owner' in rows[0]
    r=client.patch(f'/api/v1/op/platform/shops/{sid}',headers=h,json={'name':'平台修改店名','notice':'公告更新','status':'closed','reason':'测试修改'})
    assert r.status_code==200
    with SessionLocal() as db:
        assert db.get(Shop,sid).name=='平台修改店名' and db.get(Shop,sid).status=='closed'
        pid=db.scalar(select(Product.id).where(Product.shop_id==sid))
    d=client.get(f'/api/v1/op/platform/products/{pid}',headers=h).json()
    assert d['shop_name']=='平台修改店名' and d['skus']
    assert client.get('/api/v1/op/platform/shops/999999',headers=h).status_code==404
    assert client.get('/api/v1/op/platform/products/999999',headers=h).status_code==404


def test_buyer_lookup_is_exact(client):
    h=operator(client)
    with SessionLocal() as db:
        order=db.scalar(select(Order))
        username=order.buyer.username
        other=User(username=username+'_other',password_hash=order.buyer.password_hash,role='customer')
        db.add(other);db.flush()
        db.add(Order(order_no='OP-OTHER-BUYER',shop_id=order.shop_id,user_id=other.id,total_cents=100,address='隔离测试'))
        db.commit()
    items=client.get('/api/v1/op/platform/orders',params={'q':username},headers=h).json()['items']
    assert items and all(r['buyer']==username for r in items)
