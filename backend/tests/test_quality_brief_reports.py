import json
from app.quality.report_batches import brief_report


def test_large_evidence_detail_preserves_order_without_database_json_filesort(client):
    from sqlalchemy import event, select
    from app.db.session import SessionLocal, engine
    from app.models.quality import QualityResult
    from test_quality import operator
    from test_quality_report_batches import fixture_run

    headers, uid = operator(client)
    evidence = {"cleanup_ok": True, "transcript": "large evidence " * 20000}
    with SessionLocal() as db:
        run_id = fixture_run(db, uid, "RF02")
        first = db.scalar(select(QualityResult).where(QualityResult.run_id == run_id))
        first.evidence = evidence
        db.add(QualityResult(run_id=run_id, case_id="RF01", kind="functional", status="passed", evidence=evidence))
        db.commit()

    def guard_sort(_connection, _cursor, statement, *_args):
        if "FROM qa_results" in statement and "qa_results.evidence" in statement:
            assert "ORDER BY" not in statement, "MySQL cannot filesort rows containing large evidence JSON"

    event.listen(engine, "before_cursor_execute", guard_sort)
    try:
        response = client.get("/api/v1/op/qa/runs/" + run_id, headers=headers)
        assert response.status_code == 200
        rows = response.json()["results"]
        assert [row["id"] for row in rows] == ["RF02", "RF01"]
        assert all(row["evidence"] == evidence for row in rows)
    finally:
        event.remove(engine, "before_cursor_execute", guard_sort)


def test_brief_report_preserves_counts_and_drops_transcripts_without_mutating_source():
    original={'id':'report','kind':'joint','status':'failed','created_at':'2026-10-21',
              'summary':{'groups':{'functional':{'counts':{'passed':1,'failed':1}}}},
              'target':{'environment_id':'real-nanzhi','target_revision':'version','case_snapshots':[{'definition':'x'*10000}]},
              'planning':{'tools':['x'*10000]},
              'results':[{'id':'RF01','kind':'functional','status':'passed','evidence':{'requests':['x'*10000]}},
                         {'id':'RA01','kind':'assistant','status':'failed','evidence':{'error':'kept in full report'}}]}
    brief=brief_report(original)
    assert brief['summary']==original['summary'] and brief['status']=='failed'
    assert brief['target']['environment_id']=='real-nanzhi'
    assert [(r['id'],r['status']) for r in brief['results']]==[('RF01','passed'),('RA01','failed')]
    assert len(json.dumps(brief))<len(json.dumps(original))/10
    assert 'evidence' not in brief['results'][0] and 'requests' in original['results'][0]['evidence']


def test_brief_list_is_opt_in_and_detail_retains_evidence(client,monkeypatch):
    from test_quality import operator
    from app.quality import report_batches
    headers,_=operator(client)
    report={'id':'r','kind':'functional','status':'passed','target':{'environment_id':'isolated-local'},
            'results':[{'id':'F11','kind':'functional','status':'passed','evidence':{'assertions':[{'passed':True}]}}]}
    monkeypatch.setattr(report_batches,'listing',lambda db,day:[report])
    monkeypatch.setattr(report_batches,'get',lambda db,ident:report)
    path='/api/v1/op/qa/runs'
    assert client.get(path+'?brief=true').status_code==401
    brief=client.get(path+'?brief=true&report_date=2026-10-21',headers=headers)
    assert brief.status_code==200 and brief.json()[0]['brief'] is True
    full=client.get(path,headers=headers).json()[0]
    detail=client.get(path+'/r',headers=headers).json()
    assert full['results'][0]['evidence']==detail['results'][0]['evidence']


def test_evaluation_brief_list_does_not_include_snapshot_and_detail_is_protected(client,monkeypatch):
    from types import SimpleNamespace
    from app.api import agent_quality
    row=SimpleNamespace(id='e',target='business',source_run='r',status='completed',version=1,created_at='2026-10-21',program={'decision':'incomplete'},snapshot={'evidence':'large'},model_score={},reviews=[])
    class FakeDB:
        # 列表先只取 id 排序，再按主键取行；模拟这两类结果，避免把整行当成 id。
        def scalars(self,statement):return [row] if statement.column_descriptions[0]['name']=='AgentEvaluation' else [row.id]
        def commit(self):pass
    db=FakeDB()
    result=agent_quality.listing(target='business',brief=True,db=db)
    assert result[0]['brief'] and 'snapshot' not in result[0]
    monkeypatch.setattr(agent_quality,'record',lambda db,ident:row)
    assert agent_quality.evaluation_detail('e',db=db)['snapshot']==row.snapshot
    assert client.get('/api/v1/op/qa/agent-quality/evaluations/e/detail').status_code==401
