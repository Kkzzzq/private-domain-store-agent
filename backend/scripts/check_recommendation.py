import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from app.core.config import Settings, settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--report", default="data/acceptance/recommendation-live.json")
    args = parser.parse_args()
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    configured = Settings(_env_file=args.env_file)
    if configured.model_provider != "cloud":
        parser.error("需要真实云端模型配置")
    database = Path("data/acceptance") / ("recommendation-" + uuid.uuid4().hex + ".db")
    database.parent.mkdir(parents=True, exist_ok=True)
    configured.database_url = "sqlite:///" + database.as_posix()
    configured.redis_url = "memory"
    configured.strict_dependencies = False
    configured.agent_mode = "auto"
    configured.agent_require_llm = True
    configured.agent_rate_limit_per_minute = 120
    for name in Settings.model_fields:
        setattr(settings, name, getattr(configured, name))
    from app.agent.assistant import assistant
    from app.agent.context import Actor, reset_actor, set_actor
    from app.agent.model import create_chat_model
    from app.db.base import Base
    from app.db.session import engine, SessionLocal
    from app.models.tables import Product, Shop, Sku, User
    Base.metadata.create_all(engine)
    observed_models = []

    class ObservedModel:
        def __init__(self, inner):
            self.inner = inner
        def bind_tools(self, tools):
            return ObservedModel(self.inner.bind_tools(tools))
        def invoke(self, messages):
            result = self.inner.invoke(messages)
            observed_models.append(result.response_metadata.get("model"))
            report.setdefault("model_calls", []).append({"tools": result.tool_calls, "answer": result.content})
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            return result

    report = {"at": datetime.now(timezone.utc).isoformat(), "scope": "real_cloud_model_real_isolated_sqlite_tools_memory_session_no_mysql_redis_rag_acceptance", "cases": []}
    with SessionLocal() as db:
        merchant = User(username="fixture_merchant", password_hash="disabled-fixture", role="merchant", nickname="测试商家")
        buyer = User(username="fixture_buyer", password_hash="disabled-fixture", role="customer", nickname="测试买家")
        db.add_all([merchant, buyer])
        db.flush()
        shop = Shop(merchant_id=merchant.id, name="隔离推荐测试店", share_code="recommend_fixture")
        db.add(shop)
        db.flush()
        db.add_all([
            Product(shop_id=shop.id, name="陶瓷日用杯", category="杯具", description="陶瓷饮水杯，蓝色和白色可选，无礼盒。", status="on",
                    skus=[Sku(spec="蓝色单只", price_cents=4500, stock=10), Sku(spec="白色单只", price_cents=3900, stock=10), Sku(spec="低价缺货", price_cents=500, stock=0)]),
            Product(shop_id=shop.id, name="香薰玻璃杯", category="香薰", description="香薰玻璃容器。", status="on", skus=[Sku(spec="标准", price_cents=2000, stock=20)]),
            Product(shop_id=shop.id, name="木制收纳碗", category="收纳", description="木制收纳用品。", status="on", skus=[Sku(spec="原木", price_cents=3000, stock=10)]),
        ])
        db.commit()
        token = set_actor(db, Actor(buyer.id, buyer.role, buyer.username, shop.id))
        try:
            model = ObservedModel(create_chat_model())
            session = None
            questions = ["预算100元，买两只陶瓷杯送朋友，不要香薰。请先了解本店商品，再按要求推荐，说明依据和小计。",
                         "不要蓝色了，换白色，数量和预算不变。"]
            for question in questions:
                result = assistant.chat(user_id=buyer.id, shop_id=shop.id, session_id=session, message=question, llm=model)
                session = result["session_id"]
                traces = result["tools"]
                assert traces[0]["tool"] == "get_store_catalog"
                recommendation = next(trace for trace in traces if trace["tool"] == "recommend_products")
                assert result["mode"] == "llm" and result["products"]
                assert recommendation["args"].get("quantity") == 2
                assert recommendation["args"].get("budget_yuan") == 100
                assert all(row["name"] == "陶瓷日用杯" for row in result["products"])
                assert all(sku["stock"] >= 2 and sku["price_yuan"] * 2 <= 100 for row in result["products"] for sku in row["skus"])
                if len(report["cases"]) == 1:
                    assert all("白色" in sku["spec"] for row in result["products"] for sku in row["skus"])
                report["cases"].append({"question": question, "tools": traces, "products": result["products"], "answer": result["answer"], "passed": True})
            report["passed"] = True
        except Exception as error:
            report["passed"] = False
            report["error_type"] = type(error).__name__
        finally:
            reset_actor(token)
    report["actual_models"] = sorted({name for name in observed_models if name})
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "completed_cases": len(report["cases"]), "actual_models": report["actual_models"], "error_type": report.get("error_type")}, ensure_ascii=False))
    engine.dispose()
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
