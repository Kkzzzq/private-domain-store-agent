def test_op_demo_prefill_is_opt_in_and_never_cached(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, 'op_demo_login_enabled', False)
    monkeypatch.setattr(settings, 'op_demo_login_username', 'demo-admin')
    monkeypatch.setattr(settings, 'op_demo_login_password', 'demo-test-password')
    response = client.get('/api/v1/auth/op-demo-login')
    assert response.json() == {'enabled': False, 'username': '', 'password': ''}
    assert response.headers['cache-control'] == 'no-store'
    monkeypatch.setattr(settings, 'op_demo_login_enabled', True)
    assert client.get('/api/v1/auth/op-demo-login').json() == {
        'enabled': True, 'username': 'demo-admin', 'password': 'demo-test-password'}
    monkeypatch.setattr(settings, 'op_demo_login_password', '')
    assert client.get('/api/v1/auth/op-demo-login').json()['enabled'] is False
