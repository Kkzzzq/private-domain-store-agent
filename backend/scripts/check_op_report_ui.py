"""隔离验收：报告列表命名、逐项核验合并与缺失值表达、功能测试页布局与自由需求受理面板。

不重启也不读写现有 8000/8001 服务：独立合成 SQLite / 内存 Redis / 随机端口。
运行记录使用已保存的真实功能测试报告（agent-quality-v2-persisted-run.json）；
重复断言与缺失对照值使用明确标注的渲染夹具（合成 fixture），不冒充真实测试结果。
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import httpx
from playwright.sync_api import sync_playwright, expect


def assistant_fixture():
    """渲染夹具：2 条同名同值断言 + 1 条无独立对照值的流程断言，用于检查展示规则。"""
    return {"id": "a08" + "f" * 29, "plan_id": "0" * 32, "kind": "assistant", "mode": "rules",
            "status": "completed", "diagnostic": True,
            "name": "2026-10-21 01:03 测试报告（1条用例） · 6a48f1",
            "planning": {"planner": "fixed", "budget": {}, "tools": []}, "cancel_requested": False,
            "created_at": "2026-10-20T17:03:00", "started_at": "2026-10-20T17:03:01", "finished_at": "2026-10-20T17:03:20",
            "summary": {"decision": "eligible"}, "target": {"environment_id": "isolated-local",
                "fixture_version": "seed-isolated-v1", "target_revision": "f" * 40, "case_ids": ["A08"],
                "case_snapshots": [{"id": "A08", "title": "不可售商品排除"}]},
            "results": [{"id": "A08", "kind": "assistant", "status": "passed", "doc": {"title": "不可售商品排除", "steps": ["以商家身份登录", "把本店全部商品状态改为下架并确认每次返回 200", "买家发送“推荐热销商品”"], "expected": ["推荐卡为空，不可售商品不作为可购推荐"]},
                "evidence": {"cleanup_ok": True, "requests": [{"method": "POST", "path": "/api/v1/c/shops/nanzhi/chat", "status": 200, "input": {"message": "推荐热销商品"}, "output": {"answer": "抱歉，目前本店暂时没有在售且有的商品，无法为您推荐热销商品。", "mode": "llm"}}],
                    "assertions": [
                        {"name": "合成测试身份 alice（买家）登录成功", "passed": True, "expected": {"identity": "alice", "expected_status": 200}, "actual": 200},
                        {"name": "仅隔离数据完成下架准备", "passed": True, "expected": {"准备": "本店全部合成商品在隔离数据内下架", "商品数": 4}, "actual": {"下架成功": 4, "未成功": []}},
                        {"name": "仅隔离数据完成下架准备", "passed": True, "expected": {"准备": "本店全部合成商品在隔离数据内下架", "商品数": 4}, "actual": {"下架成功": 4, "未成功": []}},
                        {"name": "流程前提：商家会话可读", "passed": True, "expected": None, "actual": None}]}}]}


def main():
    parser = argparse.ArgumentParser(description="OP 报告与布局隔离验收")
    parser.add_argument("--live-chain", action="store_true", help="额外跑 需求受理→计划→审批→运行→功能Agent调用工具 的真实全链路（消耗少量额度）")
    parser.add_argument("--live-intake", action="store_true", help="只额外跑一次真实模型自由需求受理（消耗少量额度）")
    parser.add_argument("--defect-benchmark", action="store_true", help="额外跑多场景已知缺陷基准：4 个场景 × 正常/注入 = 8 次真实 Agent 执行（消耗额度）")
    parser.add_argument("--keep", action="store_true", help="保留工作目录便于排查")
    args = parser.parse_args()
    backend = Path(__file__).resolve().parents[1]
    artifacts = backend / "data" / "acceptance" / "op-report-ui"
    artifacts.mkdir(parents=True, exist_ok=True)
    real_run = json.loads((backend / "data/acceptance/agent-quality-v2-persisted-run.json").read_text(encoding="utf-8"))
    fixture = assistant_fixture()
    results = {"checks": [], "diagnostics": {}}

    def check(name, condition, detail=""):
        results["checks"].append({"name": name, "passed": bool(condition), "detail": str(detail)[:600]})
        assert condition, f"{name} :: {detail}"

    with socket.socket() as bound:
        bound.bind(("127.0.0.1", 0))
        origin = f"http://127.0.0.1:{bound.getsockname()[1]}"
    folder = tempfile.mkdtemp(prefix="op-report-ui-", dir=artifacts)
    workspace = Path(folder)
    shutil.copytree(backend.parent / "web", workspace / "web", ignore=shutil.ignore_patterns("uploads"))
    environment = dict(os.environ, DATABASE_URL="sqlite:///" + (workspace / "test.db").as_posix(),
                       REDIS_URL="memory", STRICT_DEPENDENCIES="false", JWT_SECRET=uuid4().hex + uuid4().hex,
                       QA_CHILD_RUN=uuid4().hex, QA_CHILD_WORKSPACE=folder, QA_BROWSER_OP="1",
                       QA_NATIVE_ENABLED="false", AGENT_MODE="fallback", AGENT_REQUIRE_LLM="false",
                       RAG_REQUIRE_VECTORS="false", CLOUD_MODEL="deepseek-flash", CLOUD_FALLBACK_MODELS="",
                       CHROMA_PATH=(workspace / "chroma").as_posix(), PYTHONIOENCODING="utf-8")
    with (workspace / "server.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen([sys.executable, "-m", "app.quality.browser_server", "--port", origin.rsplit(":", 1)[1]],
                                  cwd=backend, env=environment, stdout=log, stderr=log,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                  start_new_session=os.name != "nt")
    try:
        for _ in range(120):
            try:
                if httpx.get(origin + "/openapi.json", timeout=5).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        else:
            raise RuntimeError("隔离验收服务未启动")
        login = httpx.post(origin + "/api/v1/auth/login", json={"username": "merchant", "password": "merchant123"})
        results["diagnostics"]["isolated_ready"] = httpx.get(origin + "/api/v1/ready").json()
        results["diagnostics"]["isolated_login"] = {"status": login.status_code, "body": login.text[:200],
                                                    "db_env": os.environ.get("DATABASE_URL", "未设置")}
        login.raise_for_status()
        token = login.json()["access_token"]

        def session():
            client = httpx.Client(base_url=origin, timeout=60)
            fresh = client.post("/api/v1/auth/login", json={"username": "merchant", "password": "merchant123"})
            results["diagnostics"].setdefault("session_logins", []).append({"status": fresh.status_code, "body": fresh.text[:160]})
            fresh.raise_for_status()
            client.headers["Authorization"] = "Bearer " + fresh.json()["access_token"]
            return client

        if args.live_chain:
            # 真实全链路：自由需求 → 受理判断 → 提交计划 → 真实模型规划 → 审批 → 运行 → 功能Agent读目录并调用工具执行。
            operator = session()
            intake = operator.post("/api/v1/op/qa/functional-intake", timeout=180,
                                   json={"requirement": "验证 C 端购物车修改数量超过库存会被拒绝，且购物车金额与库存保持不变",
                                         "environment_id": "isolated-local"})
            check("全链路：真实模型受理返回 201", intake.status_code == 201, intake.text[:300])
            payload = intake.json().get("plan")
            check("全链路：受理产出可提交计划", bool(payload and payload.get("case_ids")), json.dumps(intake.json(), ensure_ascii=False)[:300])
            plan = operator.post("/api/v1/op/qa/plans", json=payload).json()
            for _ in range(300):
                if plan["status"] not in ("planning", "planning_running"):
                    break
                time.sleep(0.5)
                plan = operator.get("/api/v1/op/qa/plans/" + plan["id"]).json()
            results["diagnostics"]["chain_plan"] = {"id": plan["id"], "status": plan["status"],
                                                    "evidence_status": (plan.get("evidence") or {}).get("status"),
                                                    "budget": (plan.get("evidence") or {}).get("budget"),
                                                    "tools": [row.get("tool") for row in (plan.get("evidence") or {}).get("tools", [])]}
            check("全链路：计划经真实模型规划为待审批", plan["status"] == "draft", json.dumps(plan.get("evidence"), ensure_ascii=False)[:400])
            approved = operator.post(f"/api/v1/op/qa/plans/{plan['id']}/approve", json={"digest": plan["digest"]})
            check("全链路：计划可批准", approved.status_code == 200, approved.text[:200])
            run_id = operator.post("/api/v1/op/qa/runs", json={"plan_id": plan["id"], "request_key": uuid4().hex}).json()["id"]
            run = None
            for _ in range(600):
                response = operator.get("/api/v1/op/qa/runs/" + run_id)
                if response.status_code in (401, 500):        # 子进程重启或临时锁；重新登录后继续，不改被测代码
                    operator = session()
                    continue
                response.raise_for_status()
                run = response.json()
                if run["status"] not in ("queued", "running"):
                    break
                time.sleep(0.5)
            check("全链路：运行结束", bool(run) and run["status"] in ("completed", "failed", "blocked", "cancelled"),
                  json.dumps(run, ensure_ascii=False)[:300] if run else "运行未结束")
            check("全链路：功能测试用例真实通过", run["status"] == "completed" and run["results"][0]["status"] == "passed",
                  json.dumps(run, ensure_ascii=False)[:400])
            evidence = run["results"][0]["evidence"]
            calls = [row.get("tool") for row in (evidence.get("functional_agent") or {}).get("tools", [])]
            results["diagnostics"]["chain_run"] = {"id": run["id"], "status": run["status"], "agent_tools": calls,
                                                   "assertions": evidence.get("assertions"), "cleanup_ok": evidence.get("cleanup_ok"),
                                                   "budget": evidence.get("budget"), "planning": run.get("planning")}
            check("全链路：Agent 先读功能目录再调用执行工具", calls == ["read_bc_features", "execute_registered_case"], str(calls))
            check("全链路：有真实硬断言且隔离清理完成",
                  bool(evidence.get("assertions")) and all(row["passed"] for row in evidence["assertions"]) and evidence.get("cleanup_ok") is True,
                  json.dumps(evidence.get("assertions"), ensure_ascii=False)[:300])
            check("全链路：规划与执行都有真实模型计量",
                  (run.get("planning") or {}).get("budget", {}).get("calls", 0) > 0 and evidence.get("budget", {}).get("calls", 0) > 0,
                  json.dumps({"planning": run.get("planning"), "execute": evidence.get("budget")}, ensure_ascii=False)[:300])

        if args.defect_benchmark:
            # 该基准确认过会由诊断子进程重置浏览器 harness 自己的库（子进程与父进程共用同一个 SQLite 文件），
            # 因此真实基准移到 pytest 内执行（每个子进程自带独立库）：tests/test_defect_benchmark_live.py。
            raise RuntimeError("多场景缺陷基准请用 QA_LIVE_DEFECTS=1 pytest tests/test_defect_benchmark_live.py 运行")

        if args.live_intake:
            intake = httpx.post(origin + "/api/v1/op/qa/functional-intake", timeout=180,
                                headers={"Authorization": "Bearer " + token},
                                json={"requirement": "验证 C 端购物车修改数量超过库存会被拒绝，且购物车金额与库存保持不变",
                                      "environment_id": "isolated-local"})
            results["diagnostics"]["live_intake_http"] = intake.status_code
            results["diagnostics"]["live_intake"] = intake.json() if intake.status_code < 500 else intake.text
            check("真实模型受理返回 201", intake.status_code == 201, intake.text[:400])
            body = intake.json()
            check("真实模型给出可实现性判断", body.get("verdict", {}).get("reason") is not None, json.dumps(body, ensure_ascii=False)[:400])
            check("真实模型受理有工具调用与用量证据",
                  bool(body["evidence"].get("tools")) and body["evidence"].get("budget", {}).get("calls", 0) > 0,
                  json.dumps(body["evidence"].get("budget"), ensure_ascii=False))

        errors = []
        with sync_playwright() as playwright:
            edge = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
            browser = playwright.chromium.launch(headless=True, args=["--disable-gpu"],
                                                **({"executable_path": str(edge)} if edge.exists() else {}))
            try:
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                context.add_init_script("sessionStorage.setItem('token_op'," + json.dumps(token) + ");")
                page = context.new_page()
                page.set_default_timeout(20000)
                page.on("pageerror", lambda error: errors.append(str(error)))
                listing = json.dumps([real_run, fixture])

                def api_body(payload):
                    return lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(payload, ensure_ascii=False))

                def layout(primary):
                    return page.evaluate("""(primary) => {
                      const box = sel => { const node = document.querySelector(sel); if (!node) return null;
                        const r = node.getBoundingClientRect(); return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}; };
                      const desc = node => node ? node.tagName.toLowerCase() + (node.id ? "#" + node.id : "") + (typeof node.className === "string" && node.className ? "." + node.className.trim().split(/\\s+/).slice(0, 2).join(".") : "") : "无";
                      const blockers = [];
                      const content = document.querySelector("#content");
                      for (const node of document.querySelectorAll("aside nav button")) {
                        const r = node.getBoundingClientRect(), cy = r.y + r.height / 2;
                        if (r.width < 2 || cy < 0 || cy > innerHeight) continue;
                        const top = document.elementFromPoint(r.x + r.width / 2, cy);
                        if (top && (top === node || node.contains(top))) continue;
                        // 只把「被页面内容压住」算作覆盖；侧栏自身底栏或折叠在视口外属于既有外壳行为。
                        if (top && content && content.contains(top)) blockers.push({button: node.textContent.trim(), by: desc(top)});
                      }
                      const wide = [];
                      for (const node of document.querySelectorAll("body *")) {
                        const r = node.getBoundingClientRect();
                        if (r.width > 0 && r.right > document.documentElement.clientWidth + 1) wide.push({element: desc(node), right: Math.round(r.right), width: Math.round(r.width)});
                      }
                      return {scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth,
                        aside: box("aside"), content: box("#content"), primary: box(primary), grid: box(".ao-grid"),
                        inspector: box(".ae-inspector"), evidence: box(".ae-main-evidence"), trace: box(".ae-main>.ae-details"),
                        coveredNav: blockers.length, blockers, wideOverflow: wide.slice(0, 6)};
                    }""", primary)

                page.route(re.compile(r".*/api/v1/op/qa/runs(\?.*)?$"), api_body([real_run, fixture]))
                page.route(re.compile(r".*/api/v1/op/qa/runs/" + real_run["id"] + r"$"), api_body(real_run))
                page.route(re.compile(r".*/api/v1/op/qa/runs/" + fixture["id"] + r"$"), api_body(fixture))
                # 渲染夹具：一条已完成的合成对话，用于检查对话形式与数据来源标注。
                dialogue = {"id": "d" * 32, "created_at": "2026-10-21T02:30:00", "role": "customer",
                            "messages": ["我要买吃的"], "status": "completed",
                            "evidence": {"environment": {"id": "isolated-local", "fixture_version": "seed-isolated-v1"},
                                         "budget": {"calls": 2, "tokens": 1800},
                                         "requests": [{"method": "POST", "path": "/api/v1/c/shops/nanzhi/chat", "status": 200,
                                                       "input": {"message": "我要买吃的"},
                                                       "output": {"mode": "llm", "answer": "咱们店目前没有在售的食品，暂时没法帮您配到吃的；店里主要是家居和餐具类商品。"}}]}}
                page.route(re.compile(r".*/api/v1/op/qa/business-debug(\?.*)?$"), api_body([dialogue]))

                # 1) 报告列表：主标题是登记用例名称，时间与短编号只作次要信息。
                page.goto(origin + "/op.html#/testing/runs")
                expect(page.get_by_text("测试用例报告（按小时汇总）", exact=False)).to_be_visible()
                # B 的报告按小时分组且默认收起：先展开才能真正读到报告行文本。
                page.evaluate("() => document.querySelectorAll('details.qa-hour-report').forEach(node => { node.open = true; })")
                expect(page.locator(".qa-case-row button").first).to_be_visible()
                labels = page.locator(".qa-case-row button").all_inner_texts()
                results["diagnostics"]["report_labels"] = labels
                check("报告列表显示登记用例名称", any("购物车数量校验" in text for text in labels), labels)
                check("报告列表不再以时间+短编号为主标题", all("测试报告（1条用例）" not in text for text in labels), labels)
                row_texts = page.locator(".qa-case-row").all_inner_texts()
                results["diagnostics"]["report_rows"] = row_texts
                check("报告编号仍可追溯", all(re.search(r"报告 [0-9a-f]{6}", text) for text in row_texts), row_texts)
                results["diagnostics"]["reports_layout"] = layout("#content")
                page.screenshot(path=str(artifacts / "reports-list.png"), full_page=True)

                # 2) 功能测试页：历史下拉显示用例名称 + 自由需求受理面板 + 布局不遮挡导航。
                page.goto(origin + "/op.html#/testing/functional")
                expect(page.locator(".fi-panel")).to_be_visible()
                expect(page.get_by_label("功能测试需求")).to_be_visible()
                expect(page.get_by_label("测试环境")).to_be_visible()
                # 功能页把历史回放放在末尾折叠区：先展开，再取参考区内第一个有选项的下拉（标签随布局调整）。
                page.evaluate("() => document.querySelectorAll('.qa-agent-reference').forEach(node => { node.open = true; })")
                page.wait_for_timeout(400)
                options = page.evaluate("""() => {
                  const selects = [...document.querySelectorAll('select')];
                  const target = selects.find(node => [...node.options].some(option => /报告 [0-9a-f]{6}/.test(option.textContent) || option.textContent.includes('购物车数量校验')));
                  return target ? [...target.options].map(option => option.textContent) : [];
                }""")
                results["diagnostics"]["functional_history_options"] = options
                # 历史回放位置已由 B 的布局改版调整；这里只记录现状，不再把“功能页一定有历史下拉”当硬断言。
                check("功能测试页提供自由需求输入与判断入口",
                      page.get_by_label("功能测试需求").is_visible()
                      and page.get_by_role("button", name="分析需求并匹配用例").is_visible(), "")
                results["diagnostics"]["intake_help"] = page.locator(".fi-panel").inner_text()[:300]
                results["diagnostics"]["overflow_source"] = page.evaluate("""() => {
                  const doc = document.documentElement, base = doc.scrollWidth, out = [];
                  const probe = node => { if (!node) return null; const prev = node.style.display; node.style.display = "none";
                    const width = doc.scrollWidth; node.style.display = prev; return width; };
                  const panel = document.querySelector(".fi-panel");
                  out.push({target: "fi-panel", width: probe(panel)});
                  const walk = (node, depth) => {
                    if (depth > 2 || !node) return;
                    for (const child of node.children) {
                      const width = probe(child);
                      if (width !== null && width < base) out.push({target: "HIDDEN " + (child.id ? "#" + child.id : "") + "." + (child.className || child.tagName), width});
                      walk(child, depth + 1);
                    }
                  };
                  walk(document.querySelector("#content"), 0);
                  const wide = [];
                  for (const node of document.querySelectorAll("#content *")) {
                    if (node.scrollWidth > node.clientWidth + 1 && node.clientWidth > 0) wide.push({element: node.className || node.tagName, clientWidth: node.clientWidth, scrollWidth: node.scrollWidth});
                  }
                  return {base, out, internal_overflows: wide.slice(0, 8)};
                }""")

                dt = layout(".fi-panel")
                results["diagnostics"]["functional_layout"] = dt
                check("功能测试页无横向溢出", dt["scrollWidth"] <= dt["clientWidth"] + 1, json.dumps(dt))
                check("功能测试内容不覆盖左侧导航", dt["coveredNav"] == 0, json.dumps(dt))
                if dt["primary"] and dt["aside"]:
                    check("功能测试主区在导航右侧", dt["primary"]["x"] >= dt["aside"]["x"] + dt["aside"]["w"] - 1, json.dumps(dt))
                page.screenshot(path=str(artifacts / "functional-intake.png"), full_page=True)

                # 3) 业务页：执行轨迹与业务证据进入主内容区，不挤成窄侧栏。
                page.goto(origin + "/op.html#/testing/business")
                expect(page.locator(".ae-main")).to_be_visible()
                dt = layout(".ae-main")
                results["diagnostics"]["business_layout"] = dt
                check("业务页存在主内容区", dt["primary"] is not None, json.dumps(dt))
                check("业务页不再使用窄侧栏", dt["inspector"] is None, json.dumps(dt))
                check("业务页内容不覆盖左侧导航", dt["coveredNav"] == 0, json.dumps(dt))
                check("业务页无横向溢出", dt["scrollWidth"] <= dt["clientWidth"] + 1, json.dumps(dt))
                if dt["primary"] and dt["aside"]:
                    check("业务页主内容区在导航右侧", dt["primary"]["x"] >= dt["aside"]["x"] + dt["aside"]["w"] - 1, json.dumps(dt))
                business_text = page.locator(".ae-main").text_content() or ""
                results["diagnostics"]["business_dialogue"] = business_text[:400]
                check("业务页与另两页一致：标题后有三步编号引导",
                      page.locator(".qa-eval-guide .qa-eval-step").count() == 3
                      and page.locator(".qa-eval-guide .qa-eval-number").count() == 3, "")
                check("业务页能力说明默认折叠（与功能/评测页一致）",
                      page.locator(".qa-agent-reference").first.evaluate("node => node.open") is False, "")
                check("业务工作台标题与折叠说明在同一样式下",
                      page.locator(".ae-business-workspace > .ao-summary > h3").count() == 1
                      and page.locator(".ae-business-workspace > .ao-details > summary").count() == 1, "")
                check("业务对话显示为左右气泡与说话人",
                      page.locator(".ao-bubble-user").count() >= 1 and page.locator(".ao-bubble-agent").count() >= 1
                      and "我（合成买家）" in business_text and "购物小助手" in business_text, business_text[:200])
                check("业务对话写明数据来源不是线上真实库",
                      "独立合成副本" in business_text and "不是线上南枝真实库" in business_text, business_text[:200])
                check("业务对话保留原始问答内容",
                      "我要买吃的" in business_text and "没有在售的食品" in business_text, business_text[:200])
                page.screenshot(path=str(artifacts / "business-layout.png"), full_page=True)

                # 4) 评测页逐项核验：同名同值断言合并，缺失对照值不再显示为通过。
                page.goto(origin + "/op.html#/testing/evaluator")
                page.locator(".qa-eval-fold").filter(has=page.locator("summary", has_text="查看来源运行的执行过程")).locator("summary").first.click()
                page.get_by_label("历史运行", exact=True).select_option(index=1)
                expect(page.locator(".ae-result-column")).to_be_visible()
                kernel = page.locator(".ae-result-column")
                heading = kernel.locator("h4", has_text="逐项核验").first.inner_text()
                names = kernel.locator(".ae-check > .ae-check-head > strong").all_inner_texts()
                results["diagnostics"]["assertion_heading"] = heading
                results["diagnostics"]["assertion_names"] = names
                check("逐项核验标注合并数量", "已合并 1 条同名同值记录" in heading, heading)
                check("逐项核验名称不再重复", len(names) == len(set(names)), names)
                check("同名断言显示合并条数", kernel.locator(".ae-check-head").filter(has_text="同类记录 2 条已合并").count() == 1, names)
                text = kernel.inner_text()
                check("缺失对照值不再写成未采集独立值", "未采集独立值" not in text, text[:200])
                check("流程型断言说明其证明边界", "只核对流程结果" in text, text[:300])
                page.screenshot(path=str(artifacts / "evaluator-checks.png"), full_page=True)

                # 5) 双对象评测与功能地图：评测页可切换两类对象并声明三层证据；功能页展示真实覆盖情况。
                panel = page.locator(".aq-panel")
                expect(panel).to_be_visible()
                targets = page.get_by_label("评测对象").locator("option").all_inner_texts()
                check("评测页可切换业务 Agent / 功能测试 Agent 两类对象", targets == ["业务 Agent", "功能测试 Agent"], targets)
                check("评测页说明程序核验、模型评分与人工复核分层",
                      "程序核验" in panel.inner_text() and "模型评分和人工复核" in panel.inner_text(), panel.inner_text()[:200])
                check("评测页提供对所选运行创建评测的入口",
                      page.get_by_role("button", name="生成程序核验").is_visible(), "")
                panel.locator("details").evaluate_all("nodes => nodes.forEach(node => { node.open = true; })")
                panel_text = panel.text_content() or ""
                check("评测页提供不公开评测集（只给摘要、可审批揭示）",
                      "不公开评测集" in panel_text and "expectation_unavailable" in panel_text
                      and page.get_by_role("button", name="揭示答案").count() > 0, panel_text[:200])
                check("评测页提供跨版本对比入口",
                      "评测版本对比" in panel_text and "暂无独立评测记录" in panel_text
                      and page.get_by_role("button", name="生成对比").count() == 0, panel_text[:200])
                page.goto(origin + "/op.html#/testing/functional")
                page.locator(".qa-agent-reference").evaluate("node => { node.open = true; }")
                feature_panel = page.locator(".aq-panel")
                expect(feature_panel).to_be_visible()
                expect(feature_panel.locator("summary", has_text="接口覆盖").first).to_be_visible()   # 等待功能目录异步渲染
                feature_text = feature_panel.inner_text()
                summaries = [text for text in feature_panel.locator("summary").all_inner_texts()
                             if re.search(r"接口覆盖 \d+ 条 · 页面覆盖 \d+ 条", text)]
                results["diagnostics"]["coverage_summaries"] = summaries[:6]
                results["diagnostics"]["feature_map"] = feature_text[:400]
                check("功能页展示代码同源的 B/C 功能依据与覆盖情况",
                      "B/C 功能依据与执行工具" in feature_text and ("接口覆盖" in feature_text and "页面覆盖" in feature_text), feature_text[:200])
                check("功能页把接口覆盖与页面覆盖分开列出", len(summaries) >= 5, str(summaries[:4]))
                check("页面覆盖既有已登记场景也有未覆盖的域",
                      any(re.search(r"页面覆盖 [1-9]\d* 条", text) for text in summaries)
                      and any("页面覆盖 0 条" in text for text in summaries), str(summaries[:6]))
                raw_text = feature_panel.text_content() or ""      # 折叠卡片内的场景明细也要读到
                check("功能页按正常/异常/权限/边界展示场景",
                      "正常/异常/权限/边界场景" in raw_text and "正常流程" in raw_text and "边界值" in raw_text,
                      raw_text[:300])
                check("功能页标注待确认与暂不可测试状态",
                      "待确认" in raw_text and "暂不可测试" in raw_text,
                      [row for row in summaries if "待确认" in row][:3])
                check("功能页给出逐功能清理方式",
                      "测试数据要求与清理方式" in raw_text and "销毁子进程与临时工作区" in raw_text
                      and "不等于用例通过" in raw_text, raw_text[:200])
                check("功能页展示可复用点击工具库",
                      "可复用点击工具" in raw_text and "c_open_product_card" in raw_text
                      and "点击商品卡片进入详情" in raw_text, raw_text[:300])
                check("点击工具区分可用与待验证",
                      "个可用" in raw_text or "待验证" in raw_text, raw_text[:200])
                check("页面无 JS 错误（含双对象评测与功能地图）", not errors, errors)
                context.close()
            finally:
                browser.close()
        results["status"] = "passed"
    except Exception as exc:                                        # noqa: BLE001 - 记录失败证据后重新抛出
        results["status"] = "failed"
        results["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        try:
            server.terminate()
            server.wait(timeout=15)
        except Exception:                                            # noqa: BLE001
            pass
        (artifacts / "op-report-ui.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        if not args.keep:
            shutil.rmtree(folder, ignore_errors=True)
        print(json.dumps({"status": results.get("status"), "error": results.get("error"),
                          "checks": results["checks"], "diagnostics": results["diagnostics"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
