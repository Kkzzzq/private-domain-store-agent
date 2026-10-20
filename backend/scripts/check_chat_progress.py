import argparse
import json
import time
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description="测试本机演示助手的真实阶段响应，不输出令牌或工具数据")
    parser.add_argument("--message", default="抱枕有货吗")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    report = {"events": [], "success": False}
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=240) as client:
        auth = client.post("/api/v1/auth/login", json={"username": "alice", "password": "alice123"})
        auth.raise_for_status()
        headers = {"Authorization": "Bearer " + auth.json()["access_token"]}
        started = time.perf_counter()
        with client.stream("POST", "/api/v1/c/shops/nanzhi/chat/stream", headers=headers,
                           json={"message": args.message}) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.strip():
                    continue
                event = json.loads(line)
                elapsed = round((time.perf_counter() - started) * 1000)
                report.setdefault("first_event_ms", elapsed)
                if event["type"] == "preview":
                    report.setdefault("first_preview_ms", elapsed)
                safe = {key: event[key] for key in ("type", "stage", "tool", "step", "duration_ms", "elapsed_ms", "status") if key in event}
                safe["client_elapsed_ms"] = elapsed
                report["events"].append(safe)
                print(safe, flush=True)
                if event["type"] == "result":
                    data = event["data"]
                    report.update(success=data["mode"] == "llm", mode=data["mode"], intent=data["intent"],
                                  tools=[item["tool"] for item in data["tools"]], retries=data["model_retries"],
                                  total_ms=elapsed)
                elif event["type"] == "error":
                    report["total_ms"] = elapsed
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not report["success"]:
        raise SystemExit("真实模型请求未完成，报告已保留")


if __name__ == "__main__":
    main()
