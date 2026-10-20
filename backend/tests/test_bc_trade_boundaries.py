"""B/C trade boundaries discovered during integration acceptance."""
from types import SimpleNamespace
from test_bc_link import login, find


def test_purchase_limit_accumulates_all_skus_before_reserving_stock(client):
    merchant, buyer = login(client, 'merchant'), login(client, 'alice')
    product = client.post('/api/v1/b/products', headers=merchant, json={
        'name': '限购多规格验收', 'limit_per_user': 2,
        'skus': [{'spec': name, 'price_yuan': 10, 'stock': 10} for name in ['米白', '雾蓝']]
    }).json()
    assert client.post(f"/api/v1/b/products/{product['id']}/status", headers=merchant, json={'action':'on'}).status_code == 200
    items = [{'sku_id': sku['id'], 'quantity': 2} for sku in product['skus']]
    blocked = client.post('/api/v1/c/shops/nanzhi/orders', headers=buyer, json={'items':items, 'address':'验收测试地址'})
    assert blocked.status_code == 400, blocked.text
    assert '限购' in blocked.json()['detail']
    current = client.get(f"/api/v1/c/shops/nanzhi/products/{product['id']}").json()
    assert [sku['stock'] for sku in current['skus']] == [10, 10]


def test_order_numbers_are_unique_before_any_commit(client):
    from app.services.orders import _next_order_no
    from app.db.session import SessionLocal
    with SessionLocal() as db:
        numbers = [_next_order_no(db) for _ in range(1000)]
    assert len(set(numbers)) == len(numbers)
    assert all(len(number) <= 32 for number in numbers)


def test_stock_releases_do_not_overwrite_another_session(client):
    from app.db.session import SessionLocal
    from app.models.tables import Sku
    from app.services.orders import _restore_stock
    sku_id = client.get('/api/v1/c/shops/nanzhi/products').json()[0]['skus'][0]['id']
    with SessionLocal() as first, SessionLocal() as second:
        stale_first, stale_second = first.get(Sku, sku_id), second.get(Sku, sku_id)
        before = stale_first.stock
        _restore_stock(first, SimpleNamespace(items=[SimpleNamespace(sku_id=sku_id, quantity=1)]))
        first.commit()
        _restore_stock(second, SimpleNamespace(items=[SimpleNamespace(sku_id=sku_id, quantity=2)]))
        second.commit()
    with SessionLocal() as db:
        assert db.get(Sku, sku_id).stock == before + 3


def test_payments_do_not_overwrite_sales_from_another_session(client):
    from app.db.session import SessionLocal
    from app.models.tables import Product, User
    from app.services.orders import pay_order
    from sqlalchemy import select
    buyer = login(client, 'alice')
    product = find(client.get('/api/v1/c/shops/nanzhi/products').json(), '陶瓷马克杯')
    orders = [client.post('/api/v1/c/shops/nanzhi/orders', headers=buyer, json={
        'sku_id': product['skus'][0]['id'], 'quantity': 1, 'address':'验收测试地址'}).json() for _ in range(2)]
    with SessionLocal() as first, SessionLocal() as second:
        cached_first, cached_second = first.get(Product, product['id']), second.get(Product, product['id'])
        before = cached_first.sales_count
        user1 = first.scalar(select(User).where(User.username == 'alice'))
        user2 = second.scalar(select(User).where(User.username == 'alice'))
        pay_order(first, user1, orders[0]['order_no'])
        pay_order(second, user2, orders[1]['order_no'])
    with SessionLocal() as db:
        assert db.get(Product, product['id']).sales_count == before + 2
