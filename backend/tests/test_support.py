from uuid import uuid4
import pytest
from test_bc_link import login


def start(client, headers):
    response=client.post('/api/v1/support/shops/nanzhi/conversation', headers=headers)
    assert response.status_code == 200, response.text
    return response.json()['id']


def message(client, headers, conversation, text='你好，想咨询一下订单', **extra):
    return client.post(f'/api/v1/support/conversations/{conversation}/messages', headers=headers,
        json=dict(content=text, client_id=uuid4().hex, **extra))


def test_human_messages_persist_deduplicate_and_mark_read(client):
    buyer, merchant=login(client,'alice'),login(client,'merchant')
    conv=start(client,buyer)
    assert start(client,buyer)==conv
    body=dict(content='售后咨询',client_id=uuid4().hex,order_no='PS202601150001')
    first=client.post(f'/api/v1/support/conversations/{conv}/messages',headers=buyer,json=body)
    assert first.status_code==200
    retry=client.post(f'/api/v1/support/conversations/{conv}/messages',headers=buyer,json=body)
    assert retry.json()['id']==first.json()['id']
    assert client.get('/api/v1/support/conversations',headers=merchant).json()[0]['unread']==1
    path=f'/api/v1/support/conversations/{conv}'
    assert client.post(path+'/read',headers=merchant,json={'message_id':first.json()['id']}).status_code==200
    assert client.get('/api/v1/support/conversations',headers=merchant).json()[0]['unread']==0
    assert message(client,merchant,conv,'请描述一下问题').status_code==200
    assert client.get('/api/v1/support/conversations',headers=buyer).json()[0]['unread']==1
    history=client.get(path+'/messages',headers=buyer).json()
    assert [m['sender_role'] for m in history]==['customer','merchant']
    assert history[0]['order_no']=='PS202601150001'
    assert client.get(path+'/messages',headers=buyer,params={'after':history[0]['id']}).json()==history[1:]


def test_support_isolated_by_user_shop_and_order(client):
    alice,bob,merchant=login(client,'alice'),login(client,'bob'),login(client,'merchant')
    conv=start(client,alice)
    assert client.get(f'/api/v1/support/conversations/{conv}/messages').status_code==401
    for headers in [bob]:
        assert client.get(f'/api/v1/support/conversations/{conv}/messages',headers=headers).status_code==404
        assert message(client,headers,conv).status_code==404
        assert client.post(f'/api/v1/support/conversations/{conv}/read',headers=headers,json={'message_id':0}).status_code==404
    other=client.post('/api/v1/auth/register',json={'username':'other_support','password':'test1234','role':'merchant'}).json()
    foreign={'Authorization':'Bearer '+other['access_token']}
    assert message(client,foreign,conv).status_code==404
    assert client.get('/api/v1/support/conversations',headers=foreign).json()==[]
    assert message(client,alice,conv,order_no='PS202601200001').status_code==404
    assert client.post('/api/v1/support/shops/nanzhi/conversation',headers=merchant).status_code==403
    assert message(client,alice,conv,'   ').status_code==422
    assert message(client,alice,conv,'x'*2001).status_code==422
    assert client.post('/api/v1/support/orders/PS202601150001/conversation',headers=bob).status_code==404
    assert client.post('/api/v1/support/orders/PS202601150001/conversation',headers=merchant).json()['id']==conv


def test_recent_message_pagination_does_not_lose_history(client):
    from app.db.session import SessionLocal
    from app.models.support import Message
    from app.models.tables import User
    from sqlalchemy import select
    buyer=login(client,'alice');conv=start(client,buyer)
    with SessionLocal() as db:
        uid=db.scalar(select(User.id).where(User.username=='alice'))
        db.add_all([Message(conversation_id=conv,sender_id=uid,sender_role='customer',client_id=uuid4().hex,content=str(i)) for i in range(125)])
        db.commit()
    path=f'/api/v1/support/conversations/{conv}/messages'
    recent=client.get(path,headers=buyer).json()
    assert len(recent)==100 and recent[0]['content']=='25' and recent[-1]['content']=='124'
    older=client.get(path,headers=buyer,params={'before':recent[0]['id']}).json()
    assert len(older)==25 and older[0]['content']=='0'


def test_shipping_is_shared_and_state_transitions_are_protected(client):
    merchant,alice,bob=login(client,'merchant'),login(client,'alice'),login(client,'bob')
    path='/api/v1/support/orders/PS202601150001/shipment'
    assert client.get(path,headers=alice).json() is None
    body={'carrier':'顺丰速运','tracking_number':'SF1234567890'}
    assert client.put(path,headers=alice,json=body).status_code==403
    assert client.put(path,headers=merchant,json=body).status_code==200
    assert client.get(path,headers=bob).status_code==404
    c=client.get(path,headers=alice).json()
    assert c==client.get(path,headers=merchant).json() and c['source']=='merchant'
    order=next(o for o in client.get('/api/v1/c/orders',headers=alice).json() if o['order_no']=='PS202601150001')
    assert order['status']=='shipped'
    assert client.post(path+'/events',headers=merchant,json={'status':'transit','description':'商家确认包裹已交快递'}).status_code==200
    assert client.post(path+'/events',headers=merchant,json={'status':'delivered','description':'商家根据签收凭证更新'}).status_code==200
    assert client.put(path,headers=merchant,json=body).status_code==409
    assert client.post(path+'/events',headers=merchant,json={'status':'transit','description':'回退'}).status_code==409
    assert len(client.get(path,headers=alice).json()['events'])==3


def test_unpaid_orders_and_invalid_tracking_cannot_be_shipped(client):
    merchant,alice=login(client,'merchant'),login(client,'alice')
    product=client.get('/api/v1/c/shops/nanzhi/products').json()[0]
    order=client.post('/api/v1/c/shops/nanzhi/orders',headers=alice,json={
        'sku_id':product['skus'][0]['id'],'quantity':1,'address':'隔离物流测试地址'}).json()
    path=f"/api/v1/support/orders/{order['order_no']}/shipment"
    assert client.put(path,headers=merchant,json={'carrier':'顺丰','tracking_number':'SF123456'}).status_code==409
    assert client.get(path,headers=alice).json() is None
    assert client.put('/api/v1/support/orders/PS202601150001/shipment',headers=merchant,
        json={'carrier':'顺丰','tracking_number':'<script>'}).status_code==422


def test_after_sale_lifecycle_without_funds_or_order_rewrite(client):
    alice,merchant,bob=login(client,'alice'),login(client,'merchant'),login(client,'bob')
    path='/api/v1/support/orders/PS202601150001/after-sale'
    body={'kind':'exchange','reason':'杯身有一处破损，希望换货'}
    assert client.post(path,headers=bob,json=body).status_code==404
    response=client.post(path,headers=alice,json=body)
    assert response.status_code==200,response.text
    row=response.json();process=f"/api/v1/support/after-sales/{row['id']}/process"
    assert client.post(path,headers=alice,json=body).status_code==409
    assert client.post(process,headers=alice,json={'action':'accept','note':'同意'}).status_code==403
    assert client.post(process,headers=bob,json={'action':'withdraw','note':'撤销'}).status_code==404
    assert client.post(process,headers=merchant,json={'action':'resolve','note':'处理完成'}).status_code==409
    assert client.post(process,headers=merchant,json={'action':'accept','note':'同意换货，请寄回，退回地址请在聊天中确认'}).status_code==200
    assert client.post(process,headers=alice,json={'action':'return_ship','note':'已寄回'}).status_code==422
    assert client.post(process,headers=alice,json={'action':'return_ship','note':'包裹已经寄回','carrier':'中通','tracking_number':'ZT1234567890'}).status_code==200
    assert client.post(process,headers=merchant,json={'action':'resolve','note':'收到退件，新品已补发，运单在聊天中提供'}).json()['status']=='resolved'
    assert client.get('/api/v1/support/after-sales',headers=alice).json()==client.get('/api/v1/support/after-sales',headers=merchant).json()
    assert client.get('/api/v1/support/after-sales',headers=bob).json()==[]
    assert client.post(process,headers=merchant,json={'action':'reject','note':'重复操作'}).status_code==409


@pytest.mark.parametrize('action,role,status',[('withdraw','alice','withdrawn'),('reject','merchant','rejected')])
def test_withdraw_and_reject_are_audited(client,action,role,status):
    row=client.post('/api/v1/support/orders/PS202601150001/after-sale',headers=login(client,'alice'),json={'kind':'other','reason':'需要帮助处理订单'}).json()
    result=client.post(f"/api/v1/support/after-sales/{row['id']}/process",headers=login(client,role),json={'action':action,'note':'测试处理说明'})
    assert result.json()['status']==status and len(result.json()['events'])==2
