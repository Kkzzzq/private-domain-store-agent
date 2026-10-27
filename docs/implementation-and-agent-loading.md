# 已实现能力与线上验收

以下是代码与实际验收范围，不表示所有业务分支都已获得自动化覆盖。

- 交易接口、商品状态、SKU 与权限：`backend/app/api/b_api.py`、`c_api.py`、`op_api.py` 及 `backend/app/services/`。MySQL 保存业务数据，Redis 保存会话与缓存。当前支付、退款、物流是演示流程，未对接外部支付机构和快递服务。
- SPU/SKU/C 端一致性：B/OP 商品管理读权威 SPU/SKU，C 端展示读宽表；草稿、上架、下架、禁售均为状态。规则与迁移见 `catalog-data-model.md`。对应 `test_c_projection.py`、`test_catalog_migration.py`、`test_bc_catalog_boundaries.py`、`test_op_business_states.py`。
- 店铺配置和交易回归：`test_decoration.py`、`test_bc_link.py`、`test_bc_trade_boundaries.py`，以及 `quality/real_scenarios_ui.py` 的真实 Playwright 场景。用例共用 UI 操作和交易步骤，接口断言与页面覆盖分别记录。
- 三类 Agent：`agent/assistant.py` 的业务工具循环；`quality/intake_driver.py`、`functional_driver.py` 的需求受理和批准后执行；`quality/agent_evaluation.py` 的程序核验、模型评分与人工复核。模型调用均通过受控工具，不以模型声称成功替代业务断言。
- RAG：`rag/cleaner.py` 清洗分块，`rag/knowledge.py`、`routing.py` 使用千问 Embedding 和持久化 Chroma，保留文档来源、模型与输入格式。2026-10-27 补齐线上 API 环境缺少的 Chroma 和旧 Linux SQLite 兼容依赖；14 个知识块实际写入，售后问题命中真实文档。失败时仍允许有明确记录的关键词兜底，不能把兜底结果称为向量命中。
- 上下文：`services/session.py` 使用用户、店铺、角色、会话组合键隔离 Redis 记忆，`compact_messages` 截断并摘要历史。真实模型回归包含会话隔离、订单隐私和多轮追问。
- 工具安全：`agent/guard.py`、`tools.py` 负责工具白名单、Pydantic 参数校验、身份范围与调用审计；`agent/model.py`、`assistant.py` 处理重试、异常和兜底。严格验收要求 `mode=llm`。

上一版 `c7555fb` 已部署：全量 565 passed / 7 skipped；线上 16 项真实模型回归报告 `cd27e95063ce4b899787e26d980c1ac5` 全通过，185 条断言，实际模型均为 qwen-flash。商品三端完整功能与页面报告 `35d556551e3e441f8ff654e23c02300c` 为 60 项、1004 条断言、26 张截图；它们是各自版本的证据，不混成同一轮。

## Agent 标签页加载优化

原列表虽然使用 brief 响应，服务端仍逐份读取完整计划与证据 JSON，随后才裁剪；Agent 统计也逐个加载计划，造成重复 SQL。三个页面必须等待这些请求全部完成才渲染。

现在 brief 列表用固定数量的批量查询和 SQL JSON 字段投影，只读取状态、计数和清理标记；沿用相同的汇总判定函数。完整证据、失败原因和截图依然按点击下载，不删减原始报告。

Agent 统计批量读取计划的诊断标记。前端在同一账号的三个 Agent 页面间复用十秒内元数据；写操作立即失效、显式刷新重新请求、退出登录清空，活动任务继续轮询。缓存不跨账号，报告详情保持原有独立下载缓存。

新增回归同时检查报告结果一致、缺失子运行不得判通过、批量查询数量不会随报告逐份增长，以及写操作/退出登录清理页面缓存。

启用真实向量后补充验证发现：包含唯一编号的不存在商品查询可能召回语义相似卡片。搜索现在把明确型号/编号作为硬约束，逐 SKU 核验，完全不存在时直接返回空；普通自然语言查询仍保留语义召回。原失败报告保留。

推荐支持明确的 AND 必含词与 OR 任选词组；若模型把用户本轮明说的“A或B”误填为AND，执行器仅按该原话恢复任选关系，保留其它必含、排除、数量与预算约束，否定句不作正向任选。精确分类的冗余泛称不会再错误过滤商品。工具循环耗尽必须进入异常/兜底流程，不能用固定提示冒充完成的模型回答。
