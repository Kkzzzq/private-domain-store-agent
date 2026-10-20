# 真实服务联调交付与证据

## 最新交付：2026-10-19

- 核心真实链路已补齐。full-native.json七组通过；增加MySQL/Redis真实需求推荐追问后的full-native-enhanced-v2.json也七组通过。首次增强失败报告保留，未放宽断言。
- 实际组件：MySQL 8.4.11、真实Redis 8.10.2社区Windows构建、GLM-5.3-FlashX、Embedding-3/1024维与Chroma。原Ollama/Docker适配保留，但本轮不是它们的全链路或API镜像构建验收。
- RAG三道原题从真实Embedding建库、Chroma首位来源到最终回答通过；真实Redis摘要、跨进程、API停止重建后订单追问通过。增强推荐80元买两件37元商品返回74元，追问70元且不改数量返回无匹配；必须执行后端筛选，不能仅看概览心算结束。
- 最终全量161 passed、117条既有短测试JWT警告，109.33秒退出0；A07故障契约明确含模拟协议与真实不可达端点，不冒称161个真实云模型样本。
- 本项目独立API的真实TCP/HTTP抓包15包、GET/200通过，见wireshark-api.json；不捕获认证令牌或日常流量，不声称定位了未发生的故障。
- 常驻8000演示已使用独立MySQL演示库、Redis DB0、智谱模型、Embedding/Chroma，14块真实向量建库；买家RAG、商家经营概览、需求推荐三场景在真实演示API通过。旧SQLite保留；验收库和Redis DB1与演示隔离。未改虚拟化/BCD、未重启、未推送部署。

操作见native-live.md，需求见prd-native-live.md。支付仍为业务状态演示，不是资金支付；预算小计不含运费，累计限购由下单接口最终校验，不能承诺任意问法准确或生产级可用性。

## 以下为阶段性历史记录

下文包含较早回归数量、Ollama失败及当时环境阻塞，作为过程记录保留；当前完成度以上述最新交付和对应JSON为准。

基线：`prd-live-acceptance.md`；操作：`live-acceptance.md`。

## 实现

- 独立Compose提供MySQL、Redis、Ollama、可选API容器和持久化卷；回环独立端口，不改原商城数据库。
- STRICT_DEPENDENCIES禁止SQLite/内存Redis代替真实依赖；/api/v1/ready执行真实SELECT 1、Redis PING。
- AGENT_REQUIRE_LLM禁止规则降级冒充模型成功，工具失败/步骤耗尽判失败；RAG_REQUIRE_VECTORS禁止关键词冒充语义检索。
- ChatOut提供sources、retrieval_mode、summary_mode；双端展示知识来源。Chroma记录Embedding模型、标题路径与距离，拒绝模型不一致的检索。
- 修复云端摘要器字符串入参与消息列表接口不一致的问题；保留字符预算、事实摘要回退和订单锚点。
- Redis运行时断连：严格模式稳定503；开发模式切换内存，健康状态可见。商品缓存失效使用SCAN遍历真实Redis键。
- 真实验收脚本验证7组需求，报告不完整不得全绿；支持独立子进程故障契约及自行管理/重启独立API进程。
- 网络受限时可使用官方注册表下载辅助脚本，限制HTTPS来源与公网重定向、分段续传，并验证最终SHA256后才发布模型清单。

## 已获得的结果

本轮完整Pytest回归：145 passed。包含真实不可达回环端口的模型/Embedding/Redis故障测试、模拟协议与工具安全测试，以及智谱协议、密钥文件校验、5.3工具推理上下文、额度切换和需求推荐约束/阶段/分页；不能将其称为145项真实模型用例。

最新需求推荐：已先完成prd-recommendation-agent.md，新增本店概览→需求筛选→理由/取舍及同会话追问。GLM-5.3-FlashX+独立SQLite真实商品查询+内存会话两轮通过，报告recommendation-live-flashx.json；这不是MySQL/Redis/RAG统一验收。Flash首轮通过、追问最终回答超时保留失败证据。逐项简历核对与具体边界见feature-audit-20261019.md；不得据此次推荐成功宣称简历全部功能已真实验收。

2026-10-19新增智谱适配，本机backend/.env仅保存外部密钥文件路径，不复制密钥。glm-4.7-flash真实对话、原生工具调用和合成工具结果回传后的回答已实测通过；该协议冒烟不访问MySQL、Redis或Chroma，不能据此更改下列完整验收失败状态。可复跑脚本为 `backend/scripts/check_cloud_model.py`，配置为 `.env.zhipu.example`。

随后根据用户提供的赠送模型额度，默认切换glm-5.3-flash，另实测glm-5.3-flashx。两者真实对话、原生search_knowledge调用及合成工具结果回传回答均通过，分别保存 `backend/data/acceptance/zhipu-53-flash-smoke.json`、`backend/data/acceptance/zhipu-53-flashx-smoke.json`。适配5.3强制思考、低推理强度、4096输出预算及工具往返reasoning_content；不自动切换模型或使用联网搜索，不把用户提供的额度视为已核验扣费账单。

用户随后授权余额耗尽自动切换，已增加Flash → FlashX → GLM-5.3 → 免费4.7-Flash有序候选和进程内300秒额度冷却。仅明确额度业务码触发切换，普通限流/503重试原模型，认证/参数/安全拒绝不切换；所有候选失败有界报错，不循环。GLM-5.3真实协议冒烟通过；注入主模型1113后，由真实FlashX完成对话/原生工具往返的测试也通过（`backend/data/acceptance/zhipu-injected-quota-live-fallback.json`），报告明确标记错误为注入，非账户真实欠费。未为测试耗尽用户额度，也未把联网搜索接口混入聊天模型链。

API在赠送额度用尽后可能直接扣现金余额而不报错；当前没有余额查询接口接入，无法保证只用赠送包或精准按赠送剩余量切换，消费控制仍须用户在控制台核验。详细边界见操作手册“余额与额度自动切换”。

基础真实联调报告：`backend/data/acceptance/infrastructure.json`，passed=true，4组通过：

- A01：MySQL 8.4.11实际落库，接口订单归属/金额与数据库一致，支付与发货状态正确。
- A02：真实Redis缓存与TTL可观测；SKU价格/库存修改后缓存失效、重新读取一致，下架后买家不可见。
- A06：真实接口身份/跨店校验、跨用户工具拒绝、MySQL审计脱敏、真实Redis限流429。
- A07：故障契约独立测试进程通过，明确属于确定性测试和不可达端口测试。

完整Ollama报告：`backend/data/acceptance/full.json`，2026-10-18运行，passed=false。其中A01/A02/A03/A06/A07通过；A03真实完成商品搜索、SKU库存、本人订单、预算推荐、商家经营概览的原生工具调用，包含参数、脱敏结果、最终回答和耗时证据。没有使用规则回复替代。

A04未通过：qwen2.5:1.5b对售后问题直接输出常识性回答，没有发出search_knowledge工具调用；追加一次模型纠正仍未调用，严格模式正确返回503。不能把恰好答对“7天”当作RAG通过。

A05未通过：真实模型摘要、Redis保存、独立进程恢复及实际API进程重启已执行，但重启后的订单追问没有发出query_orders，整个场景判失败。不得仅凭摘要/恢复成功宣称连续对话已通过。

## 检索选型与当前阻塞

官方完整Ollama镜像运行库下载较大；已复用既有官方CPU运行库并校验命令行程序SHA256，本地隔离Ollama 0.40.4服务运行。模型注册表CDN受本机代理假IP及网络速度影响，使用限制来源及SHA256校验的下载辅助脚本。

真实nomic向量链路已运行，但原三道中文题的首位命中未全部通过；补任务前缀及细化段落后仍不稳定。独立验收已改用中文BGE-small-zh-v1.5的Ollama社区GGUF版，重新建立独立集合。真实Embedding/Chroma三道原题首位命中全部通过，见 `backend/data/acceptance/retrieval.json`；此报告范围明确为检索，不包含聊天模型最终回答。

2026-10-19继续采用已配置的云端Qwen模型运行完整验收，凭据只读加载到进程内存，没有写入仓库、报告或命令参数。最新报告为 `backend/data/acceptance/full-cloud.json`，passed=false：本机Docker已停止，WSL2启动报HCS_E_HYPERV_NOT_INSTALLED，系统HypervisorPresent=False、固件虚拟化=True；严格Redis不可达导致API启动失败，A01失败，后续模型组未执行。此次没有获得云端完整链路的新通过证据。未改Windows启动项、系统功能或重启电脑，也未修改生产服务/数据。

因此本轮可确认真实Ollama业务Function Calling与真实中文Embedding→Chroma检索；尚不能确认完整Embedding→Chroma→模型回答及摘要压缩后重启追问全部通过。既有2026-10-14云端工具记录不代替本轮独立MySQL/Redis环境完整验收。服务恢复后需使用更可靠的聊天模型复跑，而不是降低原题或断言要求。

完成条件：模型就绪后运行full --manage-api或full --restart-api，七组全部通过；保存真实配置、来源、结论和耗时证据，再更新此处。任何失败不得通过放宽断言或隐式fallback改成成功。
