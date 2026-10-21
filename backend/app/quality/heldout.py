"""不公开评测集：只发布“检查什么”和期望答案的摘要，答案本身不进代码、不进目录、不进报告。

设计要点
- HELDOUT_SUITE 只保存条目元数据与期望答案的 sha256 摘要；期望答案放在本地文件
  （默认 backend/data/heldout/expectations.json，backend/data 已在 .gitignore 中）。
- 没有本地答案文件时，条目状态是 expectation_unavailable，明确不计通过（不猜、不放水）。
- 本地答案与摘要不一致时拒绝使用，避免有人改了答案还沿用旧摘要。
- 比对逻辑是通用的“取值 + 比对”，代码里不含任何具体期望值。
- 公开视图只返回摘要；揭示答案需要 qa.approve（由 API 层强制），并在 Redis 留痕。
"""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from app.core.config import settings

DEFAULT_EXPECTATION_FILE = "data/heldout/expectations.json"

# 条目只说明“检查哪个用例的哪个断言”，具体期望值不在代码里。
HELDOUT_SUITE = (
    {'id': 'H-cart-illegal-quantity', 'case_id': 'F11', 'domain': 'cart',
     'goal': '用未公开的期望值检查购物车数量校验：非法与边界数量必须被拒绝且购物车不变',
     'probe': {'kind': 'assertion', 'name': '固定回归确实收集并执行且未跳过', 'field': 'passed'}, 'compare': 'equals'},
    {'id': 'H-order-shortage', 'case_id': 'F17', 'domain': 'orders',
     'goal': '用未公开的期望值检查库存不足时的下单行为',
     'probe': {'kind': 'assertion', 'name': '固定回归确实收集并执行且未跳过', 'field': 'passed'}, 'compare': 'equals'},
    {'id': 'H-buyer-merchant-denied', 'case_id': 'F02', 'domain': 'auth',
     'goal': '用未公开的期望值检查买家访问商家接口的权限边界',
     'probe': {'kind': 'assertion', 'name': '固定回归确实收集并执行且未跳过', 'field': 'passed'}, 'compare': 'equals'},
)
SUITE_BY_ID = {row['id']: row for row in HELDOUT_SUITE}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def expectation_hash(expect):
    return sha256(canonical(expect).encode()).hexdigest()


def expectation_path():
    return settings.backend_root / DEFAULT_EXPECTATION_FILE


def load_expectations(path=None):
    """读取本地答案文件；缺失或不完整时返回空表，绝不回退到默认值。"""
    file = Path(path) if path else expectation_path()
    if not file.exists():
        return {}
    payload = json.loads(file.read_text(encoding="utf-8"))
    answer = {}
    for entry in payload.get("entries", []):
        entry_id = entry.get("id")
        if entry_id not in SUITE_BY_ID or "expect" not in entry:
            continue
        if entry.get("expect_hash") != expectation_hash(entry["expect"]):
            raise ValueError(f"不公开评测集答案与摘要不一致：{entry_id}")
        answer[entry_id] = entry["expect"]
    return answer


def sealed_digest(path=None):
    """整份答案文件的摘要；用于报告里说明“用哪一版未公开答案评测”，但不泄露内容。"""
    file = Path(path) if path else expectation_path()
    if not file.exists():
        return None
    return sha256(file.read_bytes()).hexdigest()


def public_view(path=None):
    """公开视图：只有条目、用例与摘要，没有期望值。"""
    answers = load_expectations(path)
    return {'sealed_digest': sealed_digest(path),
            'available': bool(answers),
            'note': '答案不随代码发布；未提供本地答案时标记 expectation_unavailable，不计通过',
            'entries': [{**{key: row[key] for key in ('id', 'case_id', 'domain', 'goal')},
                         'probe': row['probe'], 'compare': row['compare'],
                         'expect_hash': expectation_hash(answers[row['id']]) if row['id'] in answers else None,
                         'status': 'sealed' if row['id'] in answers else 'expectation_unavailable'}
                        for row in HELDOUT_SUITE]}


def observed_value(result, probe):
    """从真实运行结果里取通用字段，不认识的结构直接返回 None（记为未观察）。"""
    if probe.get('kind') == 'assertion':
        for assertion in result.get('evidence', {}).get('assertions', []):
            if assertion.get('name') == probe.get('name'):
                return assertion.get(probe.get('field'))
        return None
    if probe.get('kind') == 'fact':
        return (result.get('evidence', {}).get('facts') or {}).get(probe.get('key'))
    if probe.get('kind') == 'request_status':
        for request in result.get('evidence', {}).get('requests', []):
            if str(request.get('path', '')).endswith(probe.get('path_suffix', '')):
                return request.get('status')
        return None
    return None


def score_results(results, path=None):
    """按条目比对真实结果；未提供答案或未观察到一律不计通过。"""
    answers = load_expectations(path)
    by_case = {row.get('id'): row for row in results}
    entries = []
    for row in HELDOUT_SUITE:
        entry_id = row['id']
        if entry_id not in answers:
            entries.append({'id': entry_id, 'case_id': row['case_id'], 'status': 'expectation_unavailable',
                            'passed': False, 'expect_hash': None, 'observed_digest': None})
            continue
        result = by_case.get(row['case_id'])
        expect = answers[entry_id]
        observed = observed_value(result, row['probe']) if result else None
        matched = observed is not None and ((observed == expect) if row['compare'] == 'equals' else expect in observed)
        entries.append({'id': entry_id, 'case_id': row['case_id'],
                        'status': 'matched' if matched else 'mismatched' if observed is not None else 'not_observed',
                        'passed': bool(matched), 'expect_hash': expectation_hash(expect),
                        'observed_digest': sha256(canonical(observed).encode()).hexdigest()})
    scored = [row for row in entries if row['status'] != 'expectation_unavailable']
    return {'sealed_digest': sealed_digest(path), 'available': bool(answers), 'entries': entries,
            'passed': bool(scored) and all(row['passed'] for row in scored),
            'note': 'absence of the local answer file means expectation_unavailable and never counts as pass'}


def reveal(entry_id, path=None):
    """揭示单条期望值；调用方（API）必须先校验 qa.approve 权限。"""
    if entry_id not in SUITE_BY_ID:
        raise KeyError(entry_id)
    answers = load_expectations(path)
    if entry_id not in answers:
        return {'id': entry_id, 'status': 'expectation_unavailable', 'expect': None,
                'expect_hash': None, 'source': str(Path(path) if path else expectation_path())}
    return {'id': entry_id, 'status': 'revealed', 'expect': answers[entry_id],
            'expect_hash': expectation_hash(answers[entry_id]), 'source': str(Path(path) if path else expectation_path())}


def write_expectations(entries, path=None):
    """把本地答案写成可校验的文件（仅本地使用；文件在 backend/data 下，不入仓库）。"""
    file = Path(path) if path else expectation_path()
    file.parent.mkdir(parents=True, exist_ok=True)
    payload = {'schema': 'heldout-expectations-v1',
               'entries': [{'id': entry_id, 'expect': expect, 'expect_hash': expectation_hash(expect)}
                           for entry_id, expect in entries.items()]}
    file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return file


def main():
    parser = argparse.ArgumentParser(description='不公开评测集：查看公开视图或写入本地答案文件')
    parser.add_argument('--write', help='写入本地答案文件的 JSON 内容（{"H-...": 期望值}）')
    args = parser.parse_args()
    if args.write:
        print(write_expectations(json.loads(args.write)))
        return
    print(json.dumps(public_view(), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()