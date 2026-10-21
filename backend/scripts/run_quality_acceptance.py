"""真实执行已登记用例并将步骤、请求、断言和截图持久化到 OP 报告。

从 backend 运行：python -m scripts.run_quality_acceptance --kind functional
助手真实模型：python -m scripts.run_quality_acceptance --kind assistant
仅使用本机配置；业务操作由执行器放入独立合成数据库。
"""
import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.operations import Operator
from app.models.quality import QualityRun
from app.models.tables import User
from app.quality import service
from app.quality.catalog import cases
from app.quality.worker import run_one, plan_one


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=['functional', 'assistant'], required=True)
    parser.add_argument('--username', default='platform_ops')
    parser.add_argument('--cases', nargs='+')
    parser.add_argument('--environment', default='isolated-local', choices=['isolated-local', 'native-local'])
    parser.add_argument('--report', default='data/acceptance/current-runs.json')
    args = parser.parse_args()
    if make_url(settings.database_url).host not in (None, 'localhost', '127.0.0.1'):
        raise SystemExit('验收脚本只允许本机报告数据库；禁止误连生产库')
    rows = [r for r in cases() if r['kind'] == args.kind and r['state'] == 'active' and (not args.cases or r['id'] in args.cases)]
    if not rows or (args.cases and set(args.cases) != {r['id'] for r in rows}):
        raise SystemExit('指定用例必须全部存在且与类型一致')
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == args.username))
        if not user or not db.get(Operator, user.id):
            raise SystemExit('需要既有平台运营账号，不会自动提升普通账号')
        user_id = user.id
    reports = []
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    size = 10
    for index in range(0, len(rows), size):
        batch = rows[index:index + size]
        with SessionLocal() as db:
            body = service.PlanIn(goal='三端全面验收：' + '、'.join(r['title'] for r in batch), kind=args.kind,
                                  mode='live' if args.kind == 'assistant' else 'rules', case_ids=[r['id'] for r in batch],
                                  environment_id=args.environment, max_calls=50, max_tokens=60000, timeout_seconds=1200)
            plan = service.new_plan(db, user_id, body)
            plan_id = plan.id
        planning_deadline = time.monotonic() + 130
        while True:
            with SessionLocal() as db:
                from app.models.quality import QualityPlan
                plan = db.get(QualityPlan, plan_id)
                if plan.status not in ('planning', 'planning_running'):
                    if plan.status != 'draft':
                        raise RuntimeError('真实模型规划未完成：' + str(plan.evidence.get('error', plan.status)))
                    break
            if time.monotonic() > planning_deadline:
                raise RuntimeError('等待真实规划超时：' + plan_id)
            plan_one(plan_id)
            time.sleep(0.5)
        with SessionLocal() as db:
            plan = db.get(QualityPlan, plan_id)
            if set(plan.payload['case_ids']) != {row['id'] for row in batch}:
                raise RuntimeError('规划未包含全部请求用例，未将遗漏计通过')
            service.approve(db, plan, user_id, plan.digest)
            run_id = service.create_run(db, plan, user_id, uuid4().hex).id
        deadline = time.monotonic() + 1500
        while True:
            with SessionLocal() as db:
                run = db.get(QualityRun, run_id)
                if run.status not in ('queued', 'running'):
                    report = service.run_out(db, run)
                    break
            if time.monotonic() > deadline:
                raise RuntimeError('等待报告超时：' + run_id)
            run_one(run_id)
            time.sleep(0.5)
        reports.append(report)
        path.write_text(json.dumps(reports, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        print(run_id[:8], [(r['id'], r['status']) for r in report['results']], flush=True)
    failed = [r for report in reports for r in report['results'] if r['status'] != 'passed']
    print(f'实际执行 {len(rows)} 条，通过 {len(rows) - len(failed)} 条，失败或阻塞 {len(failed)} 条；报告已入库。')
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
