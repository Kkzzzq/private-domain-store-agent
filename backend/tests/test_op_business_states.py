from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.tables import Shop
from scripts.seed_nanzhi_showcase import seed,govern,BATCH
from test_quality import operator


def test_op_can_filter_actual_shipping_after_sale_and_coupon_lifecycles(client):
    headers,uid=operator(client)
    with SessionLocal() as db:
        shop=db.scalar(select(Shop).where(Shop.share_code=='nanzhi'));sid=shop.id;seed(db,sid);db.commit()
    for key,states,field in [
        ('shipment_status',['shipped','transit','exception','delivered'],'shipment_status'),
        ('after_sale_status',['requested','accepted','rejected','return_shipped','resolved','withdrawn'],'after_sale_status')]:
        for state in states:
            response=client.get(f'/api/v1/op/platform/orders?shop_id={sid}&{key}={state}',headers=headers)
            assert response.status_code==200,response.text
            rows=response.json()['items'];assert rows and all(r[field]==state for r in rows)
    for state in ['active','scheduled','expired','disabled','exhausted']:
        response=client.get(f'/api/v1/op/platform/coupons?shop_id={sid}&status={state}',headers=headers)
        assert response.status_code==200,response.text
        rows=response.json()['items'];assert rows and all(r['issuance_state']==state for r in rows)
    assert client.get('/api/v1/op/platform/coupons?status=unknown',headers=headers).status_code==422
    assert client.get('/api/v1/op/platform/orders?shipment_status=unknown',headers=headers).status_code==422
    assert client.get('/api/v1/op/platform/orders',headers=headers).json()['needs_filter']


def test_showcase_governance_generates_authentic_logs_and_is_repeatable(client,monkeypatch):
    import httpx
    headers,uid=operator(client)
    with SessionLocal() as db:
        shop=db.scalar(select(Shop).where(Shop.share_code=='nanzhi'));info=seed(db,shop.id);db.commit()
    def factory(**kwargs):
        client.headers.update(kwargs['headers']);return client
    monkeypatch.setattr(httpx,'Client',factory)
    govern(info,uid,'https://shop.kkzzzq.cyou');govern(info,uid,'https://shop.kkzzzq.cyou')
    from app.models.governance import WorkspaceAction,AccountRestriction,ShopRestriction
    from app.models.tables import Product
    with SessionLocal() as db:
        assert db.get(AccountRestriction,info['user_ids'][8]).disabled
        assert db.get(Product,info['product_ids'][10]).status=='banned'
        assert set(db.scalars(select(WorkspaceAction.status).where(WorkspaceAction.reason=='【演示】全页状态补齐 '+BATCH)))=={'failed','succeeded'}
        assert db.scalar(select(Shop).where(Shop.share_code=='nanzhi')).status=='open'
