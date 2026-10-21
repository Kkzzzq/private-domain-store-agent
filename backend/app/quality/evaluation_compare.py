"""评测记录跨版本对比：程序检查状态、模型维度分与人工结论的差异，并先声明可比性。

只比较同一评测对象；评分口径（rubric）、维度集合与证据版本不一致时明确标为不可比，不硬算差值。
"""

TRANSITIONS = {'passed': {'failed': '由通过变为失败（需要复查）', 'not_observed': '由通过变为未观察'},
               'failed': {'passed': '由失败变为通过（需要复查）'}, 'not_observed': {'passed': '由未观察变为通过'}}


def _checks(row):
    return {item['name']: item for item in (row.get('program') or {}).get('checks', [])}


def _dimensions(row):
    return {item['dimension']: item for item in ((row.get('model_score') or {}).get('dimensions') or [])}


def compare(baseline, candidate):
    reasons = []
    if (baseline.get('target') or '') != (candidate.get('target') or ''):
        reasons.append('评测对象不同')
    rubrics = {(row.get('snapshot') or {}).get('rubric') for row in (baseline, candidate)}
    if len(rubrics) > 1:
        reasons.append('评分口径版本不同，分数不可直接比较')
    base_dims, cand_dims = _dimensions(baseline), _dimensions(candidate)
    if set(base_dims) != set(cand_dims):
        reasons.append('参与评分的维度集合不同')
    base_checks, cand_checks = _checks(baseline), _checks(candidate)
    program = []
    for name in sorted(set(base_checks) | set(cand_checks)):
        before = (base_checks.get(name) or {}).get('status')
        after = (cand_checks.get(name) or {}).get('status')
        program.append({'name': name, 'before': before, 'after': after,
                        'transition': TRANSITIONS.get(before, {}).get(after, '未变化' if before == after else '状态变化'),
                        'changed': before != after})
    dimensions = []
    for dimension in sorted(set(base_dims) | set(cand_dims)):
        before = (base_dims.get(dimension) or {}).get('score')
        after = (cand_dims.get(dimension) or {}).get('score')
        dimensions.append({'dimension': dimension, 'before': before, 'after': after,
                           'delta': None if before is None or after is None else after - before,
                           'observed': before is not None and after is not None})
    source_changed = (baseline.get('source_run') or '') != (candidate.get('source_run') or '')
    if source_changed:
        reasons.append('来源运行不同，只能看同维度趋势，不能当作同一份证据的复测')
    return {'comparable': not reasons, 'incompatible_reasons': reasons,
            'baseline': {'id': baseline.get('id'), 'version': baseline.get('version'),
                         'source_run': baseline.get('source_run'), 'decision': (baseline.get('program') or {}).get('decision')},
            'candidate': {'id': candidate.get('id'), 'version': candidate.get('version'),
                          'source_run': candidate.get('source_run'), 'decision': (candidate.get('program') or {}).get('decision')},
            'program': program, 'dimensions': dimensions,
            'reviews': {'baseline': len(baseline.get('reviews') or []), 'candidate': len(candidate.get('reviews') or [])},
            'note': '程序检查与模型分数分别比较；未观察的维度不参与差值计算；人工复核只统计条数，不自动改判'}