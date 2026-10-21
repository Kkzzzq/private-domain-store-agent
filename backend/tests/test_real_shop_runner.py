from types import SimpleNamespace
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.tables import Shop, Product, User
from app.quality import real_runner
from app.quality.real_cases import SPECS, cases, doc_for
from test_quality import operator


@pytest.mark.parametrize('case_id',[key for key in SPECS if key.startswith('RF')])
def test_real_api_adapter_uses_business_routes_and_archives_only_owned_records(client,monkeypatch,case_id):
    _,user_id=operator(client)
    with SessionLocal() as db:
        shop=db.scalar(select(Shop).where(Shop.share_code=='nanzhi'));shop_id=shop.id
        original={p.id:p.status for p in db.scalars(select(Product).where(Product.shop_id==shop.id))}
        if case_id=='RF12':
            from scripts.seed_nanzhi_demo import seed
            seed(db,shop_id);db.commit()
    monkeypatch.setattr(settings,'qa_real_shop_enabled',True)
    monkeypatch.setattr(real_runner,'httpx',SimpleNamespace(Client=lambda **kwargs:client))
    output=real_runner.execute({'environment_id':'real-nanzhi','case_id':case_id,'mode':'rules','real_operator_id':user_id,'timeout_seconds':90,'max_tokens':60000})
    assert output['status']=='passed',output.get('error')
    assert output['cleanup_ok'] and all(item['passed'] for item in output['assertions'])
    assert any(item['via']=='real_shop_http' for item in output['requests'])
    with SessionLocal() as db:
        for pid,status in original.items():assert db.get(Product,pid).status==status
        for pid in output['cleanup']['archived_product_ids']:assert db.get(Product,pid).status=='off'


def test_real_profile_is_opt_in_and_catalog_has_chinese_steps(monkeypatch):
    monkeypatch.setattr(settings,'qa_real_shop_enabled',False)
    result=real_runner.execute({'case_id':'RF01','mode':'rules','environment_id':'real-nanzhi'})
    assert result['status']=='blocked' and '未启用' in result['error']
    for row in cases():
        assert doc_for(row['id'])['steps'] and doc_for(row['id'])['expected']
        assert row['environments']==['real-nanzhi']
    monkeypatch.setattr(settings,'qa_real_shop_enabled',True)
    from app.quality.service import PlanIn
    with pytest.raises(ValueError,match='live'):
        PlanIn(goal='禁止规则回退',kind='assistant',environment_id='real-nanzhi',case_ids=['RA01'],mode='rules')


def test_real_profile_rejects_arbitrary_origin_before_creating_identity(monkeypatch):
    monkeypatch.setattr(settings,'qa_real_shop_enabled',True)
    monkeypatch.setattr(settings,'qa_real_shop_origin','https://example.com')
    with SessionLocal() as db:before=list(db.scalars(select(User.id)))
    result=real_runner.execute({'case_id':'RF01','mode':'rules','environment_id':'real-nanzhi'})
    assert result['status']=='blocked' and 'shop.kkzzzq.cyou' in result['error']
    with SessionLocal() as db:assert list(db.scalars(select(User.id)))==before


def test_real_profile_standard_plan_worker_and_persisted_report(client,monkeypatch):
    from app.quality import service
    from app.quality.worker import run_one
    from app.models.quality import QualityRun
    headers,user_id=operator(client)
    monkeypatch.setattr(settings,'qa_real_shop_enabled',True)
    monkeypatch.setattr(real_runner,'httpx',SimpleNamespace(Client=lambda **kwargs:client))
    response=client.post('/api/v1/op/qa/plans',headers=headers,json={'goal':'真实南枝链路测试','kind':'functional','environment_id':'real-nanzhi','case_ids':['RF02']})
    assert response.status_code==201,response.text
    plan=response.json();assert plan['status']=='draft'
    assert plan['payload']['real_operator_id']==user_id
    assert client.post('/api/v1/op/qa/plans/'+plan['id']+'/approve',headers=headers,json={'digest':plan['digest']}).status_code==200
    response=client.post('/api/v1/op/qa/runs',headers=headers,json={'plan_id':plan['id'],'request_key':'real-standard-run'})
    assert response.status_code==201,response.text
    run_id=response.json()['id']
    assert run_one(run_id,executor=lambda spec,cancelled:real_runner.execute(spec))
    with SessionLocal() as db:
        report=service.run_out(db,db.get(QualityRun,run_id))
        assert report['status']=='completed'
        assert report['target']['environment_id']=='real-nanzhi'
        assert report['results'][0]['status']=='passed'
        assert report['results'][0]['doc']['steps']
        assert report['results'][0]['evidence']['cleanup_ok']


def test_real_recovery_only_archives_unpredictably_tagged_owned_products(client):
    from app.quality.real_cleanup import ledger_path,recover
    from uuid import uuid4
    import json
    tag=uuid4().hex[:12];ledger=uuid4().hex
    with SessionLocal() as db:
        shop=db.scalar(select(Shop).where(Shop.share_code=='nanzhi'))
        original={p.id:p.status for p in db.scalars(select(Product).where(Product.shop_id==shop.id))}
        p=Product(shop_id=shop.id,name='【实测】恢复 '+tag,description='恢复 '+tag,status='on');db.add(p);db.commit();pid=p.id
        ledger_path(ledger).write_text(json.dumps({'tag':tag,'shop_id':shop.id}))
    assert recover(ledger)['ok']
    assert not ledger_path(ledger).exists()
    with SessionLocal() as db:
        assert db.get(Product,pid).status=='off'
        for key,value in original.items():assert db.get(Product,key).status==value
