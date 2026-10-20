import argparse
import json
import os
import re
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
import redis
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import Settings, settings


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class AcceptanceBlocked(RuntimeError):
    pass


def redact_evidence(value):
    value = re.sub(r"PS\d{8,}", "PS***", str(value))
    value = re.sub(r"地址[^。\n]*", "地址[redacted]", value)
    return re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[phone-redacted]", value)


class Acceptance:
    def __init__(self, args):
        self.args = args
        self.http = httpx.Client(base_url=args.api_url.rstrip("/"), timeout=300, trust_env=False)
        self.engine = create_engine(settings.database_url, pool_pre_ping=True)
        self.redis = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=3)
        self.prefix = secrets.token_hex(5)
        self.password = secrets.token_urlsafe(18)
        self.report = {"started_at": datetime.now(timezone.utc).isoformat(), "phase": args.phase,
                       "model_provider": settings.model_provider,
                       "model": settings.cloud_model if settings.model_provider == "cloud" else settings.ollama_model,
                       "embedding_provider": settings.embedding_provider,
                       "embedding_model": settings.embedding_model_name,
                       "embedding_dimensions": settings.cloud_embedding_dimensions if settings.embedding_provider == "zhipu" else None, "cases": []}
        self.headers = {}
        self.identities = {}
        self.process = None

    def start_api(self):
        target = urlparse(self.args.api_url)
        require(target.hostname in ("127.0.0.1", "localhost") and target.port, "托管API仅允许显式本机端口")
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", target.port))
            except OSError:
                require(False, "托管API端口已被占用，请选择独立端口")
        try:
            self.http.get("/api/v1/ready", timeout=2)
        except httpx.TransportError:
            pass
        else:
            require(False, "托管API端口已被占用，请选择独立端口")
        log_path = Path("data/acceptance") / f"api-{self.prefix}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("ab") as output:
            self.process = subprocess.Popen([sys.executable, "-m", "scripts.serve_acceptance", "--env-file", self.args.env_file,
                                             "--port", str(target.port)], stdout=output, stderr=output,
                                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.report.setdefault("managed_api_processes", []).append(self.process.pid)
        for _ in range(40):
            try:
                if self.http.get("/api/v1/ready", timeout=2).status_code == 200:
                    return
            except httpx.TransportError:
                pass
            require(self.process.poll() is None, "托管API进程提前退出")
            time.sleep(1)
        require(False, "托管API未就绪")

    def stop_api(self):
        if self.process is not None and self.process.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"], capture_output=True, timeout=15)
            else:
                self.process.terminate()
            self.process.wait(timeout=15)
        self.process = None

    def request(self, method, path, who=None, expected=200, **kwargs):
        response = self.http.request(method, "/api/v1" + path, headers=self.headers.get(who, {}), **kwargs)
        require(response.status_code == expected, f"{method} {path} HTTP {response.status_code}, expected {expected}")
        return response.json()

    def run_case(self, name, function):
        started = time.monotonic()
        print(f"RUN {name}", flush=True)
        try:
            evidence = function()
            result = {"name": name, "status": "passed", "evidence": evidence}
        except Exception as exc:
            detail = str(exc) if isinstance(exc, (AssertionError, AcceptanceBlocked)) else type(exc).__name__
            detail = re.sub(r"PS\d{8,}", "PS***", detail)
            result = {"name": name, "status": "blocked" if isinstance(exc, AcceptanceBlocked) else "failed", "detail": detail}
        result["duration_seconds"] = round(time.monotonic() - started, 3)
        self.report["cases"].append(result)
        print(f"{result['status'].upper()} {name}", flush=True)
        self.save()
        return result["status"] == "passed"

    def save(self):
        self.report["finished_at"] = datetime.now(timezone.utc).isoformat()
        expected = 7 if self.args.phase == "full" else 4
        self.report["expected_cases"] = expected
        self.report["passed"] = len(self.report["cases"]) == expected and all(case["status"] == "passed" for case in self.report["cases"])
        output = Path(self.args.report)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(self.report, ensure_ascii=False, indent=2), encoding="utf-8")

    def register(self, who, role):
        data = self.request("POST", "/auth/register", json={"username": f"live_{who}_{self.prefix}",
                            "password": self.password, "role": role, "nickname": f"验收{who}"})
        self.headers[who] = {"Authorization": "Bearer " + data["access_token"]}
        self.identities[who] = data["user"]["id"]

    def bootstrap(self):
        require(make_url(settings.database_url).database == "private_store_acceptance", "只允许独立验收数据库")
        if self.args.manage_api:
            self.start_api()
        ready = self.request("GET", "/ready")
        require(ready["acceptance_environment"] and ready["strict_dependencies"], "目标不是严格隔离验收API")
        require(ready["database"] == "mysql" and ready["redis"] == "redis", "禁止替代数据库或缓存")
        require(ready["require_llm"] and ready["require_vectors"], "目标必须禁止模型/向量降级")
        require(ready["model_provider"] == self.report["model_provider"] and ready["model"] == self.report["model"], "API与验收配置的聊天模型不一致")
        require(ready["embedding_model"] == settings.embedding_model_name and ready["embedding_provider"] == settings.embedding_provider, "API与验收配置的Embedding不一致")
        if settings.embedding_provider == "zhipu":
            require(ready["embedding_dimensions"] == settings.cloud_embedding_dimensions, "API与验收配置的向量维度不一致")
        self.report["services"] = ready
        with self.engine.connect() as connection:
            require(connection.scalar(text("SELECT DATABASE()")) == "private_store_acceptance", "数据库实际schema不匹配")
            self.report["mysql_version"] = connection.scalar(text("SELECT VERSION()"))
        require(self.redis.ping(), "Redis PING未通过")
        for who, role in (("seller", "merchant"), ("other", "merchant"), ("buyer", "customer"), ("stranger", "customer")):
            self.register(who, role)
        self.shop = self.request("GET", "/b/shop", "seller")
        self.code = self.shop["share_code"]
        self.product = self.request("POST", "/b/products", "seller", json={
            "name": "联调马克杯", "category": "杯具", "description": "独立联调商品，不修改现有店铺数据。",
            "skus": [{"spec": "单只", "price_yuan": 39, "stock": 20}]})
        self.sku = self.product["skus"][0]["id"]
        self.request("POST", f"/b/products/{self.product['id']}/status", "seller", json={"action": "on"})
        self.order = self.request("POST", f"/c/shops/{self.code}/orders", "buyer",
                                  json={"sku_id": self.sku, "quantity": 1, "address": "独立验收测试地址"})
        with self.engine.connect() as connection:
            row = connection.execute(text("SELECT user_id, shop_id, total_cents FROM orders WHERE order_no=:number"),
                                     {"number": self.order["order_no"]}).one()
            require(row.user_id == self.identities["buyer"] and row.shop_id == self.shop["id"], "MySQL订单归属不符")
            require(row.total_cents == round(self.order["total_yuan"] * 100), "MySQL金额与接口不符")
        self.request("POST", f"/c/orders/{self.order['order_no']}/pay", "buyer")
        self.request("POST", f"/b/orders/{self.order['order_no']}/ship", "seller")
        require(self.request("GET", "/b/orders", "seller")[0]["status"] == "shipped", "商家发货状态未更新")
        return {"database": "mysql", "redis": "redis", "isolated_shop_id": self.shop["id"], "sku_id": self.sku,
                "order_persisted": True, "status": "shipped"}

    def cache(self):
        path = f"/c/shops/{self.code}/products"
        self.request("GET", path)
        keys = list(self.redis.scan_iter(f"cache:c-products:{self.shop['id']}:*"))
        require(bool(keys), "真实Redis没有商品缓存")
        require(all(0 < self.redis.ttl(key) <= 60 for key in keys), "缓存TTL不符")
        self.request("PATCH", f"/b/skus/{self.sku}", "seller", json={"price_yuan": 37, "stock": 17})
        require(not list(self.redis.scan_iter(f"cache:c-products:{self.shop['id']}:*")), "修改后缓存未失效")
        rows = self.request("GET", path)
        require(rows[0]["price_from"] == 37 and rows[0]["skus"][0]["stock"] == 17, "买家缓存回填数据错误")
        self.request("POST", f"/b/products/{self.product['id']}/status", "seller", json={"action": "off"})
        require(self.request("GET", path) == [], "下架后仍可见")
        self.request("POST", f"/b/products/{self.product['id']}/status", "seller", json={"action": "on"})
        return {"redis_cache_observed": True, "invalidation": True, "price_yuan": 37, "stock": 17}

    def security(self):
        self.request("GET", "/b/products", "buyer", expected=403)
        self.request("POST", f"/c/orders/{self.order['order_no']}/pay", "stranger", expected=404)
        self.request("POST", f"/b/orders/{self.order['order_no']}/ship", "other", expected=404)
        self.request("POST", f"/c/shops/{self.code}/chat", "buyer", expected=422, json={"message": "   "})
        from app.agent.context import Actor, set_actor, reset_actor
        from app.agent.guard import execute_tool
        from sqlalchemy.orm import Session
        with Session(self.engine) as db:
            token = set_actor(db, Actor(self.identities["stranger"], "customer", "验收", self.shop["id"], self.prefix))
            try:
                require("没有找到这个订单" in execute_tool("query_orders", {"order_no": self.order["order_no"]}), "跨用户工具泄漏")
                require("身份" in execute_tool("query_orders", {"user_id": self.identities["buyer"]}), "身份参数未拒绝")
                require("无权" in execute_tool("merchant_overview", {}), "买家调用商家工具")
            finally:
                reset_actor(token)
        with self.engine.connect() as connection:
            rows = connection.execute(text("SELECT args, flag FROM agent_tool_logs WHERE session_id=:session"), {"session": self.prefix}).all()
            require(len(rows) >= 3, "MySQL中缺少工具审计")
            require(all(self.order["order_no"] not in row.args for row in rows), "审计订单号未脱敏")
        limit_key = f"agent-rate:{self.identities['stranger']}:{int(time.time() // 60)}"
        self.redis.set(limit_key, 1000000, ex=65)
        try:
            self.request("POST", f"/c/shops/{self.code}/chat", "stranger", expected=429, json={"message": "你好"})
        finally:
            self.redis.delete(limit_key)
        return {"role_checks": True, "cross_user_and_shop_checks": True, "mysql_audit_redacted": True, "real_redis_429": True}

    def model_chat(self, who, message, expected_tool, session=None, code=None):
        started = time.monotonic()
        path = "/b/chat" if who == "seller" else f"/c/shops/{code or self.code}/chat"
        data = self.request("POST", path, who, json={"message": message, "session_id": session})
        traces = []
        for trace in data["tools"]:
            safe_args = {name: value for name, value in trace["args"].items() if name in ("keyword", "limit", "sku_id", "product_id", "reason", "budget_yuan", "threshold", "quantity", "category", "keywords", "excluded_keywords", "min_price_yuan")}
            safe_args = {name: [redact_evidence(item) for item in value] if isinstance(value, list) else redact_evidence(value) if isinstance(value, str) else value for name, value in safe_args.items()}
            if trace["args"].get("order_no"):
                safe_args["order_no"] = "***" + str(trace["args"]["order_no"])[-4:]
            traces.append({"tool": trace["tool"], "args": safe_args, "result_preview": redact_evidence(trace["result"])[:1000]})
        self.report.setdefault("observed_model_calls", []).append({"question": redact_evidence(message), "role": who,
            "mode": data["mode"], "tools": traces, "answer": redact_evidence(data["answer"])[:1000],
            "model_retries": data.get("model_retries", 0),
            "duration_seconds": round(time.monotonic() - started, 3)})
        require(data["mode"] == "llm", "真实模型用例发生降级")
        require(any(trace["tool"] == expected_tool for trace in data["tools"]), f"模型未调用{expected_tool}")
        require(bool(data["answer"].strip()), "模型最终回答为空")
        require(not any(trace["result"].startswith(("工具执行失败", "参数缺失", "不支持的工具")) for trace in data["tools"]), "工具调用失败")
        return data

    def function_calling(self):
        if settings.model_provider == "ollama":
            version = httpx.get(settings.ollama_base_url.rstrip("/") + "/api/version", timeout=10, trust_env=False).json()
            self.report["ollama_version"] = version["version"]
            models = httpx.get(settings.ollama_base_url.rstrip("/") + "/api/tags", timeout=10, trust_env=False).json()["models"]
            if not any(row["name"] in (settings.ollama_model, settings.ollama_model + ":latest") for row in models):
                raise AcceptanceBlocked("真实聊天模型尚未下载就绪")
        search = self.model_chat("buyer", "搜索马克杯商品", "search_products")
        require(any(row["id"] == self.product["id"] for row in search["products"]), "搜索未返回本店商品")
        require("联调马克杯" in search["answer"], "最终回答未引用查到的商品")
        inventory = self.model_chat("buyer", f"请查询 SKU {self.sku} 的库存", "check_inventory")
        require("17" in inventory["answer"], "最终库存回答与数据库不符")
        orders = self.model_chat("buyer", f"查询我的订单 {self.order['order_no']}", "query_orders")
        require("发货" in orders["answer"], "模型订单回答状态不符")
        self.model_session = orders["session_id"]
        recommended = self.model_chat("buyer", "预算40元，推荐本店商品", "recommend_products")
        recommendation_args = next(trace["args"] for trace in recommended["tools"] if trace["tool"] == "recommend_products")
        require(recommendation_args.get("reason") == "budget" and float(recommendation_args.get("budget_yuan", -1)) == 40, "模型预算参数提取错误")
        require(bool(recommended["products"]) and all(row["price_from"] <= 40 for row in recommended["products"]), "推荐超预算或为空")
        needs = self.model_chat("buyer", "预算80元，买两件联调马克杯，请按需求推荐有货的规格并说明小计", "recommend_products")
        need_args = next(trace["args"] for trace in needs["tools"] if trace["tool"] == "recommend_products")
        require(needs["tools"][0]["tool"] == "get_store_catalog", "推荐未先了解本店商品")
        require(need_args.get("quantity") == 2 and need_args.get("budget_yuan") == 80, "多条件推荐预算或数量提取错误")
        require(bool(needs["products"]) and all(sku["stock"] >= 2 and sku["price_yuan"] * 2 <= 80 for row in needs["products"] for sku in row["skus"]), "SKU推荐超预算或缺货")
        changed = self.model_chat("buyer", "数量不变，把总预算降到70元，只要刚才同款商品；不符合就告诉我，不要放宽条件", "recommend_products", needs["session_id"])
        changed_args = next(trace["args"] for trace in changed["tools"] if trace["tool"] == "recommend_products")
        require(changed_args.get("quantity") == 2 and changed_args.get("budget_yuan") == 70, "追问未继承数量或更新预算")
        require(not changed["products"], "无匹配条件时擅自放宽或残留推荐卡")
        overview = self.model_chat("seller", "查询本店经营概览", "merchant_overview")
        require("47" in overview["answer"], "本店成交额回答不符")
        denied = self.model_chat("stranger", f"查询订单 {self.order['order_no']}", "query_orders")
        require("没有找到这个订单" in denied["tools"][0]["result"], "真实模型跨用户访问未拒绝")
        return {"provider": settings.model_provider, "tools": ["search_products", "check_inventory", "query_orders", "recommend_products", "merchant_overview"],
                "model_tool_calls_and_final_answers_verified": True, "needs_recommendation_and_redis_followup": True}

    def rag(self):
        if settings.embedding_provider == "ollama":
            models = httpx.get(settings.ollama_base_url.rstrip("/") + "/api/tags", timeout=10, trust_env=False).json()["models"]
            if not any(row["name"] in (settings.ollama_embed_model, settings.ollama_embed_model + ":latest") for row in models):
                raise AcceptanceBlocked("真实Embedding模型尚未下载就绪")
        self.headers["demo"] = {"Authorization": "Bearer " + self.request("POST", "/auth/login", json={"username": "merchant", "password": "merchant123"})["access_token"]}
        reindex = self.request("POST", "/b/knowledge/reindex", "demo")
        require(reindex["mode"] == "chroma" and reindex["chunks"] > 0, "真实Embedding建库未通过")
        cases = [("签收以后退货期限有几天？", "after_sales.md", ("7", "七", "一周")),
                 ("刻字定制品能无理由退货吗？", "after_sales.md", ("不支持", "不能", "不适用", "不可以", "不允许", "无法", "不享受")),
                 ("亚麻抱枕套应该如何清洗养护？", "product_care.md", ("冷水",))]
        evidence = []
        for question, source, conclusions in cases:
            data = self.model_chat("buyer", question, "search_knowledge", code="nanzhi")
            require(data["retrieval_mode"] == "chroma", "RAG退回关键词")
            hits = [hit for hit in data["sources"] if hit["source"] == source]
            require(bool(hits) and all(hit["heading_path"] and hit["distance"] is not None for hit in hits), "缺少语义召回来源/距离")
            require(data["sources"][0]["source"] == source, "语义检索首位不是目标知识文档")
            require(any(word in data["answer"] for word in conclusions), "模型最终结论与知识片段不符")
            evidence.append({"question": question, "source": source, "heading_path": hits[0]["heading_path"], "distance": hits[0]["distance"], "answer": data["answer"]})
        return {"mode": "chroma", "chunks": reindex["chunks"], "cases": evidence}

    def context(self):
        if not hasattr(self, "model_session"):
            raise AcceptanceBlocked("依赖的真实模型订单查询尚未通过")
        from app.agent.model import create_chat_model
        from app.services.session import compact_messages, SessionService
        session = self.model_session
        user_id = self.identities["buyer"]
        key = f"session:{user_id}:{self.shop['id']}:{session}"
        require(0 < self.redis.ttl(key) <= 604800, "真实Redis会话TTL缺失")
        state = json.loads(self.redis.get(key))
        state["messages"] += [{"role": role, "content": content} for _ in range(max(12, settings.session_max_chars // 100)) for role, content in (
            ("user", f"请记住订单 {self.order['order_no']}，我关心订单发货状态。" + "这是上下文预算验证。" * 15),
            ("assistant", "已记录关注的订单。"))]
        compacted, notice = compact_messages(state, settings.session_max_chars, create_chat_model())
        require(notice and compacted["summary_mode"] == "llm", "真实模型摘要未完成")
        require(self.order["order_no"] in compacted["summary"], "摘要丢失订单号")
        require(len(compacted["summary"]) + sum(len(row["content"]) for row in compacted["messages"]) <= settings.session_max_chars, "超出上下文预算")
        SessionService().save(user_id, self.shop["id"], session, compacted)
        env = os.environ.copy()
        env["REDIS_URL"] = settings.redis_url
        code = "from app.services.session import SessionService; import sys; s=SessionService().load(int(sys.argv[1]),int(sys.argv[2]),sys.argv[3]); assert sys.argv[4] in s['summary']; print('restored')"
        restored = subprocess.run([sys.executable, "-c", code, str(user_id), str(self.shop["id"]), session, self.order["order_no"]], env=env, capture_output=True, timeout=20)
        require(restored.returncode == 0, "另一进程未恢复Redis会话")
        if self.args.manage_api:
            self.stop_api()
            self.start_api()
        elif self.args.restart_api:
            compose = Path(__file__).resolve().parents[2] / "compose.acceptance.yml"
            restart = subprocess.run(["docker", "compose", "-f", str(compose), "restart", "api"], capture_output=True, timeout=60)
            require(restart.returncode == 0, "API重启失败")
            for _ in range(30):
                try:
                    if self.http.get("/api/v1/ready").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
        else:
            require(False, "完整A05需要--restart-api或--manage-api验证API重启；独立进程恢复已验证")
        followup = self.model_chat("buyer", "这个订单发货了吗？", "query_orders", session)
        require(followup["tools"][0]["args"].get("order_no") == self.order["order_no"], "压缩后追问订单错误")
        stranger = self.request("GET", f"/c/shops/{self.code}/sessions/{session}", "stranger")
        require(stranger["messages"] == [] and stranger["summary"] == "", "会话跨用户泄漏")
        return {"storage": "redis", "summary_mode": "llm", "summary_chars": len(compacted["summary"]), "retained_messages": len(compacted["messages"]),
                "redis_ttl_seconds": self.redis.ttl(key), "within_budget": True, "cross_process_restore": True, "api_restart": True, "followup": True}

    def faults(self):
        env = os.environ.copy()
        env.update({"STRICT_DEPENDENCIES": "false", "AGENT_REQUIRE_LLM": "false", "RAG_REQUIRE_VECTORS": "false",
                    "ACCEPTANCE_ENVIRONMENT": "false", "MODEL_PROVIDER": "ollama", "EMBEDDING_PROVIDER": "ollama"})
        temporary = Path("data") / "acceptance" / ("pytest-" + self.prefix)
        completed = subprocess.run([sys.executable, "-m", "pytest", "tests/test_live_contract.py", "tests/test_agent.py", "-q", "--basetemp", str(temporary)],
                                   capture_output=True, env=env, timeout=180)
        require(completed.returncode == 0, "故障/安全回归测试失败；请独立运行test_live_contract.py和test_agent.py查看详情")
        return {"kind": "deterministic_unit_tests_and_real_unreachable_loopback_endpoints",
                "tests": ["test_live_contract.py", "test_agent.py"], "exit_code": 0,
                "covers": ["model_unreachable", "embedding_unreachable", "redis_unreachable", "strict_no_fallback", "invalid_args", "tool_retry", "summary_interface"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--api-url", default="http://127.0.0.1:18000")
    parser.add_argument("--phase", choices=["infrastructure", "full"], default="infrastructure")
    parser.add_argument("--restart-api", action="store_true")
    parser.add_argument("--manage-api", action="store_true")
    parser.add_argument("--report", default="data/acceptance/report.json")
    args = parser.parse_args()
    configured = Settings(_env_file=args.env_file)
    if not configured.acceptance_environment or make_url(configured.database_url).database != "private_store_acceptance":
        parser.error("只允许独立验收环境，禁止操作业务库")
    for name in Settings.model_fields:
        setattr(settings, name, getattr(configured, name))
    suite = Acceptance(args)
    if suite.run_case("A01_real_mysql_business", suite.bootstrap):
        suite.run_case("A02_real_redis_cache", suite.cache)
        suite.run_case("A06_permissions_audit_rate_limit", suite.security)
        if args.phase == "full":
            suite.run_case("A03_real_function_calling", suite.function_calling)
            suite.run_case("A04_real_embedding_chroma_answer", suite.rag)
            suite.run_case("A05_real_summary_redis_restart", suite.context)
    else:
        suite.report["blocked"] = "依赖预检或业务初始化失败，其余用例未运行"
    suite.run_case("A07_fault_contracts", suite.faults)
    suite.save()
    suite.stop_api()
    suite.http.close()
    suite.engine.dispose()
    sys.exit(0 if suite.report["passed"] else 1)


if __name__ == "__main__":
    main()
