import argparse
import subprocess
import sys
from types import SimpleNamespace

from app.core.config import Settings, settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--report", default="data/acceptance/wireshark-api.json")
    args = parser.parse_args()
    configured = Settings(_env_file=args.env_file)
    if not configured.acceptance_environment or not configured.strict_dependencies:
        parser.error("只允许严格隔离验收配置")
    for name in Settings.model_fields:
        setattr(settings, name, getattr(configured, name))
    from scripts.live_acceptance import Acceptance
    suite = Acceptance(SimpleNamespace(api_url="http://127.0.0.1:18003", env_file=args.env_file,
                                       phase="infrastructure", manage_api=True, report=args.report))
    code = 1
    try:
        suite.start_api()
        completed = subprocess.run([sys.executable, "-m", "scripts.check_packet_capture", "--api-url", "http://127.0.0.1:18003/api/v1/ready", "--report", args.report], timeout=45)
        code = completed.returncode
    finally:
        suite.stop_api()
        suite.http.close()
        suite.engine.dispose()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
