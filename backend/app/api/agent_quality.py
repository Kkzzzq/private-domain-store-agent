from typing import Literal
from uuid import uuid4
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select,update
from app.api.quality import quality_user
from app.core.deps import get_db
from app.db.redis_client import get_redis
from app.models.agent_evaluation import AgentEvaluation
from app.models.quality import QualityPlan, QualityRun
from app.models.tables import utcnow
from app.quality import service
from app.quality.agent_evaluation import snapshot_for,program_checks
from app.quality.feature_catalog import catalog

router=APIRouter(prefix='/agent-quality',tags=['Agent evaluation'])


def output(row):
    review=row.reviews[-1] if row.reviews else None
    adverse=row.program.get('decision')=='failed' or any(d.get('score') is not None and d['score']<=1 for d in row.model_score.get('dimensions',[]))
    conflict=bool(review and (review['decision']=='accepted' and adverse or review['decision']=='rejected' and row.program.get('decision')=='passed'))
    return {k:getattr(row,k) for k in ('id','target','source_run','status','program','model_score','reviews','version','created_at')} | {'snapshot':row.snapshot,'review_conflict':conflict,'review_current':bool(review and review.get('evaluation_version')==row.version-1)}


def record(db,ident):
    row=db.get(AgentEvaluation,ident)
    if not row: raise HTTPException(404,'评测不存在')
    return row


@router.get('/features')
def features(user=Depends(quality_user),db=Depends(get_db)):
    from app.quality.case_versions import all_cases
    return catalog(all_cases(db))


class EvaluationIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    target:Literal['business','functional']
    run_id:str=Field(pattern=r'^[a-f0-9]{32}$')


@router.post('/evaluations',status_code=201)
def create(body:EvaluationIn,user=Depends(quality_user),db=Depends(get_db)):
    service.require_execution(db,user.id,'assistant' if body.target=='business' else 'functional')
    run=db.get(QualityRun,body.run_id)
    if not run: raise HTTPException(404,'来源运行不存在')
    if run.status not in ('completed','failed','blocked','cancelled'): raise HTTPException(409,'请等待运行结束')
    from fastapi.encoders import jsonable_encoder
    report=jsonable_encoder(service.run_out(db,run))
    from app.models.quality import QualityPlan
    plan=db.get(QualityPlan,run.plan_id)
    report['planning']={'goal':plan.payload['goal'],'planner':plan.payload.get('planner'),'evidence':plan.evidence}
    # Persist redacted server evidence; never accept caller-provided scores or transcripts.
    try: snapshot=snapshot_for(report,body.target)
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    row=AgentEvaluation(id=uuid4().hex,created_by=user.id,target=body.target,source_run=run.id,
        snapshot=jsonable_encoder(snapshot),program=program_checks(report,body.target))
    db.add(row);db.commit();return output(row)


@router.get('/evaluations')
def listing(target:Literal['business','functional']='business',user=Depends(quality_user),db=Depends(get_db)):
    from datetime import datetime,timedelta
    rows=list(db.scalars(select(AgentEvaluation).where(AgentEvaluation.target==target).order_by(AgentEvaluation.created_at.desc()).limit(30)))
    for row in rows:
        started=row.model_score.get('started_at')
        if row.status=='scoring' and started and datetime.fromisoformat(started)<utcnow()-timedelta(minutes=5):
            row.status='blocked';row.model_score={**row.model_score,'status':'blocked','error':'评测执行中断；没有自动重放付费调用'};row.version+=1
    db.commit()
    return [output(r) for r in rows]


@router.post('/evaluations/{ident}/model-score')
def model_score(ident:str,user=Depends(quality_user),db=Depends(get_db)):
    from app.core.config import settings
    row=record(db,ident)
    service.require_execution(db,user.id,'assistant' if row.target=='business' else 'functional')
    if row.model_score.get('status') in ('completed','needs_review'): raise HTTPException(409,'已完成的模型评分不可覆盖；需要重评请创建新评测')
    if not settings.qa_chat_model or not settings.qa_chat_api_key_file: raise HTTPException(503,'缺少独立评测模型配置')
    claimed=db.execute(update(AgentEvaluation).where(AgentEvaluation.id==ident,AgentEvaluation.version==row.version,AgentEvaluation.status!='scoring').values(status='scoring',version=row.version+1,model_score={'status':'scoring','started_at':utcnow().isoformat(),'previous_attempt':row.model_score}))
    db.commit()
    if claimed.rowcount!=1: raise HTTPException(409,'评测正在变化，请刷新')
    db.refresh(row)
    from app.quality.worker import subprocess_job
    def revoked():
        db.commit()
        kind='assistant' if row.target=='business' else 'functional'
        return not {'qa.view',f'qa.{kind}.run'}.issubset(service.capabilities(db,user.id))
    score=subprocess_job({'evaluation_job':True,'evaluation_snapshot':row.snapshot,'max_calls':2,'max_tokens':60000,'timeout_seconds':60,'mode':'live'},revoked)
    previous=row.model_score
    row.model_score={**score,'previous_attempt':previous};row.status='completed' if score.get('status') in ('completed','needs_review') else 'blocked';row.version+=1
    db.commit();return output(row)


class ReviewIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=1)
    decision:Literal['accepted','rejected','needs_evidence']
    reason:str=Field(min_length=3,max_length=2000)


@router.post('/evaluations/{ident}/reviews')
def review(ident:str,body:ReviewIn,user=Depends(quality_user),db=Depends(get_db)):
    service.require_capability(db,user.id,'qa.approve')
    row=record(db,ident)
    if row.status=='scoring':raise HTTPException(409,'等待模型评分结束再复核')
    entry={'reviewer':user.id,'at':utcnow().isoformat(),'decision':body.decision,'reason':body.reason,'source_digest':row.snapshot['source_digest'],'evaluation_version':body.version}
    changed=db.execute(update(AgentEvaluation).where(AgentEvaluation.id==ident,AgentEvaluation.version==body.version,AgentEvaluation.status!='scoring').values(reviews=[*row.reviews,entry],version=body.version+1))
    db.commit()
    if changed.rowcount!=1:raise HTTPException(409,'评测已变化，请刷新后复核')
    db.refresh(row);return output(row)


@router.post('/evaluations/{ident}/defect-benchmark')
def tester_benchmark(ident:str,user=Depends(quality_user),db=Depends(get_db)):
    from app.core.config import settings
    service.require_execution(db,user.id,'functional')
    row=record(db,ident)
    if row.target!='functional': raise HTTPException(422,'缺陷基准仅适用功能测试Agent')
    if row.status=='scoring' or row.model_score.get('status')=='completed': raise HTTPException(409,'请在模型评分前运行基准，或创建新评测')
    if not settings.qa_chat_model or not settings.qa_chat_api_key_file:raise HTTPException(503,'缺少独立测试模型配置')
    version=row.version
    claimed=db.execute(update(AgentEvaluation).where(AgentEvaluation.id==ident,AgentEvaluation.version==version,AgentEvaluation.status!='scoring').values(status='scoring',version=version+1,model_score={'status':'scoring','operation':'defect_benchmark','started_at':utcnow().isoformat(),'previous_attempt':row.model_score}))
    db.commit()
    if claimed.rowcount!=1:raise HTTPException(409,'评测已变化')
    from app.quality.agent_evaluation import calibrate_tester
    from app.quality.worker import subprocess_job
    calibration=calibrate_tester(subprocess_job)
    scenario_rows=[{'variant':r['variant'],'case_id':r['case_id'],'title':r['title'],'defect':r['defect'],
                    'observed':r['observed'],'expected':r['expected'],'detected':r['detected'],
                    'mutation_exercised':r['mutation_exercised'],'false_positive':r['false_positive'],
                    'receipt':r.get('receipt'),'error':r.get('error')} for r in calibration.get('scenarios',[])]
    snapshot={**row.snapshot,'calibration':calibration,'evidence':{**row.snapshot['evidence'],'defect_benchmark':{k:v for k,v in calibration.items() if k not in ('runs','scenarios')}|{'scenarios':scenario_rows,'runs':[{'variant':r['variant'],'observed':r['observed'],'expected':r['expected'],'assertions':r['evidence'].get('assertions',[])} for r in calibration['runs']]}}}
    program={**row.program,'checks':[dict(c) for c in row.program['checks']]}
    valid=calibration.get('scenarios_valid',calibration['valid'])
    detected=calibration.get('scenarios_detected',calibration['detected'])
    false_positive=calibration.get('scenarios_false_positive',calibration['false_positive'])
    detail=calibration['scope']+'；逐场景：'+'、'.join(f"{row['title']}={'检出' if row['detected'] else '未检出' if not row['false_positive'] else '误报'}" for row in scenario_rows)
    for check in program['checks']:
        if '已知缺陷检出' in check['name']:
            check.update(status='not_observed' if not valid else 'passed' if detected and not false_positive else 'failed',evidence_ids=['defect_benchmark'],detail=detail)
    program['decision']='failed' if any(c['status']=='failed' for c in program['checks']) else 'incomplete' if any(c['status']=='not_observed' for c in program['checks']) else 'passed'
    db.refresh(row);row.snapshot=snapshot;row.program=program;row.status='completed' if valid else 'blocked';row.model_score={'status':'not_scored','previous_attempt':row.model_score};row.version+=1
    db.commit();return output(row)


@router.post('/defect-benchmark')
def defect_benchmark(user=Depends(quality_user),db=Depends(get_db)):
    service.require_execution(db,user.id,'functional')
    from app.quality.defect_benchmark import benchmark
    return benchmark()


@router.get('/heldout')
def heldout(user=Depends(quality_user)):
    """不公开评测集：只给条目与期望答案摘要，答案本身不在这里返回。"""
    from app.quality.heldout import public_view
    return public_view()


class RevealIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    entry_id:str=Field(min_length=2,max_length=80)
    reason:str=Field(min_length=3,max_length=500)


@router.post('/heldout/reveal')
def heldout_reveal(body:RevealIn,user=Depends(quality_user),db=Depends(get_db)):
    """揭示期望答案需要审批权限，并在 Redis 留下揭示记录（不写进报告正文）。"""
    from datetime import datetime,timezone
    service.require_capability(db,user.id,'qa.approve')
    from app.quality.heldout import reveal
    try: answer=reveal(body.entry_id)
    except KeyError as exc: raise HTTPException(404,'不公开评测集里没有该条目') from exc
    record={'operator':user.id,'at':datetime.now(timezone.utc).isoformat(),'entry_id':body.entry_id,
            'reason':body.reason,'expect_hash':answer.get('expect_hash'),'status':answer['status']}
    cache=get_redis();key='qa:heldout-reveals'
    cache.set_json(key,[record,*(cache.get_json(key) or [])][:50],ex=604800)
    return {'answer':answer,'audit':record}


@router.get('/heldout/reveals')
def heldout_reveals(user=Depends(quality_user)):
    return get_redis().get_json('qa:heldout-reveals') or []


@router.get('/stability')
def stability(plan_id:str,user=Depends(quality_user),db=Depends(get_db)):
    """同一计划重复执行的稳定性统计；重复次数不足时明确判为证据不足。"""
    from app.models.quality import QualityRun
    from app.quality import stability as stability_module
    from fastapi.encoders import jsonable_encoder
    plan=db.get(QualityPlan,plan_id)
    if not plan:raise HTTPException(404,'计划不存在')
    rows=list(db.scalars(select(QualityRun).where(QualityRun.plan_id==plan_id,QualityRun.status.in_(('completed','failed','blocked','cancelled'))).order_by(QualityRun.created_at)))
    reports=[jsonable_encoder(service.run_out(db,row)) for row in rows[-5:]]
    kind='functional' if plan.payload.get('kind')!='assistant' else 'assistant'
    return stability_module.summarize_runs(reports,case_kind=kind,plan_id=plan_id)


@router.get('/evaluations/compare')
def compare_evaluations(baseline:str,candidate:str,user=Depends(quality_user),db=Depends(get_db)):
    from app.quality.evaluation_compare import compare
    return compare(output(record(db,baseline)),output(record(db,candidate)))
