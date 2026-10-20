"""Read-only production smoke checks; never print passwords or session tokens."""
import json
from pathlib import Path
import httpx
from sqlalchemy import func, select
from app.db.base import Base
from app.db.session import engine
import app.models.tables  # noqa: F401

accounts = dict(line.split(': ', 1) for line in Path('/root/private-store-accounts.txt').read_text().splitlines() if ': ' in line)
with httpx.Client(base_url='https://kkzzzq.cyou', timeout=30, trust_env=False) as client:
    ready = client.get('/api/v1/ready')
    ready.raise_for_status()
    assert ready.json()['database'] == 'mysql' and ready.json()['redis'] == 'redis'
    auth = client.post('/api/v1/auth/login', json={'username': 'merchant', 'password': accounts['merchant']})
    auth.raise_for_status()
    headers = {'Authorization': 'Bearer ' + auth.json()['access_token']}
    shop = client.get('/api/v1/b/shop', headers=headers)
    shop.raise_for_status()
    prefix = '/api/v1/c/shops/' + shop.json()['share_code']
    public = client.get(prefix)
    public.raise_for_status()
    assert public.json() == shop.json()
    products = client.get('/api/v1/b/products', headers=headers)
    products.raise_for_status()
    catalog = client.get(prefix + '/products')
    catalog.raise_for_status()
    expected = {p['id'] for p in products.json() if p['status'] == 'on' and any(s['status'] == 'on' for s in p['skus'])}
    assert expected == {p['id'] for p in catalog.json()}
    for endpoint in ('/api/v1/b/decoration', '/api/v1/b/coupons', '/api/v1/b/orders', prefix + '/home'):
        client.get(endpoint, headers=headers).raise_for_status()
    assets = set()
    def collect(value):
        if isinstance(value, dict):
            for name, child in value.items():
                if name in ('image_url', 'logo_url') and isinstance(child, str) and child.startswith('/'):
                    assets.add(child)
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)
    collect(products.json())
    home = client.get(prefix + '/home').json()
    collect(home)
    for asset in assets:
        response = client.get(asset)
        response.raise_for_status()
        assert response.headers.get('content-type', '').startswith('image/')
    for path in ('/', '/c.html?code=nanzhi', '/b.html'):
        response = client.get(path)
        response.raise_for_status()
        assert '/site-registration.js' in response.text
    client.get('/portal.css').raise_for_status()
    counts = {}
    with engine.connect() as connection:
        for table in Base.metadata.sorted_tables:
            counts[table.name] = connection.scalar(select(func.count()).select_from(table))
            for fk in table.foreign_keys:
                column, parent = fk.parent, fk.column
                orphan = select(func.count()).select_from(table.outerjoin(parent.table, column == parent)).where(column.is_not(None), parent.is_(None))
                assert connection.scalar(orphan) == 0, str(fk)
    print(json.dumps({'readiness': 'mysql/redis', 'business_tables': len(counts), 'counts': counts,
                      'image_assets_verified': len(assets), 'foreign_keys': 'valid', 'merchant_login': 'passed',
                      'shop_and_catalog_alignment': 'passed'}))
