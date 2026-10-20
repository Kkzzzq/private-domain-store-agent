"""三类 Agent 的说明卡：角色、用法、如何修改、源码入口。

内容刻意与实现同源：工具清单直接读 `app.agent.tools.SPECS`，模型读运行时 settings，
接入用例数由 catalog 现算，避免文档漂移。运行统计由 API 层从数据库补齐。
"""


def _business():
    from app.agent.tools import SPECS
    from app.core.config import settings
    return {
        "id": "business",
        "name": "业务 Agent（助手）",
        "kind": "assistant",
        "role": "面向买家与商家的业务助手：真实回答商品、库存、价格、订单、物流、售后与平台政策问题。",
        "purpose": "把「用户问什么」翻译成对业务数据与知识库的受控查询，再用事实组织回答；不靠模型记忆编造业务信息。",
        "entry_points": [
            {"name": "买家助手", "value": "POST /api/v1/c/shops/{shop_id}/chat"},
            {"name": "商家助手", "value": "POST /api/v1/b/chat"},
            {"name": "会话上下文", "value": "Redis 会话 + 历史截断/摘要，跨用户隔离"},
        ],
        "model": {
            "provider": getattr(settings, "model_provider", "unknown"),
            "cloud_style": getattr(settings, "cloud_api_style", ""),
            "cloud_model": getattr(settings, "cloud_model", ""),
            "ollama_model": getattr(settings, "ollama_model", ""),
            "note": "改模型只改 backend/.env，不改代码；质量中心评测时用的是同一套模型配置。",
        },
        "tools": sorted(SPECS),
        "guardrails": [
            "工具优先：业务数字必须来自工具或知识库，禁止凭记忆回答",
            "越权保护：跨用户/跨店铺的订单与数据一律拒绝",
            "写操作需确认：加购、下单、改价等以「待确认提案」形式返回，不直接落库",
            "失败可观测：工具失败/缺参数有重试、澄清与兜底回复，并记录调用轨迹",
        ],
        "how_to_use": [
            "以合成买家（alice）或商家（merchant）身份登录后直接对话",
            "在 OP「评测Agent」页建评测计划，用 A 类用例真实跑一遍助手",
            "回答与工具轨迹在「测试用例运行与报告」里逐条查看",
        ],
        "how_to_modify": [
            {"what": "提示词与人设", "where": "backend/app/agent/prompts.py"},
            {"what": "新增/修改业务工具", "where": "backend/app/agent/tools.py（SPECS + 实现）"},
            {"what": "编排与多轮上下文", "where": "backend/app/agent/assistant.py, context.py, intent.py"},
            {"what": "权限与安全护栏", "where": "backend/app/agent/guard.py"},
            {"what": "换模型/供应商", "where": "backend/.env（MODEL_PROVIDER / CLOUD_MODEL 等）"},
            {"what": "知识库与向量索引", "where": "backend/app/rag/knowledge.py, routing.py + 重建索引"},
        ],
        "sources": [
            "backend/app/agent/assistant.py", "backend/app/agent/prompts.py", "backend/app/agent/tools.py",
            "backend/app/agent/guard.py", "backend/app/agent/context.py", "backend/app/agent/intent.py",
            "backend/app/agent/model.py", "backend/app/rag/knowledge.py", "backend/app/rag/routing.py",
        ],
        "capabilities": ["qa.view", "qa.assistant.run"],
    }


def _evaluator():
    return {
        "id": "evaluator",
        "name": "评测 Agent",
        "kind": "assistant",
        "role": "专门评测其它 Agent 的 Agent：给业务 Agent（助手）出题、执行、并按硬断言判分。",
        "purpose": "把「助手答得好不好」变成可复现的证据：真实模型规划 + 受限工具选用例 + 隔离子进程执行 + 断言判定。",
        "entry_points": [
            {"name": "新建评测计划", "value": "POST /api/v1/op/qa/plans（kind=assistant）"},
            {"name": "AI 规划", "value": "worker 调真实模型，经 read_test_capabilities → propose_test_plan 选用例"},
            {"name": "执行", "value": "POST /runs → 队列 → 独立 worker 子进程（SQLite + 内存 Redis 隔离）"},
        ],
        "model": {
            "provider": "与业务 Agent 同源的云端模型（规划阶段计费）",
            "note": "规划与被测助手调用都计入预算；无额度/未调用工具一律记阻塞，不用规则答案补成通过。",
        },
        "tools": ["read_test_capabilities", "propose_test_plan"],
        "guardrails": [
            "计划必须人工批准，批准绑定内容摘要；改动后需重新批准",
            "真实模式必须 mode=llm，规则回退不能通过真实链路门禁",
            "执行器只跑已登记用例，不接受任意命令/SQL/URL/模型生成代码",
            "复杂场景只允许 live，不能用规则替代",
        ],
        "how_to_use": [
            "OP「评测Agent」页 → 新建业务 Agent 评测 → 选用例/模式/预算",
            "检查用例、环境、代码指纹与规划方式后批准，再启动",
            "在「测试用例运行与报告」看三栏证据：对话与工具轨迹 / 可信事实与断言",
        ],
        "how_to_modify": [
            {"what": "规划提示与工具契约", "where": "backend/app/quality/planner.py"},
            {"what": "新增/修改 A 类用例", "where": "backend/app/quality/scenarios.py, assistant_scenarios.py, rag_scenarios.py"},
            {"what": "用例清单与接入状态", "where": "backend/app/quality/catalog.py"},
            {"what": "隔离执行与预算/断言记录", "where": "backend/app/quality/case_runner.py, sandbox.py"},
            {"what": "队列、租约与子进程调度", "where": "backend/app/quality/worker.py, queue.py, service.py"},
        ],
        "sources": [
            "backend/app/quality/planner.py", "backend/app/quality/case_runner.py", "backend/app/quality/sandbox.py",
            "backend/app/quality/worker.py", "backend/app/quality/catalog.py", "backend/app/quality/scenarios.py",
            "backend/app/quality/assistant_scenarios.py", "backend/app/quality/rag_scenarios.py",
        ],
        "capabilities": ["qa.view", "qa.assistant.run", "qa.approve"],
    }


def _functional():
    return {
        "id": "functional",
        "name": "功能测试 Agent",
        "kind": "functional",
        "role": "专门测试业务功能的 Agent：跑已登记的接口用例与真实浏览器用例，验证业务状态机与权限边界。",
        "purpose": "用固定节点而不是模型文案证明功能对错：pytest 断言 API 行为，Playwright 断言真实页面行为。",
        "entry_points": [
            {"name": "新建功能测试计划", "value": "POST /api/v1/op/qa/plans（kind=functional）"},
            {"name": "接口用例", "value": "adapter=registered_pytest（每用例一个真实 pytest 节点）"},
            {"name": "浏览器用例", "value": "adapter=registered_browser（隔离起服务 + 真实 Edge/Chromium）"},
        ],
        "model": {"provider": "不调用模型（固定回归 0 tokens）", "note": "只有规划/解释阶段才计费。"},
        "tools": [],
        "guardrails": [
            "只执行白名单里的 pytest 节点与浏览器场景，无任意命令/URL",
            "每条用例独立子进程与合成数据，不写现有店铺库",
            "清理失败不放行；库存/订单类用例必须核对前后状态",
            "浏览器用例保存截图作为 UI 证据",
        ],
        "how_to_use": [
            "OP「功能测试Agent」页 → 新建功能测试计划 → 批准 → 启动",
            "或在「测试用例管理」里单条/批量/一键全部运行",
            "失败用例在报告里标红，UI 用例可直接看截图",
        ],
        "how_to_modify": [
            {"what": "新增接口用例", "where": "backend/app/quality/catalog.py（FUNCTIONAL_TITLES + FUNCTIONAL_TESTS 映射）+ backend/tests/test_*.py"},
            {"what": "新增浏览器用例", "where": "backend/app/quality/browser.py（BROWSER_CASES + execute_browser）"},
            {"what": "执行入口与断言收集", "where": "backend/app/quality/case_runner.py"},
            {"what": "隔离服务与端口", "where": "backend/app/quality/browser_server.py"},
            {"what": "用例文案（步骤/预期/代码文件）", "where": "backend/app/quality/case_docs*.py"},
        ],
        "sources": [
            "backend/app/quality/browser.py", "backend/app/quality/browser_server.py",
            "backend/app/quality/case_runner.py", "backend/app/quality/catalog.py",
            "backend/app/quality/case_docs.py", "backend/app/quality/case_docs_functional.py",
            "backend/app/quality/case_docs_browser.py",
        ],
        "capabilities": ["qa.view", "qa.functional.run", "qa.approve"],
    }


def descriptors():
    return [_business(), _evaluator(), _functional()]