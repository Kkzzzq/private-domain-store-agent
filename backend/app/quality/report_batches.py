"""一次操作、一份多用例报告。执行预算和原始证据仍按子运行隔离。"""
from collections import Counter
from datetime import datetime, time, timedelta
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models.quality import QualityPlan,QualityRun,QualityReportBatch,QualityReportMember
from app.quality import service


def members(db,batch_id):
    return list(db.scalars(select(QualityReportMember).where(QualityReportMember.batch_id==batch_id).order_by(QualityReportMember.position)))


def create(db,user_id,run_ids,request_key,requested_cases=None):
    service.require_capability(db,user_id,'qa.view')
    if not run_ids or len(run_ids)>200 or len(set(run_ids))!=len(run_ids):raise HTTPException(422,'请选择不重复的执行记录，最多200份')
    old=db.scalar(select(QualityReportBatch).where(QualityReportBatch.request_key==request_key))
    if old:
        if old.created_by!=user_id or [m.run_id for m in members(db,old.id)]!=run_ids or old.requested_cases!=list(requested_cases or []):raise HTTPException(409,'汇总请求内容已改变')
        return output(db,old)
    runs=[];seen=set();environments=set();revisions=set()
    for rid in run_ids:
        run=db.get(QualityRun,rid)
        if not run:raise HTTPException(404,'原始执行记录不存在')
        if run.user_id!=user_id:raise HTTPException(403,'只能汇总当前账号发起的执行')
        if db.get(QualityReportMember,rid):raise HTTPException(409,'执行已属于另一份汇总报告')
        plan=db.get(QualityPlan,run.plan_id);ids=plan.payload['case_ids']
        if seen.intersection(ids):raise HTTPException(409,'同一份报告不能混入同一用例的多次执行')
        seen.update(ids);runs.append(run);environments.add(plan.payload.get('environment_id'));revisions.add(plan.payload.get('target_revision'))
    if len(environments)!=1 or len(revisions)!=1:raise HTTPException(409,'不能把不同环境或代码版本混为同一轮测试')
    requested=list(requested_cases or [])
    if len(requested)!=len(set(requested)) or len(requested)>500 or requested and not seen.issubset(requested):raise HTTPException(422,'请求用例集合与执行记录不一致')
    batch=QualityReportBatch(id=uuid4().hex,created_by=user_id,request_key=request_key,requested_cases=requested,created_at=min(r.created_at for r in runs))
    try:
        db.add(batch);db.flush()
        for i,r in enumerate(runs):db.add(QualityReportMember(run_id=r.id,batch_id=batch.id,position=i))
        db.commit()
    except IntegrityError as exc:
        db.rollback();raise HTTPException(409,'执行已被汇总，请刷新后查看') from exc
    return output(db,batch)


def output(db,batch):
    links=members(db,batch.id);children=[];missing=[]
    for link in links:
        run=db.get(QualityRun,link.run_id)
        if run:children.append(service.run_out(db,run))
        else:missing.append(link.run_id)
    results=[];snapshots=[];seen=set()
    for child in children:
        snapshots.extend(child['target'].get('case_snapshots') or [])
        for result in child['results']:
            results.append(dict(result,source_run_id=child['id'],execution_mode=child['mode']));seen.add(result['id'])
    for cid in batch.requested_cases:
        if cid not in seen:
            from app.quality.case_docs import doc_for
            from app.quality.catalog import case_by_id
            case=case_by_id(cid) or {'id':cid,'title':cid,'kind':'functional'}
            snapshots.append(case);results.append(dict(id=cid,kind=case['kind'],status='blocked',doc=doc_for(cid),evidence={'error':'该用例未启动，或原始执行证据已按保留策略清理','cleanup_ok':False}))
    counts=Counter(r['status'] for r in results)
    active=any(c['status'] in ('queued','running') for c in children)
    status='running' if active else 'failed' if counts['failed'] or any(c['status']=='failed' for c in children) else 'blocked' if counts['blocked'] or missing or not results or any(c['status']=='blocked' for c in children) else 'cancelled' if counts['cancelled'] or any(c['status']=='cancelled' for c in children) else 'completed'
    kinds={c['kind'] for c in children};kind=next(iter(kinds)) if len(kinds)==1 else 'joint'
    first=children[0] if children else {};target=dict(first.get('target') or {});target['case_snapshots']=snapshots
    groups={}
    for k in ('assistant','functional'):
        selected=[r for r in results if r['kind']==k]
        if selected:groups[k]={'planned':len(selected),'counts':dict(Counter(r['status'] for r in selected)),'eligible':all(r['status']=='passed' and r['evidence'].get('cleanup_ok') for r in selected)}
    starts=[c['started_at'] for c in children if c['started_at']];ends=[c['finished_at'] for c in children if c['finished_at']]
    summary={'counts':dict(counts),'groups':groups,'decision':'eligible' if status=='completed' and all(g['eligible'] for g in groups.values()) else 'not_eligible','child_runs':len(links)}
    if missing:summary['error']='部分原始执行证据已清理，不能认定整轮通过'
    modes={c['mode'] for c in children};mode='mixed' if len(modes)>1 else next(iter(modes),'rules')
    return dict(id=batch.id,name=(batch.created_at+timedelta(hours=8)).strftime('%Y-%m-%d %H:%M 测试报告'),plan_id=None,kind=kind,mode=mode,status=status,cancel_requested=any(c['cancel_requested'] for c in children),created_at=batch.created_at,started_at=min(starts) if starts else None,finished_at=max(ends) if ends and not active else None,summary=summary,target=target,results=results,report_batch=True,source_run_ids=[m.run_id for m in links])


def get(db,rid):
    batch=db.get(QualityReportBatch,rid)
    if batch:return output(db,batch)
    run=db.get(QualityRun,rid)
    if not run:raise HTTPException(404,'测试报告不存在')
    return service.run_out(db,run)


def brief_report(report):
    """Dashboard metadata only; full immutable evidence stays on the detail endpoint."""
    result={key:value for key,value in report.items() if key not in ('results','target','planning')}
    result['brief']=True
    result['target']={key:report.get('target',{}).get(key) for key in ('environment_id','target_revision','fixture_version','catalog_version')}
    result['results']=[{'id':row['id'],'kind':row['kind'],'status':row['status']} for row in report['results']]
    return result


def listing(db,report_date=None):
    hidden=select(QualityReportMember.run_id)
    runs=select(QualityRun).where(QualityRun.id.not_in(hidden));batches=select(QualityReportBatch)
    if report_date:
        start=datetime.combine(report_date,time.min)-timedelta(hours=8);end=start+timedelta(days=1)
        runs=runs.where(QualityRun.created_at>=start,QualityRun.created_at<end)
        batches=batches.where(QualityReportBatch.created_at>=start,QualityReportBatch.created_at<end)
    rows=[service.run_out(db,r) for r in db.scalars(runs.order_by(QualityRun.created_at.desc()).limit(100))]
    rows.extend(output(db,b) for b in db.scalars(batches.order_by(QualityReportBatch.created_at.desc()).limit(100)) if any(db.get(QualityRun,m.run_id) for m in members(db,b.id)))
    return sorted(rows,key=lambda r:r['created_at'],reverse=True)[:100]


def artifact(db,rid,aid):
    from app.quality.reporting import owned_artifact
    batch=db.get(QualityReportBatch,rid)
    if not batch:return owned_artifact(db,rid,aid)
    report=output(db,batch)
    row=next((r for r in report['results'] if any(a.get('id')==aid for a in r['evidence'].get('artifacts',[]))),None)
    if not row:raise HTTPException(404,'截图不属于此报告')
    return owned_artifact(db,row['source_run_id'],aid)


def cancel(db,rid,user_id):
    batch=db.get(QualityReportBatch,rid)
    if not batch:return None
    rows=[db.get(QualityRun,m.run_id) for m in members(db,rid)];rows=[r for r in rows if r]
    for row in rows:service.require_execution(db,user_id,row.kind)
    for row in rows:
        if row.status in ('queued','running'):row.cancel_requested=True
    db.commit();return output(db,batch)


def rerun(db,rid,user_id):
    batch=db.get(QualityReportBatch,rid)
    if not batch:return None
    runs=[db.get(QualityRun,m.run_id) for m in members(db,rid)]
    if not runs or any(r is None for r in runs):raise HTTPException(409,'原始执行已清理，请重新选择用例运行')
    plans=[db.get(QualityPlan,r.plan_id) for r in runs]
    for plan in plans:service.require_execution(db,user_id,plan.payload['kind'])
    if all(p.payload.get('environment_id')=='real-nanzhi' for p in plans):
        # 重跑是新一轮，按当前代码重新生成并审批固定实店步骤，不复用过期批准。
        service.require_capability(db,user_id,'qa.approve')
        fields=('kind','mode','environment_id','case_ids','max_calls','max_tokens','timeout_seconds')
        bodies=[service.PlanIn(goal='重跑实店汇总报告 '+rid,planner='fixed',diagnostic=True,**{k:p.payload[k] for k in fields if k in p.payload}) for p in plans]
        plans=[service.new_plan(db,user_id,body) for body in bodies]
        for plan in plans:service.approve(db,plan,user_id,plan.digest)
    else:
        for plan in plans:service.validate_approval(db,plan)
    new=[service.create_run(db,p,user_id,uuid4().hex).id for p in plans]
    return create(db,user_id,new,uuid4().hex,batch.requested_cases)


def compare(db,baseline,candidate):
    from app.quality.catalog import content_digest
    a,b=get(db,baseline),get(db,candidate)
    reasons=[k for k in ('environment_id','fixture_version') if a['target'].get(k)!=b['target'].get(k)]
    if a['mode']!=b['mode']:reasons.append('mode')
    if any(r['status'] in ('queued','running') for r in (a,b)):reasons.append('unfinished_run')
    old={r['id']:r for r in a['results']};new={r['id']:r for r in b['results']}
    versions=[{r['id']:content_digest(r) for r in report['target'].get('case_snapshots') or []} for report in (a,b)]
    rows=[]
    for cid in sorted(old.keys()|new.keys()):
        before,after=old.get(cid),new.get(cid);ok=not reasons and before is not None and after is not None and cid in versions[0] and versions[0].get(cid)==versions[1].get(cid)
        transition='regressed' if ok and before['status']=='passed' and after['status']!='passed' else 'improved' if ok and before['status']!='passed' and after['status']=='passed' else 'unchanged' if ok else 'not_comparable'
        rows.append(dict(id=cid,before=before['status'] if before else 'not_selected',after=after['status'] if after else 'not_selected',comparable=bool(ok),transition=transition))
    return dict(baseline=baseline,candidate=candidate,incompatible_dimensions=reasons,cases=rows,groups={'baseline':a['summary'].get('groups',{}),'candidate':b['summary'].get('groups',{})})
