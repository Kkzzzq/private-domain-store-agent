from test_bc_link import login


def test_profile_requires_identity_and_saves_nickname(client):
    assert client.patch('/api/v1/auth/me',json={'nickname':'新昵称'}).status_code == 401
    headers=login(client,'merchant')
    assert client.patch('/api/v1/auth/me',headers=headers,json={'nickname':'  店主新昵称  '}).json()['nickname']=='店主新昵称'
    assert client.get('/api/v1/auth/me',headers=headers).json()['nickname']=='店主新昵称'
    assert client.patch('/api/v1/auth/me',headers=headers,json={'nickname':'   '}).status_code==422


def test_closing_account_checks_password_and_revokes_access(client):
    registered=client.post('/api/v1/auth/register',json={'username':'closing_shop','password':'close123','role':'merchant'}).json()
    headers={'Authorization':'Bearer '+registered['access_token']}
    body={'password':'wrong','confirmation':'注销账号'}
    assert client.post('/api/v1/auth/me/close',headers=headers,json=body).status_code==400
    body['password']='close123';body['confirmation']='错误'
    assert client.post('/api/v1/auth/me/close',headers=headers,json=body).status_code==400
    body['confirmation']='注销账号'
    assert client.post('/api/v1/auth/me/close',headers=headers,json=body).json()['closed']
    assert client.get('/api/v1/auth/me',headers=headers).status_code==401
    assert client.get('/api/v1/b/products',headers=headers).status_code==401
    assert client.post('/api/v1/auth/login',json={'username':'closing_shop','password':'close123'}).status_code==401
    from app.db.session import SessionLocal
    from app.models.tables import Shop,User
    from sqlalchemy import select
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.username=='closing_shop'))
        assert user is not None
        assert db.scalar(select(Shop).where(Shop.merchant_id==user.id)).status=='closed'


def test_outstanding_orders_block_account_closure(client):
    assert client.post('/api/v1/auth/me/close',headers=login(client,'merchant'),json={'password':'merchant123','confirmation':'注销账号'}).status_code==409
    assert client.get('/api/v1/auth/me',headers=login(client,'merchant')).status_code==200


def test_branding_round_trip_is_same_for_buyer_and_merchant(client):
    headers=login(client,'merchant')
    result=client.patch('/api/v1/b/shop',headers=headers,json={
        'name':'自定义小店','logo_url':'/covers/mug.jpg',
        'storefront':{'merchant_title':'我的经营空间','brand_slogan':'用心选物','portal_title':'欢迎来逛逛','portal_description':'新店好物等你发现'}
    })
    assert result.status_code==200,result.text
    buyer=client.get('/api/v1/c/shops/nanzhi').json()
    merchant=client.get('/api/v1/b/shop',headers=headers).json()
    for data in [buyer,merchant]:
        assert data['name']=='自定义小店' and data['logo_url']=='/covers/mug.jpg'
        assert data['storefront']['merchant_title']=='我的经营空间'
        assert data['storefront']['portal_title']=='欢迎来逛逛'
