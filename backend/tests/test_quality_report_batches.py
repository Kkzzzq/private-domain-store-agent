from datetime import datetime,timedelta
from uuid import uuid4
from hashlib import sha256
import pytest
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.quality import QualityPlan,QualityRun,QualityResult
from app.quality import service
from app.core.config import settings
from test_quality import operator


def fixture_run(db,uid,cid,status='passed',created=None,kind='functional'):
    now=created or datetime(2026,10,21,1,30)
    payload={'case_ids':[cid],'case_snapshots':[{'id':cid,'kind':kind,'title':'中文用例'+cid,'version':1}],
             'case_documents':{cid:{'steps':['执行'+cid],'expected':['预期'+cid]}},'target_revision':'same-revision','environment_id':'real-nanzhi','fixture_version':'same-fixture','catalog_version':'same-catalog','kind':kind}
    plan=QualityPlan(id=uuid4().hex,user_id=uid,status='approved',payload=payload,digest='a'*64);db.add(plan);db.flush()
    row=QualityRun(id=uuid4().hex,user_id=uid,plan_id=plan.id,request_key=uuid4().hex,kind=kind,mode='live' if kind=='assistant' else 'rules',status='completed' if status=='passed' else status,created_at=now,started_at=now,finished_at=now+timedelta(seconds=3),summary={})
    db.add(row);db.flush();db.add(QualityResult(run_id=row.id,case_id=cid,kind=kind,status=status,evidence={'cleanup_ok':True,'assertions':[{'name':'真实断言','passed':status=='passed'}],'error':'实际失败原因' if status=='failed' else ''}));db.commit();return row.id


def test_one_report_has_many_cases_original_evidence_and_beijing_date(client):
    headers,uid=operator(client)
    with SessionLocal() as db:ids=[fixture_run(db,uid,'RF01'),fixture_run(db,uid,'RA01',kind='assistant'),fixture_run(db,uid,'RE01','failed')]
    body={'run_ids':ids,'requested_cases':['RF01','RA01','RE01'],'request_key':uuid4().hex}
    response=client.post('/api/v1/op/qa/report-batches',headers=headers,json=body);assert response.status_code==201,response.text
    report=response.json();rid=report['id'];assert report['report_batch'] and report['kind']=='joint' and report['status']=='failed'
    assert [r['id'] for r in report['results']]==['RF01','RA01','RE01']
    assert report['results'][2]['evidence']['error']=='实际失败原因'
    assert all(r['source_run_id'] in ids and r['doc']['steps'] for r in report['results'])
    listing=client.get('/api/v1/op/qa/runs?report_date=2026-10-21',headers=headers).json()
    assert [r['id'] for r in listing]==[rid]
    assert client.get('/api/v1/op/qa/runs?report_date=2026-10-22',headers=headers).json()==[]
    assert client.get('/api/v1/op/qa/runs/'+rid+'/report',headers=headers).json()['results']==report['results']
    assert client.get('/api/v1/op/qa/runs/'+ids[0],headers=headers).status_code==200
    assert client.post('/api/v1/op/qa/report-batches',headers=headers,json=body).json()['id']==rid
    comparison=client.get('/api/v1/op/qa/compare',headers=headers,params={'baseline':rid,'candidate':rid}).json()
    assert len(comparison['cases'])==3 and all(r['transition']=='unchanged' for r in comparison['cases'])


def test_batch_missing_and_unstarted_cases_are_blocked_and_artifacts_still_authorized(client):
    headers,uid=operator(client)
    with SessionLocal() as db:
        run_id=fixture_run(db,uid,'RE01');result=db.scalar(select(QualityResult).where(QualityResult.run_id==run_id))
        aid=uuid4().hex+'.png';root=settings.backend_root/'data'/'quality-artifacts';root.mkdir(parents=True,exist_ok=True);path=root/aid;path.write_bytes(b'actual-test-image')
        result.evidence={**result.evidence,'artifacts':[{'id':aid,'sha256':sha256(path.read_bytes()).hexdigest()}]};db.commit()
    response=client.post('/api/v1/op/qa/report-batches',headers=headers,json={'run_ids':[run_id],'requested_cases':['RE01','RE02'],'request_key':uuid4().hex});assert response.status_code==201,response.text
    report=response.json();rid=report['id'];assert report['status']=='blocked' and report['results'][1]['status']=='blocked'
    assert client.get(f'/api/v1/op/qa/runs/{rid}/artifacts/{aid}',headers=headers).content==b'actual-test-image'
    assert client.get(f'/api/v1/op/qa/runs/{rid}/artifacts/{uuid4().hex}.png',headers=headers).status_code==404
    with SessionLocal() as db:
        db.delete(db.get(QualityRun,run_id));db.commit()
    report=client.get('/api/v1/op/qa/runs/'+rid,headers=headers).json();assert report['status']=='blocked' and '清理' in report['summary']['error']
    path.unlink()


def test_batch_rejects_duplicate_cases_other_owner_and_changed_environment(client):
    headers,uid=operator(client)
    with SessionLocal() as db:
        first=fixture_run(db,uid,'RF01');same=fixture_run(db,uid,'RF01');other=fixture_run(db,uid,'RF02')
        p=db.get(QualityPlan,db.get(QualityRun,other).plan_id);p.payload={**p.payload,'environment_id':'isolated-local'};db.commit()
    for ids in ([first,same],[first,other]):
        assert client.post('/api/v1/op/qa/report-batches',headers=headers,json={'run_ids':ids,'request_key':uuid4().hex}).status_code==409
    with SessionLocal() as db:
        from app.models.tables import User
        alice=db.scalar(select(User).where(User.username=='alice'));foreign=fixture_run(db,alice.id,'RF03')
    assert client.post('/api/v1/op/qa/report-batches',headers=headers,json={'run_ids':[foreign],'request_key':uuid4().hex}).status_code==403


def test_running_batch_cancel_and_rerun_requires_new_approval_permission(client):
    headers,uid=operator(client)
    with SessionLocal() as db:
        ids=[fixture_run(db,uid,'RF01','queued'),fixture_run(db,uid,'RF02','running')]
    response=client.post('/api/v1/op/qa/report-batches',headers=headers,json={'run_ids':ids,'requested_cases':['RF01','RF02'],'request_key':uuid4().hex})
    rid=response.json()['id'];assert response.json()['status']=='running'
    cancelled=client.post(f'/api/v1/op/qa/runs/{rid}/cancel',headers=headers);assert cancelled.status_code==200,cancelled.text
    with SessionLocal() as db:assert all(db.get(QualityRun,key).cancel_requested for key in ids)
    # 重新生成当前代码计划需要当前发起人有审批权限，不能绕过。
    with SessionLocal() as db:
        from app.models.quality import QualityGrant
        grant=db.get(QualityGrant,uid);grant.capabilities=['qa.view','qa.functional.run'];db.commit()
    assert client.post(f'/api/v1/op/qa/runs/{rid}/rerun',headers=headers).status_code in (403,409)
    with SessionLocal() as db:assert len(list(db.scalars(select(QualityRun))))==2


def test_real_batch_rerun_creates_new_current_plans_and_single_parent(client,monkeypatch):
    headers,uid=operator(client)
    monkeypatch.setattr(settings,'qa_real_shop_enabled',True)
    with SessionLocal() as db:ids=[fixture_run(db,uid,'RF01'),fixture_run(db,uid,'RF02')]
    original=client.post('/api/v1/op/qa/report-batches',headers=headers,json={'run_ids':ids,'requested_cases':['RF01','RF02'],'request_key':uuid4().hex}).json()
    response=client.post('/api/v1/op/qa/runs/'+original['id']+'/rerun',headers=headers)
    assert response.status_code==201,response.text
    report=response.json();assert report['report_batch'] and len(report['results'])==2 and set(report['source_run_ids']).isdisjoint(ids)
    with SessionLocal() as db:
        for rid in report['source_run_ids']:
            plan=db.get(QualityPlan,db.get(QualityRun,rid).plan_id)
            assert plan.status=='approved' and plan.payload['target_revision']==service.fingerprint()
