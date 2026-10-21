"""Isolated known-defect calibration. Does not mutate the shop or claim general recall."""
from fastapi import FastAPI
from fastapi.testclient import TestClient


def run_probe(client):
    response=client.get('/cart')
    if response.status_code!=200: return 'blocked'
    data=response.json()
    try: return 'passed' if data['total']==sum(r['price']*r['quantity'] for r in data['items']) else 'failed'
    except (KeyError,TypeError): return 'blocked'


def benchmark(probe=run_probe):
    reports=[]
    for variant in ('correct','wrong_total'):
        app=FastAPI()
        @app.get('/cart')
        def cart():
            return {'items':[{'price':39,'quantity':2},{'price':32,'quantity':1}], 'total':110 if variant=='correct' else 39}
        with TestClient(app) as client: observed=probe(client)
        reports.append({'variant':variant,'expected':'passed' if variant=='correct' else 'failed','observed':observed})
    return {'scope':'隔离购物车金额探针校准，非完整Agent缺陷检出率','cases':reports,
            'detected':reports[1]['observed']=='failed','false_positive':reports[0]['observed']=='failed',
            'passed':all(r['expected']==r['observed'] for r in reports)}
