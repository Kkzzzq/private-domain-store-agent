import argparse
import json
from pathlib import Path

from app.quality.worker import subprocess_job


def main():
    parser = argparse.ArgumentParser(description="只在独立子进程合成环境验收OP质量执行器")
    parser.add_argument("--cases", nargs="+", default=["A01", "A02", "A04", "A07", "A08", "A13", "A14", "A29", "A30", "A38", "A39", "F01", "F08", "F29"])
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--planner", action="store_true")
    parser.add_argument("--environment", choices=["isolated-local", "native-local"], default="isolated-local")
    parser.add_argument("--max-calls", type=int, default=12)
    parser.add_argument("--max-tokens", type=int, default=60000)
    parser.add_argument("--report", default="data/acceptance/quality-executor.json")
    args = parser.parse_args()
    if args.planner:
        result = subprocess_job({"goal": "验证业务助手具体SKU库存和跨用户订单权限", "kind": "assistant", "case_ids": ["A02", "A13"], "mode": "live", "max_calls": 5, "max_tokens": 15000, "timeout_seconds": 90}, lambda: False, planner=True)
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("planner", result["status"], result.get("error", ""))
        raise SystemExit(0 if result["status"] == "draft" and result.get("tools") else 1)
    results = []
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    for case_id in args.cases:
        result = subprocess_job({"case_id": case_id, "environment_id": args.environment, "mode": "live" if args.live and case_id.startswith("A") else "rules", "max_calls": args.max_calls, "max_tokens": args.max_tokens, "timeout_seconds": 90}, lambda: False)
        results.append({"id": case_id, **result})
        path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(case_id, result["status"], result.get("error", ""), flush=True)
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    raise SystemExit(0 if all(row["status"] == "passed" and row.get("cleanup_ok") for row in results) else 1)


if __name__ == "__main__":
    main()
