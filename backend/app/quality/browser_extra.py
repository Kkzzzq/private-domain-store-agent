"""Read-only UI checks, reusable by isolated and real-shop runners."""

CASES = {
    "E06": "OP用例三分类、搜索与空结果",
    "E07": "商家主要页面导航与请求健康",
    "E08": "买家商品搜索无结果与返回首页",
}


def first_report_row(page):
    group = page.locator("details.qa-hour-report").first
    group.wait_for(state="attached")
    if group.get_attribute("open") is None:
        group.locator("summary").first.click()
    row = group.locator("[data-run-id]").first
    row.wait_for(state="visible")
    return row


def execute(case_id, page, origin, evidence, shop_code="nanzhi"):
    from playwright.sync_api import expect

    if case_id == "E06":
        page.goto(origin + "/op.html#/testing/cases", wait_until="domcontentloaded")
        page.get_by_label("管理员账号", exact=True).fill("merchant")
        page.get_by_label("登录密码", exact=True).fill("merchant123")
        page.get_by_role("button", name="进入运营工作台").click()
        for name in ("Agent 测试用例", "接口测试用例", "UI 测试用例"):
            page.get_by_role("button", name=name, exact=True).click()
            expect(page.locator(".qa-case-item").first).to_be_visible()
            evidence.check(name + "可点击且有已接入用例", page.locator(".qa-case-item").count() > 0)
        page.get_by_role("searchbox", name="搜索用例").fill("不存在的用例-qa-empty")
        expect(page.get_by_text("没有匹配当前筛选与搜索的用例。", exact=True)).to_be_visible()
        evidence.check("搜索空结果不会展示不匹配用例", page.locator(".qa-case-item").count() == 0)
    elif case_id == "E07":
        failures = []
        page.on("response", lambda response: failures.append(response.status) if "/api/v1/" in response.url and response.status >= 500 else None)
        page.goto(origin + "/b.html#/products", wait_until="domcontentloaded")
        for route in ("products", "orders", "shop", "dashboard"):
            link = page.locator(f'.side a[href="#/{route}"]')
            expect(link).to_be_visible()
            link.click()
            expect(page).to_have_url(origin + "/b.html#/" + route)
            expect(page.locator(".side")).to_be_visible()
            evidence.check("商家导航可打开：" + route, page.url.endswith("#/" + route))
        evidence.check("商家导航无服务端错误响应", not failures, [], failures)
    elif case_id == "E08":
        page.goto(origin + f"/c.html?code={shop_code}", wait_until="domcontentloaded")
        search = page.get_by_placeholder("搜索本店商品", exact=True)
        expect(search).to_be_visible()
        search.fill("qa-no-product-83bd94ff")
        search.press("Enter")
        expect(page.get_by_role("heading", name="没有找到相关商品", exact=True)).to_be_visible()
        evidence.check("买家不存在商品搜索展示明确空态", "#/collection/all" in page.url)
        page.goto(origin + f"/c.html?code={shop_code}", wait_until="domcontentloaded")
        expect(page.get_by_placeholder("搜索本店商品", exact=True)).to_have_value("")
        evidence.check("重新打开首页恢复正常搜索状态", True)
    else:
        raise ValueError("未知UI用例")
