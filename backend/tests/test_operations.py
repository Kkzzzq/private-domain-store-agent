from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.tables import User, Product
from app.models.operations import Operator
from app.services.shelf import listed_on_c, assert_merchant_editable
from fastapi import HTTPException
import pytest


def operator(client):
    data = client.post('/api/v1/auth/register', json={'username':'operations', 'password':'test-op-password'}).json()
    with SessionLocal() as db:
        db.add(Operator(user_id=data['user']['id']))
        db.commit()
    return {'Authorization':'Bearer '+data['access_token']}


def test_operator_access_and_revoke(client):
    assert client.get('/api/v1/op/overview').status_code == 401
    data = client.post('/api/v1/auth/register', json={'username':'ordinary', 'password':'ordinary-password'}).json()
    headers = {'Authorization':'Bearer '+data['access_token']}
    assert client.get('/api/v1/op/records/orders', headers=headers).status_code == 403
    assert client.post('/api/v1/auth/register', json={'username':'fakeadmin', 'password':'password', 'role':'admin'}).status_code == 422
    headers = operator(client)
    assert client.get('/api/v1/op/overview', headers=headers).status_code == 200
    with SessionLocal() as db:
        db.delete(db.scalar(select(Operator)))
        db.commit()
    assert client.get('/api/v1/op/overview', headers=headers).status_code == 403


def test_operations_lists_and_privacy(client):
    headers = operator(client)
    for resource in ['shops','products','orders','coupons','after-sales','agent-logs','operation-logs']:
        response = client.get('/api/v1/op/records/'+resource, headers=headers)
        assert response.status_code == 200
        assert not any(secret in response.text for secret in ['password_hash','receiver','phone','address','session_id','args'])
    assert client.get('/api/v1/op/records/orders?size=101', headers=headers).status_code == 422
    assert client.get('/api/v1/op/records/orders?page=0', headers=headers).status_code == 422
    assert client.get('/api/v1/op/records/users', headers=headers).status_code == 404
    assert client.get('/api/v1/op/records/products?q=does-not-exist', headers=headers).json()['total'] == 0
    data = client.get('/api/v1/op/overview', headers=headers).json()
    assert len(data['trend']) == 7
    assert data['shops'] > 0


def test_moderation_shared_bc_and_audit(client):
    headers = operator(client)
    with SessionLocal() as db:
        product = db.scalar(select(Product).where(Product.status == 'on'))
        product_id = product.id
        assert listed_on_c(product)
    url = f'/api/v1/op/products/{product_id}/moderate'
    assert client.post(url, headers=headers, json={'action':'ban','reason':'  '}).status_code == 422
    assert client.post(url, headers=headers, json={'action':'ban','reason':'平台审核测试'}).json()['status'] == 'banned'
    with SessionLocal() as db:
        product = db.get(Product, product_id)
        assert not listed_on_c(product)
        with pytest.raises(HTTPException):
            assert_merchant_editable(product)
    assert client.post(url, headers=headers, json={'action':'release','reason':'复核通过'}).json()['status'] == 'off'
    assert client.post(url, headers=headers, json={'action':'release','reason':'复核通过'}).status_code == 409
    logs = client.get('/api/v1/op/records/operation-logs', headers=headers).json()['items']
    assert [r['action'] for r in logs] == ['release','ban']
    assert client.post('/api/v1/op/products/999999/moderate', headers=headers, json={'action':'ban','reason':'不存在'}).status_code == 404
