"""商品重构后的按钮回归；仅操作 RealCase 拥有的本轮记录。"""
import json
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.tables import Product, Sku


def run(ctx, cid):
    from playwright.sync_api import expect, sync_playwright

    expect.set_options(timeout=15000)
    root = settings.backend_root / "data" / "quality-artifacts"
    root.mkdir(parents=True, exist_ok=True)
    artifacts = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--disable-gpu"])
        errors, server_errors = [], []

        def role_page(key, token):
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            context.add_init_script("sessionStorage.setItem(" + json.dumps(key) + "," + json.dumps(token) + ");")
            page = context.new_page()
            page.set_default_timeout(12000)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("response", lambda response: server_errors.append(response.url.split('?')[0])
                    if "/api/v1/" in response.url and response.status >= 500 else None)
            return context, page

        role = ("token_op", ctx.op) if cid == "RE19" else ("token_c", ctx.buyer) if cid == "RE20" else ("token_b", ctx.merchant)
        context, page = role_page(*role)

        def navigate(url):
            page.goto(url, wait_until="commit")

        def screenshot():
            name = uuid4().hex + ".png"
            path = root / name
            page.screenshot(path=str(path), full_page=True)
            artifacts.append({"id": name, "type": "image/png", "sha256": sha256(path.read_bytes()).hexdigest()})

        def search_product(product):
            page.get_by_role("textbox", name="搜索商品名称或编号", exact=True).fill(product["spu_id"])
            expect(page.get_by_text(product["name"], exact=True).first).to_be_visible()

        def op_search(product):
            navigate(ctx.origin + "/op.html")
            page.locator('nav [data-page="products"]').click()
            page.get_by_label("搜索关键词", exact=True).fill(product["spu_id"])
            with page.expect_response(lambda r: "/op/records/products?" in r.url) as response:
                page.get_by_role("button", name="查询", exact=True).click()
            ctx.e.check("OP按SPU业务编号精确定位", [r["id"] for r in response.value.json()["items"]] == [product["id"]])
            expect(page.locator("#content tbody")).to_contain_text(product["spu_id"])

        def reason_submit(path):
            dialog = page.locator("dialog.op-action-dialog")
            dialog.get_by_label("操作原因", exact=True).fill("商品按钮实测 " + ctx.tag)
            with page.expect_response(lambda r: path in r.url and r.request.method == "POST") as response:
                dialog.get_by_role("button", name="确认提交", exact=True).click()
            ctx.e.check("平台治理按钮实际提交成功 " + path, response.value.status == 200, 200, response.value.status)

        try:
            if cid == "RE17":
                product = ctx.fixture()
                pid, sku_id = product["id"], product["skus"][0]["id"]
                # 原参数不在编辑页显示；保存价格库存不得把已有参数清空。
                ctx.call("PATCH", f"/b/skus/{sku_id}", ctx.merchant,
                         {"parameters": [{"name": "材质", "value": "棉麻"}]})
                for op, price, stock in ((False, "31.25", "7"), (True, "32.50", "8")):
                    if op:
                        context.close()
                        context, page = role_page("token_op", ctx.op)
                    navigate(ctx.origin + (f"/op-shop.html?shop_id={ctx.shop_id}#/products/{pid}" if op else "/b.html#/products"))
                    if op:
                        page.locator("#op-scope-reason").fill("商品规格维护 " + ctx.tag)
                        row = page.locator(".sku-table tbody tr").first
                    else:
                        search_product(product)
                        page.get_by_role("button", name=f"展开{product['name']}的 SKU", exact=True).click()
                        row = page.locator(f"#product-skus-{pid} .sku-table tbody tr").first
                    row.locator(".sku-price").fill(price)
                    row.locator(".sku-stock").fill(stock)
                    with page.expect_response(lambda r: r.url.endswith(f"/skus/{sku_id}") and r.request.method == "PATCH") as response:
                        row.get_by_role("button", name="保存", exact=True).click()
                    ctx.e.check(("OP" if op else "B") + "规格保存按钮成功", response.value.status == 200)
                    fresh = ctx.call("GET", f"/c/shops/nanzhi/products/{pid}")
                    sku = next(s for s in fresh["skus"] if s["id"] == sku_id)
                    ctx.e.check("C展示规格价格库存与参数同步", (sku["price_yuan"], sku["stock"], sku["parameters"]) ==
                                (float(price), int(stock), [{"name": "材质", "value": "棉麻"}]))
                    expect(page.locator(".sku-table tbody tr").first).to_be_visible()
                    screenshot()
                with SessionLocal() as db:
                    sku = db.get(Sku, sku_id)
                    ctx.e.check("规格按钮修改真实落库", sku.price_cents == 3250 and sku.stock == 8)
            elif cid == "RE18":
                navigate(ctx.origin + "/b.html#/products")
                page.get_by_role("button", name="＋ 发布商品", exact=True).click()
                dialog = page.get_by_role("dialog", name="发布商品", exact=True)
                name = "【实测】草稿按钮 " + ctx.tag
                dialog.locator('[name="name"]').fill(name)
                dialog.locator('[name="category"]').fill("家居")
                dialog.locator('[name="description"]').fill("商品按钮实测 " + ctx.tag)
                with page.expect_response(lambda r: r.url.endswith("/b/products") and r.request.method == "POST") as response:
                    dialog.get_by_role("button", name="保存商品草稿", exact=True).click()
                ctx.e.check("真实草稿创建成功", response.value.status == 200)
                product = response.value.json()
                ctx.products.append(product["id"])
                expect(dialog).to_have_count(0)
                search_product(product)
                page.get_by_role("button", name="完成创建", exact=True).click()
                expect(page.locator(".product-workspace")).not_to_contain_text(name)
                page.get_by_role("button", name="重置", exact=True).click()
                search_product(product)
                for label, status in (("上架", "on"), ("下架", "off"), ("上架", "on")):
                    with page.expect_response(lambda r: r.url.endswith(f"/products/{product['id']}/status")) as response:
                        page.get_by_role("button", name=label, exact=True).click()
                    ctx.e.check("商品状态按钮 " + label, response.value.status == 200 and response.value.json()["status"] == status)
                    ctx.call("GET", f"/c/shops/nanzhi/products/{product['id']}", status=(200,) if status == "on" else (404,))
                page.get_by_role("button", name=f"展开{name}的 SKU", exact=True).click()
                panel = page.locator(f"#product-skus-{product['id']}")
                panel.get_by_placeholder("新规格名", exact=True).fill("新增规格")
                panel.get_by_placeholder("价格", exact=True).fill("49")
                panel.get_by_placeholder("库存", exact=True).fill("3")
                with page.expect_response(lambda r: r.url.endswith(f"/products/{product['id']}/skus") and r.request.method == "POST") as response:
                    panel.get_by_role("button", name="＋ 添加规格", exact=True).click()
                ctx.e.check("添加规格按钮真实成功", response.value.status == 200)
                row = panel.locator(".sku-table tbody tr").filter(has=page.get_by_role("textbox", name="新增规格 规格名", exact=True))
                for label, state in (("下架", "off"), ("上架", "on")):
                    with page.expect_response(lambda r: "/skus/" in r.url and r.url.endswith("/status")) as response:
                        row.get_by_role("button", name=label, exact=True).click()
                    ctx.e.check("规格状态按钮 " + label, response.value.status == 200)
                    fresh = ctx.call("GET", f"/c/shops/nanzhi/products/{product['id']}")
                    ctx.e.check("C规格随按钮显隐", any(s["spec"] == "新增规格" for s in fresh["skus"]) == (state == "on"))
                screenshot()
            elif cid == "RE19":
                product = ctx.fixture()
                op_search(product)
                for label in ("禁售", "解除禁售"):
                    page.locator("#content tbody").get_by_role("button", name=label, exact=True).click()
                    reason_submit(f"/products/{product['id']}/moderate")
                    expect(page.locator("#content tbody").get_by_role("button", name="解除禁售" if label == "禁售" else "禁售", exact=True)).to_be_visible()
                    ctx.call("GET", f"/c/shops/nanzhi/products/{product['id']}", status=(404,))
                ctx.call("POST", f"/b/products/{product['id']}/status", ctx.merchant, {"action": "on"})
                for label in ("禁售规格", "解除禁售"):
                    page.get_by_role("button", name="规格详情", exact=True).click()
                    dialog = page.locator("dialog.op-detail")
                    expect(dialog).to_contain_text(product["spu_id"])
                    dialog.locator("tbody tr").first.get_by_role("button", name=label, exact=True).click()
                    reason_submit(f"/skus/{product['skus'][0]['id']}")
                    expect(dialog).to_have_count(0)
                    fresh = ctx.call("GET", f"/c/shops/nanzhi/products/{product['id']}")
                    ctx.e.check("被禁售或解除后下架的规格均不泄露", product["skus"][0]["id"] not in [s["id"] for s in fresh["skus"]])
                screenshot()
            elif cid == "RE20":
                product = ctx.fixture()
                pid = product["id"]
                ctx.call("POST", "/c/shops/nanzhi/cart", ctx.buyer, {"sku_id": product["skus"][0]["id"], "quantity": 1})
                navigate(ctx.origin + f"/c.html?code=nanzhi#/product/nanzhi/{pid}")
                expect(page.locator(".detail .info .sku-list button")).to_have_count(2)
                for sku in product["skus"]:
                    ctx.call("PATCH", f"/b/skus/{sku['id']}", ctx.merchant,
                             {"market_price_yuan": 59 if sku["price_yuan"] == 29 else 49})
                    ctx.call("POST", f"/b/skus/{sku['id']}/status", ctx.merchant, {"action": "off"})
                history = ctx.call("GET", "/c/history", ctx.buyer)
                saved = next(p for p in history if p["id"] == pid)
                ctx.e.check("无在售规格保留正确现价与同规格划线价", (saved["price_from"], saved["market_from"], saved["available"]) == (29, 59, False))
                for width in (1440, 390):
                    page.set_viewport_size({"width": width, "height": 1000})
                    navigate(ctx.origin + "/c.html?code=nanzhi#/cart")
                    row = page.locator(".cart-row").first
                    expect(row.locator(".qty button").first).to_be_disabled()
                    expect(row.locator(".qty button").last).to_be_disabled()
                    expect(row.locator('a[href*="/product/"]')).to_have_count(0)
                    expect(page.get_by_role("button", name="去结算", exact=True)).to_be_disabled()
                    ctx.e.check("失效商品数量与结算按钮禁用 " + str(width), True)
                    layout = row.evaluate("""node => {
                        const rect = index => node.children[index].getBoundingClientRect();
                        const overlap = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
                        return {priceAndQuantity: overlap(rect(3), rect(4)), quantityAndDelete: overlap(rect(4), rect(6))};
                    }""")
                    ctx.e.check("购物车价格数量删除按钮不重叠 " + str(width), not any(layout.values()), False, layout)
                    screenshot()
                with page.expect_response(lambda r: "/c/cart/" in r.url and r.request.method == "DELETE") as response:
                    row.get_by_role("button", name="删除", exact=True).click()
                ctx.e.check("失效商品仍可删除", response.value.status == 200)
            else:
                raise ValueError("未登记的商品按钮用例")
            ctx.e.check("商品按钮页面无脚本错误", not errors, [], errors)
            ctx.e.check("商品按钮页面无服务端错误", not server_errors, [], server_errors)
        finally:
            try:
                screenshot()
                ctx.e.artifacts = artifacts
            finally:
                browser.close()
