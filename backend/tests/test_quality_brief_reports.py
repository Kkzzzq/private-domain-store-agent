import json
from app.quality.report_batches import brief_report


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
    db=SimpleNamespace(scalars=lambda _: [row],commit=lambda:None)
    result=agent_quality.listing(target='business',brief=True,db=db)
    assert result[0]['brief'] and 'snapshot' not in result[0]
    monkeypatch.setattr(agent_quality,'record',lambda db,ident:row)
    assert agent_quality.evaluation_detail('e',db=db)['snapshot']==row.snapshot
    assert client.get('/api/v1/op/qa/agent-quality/evaluations/e/detail').status_code==401
