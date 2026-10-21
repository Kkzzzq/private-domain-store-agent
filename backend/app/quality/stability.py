"""重要场景重复执行的稳定性统计：稳定通过 / 稳定失败（一致缺陷）/ 不稳定 / 证据不足。

只汇总真实运行记录，不推断未执行过的场景；重复次数不足时明确说“证据不足”，不当作稳定。
"""

VERDICT_LABELS = {
    'stable_pass': '重复执行稳定通过',
    'stable_fail': '重复执行稳定失败（一致的产品缺陷，不是偶发）',
    'flaky': '重复执行不稳定，结果在通过与失败之间摆动',
    'blocked': '重复执行均阻塞，缺少可用证据',
    'insufficient': '重复次数不足（证据不足），不能据此判断稳定性',
}


def summarize_case(statuses):
    passed = statuses.count('passed')
    failed = statuses.count('failed')
    blocked = sum(1 for status in statuses if status in ('blocked', 'cancelled'))
    consistent = len(set(statuses)) == 1
    if consistent and passed:
        verdict = 'stable_pass' if len(statuses) > 1 else 'insufficient'
    elif consistent and failed:
        verdict = 'stable_fail'
    elif consistent and blocked:
        verdict = 'blocked'
    elif len(statuses) < 2:
        verdict = 'insufficient'
    else:
        verdict = 'flaky'
    return {'attempts': len(statuses), 'statuses': list(statuses), 'passed': passed, 'failed': failed,
            'blocked': blocked, 'consistent': bool(consistent), 'verdict': verdict, 'note': VERDICT_LABELS[verdict]}


def summarize_runs(runs, case_kind='functional', plan_id=None):
    """runs 为同一计划（或同一批用例）的多次已完成运行报告。"""
    ordered = sorted(runs, key=lambda row: str(row.get('created_at') or row.get('id')))
    per_case = {}
    for run in ordered:
        for result in run.get('results', []):
            if result.get('kind') != case_kind:
                continue
            per_case.setdefault(result['id'], []).append(result.get('status', 'blocked'))
    cases = [{'case_id': case_id, **summarize_case(statuses)} for case_id, statuses in sorted(per_case.items())]
    attempts = len([run for run in ordered if any(result.get('kind') == case_kind for result in run.get('results', []))])
    if not cases:
        overall = 'insufficient'
    elif attempts < 2 or any(row['verdict'] == 'insufficient' for row in cases):
        overall = 'insufficient'
    elif any(row['verdict'] == 'flaky' for row in cases):
        overall = 'flaky'
    elif all(row['verdict'] == 'stable_fail' for row in cases):
        overall = 'stable_fail'
    elif all(row['verdict'] == 'blocked' for row in cases):
        overall = 'blocked'
    elif all(row['verdict'] == 'stable_pass' for row in cases):
        overall = 'stable_pass'
    else:
        overall = 'insufficient'
    return {'plan_id': plan_id, 'case_kind': case_kind, 'attempts': attempts,
            'run_ids': [run.get('id') for run in ordered], 'cases': cases, 'verdict': overall,
            'note': VERDICT_LABELS[overall],
            'scope': '只统计同一计划在本报告中真实执行过的次数；重复次数不足时判为证据不足，不当作稳定'}