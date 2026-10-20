# 简历功能核对与需求驱动推荐

最新结论：本轮已补齐核心业务真实链路，full-native.json的七组严格验收全部通过；实际演示服务8000也已连接MySQL、Redis、真实云模型和Embedding/Chroma，不再只依赖SQLite或内存会话。本轮不是Docker API镜像构建验收，不是生产支付接入或任意自然语言准确率保证。操作见native-live.md。

## 简历逐项核对

- 商家后台/C端交易：已有商品/SKU、上下架、下单/支付演示、订单管理、身份与店铺权限、双端悬浮助手。FastAPI+SQLAlchemy实现；独立MySQL业务及Redis缓存/失效/限流曾实测通过。支付是项目演示流程，不代表接入真实支付渠道。
- Agent：LangChain工具定义、原生工具协议、参数校验、权限保护、异常处理和规则降级已有实现；Ollama业务工具及智谱Flash/FlashX/GLM-5.3协议均有真实记录。新推荐将原热销/预算筛选扩展为先概览、再结构化需求筛选与解释，不把纯排序称为完整推理。
- RAG：此前BGE检索通过但模型最终回答未过；本轮真实智谱Embedding-3/1024维、Chroma首位来源及三道原题最终回答全部通过。不是关键词或合成向量，记录来源/标题/距离；不同提供方/模型/维度禁止混用集合，原Ollama适配保留。
- 多轮：本轮真实Redis TTL、真实模型摘要、订单号锚点、独立进程恢复、API停止/重建后模型查询同一订单，A05全部通过。预算/颜色追问曾以隔离SQLite验证，最新追加MySQL/Redis多约束追问验证见增强报告。旧失败记录保留。
- 安全与异常：跨用户/跨店拒绝、身份参数防覆盖、工具校验/重试、模型空/非法输出和严格不降级有测试；不据此承诺绝对安全或所有自然语言需求解析完全正确。
- Docker/Wireshark：保留原Compose，本轮用便携服务而非Docker API镜像。Wireshark/Npcap已完成14包安装验证及本项目独立API的GET /api/v1/ready、15包TCP/HTTP200验证，报告wireshark-api.json。没有捕获认证令牌或日常流量，不声称抓到了TLS模型正文或定位了未发生的故障。未修改虚拟化或重启。

## 需求推荐实现

PRD先于代码落盘，见prd-recommendation-agent.md。工具序列为get_store_catalog → recommend_products → 回答。前者只让模型理解商品，不生成推荐卡；后者重新查询当前店铺可售SKU，校验库存、预算×数量、必含词/排除词、分类与单次限购上限，生成最终候选卡。规格关键词优先匹配具体SKU，避免低价缺货、颜色混用。多次筛选替换先前卡片，不残留已不匹配的候选。

最终回答展示需求摘要、价格小计和有商品依据的理由/取舍，不输出模型内部思维链。未提供的材质/功效/礼盒等不能补造；用户没要求礼盒时不能因商品“无礼盒”就排除。复杂要求在规则降级时明确不支持，不忽略条件改推热销。

边界：目前是按单一商品的数量小计筛选，不做多商品搭配/背包优化；小计不含运费，不能保证含运费总预算；累计已购限购剩余量仍由下单接口最终校验。关键词匹配不等于语义商品向量检索，大模型需求抽取需要用例持续验证。

## 可重复验证

最新全量回归：161 passed，117条既有短测试JWT警告，109.33秒退出0。包含原需求推荐、SKU/分页/意图测试，以及云端Embedding校验、独立进程所有权和推荐阶段纠正；不等同161个真实模型样本。full-native-enhanced-v2.json七组通过，包含真实MySQL/Redis中的多条件推荐与无匹配追问。

从backend运行：`python -m pytest tests/test_recommendation_agent.py -q --basetemp data/acceptance/pytest-recommend-新批次名`。

真实云模型与独立SQLite商品：`python -m scripts.check_recommendation --env-file .env --report data/acceptance/recommendation-live.json`。创建新的隔离数据库，不触碰业务库；真实模型原生调用本项目工具，数据库真实查询，会话为内存模式；报告明确不属于MySQL/Redis/Chroma完整验收，不打印密钥或推理内容。

本轮真实结果：GLM-5.3-FlashX两轮通过，报告 `backend/data/acceptance/recommendation-live-flashx.json`。首轮100元两只陶瓷杯、排除香薰，推荐白色39×2=78元或蓝色45×2=90元；第二轮“不选蓝色、换白色、数量和预算不变”继承100元/2只，返回白色78元，并真实查询库存。两轮均先调用概览再推荐。GLM-5.3-Flash首轮也通过，但第二轮最终回答ReadTimeout，保留失败报告recommendation-live-corrected.json，不宣称所有模型在此场景都稳定通过。

首次试跑还暴露了预算只写在需求摘要、缺失budget_yuan，以及模型擅自增加礼盒排除条件。已补数值字段说明/示例和禁止额外条件，并修复根级参数校验错误信息为空导致模型不能纠正；没有用提高工具步骤上限掩盖问题。模型解析仍需持续评估，不把两轮成功当作普遍准确率。
