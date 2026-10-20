# OP智能测试中心：运行与验收

## 当前交付边界

这是持续分批实现，不是全部规划能力交付。2026-10-20第三批已接入全部30条功能API场景、原生MySQL/Redis隔离档、浏览器E2E，以及用例版本审批、报告对比与历史保留清理；40条助手真实模型全量验收、MCP对外开放与自动发布仍未交付。

- OP独立“Agent 与测试中心”：三个Agent总览、业务Agent评测、业务功能测试、测试用例与能力、运行与报告；兼容 `op.html#/testing/assistant` 等深链接。
- 助手Agent和功能Agent分别规划、选工具、执行与汇总；可建联合运行，功能回归先执行，助手使用另一个独立合成数据副本。
- 40条助手规划现已登记执行适配，复杂场景仅允许live模式，不能用规则替代。全部真实模型验收仍进行中，不能将已登记视为40/40通过；30条功能API规划已接入并通过隔离回归。平台自身质量回归另行统计。
- 固定计划不调用规划模型；AI规划通过真实 `read_test_capabilities → propose_test_plan` Function Calling 选受限用例，必须人工批准。
- 执行器使用已登记场景和Pytest固定入口；无任意命令、SQL、URL或模型生成代码执行。
- 助手测试支持规则/直接查询模式与真实云端模型模式，分开标记。真实模式必须得到 `mode=llm`，规则回退不能通过真实链路门禁。
- QA元数据可用现有MySQL，队列和执行槽位用现有Redis；被测业务数据是每条用例独立子进程中的SQLite/内存Redis，不能把QA元数据的MySQL/Redis连接算作真实业务依赖联调。
- Chroma真实向量评测A15/A16/A35/A36已用DeepSeek+千问Embedding通过。用例版本审批、报告对比、历史保留与清理、浏览器E2E已在本地真实通过（见下节与验收记录）；MCP对外开放、自动发布、40条助手真实模型全量验收未交付，不伪装完成。

## 用例版本、报告对比与历史清理

- 用例版本：自定义助手用例（`C`+11位）先存为候选，审核启用后才能进计划；已启用版本不可就地修改，编辑只能新建版本（同一 `family_id` 递增 `version`），批准绑定 `revision_digest`。计划与运行冻结生成时的用例快照，用例撤销或版本变化后旧批准不能启动，历史报告不被新版本改写。
- 报告对比：`GET /api/v1/op/qa/compare`（前端「版本报告对比」）只在环境、fixture版本、执行模式一致且两侧运行都已结束时判定回归；用例新增/删除单列标 `not_selected`，不并入通过率；同一用例但版本摘要不同不判回归；两侧分组结论分开，不合成单一通过率。
- 历史保留与清理：先 `POST /retention/preview` 生成清理范围与摘要，再 `POST /retention/apply` 带摘要执行，范围漂移返回409。默认每次最多处理200条最早的超期终态运行，预览响应给出 `total/truncated/remaining`，可重复预览+清理直至收敛；只删除已结束运行及其不再被引用的截图，计划与活动任务保留。需要 `qa.approve`。
- 浏览器E2E适配器（E01—E04）走真实页面与真实API：规格加购用券结算、商家SKU排序同步买家、OP测试入口与买家权限隔离、OP规划审批运行重跑对比。证据请求记录耗时与来源（`via=real_browser`）。

## 权限与启动

使用既有专用OP账号，不为公开商家演示账号授予质量权限。账号密码不放静态页面、脚本或仓库。

在backend目录，显式授予已有OP账号质量能力：

```powershell
.venv/Scripts/python.exe -m app.quality.cli 专用OP账号
.venv/Scripts/python.exe -m app.quality.cli 专用OP账号 --capabilities qa.view,qa.assistant.run,qa.approve
.venv/Scripts/python.exe -m app.quality.cli 专用OP账号 --revoke
```

CLI不会创建账号、重置密码或给普通用户增加OP权限。`qa.view`、两类run能力、`qa.approve`独立检查。读取报告和下载JSON也必须有OP与质量读取能力。

启动API和独立worker，不能只启动网页：

```powershell
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
.venv/Scripts/python.exe -m app.quality.worker
```

首次启动自动建四张QA表。Web API不在请求内执行长测试，任务先入持久队列；Redis提示丢失时按数据库队列核查。worker中断后租约过期记阻塞，不自动重放结果不确定的写步骤。规划进程中断同样记阻塞，不自动重复消耗模型额度。

MemoryRedis仅单worker开发模式，不支持跨进程分布式锁；多worker必须真实Redis并开启严格依赖模式。运行目录为 `backend/data/quality-workspaces/`，每条用例临时文件夹执行后清理；清理失败不放行。

当前项目是单一平台项目授权范围，具有质量读取能力的OP可查本平台报告；尚未实现跨项目多租户。

## 使用流程

1. 在OP测试入口新建助手/功能/联合计划，选已接入用例、模式、预算。
2. 固定计划立即成为待批准版本；AI计划由worker调用真实模型工具生成，先展示轨迹与实际消耗。
3. 检查用例、合成环境、代码指纹、预算和规划方式，点击批准；批准绑定内容摘要。
4. 启动已批准计划，查看排队/运行/完成或阻塞，按需取消。
5. 点用例查看API请求、业务助手原文与工具轨迹、可信快照、硬断言和清理状态。
6. 联合运行分别给助手、功能结论，不计算混合通过率。重跑新建运行，保留原报告。

业务及质量实现改变导致目标指纹变化时，旧批准不能启动/继续后续步骤。OP管理模块自身修改不改变被测业务指纹，避免仅修改运营列表就无故废弃业务计划。

## 模型预算说明

首期真实模型预算适配使用项目当前云端模型；不支持把Ollama原生调用直接计为已受控。规划、被测助手每次云端HTTP请求和内部重试均计数，默认禁用子进程供应商候选自动扩展。

调用前按序列化UTF8字节数加输出上限保守预留；收到usage则按实际tokens结算，未给usage或结果未知时保留估算。不是供应商账单对账系统。Embedding/RAG真实测试尚未接入，不能宣称相关费用也已覆盖。

无额度、超时、预算不足或模型未调用工具时显示阻塞，不以规则答案补成通过。父任务预算包含本计划规划消耗引用，计划复用不表示又付了一次规划费用。

模型子进程未完整返回时，实际费用可能未知；平台标记uncertain并保守占用本步剩余额度，不能把预留量当账单实际值，也不能记零后继续无上限调用。纯规则执行中断仍不计模型调用。

## 已完成的验证

- 后端全量291项通过；最后补充的库存数字防误匹配等质量专项12项复测通过，包括权限、候选/任意环境拒绝、摘要失效、幂等、取消/运行中撤权、真实隔离子进程联合执行、真实模式拒绝规则响应、队列槽位隔离。
- 用例版本/报告对比/历史清理专项：`tests/test_quality_case_versions.py`、`tests/test_quality_reporting.py` 与新增 `tests/test_quality_version_retention_audit.py`（10项）通过；后者用8个内存变异（去可比性判定、忽略摘要、忽略截图引用、合并单一通过率、放宽版本校验、放宽终态范围、删计划却谎报保留、权限校验置空）逐个证明断言不是空转，每个变异都被对应测试抓到。
- 浏览器E2E E01—E04两次独立运行全部通过（exit 0）：E01真实下单并核对优惠抵扣、E02 DOM级核对SKU顺序、E03核对买家访问OP接口403且C端无质量脚本、E04真实UI走完建用例→审核→新版本→计划→批准→运行→重跑→版本对比→保留预览。报告 `backend/data/acceptance/verify-browser.json`（本地忽略产物），运行详情截图见 `screenshots/op-quality-live.png`。
- 隔离执行器固定用例回归：14/14通过且 `cleanup_ok`，报告 `backend/data/acceptance/verify-fixed.json`。
- 隔离执行器14个代表场景通过（11助手规则＋3功能），未读取/修改真实商品订单。
- 实际GLM-5.3-Flash库存场景通过，记录3次模型请求、2526 tokens和清理成功；这是单场景真实证据，不代表所有候选或真实RAG已通过。
- 真实AI规划调用 `read_test_capabilities` 和 `propose_test_plan` 成功，并返回需批准的A02/A13计划。
- 隔离18129浏览器完成联合计划创建、批准、执行：助手2/2与功能2/2分别通过，三栏证据与0模型tokens的规则模式一致。
- 本地正式环境的专用OP账号按用户明确指定配置，未把密码写入前端或仓库。线上未在本轮发布。
- 本地8000正式API与独立worker使用真实MySQL/Redis保存/调度QA任务，专用OP账号在浏览器完成A02+F01联合回归，两组各1/1通过；实际业务执行仍为合成副本，未改真实商品订单。截图见 `screenshots/op-quality-local.png`。

报告与日志：`backend/data/acceptance/quality-*.json`、`quality-*.log`，均为本地忽略的验收数据；截图见 `screenshots/op-quality-live.png`。

## 回归命令

```powershell
.venv/Scripts/python.exe -m pytest tests/test_quality.py -q
.venv/Scripts/python.exe -m pytest tests/test_quality.py tests/test_quality_case_versions.py tests/test_quality_reporting.py tests/test_quality_version_retention_audit.py -q
.venv/Scripts/python.exe -m scripts.check_quality
.venv/Scripts/python.exe -m scripts.check_quality --cases E01 E02 E03 E04 --report data/acceptance/quality-browser.json
.venv/Scripts/python.exe -m scripts.check_quality --live --cases A02 --report data/acceptance/quality-live.json
.venv/Scripts/python.exe -m scripts.check_quality --planner --report data/acceptance/quality-planner.json
```

真实两条命令会使用配置的云端API额度，勿把无模型测试与真实评测混为一谈。验收脚本仍只连接合成业务数据。
