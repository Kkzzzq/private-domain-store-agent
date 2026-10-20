"""E01–E04 用例的执行步骤、预期结果与对应浏览器适配器入口。

步骤与预期按 app/quality/browser.py 的 execute_browser 真实动作与
evidence.check 断言编写；code_node 统一指向该分支的调用入口。
"""

DOCS = {
    "E01": {
        "steps": [
            "夹具接口登录买家与商家，读取南栀店铺商品",
            "商家发券、买家领券，并记录下单前的订单号集合",
            "浏览器打开亚麻抱枕套详情，点第一个 SKU 再点加入购物车",
            "进入购物车去结算，确认页面出现优惠抵扣",
            "点提交订单并等待 /cart/checkout 返回 200",
            "跳转订单中心后读取订单列表核对新订单",
        ],
        "expected": [
            "页面依次可见已加入购物车、订单结算与优惠抵扣",
            "提交订单接口真实返回 200，并进入订单中心",
            "新增恰好 1 笔订单且 discount_yuan 为 10 元",
            "证据包含 real_browser 请求与全页截图",
        ],
        "code_file": "backend/app/quality/browser.py",
        "code_node": 'execute_browser("E01", evidence)',
        "risk": "writes",
    },
    "E02": {
        "steps": [
            "以商家身份打开 b.html 商品页并搜索目标商品",
            "展开该商品 SKU 表，读取每行 data-sort-id",
            "聚焦首行拖拽手柄并按 ArrowDown 触发排序保存",
            "回到 c.html 详情页读取 SKU 按钮的 data-sku-id",
        ],
        "expected": [
            "排序保存接口 /skus/sort 返回 200",
            "期望顺序为交换前两位、其余保持原顺序",
            "买家端首个 SKU 按钮的 data-sku-id 等于期望首位",
            "C 端 DOM 的 SKU 顺序与期望列表完全一致",
        ],
        "code_file": "backend/app/quality/browser.py",
        "code_node": 'execute_browser("E02", evidence)',
        "risk": "writes",
    },
    "E03": {
        "steps": [
            "打开买家页 c.html 并检查测试插件脚本",
            "打开 OP 测试入口页面 op.html",
            "用买家令牌直接请求 OP 用例接口",
            "记录页面截图与真实浏览器请求证据",
        ],
        "expected": [
            "买家页面没有加载 op-quality 测试插件脚本",
            "未登录进入 OP 页面时可见欢迎回来的登录门",
            "买家身份请求 /api/v1/op/qa/cases 返回 403",
            "证据中存在 real_browser 请求与全页截图",
        ],
        "code_file": "backend/app/quality/browser.py",
        "code_node": 'execute_browser("E03", evidence)',
        "risk": "read-only",
    },
    "E04": {
        "steps": [
            "以商家管理员登录 OP 并进入运营工作台",
            "在测试用例与能力中新增助手用例并保存候选",
            "审核启用后新建版本并保存第二版",
            "新建业务 Agent 评测，勾选用例并生成待审批计划",
            "批准计划并启动，轮询直到任务全部完成",
            "新建重跑、生成版本报告对比、预览清理范围",
        ],
        "expected": [
            "新版本保存返回 201",
            "用例存在 active 第 1 版与 candidate 第 2 版两个版本",
            "首个任务的所有用例结果状态都为 passed",
            "重跑后可见报告差异标题，清理预览显示将清理 0 次",
            "证据包含真实浏览器请求与全页截图",
        ],
        "code_file": "backend/app/quality/browser.py",
        "code_node": 'execute_browser("E04", evidence)',
        "risk": "writes",
    },
}
DOCS["E05"] = {"steps":["在真实浏览器（Edge/Chromium）登录OP并打开店铺完整维护", "通过表单修改公告保存，读取B和C接口核对", "查询数据库维护审计，再点击冻结与解冻检查C端商品"], "expected":["表单保存200，B和C公告与输入一致", "操作审计包含真实原因和成功状态", "冻结后C端无商品，解冻后恢复；保存现场截图"], "code_file":"backend/app/quality/browser.py", "code_node":"execute_browser(E05)", "risk":"writes"}
DOCS.update({
    "E06": {"steps": ["登录OP并进入测试用例管理", "依次点击Agent、接口、UI三类用例", "输入不存在的用例名称搜索"], "expected": ["三个分类均可点击且显示已接入用例", "无匹配时展示明确空态，不显示其他用例", "保存真实请求证据及页面截图"], "code_file": "backend/app/quality/browser_extra.py", "code_node": "execute(E06)", "risk": "read-only"},
    "E07": {"steps": ["以商家身份打开商品页", "依次点击商品、订单、店铺设置和经营概览导航", "检查路由地址、侧栏可见性及接口错误"], "expected": ["各导航可以点击且路由与目标一致", "未出现服务端500类响应", "保存实际页面截图"], "code_file": "backend/app/quality/browser_extra.py", "code_node": "execute(E07)", "risk": "read-only"},
    "E08": {"steps": ["打开南枝小店买家首页", "搜索不存在的商品并按回车", "重新打开首页核对搜索恢复"], "expected": ["搜索进入全部商品页并显示没有找到相关商品", "重新打开首页输入框为空", "保存真实页面和请求证据"], "code_file": "backend/app/quality/browser_extra.py", "code_node": "execute(E08)", "risk": "read-only"},
})
