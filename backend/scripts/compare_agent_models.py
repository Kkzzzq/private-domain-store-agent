import argparse
import json
from pathlib import Path

from app.core.config import settings
from app.quality.catalog import ASSISTANT_CASES
from app.quality.worker import subprocess_job


def main():
    parser = argparse.ArgumentParser(description="固定合成场景真实模型对照实验，不操作实际业务数据")
    parser.add_argument("--cases", nargs="+", default=["A02", "A03", "A05", "A09", "A12", "A13"])
    args = parser.parse_args()
    if not set(args.cases).issubset(ASSISTANT_CASES):
        raise ValueError("只允许已登记助手场景")
    path = Path("data/acceptance/model-suitability-live.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    results = []
    profiles = [("glm-4-flash", "zhipu", "https://open.bigmodel.cn/api/paas/v4", settings.qa_chat_api_key_file),
                ("deepseek-flash", "deepseek", "https://api.deepseek.com", settings.cloud_api_key_file)]
    for model, style, endpoint, credential in profiles:
        settings.qa_target_chat_model = model
        settings.qa_target_chat_api_style = style
        settings.qa_target_chat_base_url = endpoint
        settings.qa_target_chat_api_key_file = credential
        for case_id in args.cases:
            result = subprocess_job({"case_id": case_id, "mode": "live", "environment_id": "isolated-local",
                                     "max_calls": 20, "max_tokens": 60000, "timeout_seconds": 90}, lambda: False)
            results.append({"tested_model": model, "id": case_id, **result})
            path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(model, case_id, result["status"], result.get("error", ""), flush=True)
    print("scope:模型适用性合成对照实验，不是全量验收，不改变服务默认模型", flush=True)


if __name__ == "__main__":
    main()
