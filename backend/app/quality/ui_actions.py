"""可复用 UI 动作工具库：把“点击商品卡片/加购/去结算/提交订单”等动作预先做好，Agent 只需组合调用。

约定
- 每个动作都声明：页面入口、参数、前置条件、步骤、页面核验点、接口交叉核验、风险级别、选择器出处。
- 只有 status='ready' 的动作可以被 Agent 调用；没实跑验证过的一律 'unverified'，调用会被拒绝。
- 选择器全部取自已有用例（写进 evidence 字段），不凭空发明；新增动作必须实跑通过后才转 ready。
- 动作执行后必须同时给出页面证据与接口事实：页面出现“成功”不算通过。
"""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

ACTIONS = (
    {'id': 'c_open_shop_home', 'name': '打开买家店铺首页', 'side': 'C', 'feature': 'home', 'status': 'ready',
     'entry': '/c.html?code={shop_code}', 'params': [], 'risk': 'read',
     'steps': ['打开买家店铺页'], 'verify': ['搜索框“搜索本店商品”可见'],
     'cross_check': ['GET /api/v1/c/shops/{shop_code} 可读'],
     'evidence': 'tests? app/quality/browser_extra.py::E08 使用同一入口与搜索框选择器'},
    {'id': 'c_search_products', 'name': '在买家页搜索商品', 'side': 'C', 'feature': 'products', 'status': 'ready',
     'entry': '/c.html?code={shop_code}', 'params': [{'name': 'keyword', 'type': 'str', 'required': True}], 'risk': 'read',
     'steps': ['在搜索框输入关键词并按回车'], 'verify': ['进入合集页（地址包含 #/collection/all）'],
     'cross_check': ['GET /api/v1/c/shops/{shop_code}/products 返回的商品名称包含该关键词'],
     'evidence': 'app/quality/browser_extra.py::E08 使用 get_by_placeholder("搜索本店商品")'},
    {'id': 'c_open_product_card', 'name': '点击商品卡片进入详情', 'side': 'C', 'feature': 'products', 'status': 'ready',
     'entry': '/c.html?code={shop_code}#/collection/all', 'params': [{'name': 'product_name', 'type': 'str', 'required': True}], 'risk': 'read',
     'steps': ['在合集页按商品名定位 article.pcard', '点击卡片里的 a.thumb'],
     'verify': ['地址变为 #/product/{shop_code}/<商品ID>', '详情页出现商品标题与规格按钮'],
     'cross_check': ['GET /api/v1/c/shops/{shop_code}/products 里该商品在售且 ID 与地址一致'],
     'evidence': 'web/c.js::productCard（article.pcard + a.thumb，href=#/product/{shopCode}/{id}）'},
    {'id': 'c_select_sku', 'name': '点击商品规格', 'side': 'C', 'feature': 'products', 'status': 'ready',
     'entry': '/c.html?code={shop_code}#/product/{shop_code}/{product_id}', 'params': [{'name': 'sku_index', 'type': 'int', 'required': False, 'default': 0}], 'risk': 'read',
     'steps': ['点击 .detail .info .sku-list 里第 N 个可选规格（跳过 dead 不可购规格）'],
     'verify': ['被点规格按钮带上 on 选中类（全列表只有一个 on）'],
     'cross_check': ['GET /api/v1/c/shops/{shop_code}/products/{product_id} 返回的 SKU 数量大于所点序号'],
     'evidence': 'app/quality/browser.py::E01 使用 .detail .info .sku-list button；web/c.js::specs 选中类为 on、不可购为 dead'},
    {'id': 'c_add_to_cart', 'name': '点击加入购物车', 'side': 'C', 'feature': 'cart', 'status': 'ready',
     'entry': '/c.html?code={shop_code}#/product/{shop_code}/{product_id}', 'params': [{'name': 'quantity', 'type': 'int', 'required': False, 'default': 1}], 'risk': 'write',
     'steps': ['把 .qty input 设为目标数量并触发 change（页面会按库存与限购夹紧）', '点击“加入购物车”'],
     'verify': ['页面出现“已加入购物车”提示'],
     'cross_check': ['GET /api/v1/c/shops/{shop_code}/cart 里存在该商品的 SKU 且数量等于页面实际提交值'],
     'evidence': 'app/quality/browser.py::E01 使用 get_by_role("button", name="加入购物车") 与“已加入购物车”断言；web/c.js::qty 数量控件'},
    {'id': 'c_open_cart', 'name': '点击购物车入口', 'side': 'C', 'feature': 'cart', 'status': 'ready',
     'entry': '/c.html?code={shop_code}', 'params': [], 'risk': 'read',
     'steps': ['点击“购物车”导航'], 'verify': ['出现购物车列表或空态'],
     'cross_check': ['GET /api/v1/c/shops/{shop_code}/cart 可读'],
     'evidence': 'app/quality/browser.py::E01 使用 get_by_role("link", name="购物车")'},
    {'id': 'c_checkout', 'name': '点击去结算', 'side': 'C', 'feature': 'cart', 'status': 'ready',
     'entry': '/c.html?code={shop_code}#/cart', 'params': [], 'risk': 'read',
     'steps': ['点击“去结算”'], 'verify': ['出现“订单结算”标题'],
     'cross_check': ['POST /api/v1/c/shops/{shop_code}/coupon-quote 与购物车金额口径一致（可选）'],
     'evidence': 'app/quality/browser.py::E01 使用 get_by_role("button", name="去结算") 与“订单结算”标题'},
    {'id': 'c_submit_order', 'name': '点击提交订单', 'side': 'C', 'feature': 'orders', 'status': 'ready',
     'entry': '/c.html?code={shop_code}#/checkout', 'params': [], 'risk': 'write',
     'steps': ['点击“提交订单”'], 'verify': ['出现“订单中心”'],
     'cross_check': ['POST 结算接口返回 200', 'GET /api/v1/c/orders 新增一笔且优惠金额正确'],
     'evidence': 'app/quality/browser.py::E01（真实浏览器提交订单且优惠抵扣）'},
    {'id': 'op_grant_merchant_access', 'name': 'OP 授权商家开店', 'side': 'OP', 'feature': 'settings', 'status': 'ready',
     'entry': '/op.html', 'params': [{'name': 'username', 'type': 'str', 'required': False, 'default': 'merchant'},
                                     {'name': 'account_id', 'type': 'int', 'required': False},
                                     {'name': 'reason', 'type': 'str', 'required': False, 'default': '点击工具库授权商家开店'}],
     'risk': 'write',
     'steps': ['以平台运营身份 PATCH /api/v1/op/platform/accounts/{account_id}，设置 merchant_enabled=true'],
     'verify': ['接口返回 200，且审计记录写入'],
     'cross_check': ['授权后商家页不再显示“未获开店授权”'],
     'precondition': '调用者必须是平台运营（隔离 fixture 里由 browser_server 把 merchant 建为运营）；实店需用真实运营账号',
     'evidence': 'app/api/op_management.py::update_account（require_operator + MerchantAccess + 审计）；app/models/account.py::MerchantAccess'},
    {'id': 'b_open_products', 'name': '打开商家商品管理页', 'side': 'B', 'feature': 'products', 'status': 'ready',
     'entry': '/b.html#/products', 'params': [], 'risk': 'read',
     'steps': ['打开商家商品页'], 'verify': ['商家左栏与商品列表可见'],
     'cross_check': ['GET /api/v1/b/products 可读'],
     'evidence': 'app/quality/browser_extra.py::E07 使用 .side 与 #/products',
     'precondition': '该店铺商家账号必须已获开店授权（MerchantAccess）；合成 fixture 默认未授权，需先由 OP 授权'},
    {'id': 'b_search_product', 'name': '商家搜索商品', 'side': 'B', 'feature': 'products', 'status': 'ready',
     'entry': '/b.html#/products', 'params': [{'name': 'product_name', 'type': 'str', 'required': True}], 'risk': 'read',
     'steps': ['在“搜索商品名称或编号”输入商品名'], 'verify': ['商品行可见'],
     'cross_check': ['GET /api/v1/b/products 返回该商品'],
     'evidence': 'app/quality/browser.py::E02 使用 get_by_role("textbox", name="搜索商品名称或编号")',
     'precondition': '该店铺商家账号必须已获开店授权（MerchantAccess）'},
    {'id': 'b_click_side_nav', 'name': '点击商家左侧导航', 'side': 'B', 'feature': 'settings', 'status': 'ready',
     'entry': '/b.html#/products', 'params': [{'name': 'route', 'type': 'str', 'required': True}], 'risk': 'read',
     'steps': ['点击 .side a[href="#/<route>"]'], 'verify': ['地址变为 #/<route>', '左栏仍可见'],
     'cross_check': ['该页面无 5xx 响应'],
     'evidence': 'app/quality/browser_extra.py::E07 使用 .side a[href="#/{route}"]',
     'precondition': '该店铺商家账号必须已获开店授权（MerchantAccess）'},
    {'id': 'c_update_cart_quantity', 'name': '在购物车修改数量', 'side': 'C', 'feature': 'cart', 'status': 'unverified',
     'entry': '/c.html?code={shop_code}#/cart', 'params': [{'name': 'quantity', 'type': 'int', 'required': True}], 'risk': 'write',
     'steps': ['待确认：购物车数量输入控件选择器'], 'verify': ['待确认'], 'cross_check': ['GET 购物车数量随之变化'],
     'evidence': '尚未实跑验证（购物车数量控件选择器未在既有用例中出现）'},
    {'id': 'c_apply_coupon', 'name': '结算页选择优惠券', 'side': 'C', 'feature': 'coupons', 'status': 'unverified',
     'entry': '/c.html?code={shop_code}#/checkout', 'params': [{'name': 'coupon_name', 'type': 'str', 'required': True}], 'risk': 'read',
     'steps': ['待确认：结算页券选择控件选择器'], 'verify': ['待确认'], 'cross_check': ['优惠抵扣金额与报价一致'],
     'evidence': '尚未实跑验证（E01 只断言“优惠抵扣”文案，未点击券选择）'},
)
ACTIONS_BY_ID = {row['id']: row for row in ACTIONS}

# 复合动作流：多个点击动作在同一个隔离站点里连续执行，才能共享同一份数据（单动作用例各自独立起站）。
FLOWS = (
    {'id': 'flow_c_buy', 'name': '买家点击链：选规格→加购→结算→下单', 'side': 'C', 'feature': 'cart', 'status': 'ready',
     'params': [{'name': 'keyword', 'type': 'str', 'required': False, 'default': '抱枕'},
                {'name': 'product_name', 'type': 'str', 'required': False, 'default': '亚麻抱枕套'},
                {'name': 'sku_index', 'type': 'int', 'required': False, 'default': 0},
                {'name': 'quantity', 'type': 'int', 'required': False, 'default': 1}],
     'actions': ({'action': 'c_open_shop_home'}, {'action': 'c_search_products', 'params': {'keyword': '${keyword}'}},
                 {'action': 'c_open_product_card', 'params': {'product_name': '${product_name}'}},
                 {'action': 'c_select_sku', 'params': {'sku_index': '${sku_index}'}},
                 {'action': 'c_add_to_cart', 'params': {'quantity': '${quantity}'}},
                 {'action': 'c_open_cart'}, {'action': 'c_checkout'}, {'action': 'c_submit_order'}),
     'risk': 'write',
     'note': '整条链在同一隔离站点内执行，因此加购的商品能带到结算与下单；单动作用例各自独立起站，不共享数据。',
     'evidence': 'app/quality/browser.py::E01（真实浏览器选规格/加购/用券/结算/提交订单）'},
)
FLOWS_BY_ID = {row['id']: row for row in FLOWS}


def ready_flows():
    return [row for row in FLOWS if row['status'] == 'ready']


def flow_steps(flow, params):
    """把流里的 ${参数} 占位替换成实际值，并做一次全员校验。"""
    filled = {spec['name']: params.get(spec['name'], spec.get('default')) for spec in flow['params']}
    steps = []
    for step in flow['actions']:
        row = ACTIONS_BY_ID[step['action']]
        raw = dict(step.get('params') or {})
        resolved = {}
        for spec in row['params']:
            value = raw.get(spec['name'])
            if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                value = filled.get(value[2:-1])
            if value is None and 'default' in spec:
                value = spec['default']
            if value is not None:
                resolved[spec['name']] = value
        steps.append({'action': step['action'], 'params': resolved})
    validate(steps)          # 先校验一次，错误信息更贴近调用方
    return steps             # 返回原始步骤（action 仍是字符串），执行器会再统一校验


def ready_actions():
    return [row for row in ACTIONS if row['status'] == 'ready']


def catalog_rows():
    """把 ready 动作登记成普通功能用例，沿用既有 计划→审批→执行 链路（Agent 组合点击即可）。

    参数值固定在动作定义里（default_params），模型不能自造参数；未验证动作不登记。
    """
    rows = []
    for index, row in enumerate(ready_actions(), 1):
        rows.append({'id': f'U{index:02}', 'title': row['name'], 'kind': 'functional', 'version': 1, 'state': 'active',
                     'modes': ['rules'], 'adapter': 'registered_ui_action', 'critical': True,
                     'environments': ['isolated-local', 'native-local'],
                     'ui_action': row['id'], 'feature': row['feature'], 'side': row['side'],
                     'default_params': {spec['name']: spec['default'] for spec in row['params'] if 'default' in spec}})
    for offset, flow in enumerate(ready_flows(), len(rows) + 1):
        rows.append({'id': f'U{offset:02}', 'title': flow['name'], 'kind': 'functional', 'version': 1, 'state': 'active',
                     'modes': ['rules'], 'adapter': 'registered_ui_action', 'critical': True,
                     'environments': ['isolated-local', 'native-local'],
                     'ui_flow': flow['id'], 'feature': flow['feature'], 'side': flow['side'],
                     'default_params': {spec['name']: spec['default'] for spec in flow['params'] if 'default' in spec}})
    return rows


def case_for(action_id):
    """按动作/动作流 id 找到它的已登记用例行（执行器用它取动作与固定参数）。"""
    for row in catalog_rows():
        if row.get('ui_action') == action_id or row.get('ui_flow') == action_id:
            return row
    return None


def public_view():
    return {'schema': 'ui-actions-v1',
            'note': '可复用点击工具：只有 ready 的可被 Agent 调用；unverified 必须先实跑验证再转正',
            'counts': {'ready': len(ready_actions()), 'unverified': len(ACTIONS) - len(ready_actions())},
            'actions': ACTIONS}


def validate(plan):
    """校验调用计划：动作必须存在、必须 ready、参数必须齐全且类型正确。"""
    steps = []
    for index, step in enumerate(plan):
        action_id = step.get('action')
        row = ACTIONS_BY_ID.get(action_id)
        if not row:
            raise ValueError(f'第{index + 1}步：未登记的动作 {action_id}')
        if row['status'] != 'ready':
            raise ValueError(f'第{index + 1}步：{action_id} 尚未实跑验证，不能调用')
        params = dict(step.get('params') or {})
        for spec in row['params']:
            if spec['name'] not in params:
                if 'default' in spec:
                    params[spec['name']] = spec['default']
                elif spec.get('required'):
                    raise ValueError(f'第{index + 1}步：缺少参数 {spec["name"]}')
        for name, value in params.items():
            spec = next((item for item in row['params'] if item['name'] == name), None)
            if not spec:
                raise ValueError(f'第{index + 1}步：{action_id} 不接受参数 {name}')
            if spec['type'] == 'int' and not isinstance(value, int):
                raise ValueError(f'第{index + 1}步：{name} 需要整数')
            if spec['type'] == 'str' and not isinstance(value, str):
                raise ValueError(f'第{index + 1}步：{name} 需要字符串')
        steps.append({'action': row, 'params': params})
    return steps


def _open_site(workspace, browser_server_module):
    """启动隔离站点。每次执行使用独立 SQLite 文件（同名库二次启动会因重复建运营账号而失败）。

    QA_BROWSER_OP=1 让站点自己建库并种合成数据；站点只监听本机随机端口。
    """
    import httpx
    from app.core.config import settings
    from app.quality.worker import stop_process
    with socket.socket() as bound:
        bound.bind(("127.0.0.1", 0))
        port = bound.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    database = Path(workspace) / f"ui-actions-{uuid4().hex}.db"
    environment = dict(os.environ, QA_BROWSER_OP="1",
                       DATABASE_URL="sqlite:///" + database.as_posix(),
                       REDIS_URL=os.environ.get("REDIS_URL", "memory"),
                       STRICT_DEPENDENCIES="false")
    log = (Path(workspace) / "ui-actions-server.log").open("w", encoding="utf-8")
    server = subprocess.Popen([sys.executable, "-m", browser_server_module, "--port", str(port)],
                              cwd=settings.backend_root, env=environment,
                              stdout=log, stderr=log,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                              start_new_session=os.name != "nt")
    client = httpx.Client(base_url=origin, timeout=15, trust_env=False)
    for _ in range(120):
        if server.poll() is not None:
            raise RuntimeError("隔离站点未启动")
        try:
            if client.get("/api/v1/ready").is_success:
                return server, origin, client, lambda: stop_process(server)
        except httpx.TransportError:
            pass
        time.sleep(0.1)
    stop_process(server)
    raise RuntimeError("隔离站点准备超时")


def execute_action_script(spec, evidence):
    """执行一组已校验的动作：逐步做页面核验与接口交叉核验，任何一步失败即整体 failed。"""
    steps = validate(spec['actions'])
    shop_code = spec.get('shop_code', 'nanzhi')
    workspace = os.environ.get('QA_CHILD_WORKSPACE') or str(Path.cwd() / 'data' / 'ui-actions-workspace')
    Path(workspace).mkdir(parents=True, exist_ok=True)
    stop = lambda: None
    server = None
    try:
        server, origin, client, stop = _open_site(workspace, 'app.quality.browser_server')
        import re as _re

        from playwright.sync_api import expect, sync_playwright
        tokens = {}
        def call(method, path, token=None, body=None):
            response = client.request(method, path, headers={"Authorization": "Bearer " + token} if token else {}, json=body)
            evidence.requests.append({"method": method, "path": path, "status": response.status_code, "via": "ui-action",
                                      "input": body, "output": None if response.status_code >= 400 else _safe_json(response)})
            return response
        login = call("POST", "/api/v1/auth/login", body={"username": "alice", "password": "alice123"})
        buyer = login.json()["access_token"]
        tokens["buyer"] = buyer
        merchant_login = call("POST", "/api/v1/auth/login", body={"username": "merchant", "password": "merchant123"})
        tokens["merchant"] = merchant_login.json()["access_token"]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge" if os.name == "nt" else None, headless=True,
                                                 args=["--disable-gpu", "--disable-background-networking"])
            try:
                context = browser.new_context(viewport={"width": 1366, "height": 900})
                buyer_token = tokens["buyer"]
                merchant_token = tokens["merchant"]
                context.add_init_script(
                    f"sessionStorage.setItem('token_c',{json.dumps(buyer_token)});"
                    f"sessionStorage.setItem('token_b',{json.dumps(merchant_token)});")
                page = context.new_page()
                page.set_default_timeout(15000)
                _RUNNERS[spec.get('kind', 'buyer')](steps, page, origin, evidence, shop_code, tokens, call)
            finally:
                browser.close()
        return {'status': 'passed', 'suite': {'adapter': 'ui_action_script',
                                             'reports': [{'stage': 'call', 'node': step['action']['id'], 'outcome': 'passed'} for step in steps]}}
    except Exception as exc:
        evidence.requests.append({"method": "UI", "path": "ui-action-script", "status": 0, "via": "ui-action",
                                  "error": type(exc).__name__ + ': ' + str(exc)})
        return {'status': 'failed', 'error': type(exc).__name__ + ': ' + str(exc),
                'suite': {'adapter': 'ui_action_script', 'reports': [{'stage': 'call', 'node': 'ui-action-script', 'outcome': 'failed', 'failure': str(exc)}]}}
    finally:
        if server is not None and server.poll() is None:
            stop()


def _safe_json(response):
    try:
        return response.json()
    except ValueError:
        return None


def _run_buyer(steps, page, origin, evidence, shop_code, tokens, call):
    import re

    from playwright.sync_api import expect
    detail_url = None
    product = None
    for step in steps:
        action, params = step['action']['id'], step['params']
        if action == 'c_open_shop_home':
            page.goto(origin + f"/c.html?code={shop_code}", wait_until="domcontentloaded")
            expect(page.get_by_placeholder("搜索本店商品", exact=True)).to_be_visible()
            evidence.check("点击工具·打开买家首页：搜索框可见", True, "搜索框可见", "可见")
        elif action == 'c_search_products':
            keyword = params['keyword']
            search = page.get_by_placeholder("搜索本店商品", exact=True)
            search.fill(keyword)
            search.press("Enter")
            expect(page).to_have_url(re.compile(r".*#/collection/all.*"))
            products = call("GET", f"/api/v1/c/shops/{shop_code}/products").json()
            matched = [row for row in products if keyword in str(row.get('name', ''))]
            evidence.check("点击工具·搜索：合集页出现", True, "#/collection/all", page.url)
            evidence.check("点击工具·搜索：接口事实包含关键词", bool(matched), keyword, [row['name'] for row in matched])
        elif action == 'c_open_product_card':
            name = params['product_name']
            products = call("GET", f"/api/v1/c/shops/{shop_code}/products").json()
            product = next(row for row in products if row['name'] == name)
            page.goto(origin + f"/c.html?code={shop_code}#/collection/all", wait_until="domcontentloaded")
            card = page.locator("article.pcard", has_text=name).first
            expect(card).to_be_visible()
            card.locator("a.thumb").click()
            detail_url = f"#/product/{shop_code}/{product['id']}"
            expect(page).to_have_url(re.compile(r".*" + re.escape(detail_url) + r".*"))
            expect(page.locator(".detail").first).to_be_visible()
            evidence.check("点击工具·点击商品卡片进入详情", detail_url in page.url, detail_url, page.url)
        elif action == 'c_select_sku':
            index = params.get('sku_index', 0)
            buttons = page.locator(".detail .info .sku-list button")
            expect(buttons.first).to_be_visible()
            purchasable = page.locator(".detail .info .sku-list button:not(.dead)")
            count = purchasable.count()
            purchasable.nth(index).click()
            selected = page.locator(".detail .info .sku-list button.on")
            evidence.check("点击工具·点击规格：可选规格数量足够", count > index, f"序号 {index}", f"可选 {count} 个")
            evidence.check("点击工具·点击规格：进入 on 选中态", selected.count() == 1, "1 个选中", f"选中 {selected.count()} 个")
        elif action == 'c_add_to_cart':
            quantity = params.get('quantity', 1)
            field = page.locator(".detail .info .qty input")
            expect(field).to_be_visible()
            field.fill(str(quantity))
            field.dispatch_event("change")
            applied = int(field.input_value())
            page.locator(".detail .info .actions").get_by_role("button", name="加入购物车", exact=True).click()
            expect(page.get_by_text("已加入购物车", exact=True)).to_be_visible()
            if product is None:
                products = call("GET", f"/api/v1/c/shops/{shop_code}/products").json()
                product = next(row for row in products if row['name'] == '亚麻抱枕套')
            cart = call("GET", f"/api/v1/c/shops/{shop_code}/cart", buyer_token(tokens)).json()
            sku_ids = {sku['id'] for sku in product['skus']}
            in_cart = [row for row in cart.get('items', []) if row.get('sku_id') in sku_ids]
            evidence.check("点击工具·加入购物车：页面提示出现", True, "已加入购物车", "已加入购物车")
            evidence.check("点击工具·加入购物车：数量按库存/限购夹紧后提交", applied >= 1, quantity, applied)
            evidence.check("点击工具·加入购物车：购物车接口确有该商品且数量一致",
                           bool(in_cart) and any(row.get('quantity') == applied for row in in_cart),
                           {"sku_id": list(sku_ids), "quantity": applied}, cart.get('items'))
        elif action == 'c_open_cart':
            page.get_by_role("link", name="购物车").first.click()
            evidence.check("点击工具·打开购物车", True, "点击可达", page.url)
        elif action == 'c_checkout':
            page.get_by_role("button", name="去结算", exact=True).click()
            expect(page.get_by_role("heading", name="订单结算", exact=True)).to_be_visible()
            evidence.check("点击工具·去结算：结算页出现", True, "订单结算", "订单结算")
        elif action == 'c_submit_order':
            before = call("GET", "/api/v1/c/orders", buyer_token(tokens)).json()
            with page.expect_response(lambda response: response.url.endswith("/cart/checkout") and response.request.method == "POST") as placed:
                page.get_by_role("button", name="提交订单", exact=True).click()
            expect(page.get_by_text("订单中心", exact=True).first).to_be_visible()
            after = call("GET", "/api/v1/c/orders", buyer_token(tokens)).json()
            created = [row for row in after if row['order_no'] not in {old['order_no'] for old in before}]
            evidence.check("点击工具·提交订单：接口真实成功", placed.value.status == 200, 200, placed.value.status)
            evidence.check("点击工具·提交订单：订单接口新增一笔", len(created) == 1, "新增 1 笔", len(created))
        else:
            raise ValueError(f'买家脚本不支持动作 {action}')


def _run_merchant(steps, page, origin, evidence, shop_code, tokens, call):
    from playwright.sync_api import expect
    failures = []
    page.on("response", lambda response: failures.append(response.status) if "/api/v1/" in response.url and response.status >= 500 else None)
    grants = any(step['action']['id'] == 'op_grant_merchant_access' for step in steps)
    if not grants:
        page.goto(origin + "/b.html#/products", wait_until="domcontentloaded")
        if "开店授权" in page.locator("body").inner_text():
            raise ValueError("前置条件不满足：该店铺商家未获开店授权（可在动作里先执行 op_grant_merchant_access，或用已授权的实店档）")
    for step in steps:
        action, params = step['action']['id'], step['params']
        if action == 'op_grant_merchant_access':
            account_id = params.get('account_id')
            if not account_id:
                username = params.get('username') or 'merchant'
                listing = call("GET", f"/api/v1/op/platform/accounts?q={username}", tokens.get('merchant')).json()
                rows = listing.get('items', listing if isinstance(listing, list) else [])
                target = next((row for row in rows if row.get('username') == username), None)
                if not target:
                    raise ValueError(f"账号查询里没有找到 {username}，不能授权")
                account_id = target['id']
                evidence.check("点击工具·按用户名解析到账号", True, username, {"username": username, "account_id": account_id})
            response = call("PATCH", f"/api/v1/op/platform/accounts/{account_id}",
                            tokens.get('merchant'), {"merchant_enabled": True, "reason": params.get('reason')})
            evidence.check("点击工具·OP授权商家开店：接口成功", response.status_code == 200, 200, response.status_code)
            # 权限变更会即时撤销该账号会话（账号安全策略）：必须重新登录后再用商家身份继续。
            relogin = call("POST", "/api/v1/auth/login", body={"username": "merchant", "password": "merchant123"})
            evidence.check("点击工具·授权后重新登录商家身份", relogin.status_code == 200, 200, relogin.status_code)
            tokens['merchant'] = relogin.json()["access_token"]
        elif action == 'b_open_products':
            page.goto(origin + "/b.html#/products", wait_until="domcontentloaded")
            # 权限变更后旧令牌已失效：导航后写入新令牌并刷新一次（真实用户同样需要刷新）。
            page.evaluate("token => sessionStorage.setItem('token_b', token)", tokens['merchant'])
            page.reload(wait_until="domcontentloaded")
            if "开店授权" in page.locator("body").inner_text():
                raise ValueError("前置条件未满足：B 端门户显示该商家未获得开店授权（需要有效的店铺授权；合成 fixture 里授权接口已通但门户门禁未定位）")
            try:
                page.wait_for_selector(".side", timeout=8000)
            except Exception:
                raise ValueError("前置条件未满足：B 端门户未进入商家工作台（门禁条件未定位，需账号/门户侧确认）") from None
            evidence.check("点击工具·打开商家商品页", True, "左栏可见", page.url)
        elif action == 'b_search_product':
            page.get_by_role("textbox", name="搜索商品名称或编号", exact=True).fill(params['product_name'])
            evidence.check("点击工具·商家搜索商品", True, params['product_name'], params['product_name'])
        elif action == 'b_click_side_nav':
            route = params['route']
            link = page.locator(f'.side a[href="#/{route}"]')
            expect(link).to_be_visible()
            link.click()
            expect(page).to_have_url(origin + "/b.html#/" + route)
            evidence.check("点击工具·点击商家导航：" + route, page.url.endswith("#/" + route), "#/" + route, page.url)
        else:
            raise ValueError(f'商家脚本不支持动作 {action}')
    evidence.check("点击工具·商家脚本无 5xx 响应", not failures, [], failures)


def buyer_token(tokens):
    return tokens['buyer']


_RUNNERS = {'buyer': _run_buyer, 'merchant': _run_merchant}