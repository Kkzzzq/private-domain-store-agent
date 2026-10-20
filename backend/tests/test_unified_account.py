from test_bc_link import login


def unified(client, username='merchant', password='merchant123'):
    response=client.post('/api/v1/auth/portal-login',json={'username':username,'password':password})
    assert response.status_code==200,response.text
    data=response.json()
    return data,{'Authorization':'Bearer '+data['token_b']},{'Authorization':'Bearer '+data['token_c']}


def test_demo_portal_has_explicit_demo_defaults_and_separate_login_page(client):
    demo=client.get('/api/v1/auth/demo-login').json()
    assert demo=={'enabled':True,'username':'merchant','password':'merchant123'}
    assert client.get('/account-login.html').status_code==200
    assert '/account-login.js' in client.get('/account-login.html').text
    assert client.post('/api/v1/auth/portal-session').status_code==401
    assert client.post('/api/v1/auth/portal-login',json={'username':'merchant','password':'wrong'}).status_code==401


def test_demo_prefill_can_be_disabled_without_disclosing_credentials(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings,'demo_login_enabled',False)
    response=client.get('/api/v1/auth/demo-login')
    assert response.json()=={'enabled':False,'username':'','password':''}
    assert response.headers['cache-control']=='no-store'


def test_same_account_both_views_without_changing_identity_or_legacy_role(client):
    data,b,c=unified(client)
    assert data['shop']['share_code']=='nanzhi'
    buyer=client.get('/api/v1/auth/me',headers=c).json()
    merchant=client.get('/api/v1/auth/me',headers=b).json()
    assert buyer['id']==merchant['id']==data['user']['id']
    assert buyer['role']=='customer' and merchant['role']=='merchant'
    assert client.get('/api/v1/b/products',headers=b).status_code==200
    assert client.get('/api/v1/c/orders',headers=c).status_code==200
    product=client.get('/api/v1/c/shops/nanzhi/products').json()[0]
    order=client.post('/api/v1/c/shops/nanzhi/orders',headers=c,json={'sku_id':product['skus'][0]['id'],'quantity':1,'address':'统一账号隔离测试地址'})
    assert order.status_code==200,order.text
    assert any(o['order_no']==order.json()['order_no'] for o in client.get('/api/v1/b/orders',headers=b).json())
    from app.models.tables import User
    from app.db.session import SessionLocal
    with SessionLocal() as db:
        assert db.get(User,buyer['id']).role=='merchant'


def test_other_accounts_have_their_own_two_entries_and_private_shop(client):
    data,b,c=unified(client,'alice','alice123')
    assert data['shop']['share_code']!='nanzhi'
    assert data['shop']['name']=='小满的小店'
    assert client.get('/api/v1/b/shop',headers=b).json()['id']==data['shop']['id']
    assert client.get('/api/v1/b/products',headers=b).json()==[]
    assert client.get(f"/api/v1/c/shops/{data['shop']['share_code']}/products",headers=c).json()==[]
    products=client.get('/api/v1/c/shops/nanzhi/products').json()
    assert client.patch(f"/api/v1/b/products/{products[0]['id']}",headers=b,json={'name':'跨店修改'}).status_code==404
    again=client.post('/api/v1/auth/portal-session',headers=b)
    assert again.status_code==200 and again.json()['shop']['id']==data['shop']['id']


def test_portal_refresh_reuses_valid_tokens_and_rejects_other_account_tokens(client):
    owner,b,c=unified(client)
    body={key:owner[key] for key in ['token_b','token_c']}
    same=client.post('/api/v1/auth/portal-session',headers=b,json=body).json()
    assert same['token_b']==owner['token_b'] and same['token_c']==owner['token_c']
    other,_,_=unified(client,'alice','alice123')
    body['token_c']=other['token_c']
    replaced=client.post('/api/v1/auth/portal-session',headers=b,json=body).json()
    assert replaced['token_c']!=other['token_c']
    assert client.get('/api/v1/auth/me',headers={'Authorization':'Bearer '+replaced['token_c']}).json()['id']==owner['user']['id']


def test_registration_is_shared_and_logout_revokes_each_view(client):
    response=client.post('/api/v1/auth/portal-register',json={'username':'shared_demo','password':'shared123','nickname':'新店主'})
    assert response.status_code==200,response.text
    data=response.json()
    for side in ['b','c']:
        headers={'Authorization':'Bearer '+data['token_'+side]}
        assert client.get('/api/v1/auth/me',headers=headers).status_code==200
        assert client.post('/api/v1/auth/logout',headers=headers).status_code==200
        assert client.get('/api/v1/auth/me',headers=headers).status_code==401


def test_own_store_chat_uses_view_for_unread_and_permissions(client):
    _,b,c=unified(client)
    conv=client.post('/api/v1/support/shops/nanzhi/conversation',headers=c).json()['id']
    path=f'/api/v1/support/conversations/{conv}'
    assert client.post(path+'/messages',headers=c,json={'client_id':'buyer-message-1','content':'你好商家'}).status_code==200
    assert client.get('/api/v1/support/conversations',headers=b).json()[0]['unread']==1
    assert client.post(path+'/messages',headers=b,json={'client_id':'merchant-message-1','content':'你好买家'}).status_code==200
    assert client.get('/api/v1/support/conversations',headers=c).json()[0]['unread']==1
    rows=client.get(path+'/messages',headers=c).json()
    assert [row['sender_role'] for row in rows]==['customer','merchant']


def test_legacy_role_endpoints_still_isolate_views(client):
    assert client.get('/api/v1/b/products',headers=login(client,'alice')).status_code==403
    assert client.get('/api/v1/c/shops/nanzhi/cart',headers=login(client,'merchant')).status_code==403
