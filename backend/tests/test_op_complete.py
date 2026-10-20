from datetime import timedelta, timezone
from urllib.parse import quote
from sqlalchemy import select, func
from app.db.session import SessionLocal
from app.models.tables import User, Shop, Order, Review, Product, utcnow
from app.models.governance import WorkspaceAction
from test_operations import operator
from test_bc_link import login


def context(client):
    h=operator(client);h['X-OP-Reason']=quote('隔离全功能验收')
    with SessionLocal() as db: sid=db.scalar(select(Shop.id).where(Shop.share_code=='nanzhi'))
    return h,sid,f'/api/v1/op/shops/{sid}/b'


def test_all_existing_routes_have_op_scope(client):
    from app.api.b_api import router
    from app.main import app
    paths=app.openapi()['paths']
    for r in router.routes:
        for method in r.methods:
            assert method.lower() in paths['/api/v1/op/shops/{shop_id}'+r.path]
    h,sid,url=context(client)
    assert client.get(url+'/shop',headers=h).json()['id']==sid
    assert client.get(url+'/shop').status_code==401
    assert client.get(url+'/shop',headers=login(client,'merchant')).status_code==403
    assert client.get('/api/v1/b/shop',headers=h).status_code==403
    assert client.get('/api/v1/op/shops/999999/b/shop',headers=h).status_code==404


def test_full_product_sku_images_tags_and_scope(client):
    h,sid,url=context(client)
    row=client.post(url+'/products',headers=h,json={'name':'OP完整商品','category':'平台分类','image_url':'/covers/notebook.jpg','limit_per_user':3,'tag_names':['平台标签'],'skus':[{'spec':'大号','price_yuan':88,'market_price_yuan':100,'stock':12,'image_url':'/covers/notebook.jpg','parameters':[{'name':'材质','value':'棉麻'}]}]})
    assert row.status_code==200,row.text
    product=row.json();pid=product['id'];sku=product['skus'][0]['id']
    assert client.patch(url+f'/skus/{sku}',headers=h,json={'price_yuan':89,'stock':10,'market_price_yuan':None,'parameters':[{'name':'材质','value':'纯棉'}]}).status_code==200
    assert client.post(url+f'/products/{pid}/status',headers=h,json={'action':'on'}).status_code==200
    c=client.get(f'/api/v1/c/shops/nanzhi/products/{pid}').json()
    assert c['skus'][0]['price_yuan']==89 and c['skus'][0]['stock']==10 and c['skus'][0]['parameters'][0]['value']=='纯棉'
    assert c['image_url']=='/covers/notebook.jpg' and c['limit_per_user']==3 and c['tags'][0]['name']=='平台标签'
    with SessionLocal() as db:
        other=Shop(merchant_id=db.scalar(select(User.id).where(User.username=='operations')),name='另一店',share_code='other-op')
        db.add(other);db.commit();foreign=other.id
    assert client.patch(f'/api/v1/op/shops/{foreign}/b/products/{pid}',headers=h,json={'name':'越店'}).status_code==404
    assert client.patch(url+f'/products/{pid}',headers={'Authorization':h['Authorization']},json={'name':'无原因'}).status_code==422
    logs=client.get('/api/v1/op/governance/workspace-actions',headers=h).json()['items']
    assert any(r['status']=='failed' for r in logs) and any(r['status']=='succeeded' for r in logs)
    with SessionLocal() as db:
        opid=db.scalar(select(User.id).where(User.username=='operations'))
        assert all(r['operator_id']==opid for r in logs)


def test_settings_categories_tags_content_and_coupons(client):
    h,sid,url=context(client)
    for kind,body in [('categories',{'name':'全功能分类'}),('tags',{'name':'全功能标签','color':'#669955'}),('banners',{'image_url':'/covers/notebook.jpg','title':'OP轮播'}),('testimonials',{'nickname':'展示用户','content':'OP展示文案','rating':5})]:
        r=client.post(url+'/'+kind,headers=h,json=body);assert r.status_code==200,r.text
        assert client.delete(url+f'/{kind}/{r.json()["id"]}',headers=h).status_code==200
    settings=client.get(url+'/shop',headers=h).json()['storefront'];settings['base_freight_yuan']=12;settings['assistant_welcome']='平台统一欢迎语'
    r=client.patch(url+'/shop',headers=h,json={'name':'OP店名','assistant_name':'小南','logo_url':'/covers/notebook.jpg','storefront':settings,'social_accounts':[{'platform':'微信','account':'opswechat'}]})
    assert r.status_code==200,r.text
    c=client.get('/api/v1/c/shops/nanzhi').json()
    assert c['name']=='OP店名' and c['storefront']['base_freight_yuan']==12 and c['storefront']['assistant_welcome']=='平台统一欢迎语' and c['social_accounts'][0]['account']=='opswechat'
    now=utcnow().replace(tzinfo=timezone.utc)
    r=client.post(url+'/coupons',headers=h,json={'name':'OP券','threshold_cents':9900,'amount_cents':1000,'total_count':10,'starts_at':(now-timedelta(days=1)).isoformat(),'ends_at':(now+timedelta(days=10)).isoformat()})
    assert r.status_code==200,r.text
    cid=r.json()['id']; assert any(x['id']==cid for x in client.get('/api/v1/c/shops/nanzhi/coupons').json())
    assert client.patch(url+f'/coupons/{cid}',headers=h,json={'enabled':False}).status_code==200


def test_decoration_revision_preview_save_and_sort(client):
    h,sid,url=context(client)
    data=client.get(url+'/decoration',headers=h).json()
    fields={'banners':['id','image_url','title','subtitle','link_type','link_value','enabled'],'sections':['id','title','subtitle','source','product_ids','enabled'],'testimonials':['id','nickname','content','rating','enabled']}
    draft={'revision':data['revision'],'appearance':data['appearance'],**{kind:[{k:r[k] for k in keys} for r in data[kind]] for kind,keys in fields.items()}}
    draft['appearance']['hero_height']=520
    draft['appearance']['storefront']['background_color']='#eff4ef'
    assert client.post(url+'/decoration/preview',headers=h,json=draft).status_code==200
    r=client.put(url+'/decoration',headers=h,json=draft);assert r.status_code==200,r.text
    home=client.get('/api/v1/c/shops/nanzhi/home').json()
    assert home['shop']['hero_height']==520 and home['shop']['storefront']['background_color']=='#eff4ef'
    assert client.put(url+'/decoration',headers=h,json=draft).status_code==409


def test_platform_freeze_blocks_cached_products_cart_and_merchant_reopen(client):
    h,sid,url=context(client)
    products=client.get('/api/v1/c/shops/nanzhi/products').json();pid=products[0]['id'];sku=products[0]['skus'][0]['id']
    assert client.post(f'/api/v1/op/governance/shops/{sid}',headers=h,json={'action':'freeze','reason':'平台封店测试'}).status_code==200
    assert client.get('/api/v1/c/shops/nanzhi/products').json()==[]
    assert client.get('/api/v1/c/shops/nanzhi/home').json()['banners']==[]
    assert client.get(f'/api/v1/c/shops/nanzhi/products/{pid}').status_code==404
    assert client.patch('/api/v1/b/shop',headers=login(client,'merchant'),json={'status':'open'}).status_code==403
    assert client.post('/api/v1/c/shops/nanzhi/cart',headers=login(client,'alice'),json={'sku_id':sku,'quantity':1}).status_code!=200
    assert client.patch(url+'/shop',headers=h,json={'notice':'封店期间平台维护'}).status_code==200
    assert client.post(f'/api/v1/op/governance/shops/{sid}',headers=h,json={'action':'unfreeze','reason':'解除限制测试'}).status_code==200
    assert client.get('/api/v1/c/shops/nanzhi/products').json()


def test_account_disable_enable_reset_revokes_old_sessions(client):
    h,sid,url=context(client);old=login(client,'alice')
    with SessionLocal() as db: uid=db.scalar(select(User.id).where(User.username=='alice'));opid=db.scalar(select(User.id).where(User.username=='operations'))
    endpoint=f'/api/v1/op/governance/accounts/{uid}'
    assert client.post(endpoint,headers=h,json={'action':'disable','reason':'禁用测试'}).status_code==200
    assert client.get('/api/v1/auth/me',headers=old).status_code==401
    assert client.post('/api/v1/auth/portal-login',json={'username':'alice','password':'alice123'}).status_code==401
    assert client.post(endpoint,headers=h,json={'action':'enable','reason':'恢复测试'}).status_code==200
    fresh=login(client,'alice');assert client.get('/api/v1/auth/me',headers=fresh).status_code==200
    assert client.get('/api/v1/auth/me',headers=old).status_code==401
    assert client.post(endpoint,headers=h,json={'action':'reset_password','reason':'重置测试','password':'new-password-123'}).status_code==200
    assert client.get('/api/v1/auth/me',headers=fresh).status_code==401
    assert client.post('/api/v1/auth/login',json={'username':'alice','password':'alice123'}).status_code==401
    assert client.post('/api/v1/auth/login',json={'username':'alice','password':'new-password-123'}).status_code==200
    assert client.post(f'/api/v1/op/governance/accounts/{opid}',headers=h,json={'action':'disable','reason':'避免自锁'}).status_code==409
    assert 'new-password' not in client.get('/api/v1/op/platform/audits',headers=h).text


def test_shipping_and_after_sales_share_existing_state_machine(client):
    h,sid,url=context(client)
    with SessionLocal() as db:
        order=db.scalar(select(Order).where(Order.status=='paid'));number=order.order_no;buyer=order.buyer.username
    support=f'/api/v1/op/shops/{sid}/support'
    r=client.put(support+f'/orders/{number}/shipment',headers=h,json={'carrier':'隔离快递','tracking_number':'OPSHIP-001'})
    assert r.status_code==200,r.text
    ch=login(client,buyer)
    assert client.get('/api/v1/support/orders/'+number+'/shipment',headers=ch).json()['tracking_number']=='OPSHIP-001'
    ticket=client.post('/api/v1/support/orders/'+number+'/after-sale',headers=ch,json={'kind':'return','reason':'隔离退货测试'}).json()
    r=client.post(support+f'/after-sales/{ticket["id"]}/process',headers=h,json={'action':'accept','note':'平台受理退货'})
    assert r.status_code==200,r.text
    assert client.get('/api/v1/support/after-sales',headers=ch).json()[0]['status']=='accepted'


def test_review_moderation_updates_c_rating_without_editing_original(client):
    h,sid,url=context(client)
    with SessionLocal() as db:
        order=db.scalar(select(Order));item=order.items[0]
        r=db.scalar(select(Review))
        r.rating=2;r.content='保留真实评价原文'
        db.commit();rid,pid=r.id,r.product_id
    assert client.post(f'/api/v1/op/governance/reviews/{rid}',headers=h,json={'action':'hide','reason':'违规内容测试'}).status_code==200
    assert all(r['id']!=rid for r in client.get(f'/api/v1/c/shops/nanzhi/products/{pid}/reviews').json())
    with SessionLocal() as db: assert db.get(Review,rid).content=='保留真实评价原文' and db.get(Review,rid).rating==2
    assert client.post(f'/api/v1/op/governance/reviews/{rid}',headers=h,json={'action':'show','reason':'复核恢复'}).status_code==200
    assert any(r['id']==rid for r in client.get(f'/api/v1/c/shops/nanzhi/products/{pid}/reviews').json())


def test_customer_details_are_explicit_and_op_only(client):
    h,sid,url=context(client)
    with SessionLocal() as db: uid=db.scalar(select(User.id).where(User.username=='alice'))
    for kind in ['addresses','cart','coupons','history']:
        endpoint=f'/api/v1/op/governance/customers/{uid}/{kind}'
        assert client.get(endpoint,headers=h).status_code==200
        assert client.get(endpoint,headers=login(client,'alice')).status_code==403
    assert client.get('/api/v1/op/workspace/assets/b.js').status_code==200
    assert 'token_b' not in client.get('/api/v1/op/workspace/assets/b.js').text
    assert client.get('/api/v1/op/workspace/assets/../../.env').status_code==404


def test_sku_governance_is_platform_only(client):
    h,sid,url=context(client)
    product=client.get(url+'/products',headers=h).json()[0];sku=product['skus'][0]['id']
    assert client.post(f'/api/v1/op/governance/skus/{sku}',headers=h,json={'action':'ban','reason':'规格禁售测试'}).json()['status']=='banned'
    assert client.post(f'/api/v1/b/skus/{sku}/status',headers=login(client,'merchant'),json={'action':'unban'}).status_code==403
    assert client.post(f'/api/v1/op/governance/skus/{sku}',headers=h,json={'action':'unban','reason':'规格复核通过'}).json()['status']=='off'


def test_upload_validation_and_sku_sorting(client):
    h,sid,url=context(client)
    upload=client.post(url+'/uploads',headers=h,files={'file':('test.png',b'\x89PNG\r\n\x1a\n','image/png')})
    assert upload.status_code==200,upload.text
    from app.core.config import settings
    path=settings.web_dir/upload.json()['url'].lstrip('/')
    assert path.exists();path.unlink()
    assert client.post(url+'/uploads',headers=h,files={'file':('bad.exe',b'bad','application/octet-stream')}).status_code==400
    product=client.post(url+'/products',headers=h,json={'name':'排序测试','skus':[{'spec':'一','price_yuan':10,'stock':2},{'spec':'二','price_yuan':20,'stock':3}]}).json()
    ids=[s['id'] for s in product['skus']][::-1]
    r=client.post(url+f'/products/{product["id"]}/skus/sort',headers=h,json={'ordered_ids':ids})
    assert r.status_code==200 and [s['id'] for s in r.json()['skus']]==ids


def test_platform_cancel_restores_stock_once(client):
    h,sid,url=context(client);buyer=login(client,'alice')
    products=client.get('/api/v1/c/shops/nanzhi/products').json()
    sku=next(s for p in products for s in p['skus'] if s['stock']>0)
    from app.models.tables import Sku
    with SessionLocal() as db: before=db.get(Sku,sku['id']).stock
    r=client.post('/api/v1/c/shops/nanzhi/orders',headers=buyer,json={'sku_id':sku['id'],'quantity':1,'receiver':'测试','phone':'13800000000','address':'隔离测试地址'})
    assert r.status_code==200,r.text
    order=r.json()
    with SessionLocal() as db: oid=db.scalar(select(Order.id).where(Order.order_no==order['order_no']))
    endpoint=f'/api/v1/op/governance/orders/{oid}/cancel'
    assert client.post(endpoint,headers=h,json={'action':'cancel','reason':'平台取消未付订单'}).status_code==200
    assert client.post(endpoint,headers=h,json={'action':'cancel','reason':'重复取消测试'}).status_code==400
    with SessionLocal() as db: assert db.get(Sku,sku['id']).stock==before
