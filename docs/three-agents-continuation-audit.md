# 三个 Agent 续作核查与执行链路补强

核查日期：2026-10-21。基线提交：`d8b54b4`；不覆盖其他开发者正在进行的 OP 治理用例、中文报告及页面改动。

## 1. 需求核对

当前已有业务 Agent、业务 Agent 评测、功能测试三个独立职责。OP 已提供六页测试中心、固定用例步骤/预期/源码、用例版本审核、计划批准、隔离运行、报告比较与保留策略。B/C 不应获得测试能力。

本次补强两项验收要求：

- 只修改用例说明文字，不应让已批准计划的执行目标失效；修改执行代码仍必须使旧批准失效。
- 自定义用例的“必需工具成功”不能由回答文本或工具返回文案证明，必须有本轮、同用户、同会话的真实成功审计记录。拒绝、无审计、跨身份、跨会话及历史轮次记录均不能冒充本次成功。

## 2. 技术方案与实现

- `service.fingerprint()` 仅显式排除六个 `case_docs*.py` 纯说明模块（含续作新增的 OP 用例文案），继续纳入业务代码、工具实现、测试执行器及测试代码；不用宽泛目录排除削弱审批绑定。
- `case_versions.execute_definition()` 每轮请求前记录审计 ID 高水位，请求后读取更大 ID 且用户与返回会话匹配的 `AgentToolLog`。必需工具同时满足响应工具轨迹存在、审计 `ok=true` 才通过。
- 审计证据仅记录 ID、工具名、成功标记和拒绝原因，不复制工具参数、口令或访问令牌。
- 原有声明式 schema、真实模型模式、共享预算、固定子进程合成环境和父任务审批校验保持不变。

## 3. 本批验证

- `test_quality_execution_boundaries.py` 新增七项：文案/代码指纹边界，以及成功、拒绝、缺失、跨用户、跨会话、历史轮次六种工具审计场景。模拟模型响应的专项只证明判定逻辑，不能当作真实模型验收。
- 联合版本管理、Agent 文档及质量平台测试：31 项通过。测试夹具短 JWT 密钥告警为既有测试配置，不是生产密钥。
- 扩大至报告、历史清理对抗测试与原生依赖专项后：48 项通过；JS 语法、OP Node 回归与差异空白检查通过。
- 独立子进程真实自定义商品搜索：DeepSeek V4 Pro 三次 HTTP 200，3428 tokens，执行与清理通过；报告 `backend/data/acceptance/quality-custom-executor-live.json`。这是执行器烟测，不冒充经 OP 页面新建与批准的完整端到端验收。

复现确定性验证（在 backend 目录）：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_quality_execution_boundaries.py tests/test_quality_case_versions.py tests/test_quality_agents_docs.py tests/test_quality.py -q --basetemp=data/acceptance/pytest-execution -p no:cacheprovider
```

## 4. 已有历史证据核验

以下本地报告实际存在且所有条目通过、清理成功；它们证明各自生成时的版本，不代表本次并行修改后的整库重新验收：

- `quality-assistant-release-live.json`：40/40 个真实业务 Agent 场景。
- `quality-native-functional-all.json`：30/30 个原生 MySQL/Redis 功能场景。
- `quality-native-assistant.json`：4/4 个原生依赖助手代表场景。
- `quality-browser-release.json`：E01—E03 共 3/3；后续 E04 的独立验收及用例版本操作另有报告，不混成同一批全量结果。
- `three-agents-final-tests.log`：之前一次后端回归 334 项通过；后续其他实现提交另有 354 项记录，不混称当前工作区的回归结果。

旧台账中“40 条全量真实验收尚未完成”是更早批次状态，应以对应报告和版本区分；同样不能把已登记用例数直接展示成当前版本通过数。

## 5. 仍需区分的边界

- H01—H10 平台自身测试有部分专项覆盖，但尚不能据此宣称十条均已独立登记并在 OP 一键执行。
- native-local 与 isolated-local 是不同验收档；E04 不支持原生档，不能将 SQLite 浏览器证据称为 MySQL 浏览器验收。
- 语义评分校准、真实负载基准、MCP 对外开放及自动发布不因本批补强而自动完成。
- 本批不重启正在使用的服务、不更改实际店铺数据、不修改显卡/虚拟化，不提交或发布其他开发者的并行改动。
