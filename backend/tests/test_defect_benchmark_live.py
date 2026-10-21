"""多场景已知缺陷基准的真实执行证据（默认跳过，避免 CI 消耗额度）。

运行：QA_LIVE_DEFECTS=1 pytest tests/test_defect_benchmark_live.py -q -s
每个场景都会跑两次真实执行（正常版 + 注入版），用例、环境、预算都写进子进程规格。
"""
import json
import os
from pathlib import Path

import pytest

from app.core.config import settings
from app.quality.agent_evaluation import calibrate_tester
from app.quality.faults import SCENARIOS


pytestmark = pytest.mark.skipif(os.environ.get("QA_LIVE_DEFECTS") != "1",
                                reason="真实缺陷基准需要 QA_LIVE_DEFECTS=1（会消耗模型额度）")


def load_qa_profile():
    """conftest 会清空 QA_CHAT_*；真实基准按本机 .env 的测试模型配置运行（只读键值，不落密钥内容）。"""
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.exists():
        return False
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("QA_CHAT_") and "=" in line:
            key, value = line.split("=", 1)
            setattr(settings, key.strip().lower(), value.strip())
    return bool(settings.qa_chat_model and settings.qa_chat_api_key_file)


def test_live_multi_scenario_defect_benchmark(tmp_path):
    if not load_qa_profile():
        pytest.skip("本机 .env 未配置 QA_CHAT_MODEL / QA_CHAT_API_KEY_FILE")
    from app.quality.worker import subprocess_job

    calibration = calibrate_tester(subprocess_job)
    path = tmp_path / "defect-benchmark-live.json"
    path.write_text(json.dumps(calibration, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = [{key: row.get(key) for key in ("variant", "case_id", "title", "expected", "observed",
                                              "detected", "false_positive", "mutation_exercised")}
               for row in calibration["scenarios"]]
    print("缺陷基准逐场景：", json.dumps(summary, ensure_ascii=False))
    assert [row["variant"] for row in calibration["scenarios"]] == [row["variant"] for row in SCENARIOS]
    assert calibration["scenarios_valid"], summary
    assert calibration["scenarios_detected"], summary
    assert not calibration["scenarios_false_positive"], summary
    for row in calibration["scenarios"]:
        assert row["mutation_exercised"], row
        assert row["detected"], row
        assert row["observed"] == "failed" and not row["false_positive"], row
        assert row["runs"][0]["observed"] == "passed", row
        assert row["runs"][0]["evidence"].get("cleanup_ok") is True and row["runs"][1]["evidence"].get("cleanup_ok") is True