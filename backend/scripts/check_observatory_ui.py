import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import httpx
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description="独立合成服务验收三Agent工作台，不重启现有服务")
    parser.add_argument("--live", action="store_true", help="额外经UI批准一条真实Flash调试，消耗额度")
    args = parser.parse_args()
    backend = Path(__file__).resolve().parents[1]
    artifacts = backend / "data" / "acceptance" / "observatory"
    artifacts.mkdir(parents=True, exist_ok=True)
    with socket.socket() as bound:
        bound.bind(("127.0.0.1", 0))
        origin = f"http://127.0.0.1:{bound.getsockname()[1]}"
    with tempfile.TemporaryDirectory(prefix="observatory-", dir=artifacts) as directory:
        workspace = Path(directory)
        shutil.copytree(backend.parent / "web", workspace / "web", ignore=shutil.ignore_patterns("uploads"))
        environment = dict(os.environ, DATABASE_URL="sqlite:///" + (workspace / "test.db").as_posix(),
                           REDIS_URL="memory", STRICT_DEPENDENCIES="false", JWT_SECRET=uuid4().hex + uuid4().hex,
                           QA_CHILD_RUN=uuid4().hex, QA_CHILD_WORKSPACE=directory, QA_BROWSER_OP="1",
                           QA_NATIVE_ENABLED="false", AGENT_MODE="fallback", AGENT_REQUIRE_LLM="false",
                           RAG_REQUIRE_VECTORS="false", CLOUD_MODEL="deepseek-flash", CLOUD_FALLBACK_MODELS="",
                           CHROMA_PATH=(workspace / "chroma").as_posix(), PYTHONIOENCODING="utf-8")
        from app.quality.worker import stop_process
        with (workspace / "server.log").open("w", encoding="utf-8") as log:
            server = subprocess.Popen([sys.executable, "-m", "app.quality.browser_server", "--port", origin.rsplit(":", 1)[1]],
                                      cwd=backend, env=environment, stdout=log, stderr=log,
                                      creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                      start_new_session=os.name != "nt")
            try:
                with httpx.Client(base_url=origin, timeout=20) as client:
                    for _ in range(100):
                        try:
                            if client.get("/openapi.json").status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        time.sleep(0.2)
                    else:
                        raise RuntimeError("隔离验收服务未启动")
                    login = client.post("/api/v1/auth/login", json={"username": "merchant", "password": "merchant123"})
                    login.raise_for_status()
                    token = login.json()["access_token"]
                    client.headers["Authorization"] = "Bearer " + token

                    def post(path, body):
                        response = client.post("/api/v1/op/qa" + path, json=body)
                        response.raise_for_status()
                        return response.json()

                    def start(kind, case_id):
                        plan = post("/plans", {"goal": "可视化执行验收，请选择全部请求用例", "kind": kind,
                                               "mode": "live" if args.live and kind == "assistant" else "rules",
                                               "planner": "model" if args.live else "fixed", "diagnostic": not args.live,
                                               "max_tokens": 60000, "case_ids": [case_id] if isinstance(case_id, str) else case_id})
                        for _ in range(240):
                            if plan["status"] not in ("planning", "planning_running"):
                                break
                            time.sleep(0.5)
                            plan = client.get("/api/v1/op/qa/plans/" + plan["id"]).json()
                        assert plan["status"] == "draft", plan.get("evidence")
                        post(f"/plans/{plan['id']}/approve", {"digest": plan["digest"]})
                        return post("/runs", {"plan_id": plan["id"], "request_key": uuid4().hex})["id"]

                    def completed(run_id):
                        for _ in range(240):
                            response = client.get("/api/v1/op/qa/runs/" + run_id)
                            response.raise_for_status()
                            run = response.json()
                            if run["status"] not in ("queued", "running"):
                                assert run["status"] == "completed", run["summary"]
                                assert all(row["status"] == "passed" and row["evidence"]["cleanup_ok"] for row in run["results"])
                                return run
                            time.sleep(0.5)
                        raise AssertionError("隔离运行未按时完成")

                    assistant = completed(start("assistant", "A02"))
                    functional = completed(start("functional", ["F01", "F02"]))
                    assert len(functional["results"]) == 2
                    errors = []
                    live_run = None
                    with sync_playwright() as playwright:
                        edge = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
                        browser = playwright.chromium.launch(headless=True, args=["--disable-gpu"],
                                                             **({"executable_path": str(edge)} if edge.exists() else {}))
                        try:
                            context = browser.new_context(viewport={"width": 1440, "height": 1000})
                            context.add_init_script("sessionStorage.setItem('token_op'," + json.dumps(token) + ");")
                            page = context.new_page()
                            page.set_default_timeout(15000)
                            page.on("pageerror", lambda error: errors.append(str(error)))
                            for agent in ("business", "evaluator", "functional"):
                                page.goto(origin + "/op.html#/testing/" + agent)
                                expect(page.locator(".ao-grid")).to_be_visible()
                                if agent != "business":
                                    expect(page.locator(".ao-node").first).to_be_visible()
                                reference = page.locator(".qa-agent-reference")
                                expect(reference).to_have_attribute("open", "")
                                assert reference.evaluate("node=>node===node.parentElement.lastElementChild")
                                if agent == "business":
                                    tool_font = reference.locator(".qa-tool-row dt").first.evaluate("node=>getComputedStyle(node).fontFamily")
                                    model_font = reference.get_by_role("cell", name="cloud", exact=True).evaluate("node=>getComputedStyle(node).fontFamily")
                                    assert tool_font == model_font
                                if agent == "business":
                                    expect(page.get_by_text("业务对话工作台", exact=True)).to_be_visible()
                                    expect(page.get_by_label("业务问题", exact=True)).to_be_visible()
                                    assert page.get_by_role("button", name="保存调试候选", exact=True).count() == 0
                                if agent == "evaluator":
                                    expect(page.locator(".ao-node").filter(has_text="库存回答准确")).to_be_visible()
                                if agent == "functional":
                                    expect(page.locator(".ao-node").filter(has_text="call ·")).to_be_visible()
                                if agent != "business":
                                    page.locator(".ao-node").first.click()
                                    expect(page.locator(".ao-column").last.locator(".ao-json").first).to_be_visible()
                                page.screenshot(path=str(artifacts / (agent + ".png")), full_page=True)
                            if args.live:
                                page.goto(origin + "/op.html#/testing/business")
                                page.get_by_label("业务问题", exact=True).fill("请搜索本店的亚麻抱枕套")
                                page.get_by_label("业务问题", exact=True).press("Shift+Enter")
                                assert page.get_by_label("业务问题", exact=True).input_value().endswith("\n")
                                page.get_by_label("业务问题", exact=True).fill("请搜索本店的亚麻抱枕套")
                                with page.expect_response(lambda response: response.url.endswith("/op/qa/business-debug") and response.request.method == "POST", timeout=100000) as started:
                                    page.get_by_label("业务问题", exact=True).press("Enter")
                                assert started.value.status == 200
                                dialogue = started.value.json()
                                assert dialogue["status"] == "completed", dialogue["evidence"].get("error")
                                live_run = {"id": dialogue["id"], "results": [{"evidence": dialogue["evidence"]}]}
                                expect(page.locator(".ao-node").filter(has_text="最终回答")).to_be_visible()
                                budgets = [row["evidence"]["budget"] for row in live_run["results"]]
                                assert all(model["model"] == "deepseek-flash" for budget in budgets for model in budget["models"])
                                page.get_by_label("业务问题", exact=True).fill("查询SKU 1的库存")
                                with page.expect_response(lambda response: response.url.endswith("/op/qa/business-debug") and response.request.method == "POST", timeout=100000) as second:
                                    page.get_by_role("button", name="发送到合成助手", exact=True).click()
                                replay = second.value.json()
                                assert replay["status"] == "completed", replay["evidence"].get("error")
                                chats = [row for row in replay["evidence"]["requests"] if row["path"].endswith("/chat")]
                                assert len(chats) == 2 and chats[0]["output"]["session_id"] == chats[1]["output"]["session_id"]
                                page.screenshot(path=str(artifacts / "business-live.png"), full_page=True)
                                page.goto(origin + "/op.html#/testing/functional")
                                page.get_by_role("button", name="新增功能用例", exact=True).click()
                                dialog = page.locator("dialog[open]")
                                dialog.get_by_label("功能用例名称", exact=True).fill("自建商品与匿名购物车校验")
                                dialog.get_by_role("button", name="增加业务步骤", exact=True).click()
                                dialog.get_by_label("业务动作", exact=True).nth(1).select_option("cart")
                                dialog.get_by_label("步骤身份", exact=True).nth(1).select_option("anonymous")
                                dialog.get_by_label("预期HTTP状态", exact=True).nth(1).fill("401")
                                with page.expect_response(lambda response: response.url.endswith("/op/qa/cases") and response.request.method == "POST") as saved:
                                    dialog.get_by_role("button", name="保存功能候选", exact=True).click()
                                assert saved.value.status == 201
                                custom = saved.value.json()
                                assert custom["kind"] == "functional" and custom["state"] == "candidate"
                                post(f"/cases/{custom['id']}/approve", {"digest": custom["revision_digest"]})
                                custom_run = completed(start("functional", custom["id"]))
                                assert custom_run["diagnostic"] is False
                                assert custom_run["planning"]["budget"]["calls"] > 0
                                assert all(row["model"] == "glm-4-flash" for row in custom_run["planning"]["budget"]["models"])
                                page.goto(origin + "/op.html#/testing/overview")
                                expect(page.get_by_text("进入业务对话", exact=True)).to_be_visible()
                                expect(page.locator(".qa-agent-grid")).to_contain_text("自建用例")
                                page.screenshot(path=str(artifacts / "overview-live.png"), full_page=True)
                                page.goto(origin + "/op.html#/testing/functional")
                            page.route("**/api/v1/op/qa/business-debug", lambda route: route.fulfill(status=405, content_type="application/json", body='{"detail":"Method Not Allowed"}'))
                            page.goto(origin + "/op.html#/testing/business")
                            expect(page.get_by_text("后端尚未加载业务对话接口，需要正常重启8000后端后再刷新。当前未调用模型。", exact=True)).to_be_visible()
                            expect(page.get_by_role("button", name="发送到合成助手", exact=True)).to_be_disabled()
                            assert not errors, errors
                            page.set_viewport_size({"width": 620, "height": 900})
                            assert page.locator(".ao-grid").evaluate("node=>getComputedStyle(node).gridTemplateColumns.split(' ').length") == 1
                        finally:
                            browser.close()
                    report = {"status": "passed", "assistant_run": assistant["id"], "functional_run": functional["id"],
                              "live_run": live_run["id"] if live_run else None, "page_errors": errors,
                              "live_budget": [row["evidence"]["budget"] for row in live_run["results"]] if live_run else [],
                              "functional_case_count": len(functional["results"]),
                              "custom_functional_run": custom_run["id"] if args.live else None,
                              "scope": "真实GLM规划 + 实际业务Agent模型，独立合成API/worker/浏览器" if args.live else "确定性平台UI控件诊断，不是Agent真实模型验收"}
                    (artifacts / ("report-live.json" if args.live else "report.json")).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(json.dumps(report, ensure_ascii=False))
            finally:
                stop_process(server)


if __name__ == "__main__":
    main()
