from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from uuid import uuid4


BROWSER_CASES = {"E01": "买家规格加购用券结算", "E02": "商家SKU排序同步买家页面", "E03": "OP测试入口与买家权限隔离", "E04": "OP测试规划审批运行重跑对比"}


def execute_browser(case_id, evidence):
    import httpx
    from playwright.sync_api import sync_playwright, expect
    from app.core.config import settings
    from app.quality.worker import stop_process
    from app.quality.sandbox import safe
    with socket.socket() as bound:
        bound.bind(("127.0.0.1", 0))
        port = bound.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    workspace = Path(os.environ["QA_CHILD_WORKSPACE"])
    artifact_root = settings.backend_root / "data" / "quality-artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    artifact = uuid4().hex + ".png"
    browser = None
    with (workspace / "browser-server.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen([sys.executable, "-m", "app.quality.browser_server", "--port", str(port)],
                                  cwd=settings.backend_root, env=dict(os.environ, QA_BROWSER_OP="1" if case_id == "E04" else "0"), stdout=log, stderr=log,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                  start_new_session=os.name != "nt")
        try:
            with httpx.Client(base_url=origin, timeout=10, trust_env=False) as client:
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError("隔离浏览器服务未启动")
                    try:
                        if client.get("/api/v1/ready").is_success:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError("隔离浏览器服务准备超时")
                def call(method, path, token=None, body=None):
                    started = time.perf_counter()
                    response = client.request(method, path, headers={"Authorization": "Bearer " + token} if token else {}, json=body)
                    evidence.requests.append({"method": method, "path": path, "status": response.status_code, "elapsed_ms": round((time.perf_counter() - started) * 1000), "input": safe(body), "output": safe(response.json())})
                    evidence.check("浏览器夹具API操作成功", response.is_success, None, response.status_code)
                    return response.json()
                buyer = call("POST", "/api/v1/auth/login", body={"username": "alice", "password": "alice123"})["access_token"]
                merchant = call("POST", "/api/v1/auth/login", body={"username": "merchant", "password": "merchant123"})["access_token"]
                products = call("GET", "/api/v1/c/shops/nanzhi/products")
                product = next(row for row in products if row["name"] == "亚麻抱枕套")
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(channel="msedge" if os.name == "nt" else None, headless=True,
                                                         args=["--disable-gpu", "--disable-background-networking"])
                    context = browser.new_context(viewport={"width": 1366, "height": 900})
                    identity = merchant if case_id == "E02" else buyer
                    context.add_init_script(f"sessionStorage.setItem('token_c',{json.dumps(identity)});sessionStorage.setItem('token_b',{json.dumps(identity)});")
                    page = context.new_page()
                    page.set_default_timeout(15000)
                    def capture(request):
                        response = request.response()
                        if response is None or not request.url.startswith(origin + "/api/v1/") or len(evidence.requests) >= 150:
                            return
                        timing = request.timing or {}
                        elapsed = timing.get("responseEnd", 0) - timing.get("requestStart", 0)
                        row = {"method": request.method, "path": request.url.removeprefix(origin).split("?")[0], "status": response.status, "via": "real_browser"}
                        if elapsed > 0:
                            row["elapsed_ms"] = round(elapsed)
                        evidence.requests.append(row)
                    page.on("requestfinished", capture)
                    if case_id == "E01":
                        now = datetime.now(timezone.utc)
                        coupon = call("POST", "/api/v1/b/coupons", merchant, {"name": "浏览器验收优惠券", "threshold_cents": 0, "amount_cents": 1000, "total_count": 2,
                                      "starts_at": (now-timedelta(days=1)).isoformat(), "ends_at": (now+timedelta(days=1)).isoformat()})
                        call("POST", f"/api/v1/c/shops/nanzhi/coupons/{coupon['id']}/claim", buyer)
                        before = call("GET", "/api/v1/c/orders", buyer)
                        page.goto(origin + f"/c.html?code=nanzhi#/product/nanzhi/{product['id']}", wait_until="domcontentloaded")
                        page.locator(".detail .info .sku-list button").first.click()
                        page.locator(".detail .info .actions").get_by_role("button", name="加入购物车", exact=True).click()
                        expect(page.get_by_text("已加入购物车", exact=True)).to_be_visible()
                        page.get_by_role("link", name="购物车").first.click()
                        page.get_by_role("button", name="去结算", exact=True).click()
                        expect(page.get_by_role("heading", name="订单结算", exact=True)).to_be_visible()
                        expect(page.get_by_text("优惠抵扣", exact=True)).to_be_visible()
                        with page.expect_response(lambda response: response.url.endswith("/cart/checkout") and response.request.method == "POST") as placed:
                            page.get_by_role("button", name="提交订单", exact=True).click()
                        evidence.check("浏览器提交订单接口真实成功", placed.value.status == 200)
                        expect(page.get_by_text("订单中心", exact=True).first).to_be_visible()
                        orders = call("GET", "/api/v1/c/orders", buyer)
                        created = [row for row in orders if row["order_no"] not in {old["order_no"] for old in before}]
                        evidence.check("真实浏览器提交订单且优惠抵扣", len(created) == 1 and created[0]["discount_yuan"] == 10, None, created)
                    elif case_id == "E02":
                        page.goto(origin + "/b.html#/products", wait_until="domcontentloaded")
                        page.get_by_role("textbox", name="搜索商品名称或编号", exact=True).fill(product["name"])
                        page.get_by_role("button", name=f"展开{product['name']}的 SKU", exact=True).click()
                        rows = page.locator(f"#product-skus-{product['id']} .sku-table tbody tr")
                        old_ids = rows.evaluate_all("rows=>rows.map(row=>Number(row.dataset.sortId))")
                        handle = rows.first.locator(".drag-handle")
                        handle.focus()
                        with page.expect_response(lambda response: "/skus/sort" in response.url and response.request.method == "POST") as saved:
                            handle.press("ArrowDown")
                        evidence.check("真实页面排序保存成功", saved.value.status == 200)
                        expected = [old_ids[1], old_ids[0], *old_ids[2:]]
                        page.goto(origin + f"/c.html?code=nanzhi#/product/nanzhi/{product['id']}", wait_until="domcontentloaded")
                        expect(page.locator(".detail .info .sku-list button").first).to_have_attribute("data-sku-id", str(expected[0]))
                        actual = page.locator(".detail .info .sku-list button").evaluate_all("buttons=>buttons.map(button=>Number(button.dataset.skuId))")
                        evidence.check("B端排序在C端实际DOM同步", actual == expected, expected, actual)
                    elif case_id == "E04":
                        page.goto(origin + "/op.html#/testing/assistant", wait_until="domcontentloaded")
                        page.get_by_label("管理员账号", exact=True).fill("merchant")
                        page.get_by_label("登录密码", exact=True).fill("merchant123")
                        page.get_by_role("button", name="进入运营工作台").click()
                        page.get_by_role("button", name="测试用例与能力", exact=True).click()
                        page.get_by_role("button", name="新增助手用例", exact=True).click()
                        editor = page.locator("dialog[open]")
                        editor.get_by_label("用例名称", exact=True).fill("浏览器创建搜索用例")
                        editor.get_by_label("第1轮用户输入", exact=True).fill("搜索抱枕")
                        editor.get_by_label("第1轮必须调用的工具名", exact=True).fill("search_products")
                        editor.get_by_label("第1轮回答必须包含", exact=True).fill("抱枕")
                        editor.get_by_role("button", name="保存候选", exact=True).click()
                        page.get_by_role("button", name="审核启用", exact=True).click()
                        page.get_by_role("button", name="已接入", exact=True).click()
                        page.get_by_role("button", name="新建版本", exact=True).click()
                        page.locator("dialog[open]").get_by_label("用例名称", exact=True).fill("浏览器搜索用例第二版")
                        with page.expect_response(lambda response: response.url.endswith("/revisions") and response.request.method == "POST") as revised:
                            page.locator("dialog[open]").get_by_role("button", name="保存候选", exact=True).click()
                        evidence.check("新版本保存成功", revised.value.status == 201)
                        versions = [row for row in call("GET", "/api/v1/op/qa/cases", merchant) if row.get("adapter") == "declarative_assistant"]
                        evidence.check("用例UI创建审核与版本隔离", len(versions) == 2 and versions[0]["state"] == "active" and versions[0]["version"] == 1 and versions[1]["state"] == "candidate" and versions[1]["version"] == 2, None, versions)
                        page.get_by_role("button", name="业务Agent评测", exact=True).click()
                        page.get_by_role("button", name="新建业务 Agent 评测", exact=True).click()
                        dialog = page.locator("dialog[open]")
                        dialog.get_by_label("测试目标", exact=True).fill("浏览器OP测试闭环验收")
                        dialog.get_by_role("checkbox").last.check()
                        dialog.get_by_role("button", name="生成待审批计划", exact=True).click()
                        page.get_by_role("button", name="批准此版本", exact=True).click()
                        page.get_by_role("button", name="启动已批准计划", exact=True).click()
                        def completed(count):
                            for _ in range(300):
                                response = client.get("/api/v1/op/qa/runs", headers={"Authorization": "Bearer " + merchant})
                                runs = response.json()
                                if len(runs) >= count and all(run["status"] == "completed" for run in runs[:count]):
                                    return runs
                                page.wait_for_timeout(100)
                            raise RuntimeError("浏览器OP任务未完成")
                        runs = completed(1)
                        evidence.check("UI审批后任务形成真实断言报告", all(row["status"] == "passed" for row in runs[0]["results"]), None, runs[0]["summary"])
                        page.get_by_role("button", name="新建重跑", exact=True).click()
                        completed(2)
                        page.get_by_role("button", name="版本报告对比", exact=True).click()
                        page.get_by_role("button", name="生成对比", exact=True).click()
                        expect(page.get_by_role("heading", name="报告差异", exact=True)).to_be_visible()
                        page.get_by_role("button", name="历史保留与清理", exact=True).click()
                        page.get_by_role("button", name="预览清理范围", exact=True).click()
                        expect(page.get_by_text("将清理0次", exact=False)).to_be_visible()
                        page.locator("dialog[open]").get_by_role("button", name="关闭", exact=True).click()
                    else:
                        page.goto(origin + "/c.html?code=nanzhi", wait_until="domcontentloaded")
                        evidence.check("C端未加载测试插件", page.locator('script[src*="op-quality"]').count() == 0)
                        page.goto(origin + "/op.html#/testing/assistant", wait_until="domcontentloaded")
                        expect(page.get_by_role("heading", name="欢迎回来", exact=True)).to_be_visible()
                        denied = context.request.get(origin + "/api/v1/op/qa/cases", headers={"Authorization": "Bearer " + buyer})
                        evidence.check("真实浏览器买家身份被OP测试API拒绝", denied.status == 403)
                    page.screenshot(path=str(artifact_root / artifact), full_page=True)
                    evidence.check("真实浏览器确实加载并执行业务页面", any(row.get("via") == "real_browser" for row in evidence.requests))
                    browser.close();browser = None
            return {"suite": {"adapter": "registered_browser", "reports": [{"stage": "call", "outcome": "passed", "node": case_id}]},
                    "artifacts": [{"id": artifact, "type": "image/png", "sha256": sha256((artifact_root / artifact).read_bytes()).hexdigest()}]}
        finally:
            try:
                if browser:
                    browser.close()
            except Exception:
                pass
            finally:
                stop_process(server)
