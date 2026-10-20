import argparse

from app.core.config import Settings, settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--port", type=int, default=18000)
    args = parser.parse_args()
    configured = Settings(_env_file=args.env_file)
    if not configured.acceptance_environment or not configured.strict_dependencies:
        parser.error("需要独立验收环境及严格依赖配置")
    for name in Settings.model_fields:
        setattr(settings, name, getattr(configured, name))
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
