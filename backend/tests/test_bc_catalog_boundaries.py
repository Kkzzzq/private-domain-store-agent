from merchant_fixture import authorize_merchant
from test_bc_link import login, find, sku_of


def test_collection_price_sort_ignores_hidden_skus(client):
    headers = login(client, 'merchant')
    pillow = find(client.get('/api/v1/b/products', headers=headers).json(), '亚麻抱枕套')
    sku = sku_of(pillow, '雾蓝')
    assert client.patch(f"/api/v1/b/skus/{sku['id']}", headers=headers, json={'price_yuan':1}).status_code == 200
    assert client.post(f"/api/v1/b/skus/{sku['id']}/status", headers=headers, json={'action':'off'}).status_code == 200
    for sort in ['price_asc', 'price_desc']:
        cards = client.get(f'/api/v1/c/shops/nanzhi/products?sort={sort}').json()
        collection = client.get(f'/api/v1/c/shops/nanzhi/collections/all?sort={sort}').json()
        assert [p['id'] for p in cards] == [p['id'] for p in collection['products']]


def test_reviews_cannot_be_read_through_another_shop(client):
    product = find(client.get('/api/v1/c/shops/nanzhi/products').json(), '手作餐盘')
    registered = client.post('/api/v1/auth/register', json={
        'username':'review_other_shop', 'password':'other123', 'role':'merchant'}).json()
    authorize_merchant(client, registered)
    headers = {'Authorization':'Bearer ' + registered['access_token']}
    code = client.get('/api/v1/b/shop', headers=headers).json()['share_code']
    response = client.get(f"/api/v1/c/shops/{code}/products/{product['id']}/reviews")
    assert response.status_code == 404


def test_review_refreshes_cached_catalog_rating_immediately(client):
    buyer, merchant = login(client, 'alice'), login(client, 'merchant')
    product = find(client.get('/api/v1/c/shops/nanzhi/products').json(), '陶瓷马克杯')
    order = client.post('/api/v1/c/shops/nanzhi/orders', headers=buyer, json={
        'sku_id':product['skus'][0]['id'], 'quantity':1, 'address':'评价验收地址'}).json()
    number = order['order_no']
    assert client.post(f'/api/v1/c/orders/{number}/pay', headers=buyer).status_code == 200
    assert client.post(f'/api/v1/b/orders/{number}/ship', headers=merchant).status_code == 200
    assert client.post(f'/api/v1/c/orders/{number}/confirm', headers=buyer).status_code == 200
    # Warm the catalog cache after the last order mutation.
    client.get('/api/v1/c/shops/nanzhi/products')
    pending = client.get('/api/v1/c/reviews/pending', headers=buyer).json()
    item = next(item for item in pending if item['order_no'] == number)
    response = client.post('/api/v1/c/reviews', headers=buyer, json={
        'order_item_id':item['order_item_id'], 'rating':4, 'content':'验收真实订单评价'})
    assert response.status_code == 200, response.text
    c = find(client.get('/api/v1/c/shops/nanzhi/products').json(), product['name'])
    b = find(client.get('/api/v1/b/products', headers=merchant).json(), product['name'])
    assert c['review_count'] == b['review_count'] == 1
    assert c['rating_avg'] == b['rating_avg'] == 4
