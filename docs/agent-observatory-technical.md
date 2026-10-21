# 三 Agent 可视化技术方案

## 第二版增量设计

- `QA_CHAT_*` 服务端profile仅在 `subprocess_job` 启动规划/live子进程时注入 `CLOUD_*`，清空原聊天密钥及候选；绝不在主进程修改业务settings，也不覆盖独立Embedding。
- 新增OP `POST/GET /op/qa/business-debug`：qa.view+qa.assistant.run，POST显式确认云端调用、限频、全局调试租约、固定90秒/20调用/60000tokens。仅接受合成角色及消息，不接受用户ID、URL、SQL、凭据或模型选择。
- 新 `business_debug` 固定适配调用同一业务助手接口；HTTP200、mode=llm且存在真实模型HTTP计量才视为完成。无业务预期断言，不创建QualityCaseVersion/QualityPlan/QualityRun。
- 对话历史只缓存脱敏合成记录，按OP用户键隔离、TTL7天、最多10条；将业务页映射到对话/执行步骤/详情，不展示测试术语。转评测先填预期，仅创建candidate。
- 单元测试可模拟模型以验证门禁，但真实验收必须实际调用GLM，不能用模拟或规则通过冒充。保留平台内部确定性诊断用于无密钥CI，并与正式Agent评测区分。

### 第二版实测记录

- 外部 `GLM_4.txt` 实际调用 `glm-4-flash` 返回HTTP200及usage；密钥未输出或入库。
- 33项平台/权限/隔离/版本单元回归通过。它们只证明工程边界，不算模型效果验收。
- 真实GLM助手A02库存、A03先目录再推荐通过；A09缺预算澄清阻塞（HTTP请求成功，但纠正后仍未按业务工具契约调用），保留 `quality-glm4flash-live.json`，不降级或放宽断言。
- `check_observatory_ui --live` 真实GLM规划助手计划、真实GLM运行A02、真实GLM规划功能计划后固定执行F01，以及业务页单轮/两轮对话均完成；两轮在同一子进程会话内复现，零页面脚本错误。业务单轮最近记录 `e706c6add55246c7acaa0303161431a6`：3次GLM请求、3189tokens。模型调用与固定功能断言分别记录。
- 现有8000进程的OpenAPI尚无新business-debug接口，需正常重启后端加载。本轮未绕过此前进程重启限制；隔离验收服务已正常清理，不把其记录冒充8000的现有数据。

## 复用优先

前端新增独立 `web/op-agent-observatory.js` 与样式文件，由 `op-quality.js` 在三个 Agent 页挂载。保留原有计划、报告、比较、截图组件；说明文字收纳为折叠说明，不占据主工作区域。

不新增业务写 API：读取 `/op/qa/runs` 及运行详情、`/agents`、`/cases`；调试复用 `/cases`、`/cases/{id}/approve`、`/plans`、`/plans/{id}/approve`、`/runs`。每个请求仍走 OP Bearer 与既有能力控制。

## 证据投影

纯函数将单条 QualityResult.evidence 投影成步骤：

1. requests 原数组顺序是可证明的请求次序；每个 /chat 响应内的 tools 按自身数组次序展开。
2. /chat input.message 是输入，output.intent 是识别结果，output.tools 为工具轨迹，output.sources 为知识引用，output.answer 为最终答案。
3. 同一请求内展开步骤只表示数据包含关系，不能推断模型内部调用的准确时间；source 列表不假设检索发生在最后一个工具之后。
4. summary_mode 和 session_id 仅证明摘要模式和会话关联，不等同于已采集完整 Redis 记忆或长期用户画像。
5. suite.reports 保留 pytest 的实际阶段和 outcome；assertions 的 expected/actual 是判定依据，facts 为业务核查数据。
6. budget.models 为独立 HTTP 调用清单，只在汇总显示，不与具体工具强行一一对应。没有 usage 或 uncertain 时显示估算/未知。

只渲染 DOM textContent/pre，限制单次显示长度及节点数，不用 innerHTML、不动态执行工具输出。沿用后端脱敏证据，UI 不读取任何凭据文件。

## 调试状态机

editing → candidate → case-approved → plan-draft → plan-approved → queued。

候选定义提交后冻结；要改内容先明确新建候选。批准/建计划/启动分别保存回执；请求失败停在已有阶段，重试继续已有阶段。每个调试任务固定 request_key，重复启动复用原运行，不额外付费。创建候选阶段可编辑1—5轮；之后定义只读。

工作台状态按当前账号身份与 Agent 类型在内存保存，不把 token 写入日志或 JSON。页面失效后不渲染异步结果，账号切换清空缓存。轮询由原质量页面统一管理，工作台不另起并行轮询或 worker。

## 验证

Node 纯函数测试覆盖三种证据投影、模型计数与工具次数区分、未知计时、失败断言、越界证据截断；交互测试覆盖候选/审批/幂等启动、能力门控和安全文本渲染。后端继续跑原质量版本与审批专项，确保前端复用未绕开服务端门禁；浏览器验收在独立合成服务运行，不触碰真实店铺。

## 2026-10-21 第一版验收

- 先完成上述 PRD 与技术设计，再实现工作台；既有报告与版本流程保留。
- 后端审批、版本、执行边界、Agent文档专项31项通过；Node投影/门控/幂等验证与旧OP安全渲染验证通过。
- 独立SQLite/MemoryRedis API、独立worker、真实无头Edge完成三页回放、配置切换、步骤选择、窄屏布局，零页面脚本错误。
- `python -m scripts.check_observatory_ui --live` 经真实UI保存候选、批准用例、创建/批准计划、启动、读取报告，Flash实际工具调用及硬断言通过。最后一次验收运行 `f20e4040aea84039b963a78fc60a507e`：3次模型HTTP调用、3404 tokens、5/5断言通过且清理成功。没有使用Pro。
- 截图复核发现启动新运行后回放曾被旧数据选项覆盖；已修复刷新顺序，并用运行ID断言确认展示的确实是刚启动的运行，不是旧通过记录。
- 证据位于本地忽略目录 `backend/data/acceptance/observatory/`；不能将临时服务的运行ID当作当前8000业务库中的持久记录。
- CI增补无付费浏览器工作台验收和Node回归；未推送、未宣称远程CI通过。现有后端无需新增路由或迁移；本地静态页面强刷可加载新增资源。
