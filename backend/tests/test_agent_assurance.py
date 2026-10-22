from unittest.mock import patch

import pytest

from app.quality.agent_evaluation import calibrate_tester, program_checks
from app.quality.catalog import cases
from app.quality.feature_catalog import catalog
from app.quality.heldout import HELDOUT_SUITE, score_results, write_expectations
from app.quality.service import PlanIn
from app.services.product_search import search_rows


@pytest.mark.parametrize('status', ['blocked', 'failed', 'cancelled', 'passed'])
def test_business_program_cannot_override_source_status(status):
    report = {'results': [{'id': 'A02', 'kind': 'assistant', 'status': status, 'evidence': {
        'cleanup_ok': True, 'assertions': [{'passed': True}],
        'requests': [{'path': '/chat', 'input': {'message': '查询'}, 'output': {'answer': '回答', 'tools': ['search']}}]}}],
        'target': {'case_ids': ['A02'], 'case_snapshots': [{'id': 'A02', 'kind': 'assistant'}]}}
    assert program_checks(report, 'business')['decision'] == ('passed' if status == 'passed' else 'failed')


def heldout_results():
    return [{'id': row['case_id'], 'status': 'passed', 'evidence': {'suite': {'reports': [
        {'node': row['probe']['node'], 'stage': stage, 'outcome': 'passed'} for stage in ('setup', 'call', 'teardown')]}}}
        for row in HELDOUT_SUITE]


def test_hidden_suite_requires_all_answers_and_business_nodes(tmp_path):
    path = write_expectations({row['id']: True for row in HELDOUT_SUITE}, tmp_path / 'answers.json')
    results = heldout_results()
    assert score_results(results, path)['passed']
    results[0]['status'] = 'failed'
    results[0]['evidence']['suite']['reports'][1]['outcome'] = 'failed'
    results[0]['evidence']['assertions'] = [{'name': '固定回归确实收集并执行且未跳过', 'passed': True}]
    assert not score_results(results, path)['passed']
    assert score_results(results[:1], path)['decision'] == 'failed'
    partial = write_expectations({HELDOUT_SUITE[0]['id']: True}, tmp_path / 'partial.json')
    result = score_results(heldout_results(), partial)
    assert not result['passed'] and result['missing_count'] == 2 and result['decision'] == 'incomplete'
    missing = heldout_results()
    missing[0]['evidence']['suite']['reports'] = []
    assert score_results(missing, path)['entries'][0]['status'] == 'not_observed'
    assert score_results(missing, path)['decision'] == 'incomplete'


@pytest.mark.parametrize('kind,ids', [('functional', ['F01']), ('joint', ['A02', 'F01'])])
def test_formal_functional_execution_requires_actual_agent_driver(kind, ids):
    with pytest.raises(ValueError, match='模型工具编排'):
        PlanIn(goal='真实功能执行验证', kind=kind, case_ids=ids, functional_driver=False)
    assert PlanIn(goal='真实功能执行验证', kind=kind, case_ids=ids).functional_driver
    assert not PlanIn(goal='固定平台诊断验证', kind=kind, case_ids=ids, diagnostic=True, functional_driver=False).functional_driver


def test_all_registered_functional_tools_are_mapped_without_hiding_op_scope():
    snapshot = catalog()
    mapped = {tool['case_id'] for feature in snapshot['features'] for tool in feature['tools']}
    assert {row['id'] for row in cases() if row['kind'] == 'functional' and row['state'] == 'active'} <= mapped
    platform = next(feature for feature in snapshot['features'] if feature['id'] == 'platform')
    assert platform['sides'] == ['OP'] and platform['pages'] == ['/op.html']


def test_custom_functional_actions_join_only_their_actual_domains():
    row = {'id': 'U-custom', 'kind': 'functional', 'state': 'active', 'title': '匿名购物车验证',
           'adapter': 'declarative_functional', 'definition': {'steps': [
               {'action': 'catalog'}, {'action': 'cart'}]}}
    snapshot = catalog([row])
    mapped = {feature['id'] for feature in snapshot['features'] if any(tool['case_id'] == row['id'] for tool in feature['tools'])}
    assert mapped == {'products', 'cart'}


def test_judge_projects_only_static_catalog_and_keeps_original_evidence():
    import json
    from app.quality.agent_evaluation import snapshot_for
    source = 'static implementation' * 10000
    read = {'tool': 'read_bc_features', 'args': {}, 'result': {'contracts': [{
        'id': 'cart', 'name': '购物车', 'rule': '拒绝非法数量', 'endpoints': [{
            'id': 'GET /cart', 'source_hash': 'hash', 'implementation': source}]}]}}
    report = {'target': {'case_ids': ['F11']}, 'results': [{'id': 'F11', 'kind': 'functional', 'status': 'passed',
        'evidence': {'functional_agent': {'tools': [read], 'conversation': [
            {'role': 'user', 'content': '验证购物车'},
            {'role': 'tool', 'name': 'read_bc_features', 'content': read['result']},
            {'role': 'assistant', 'content': '真实回答不可截断'}]}}}]}
    snapshot = snapshot_for(report, 'functional')
    assert snapshot['source']['results'][0]['evidence']['functional_agent']['tools'][0]['result']['contracts'][0]['endpoints'][0]['implementation'] == source
    assert len(json.dumps(snapshot['evidence'])) < 5000
    conversation = snapshot['evidence']['F11:conversation']
    assert conversation[-1]['content'] == '真实回答不可截断'
    assert 'projection_note' in conversation[1]['content']


def test_calibration_stops_before_next_model_execution_after_revocation():
    executed = []
    def cancelled():
        return bool(executed)
    def executor(spec, callback):
        assert callback is cancelled
        executed.append(spec)
        return {'status': 'passed', 'cleanup_ok': True, 'functional_agent': {'tools': []}}
    with pytest.raises(ValueError, match='撤销'):
        calibrate_tester(executor, cancelled)
    assert len(executed) == 1


def test_literal_and_semantic_skus_merge_without_duplicates():
    rows = [{'id': ident, 'name': name, 'category': '餐具', 'description': '饮水用', 'tags': [],
             'skus': [{'id': ident * 10, 'spec': '白色', 'parameters': {}}]}
            for ident, name in [(1, '马克杯'), (2, '陶瓷饮水器')]]
    with patch('app.services.product_search.semantic_matches', return_value={(1, 10): .1, (2, 20): .2}) as semantic:
        result = search_rows('马克杯', rows, None, None)
    assert semantic.called and [row['id'] for row in result] == [1, 2]
    assert len(result[0]['skus']) == 1
    with patch('app.services.product_search.semantic_matches', side_effect=RuntimeError('embedding unavailable')):
        assert search_rows('马克杯', rows, None, None)[0]['id'] == 1
        with pytest.raises(RuntimeError):
            search_rows('没有字面命中', rows, None, None)


def test_benchmark_revocation_closes_state_and_releases_lane(client, monkeypatch):
    from test_quality import operator
    from app.core.config import settings
    from app.db.session import SessionLocal
    from app.models.agent_evaluation import AgentEvaluation
    from app.models.quality import QualityGrant
    from app.quality import queue
    headers, user_id = operator(client)
    monkeypatch.setattr(settings, 'qa_chat_model', 'test-model')
    monkeypatch.setattr(settings, 'qa_chat_api_key_file', 'not-read-by-this-test')
    with SessionLocal() as db:
        db.add(AgentEvaluation(id='assurance', created_by=user_id, target='functional', source_run='source',
                               snapshot={'source_digest': 'digest'}, program={'checks': []}))
        db.commit()
    def revoked_execution(executor, cancelled):
        with SessionLocal() as db:
            db.get(QualityGrant, user_id).capabilities = []
            db.commit()
        assert cancelled()
        raise ValueError('执行授权已撤销')
    monkeypatch.setattr('app.quality.agent_evaluation.calibrate_tester', revoked_execution)
    response = client.post('/api/v1/op/qa/agent-quality/evaluations/assurance/defect-benchmark', headers=headers)
    assert response.status_code == 409
    with SessionLocal() as db:
        assert db.get(AgentEvaluation, 'assurance').status == 'blocked'
    token = queue.acquire('defect-benchmark')
    assert token
    queue.release('defect-benchmark', token)


def test_active_benchmark_is_not_expired_as_a_short_model_score(client):
    from datetime import timedelta
    from test_quality import operator
    from app.api.agent_quality import expire_stale_scores
    from app.db.session import SessionLocal
    from app.models.agent_evaluation import AgentEvaluation
    from app.models.tables import utcnow
    _, user_id = operator(client)
    with SessionLocal() as db:
        for operation in ('defect_benchmark', 'model_score'):
            db.add(AgentEvaluation(id=operation, created_by=user_id, target='functional', source_run='source',
                                   snapshot={}, program={}, status='scoring', model_score={
                                       'status': 'scoring', 'operation': operation,
                                       'started_at': (utcnow()-timedelta(minutes=10)).isoformat()}))
        db.commit()
        expire_stale_scores(db, 'functional')
        assert db.get(AgentEvaluation, 'defect_benchmark').status == 'scoring'
        assert db.get(AgentEvaluation, 'model_score').status == 'blocked'


def test_disabling_operator_account_revokes_active_quality_capabilities(client):
    from test_quality import operator
    from app.db.session import SessionLocal
    from app.models.governance import AccountRestriction
    from app.quality.service import capabilities
    _, user_id = operator(client)
    with SessionLocal() as db:
        assert 'qa.functional.run' in capabilities(db, user_id)
        db.add(AccountRestriction(user_id=user_id, disabled=True, reason='隔离撤权测试'))
        db.commit()
        assert not capabilities(db, user_id)
