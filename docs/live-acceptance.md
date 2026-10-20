# 真实联调运行手册

需求基线：`prd-live-acceptance.md`。此手册提供执行方式，具体结果以每次生成的报告为准。

## 职责与链路

SQLAlchemy 是 Python 数据访问层，MySQL 是用户/商品/SKU/订单/审计的持久化数据库。Redis 是商品列表缓存和会话/浏览/限流的临时存储，不是订单或库存的事实来源。

商品修改：业务接口 → SQLAlchemy 事务提交 MySQL → 清理 Redis 商品缓存 → 下次查询读取 MySQL 并回填。订单工具直接查询 MySQL，并带登录用户和店铺条件。

问答：用户认证 → Redis 会话 → 规则意图路由 → LangChain 工具 schema → 真实模型 tool_calls → 权限/参数校验 → 应用服务查询 MySQL → ToolMessage → 真实模型最终回答 → Redis 保存上下文。这里的业务接口是共享应用服务函数，工具不额外发内部 HTTP。

知识问答：Markdown 清洗/标题分块 → Ollama Embedding → Chroma 持久化 → 用户问题 Embedding → cosine 召回 → search_knowledge 工具回传片段 → 模型回答。响应 sources 包含文件、标题路径、片段、距离；retrieval_mode=chroma 才是语义链路。

## 前置条件

安装 Python 3.12 或兼容版本、项目 requirements.txt、Docker Desktop；确认 Docker Engine 启动，预留模型与容器内存/磁盘。所有命令在项目根目录执行，特别注明 backend 的除外。

新环境使用 compose.acceptance.yml，项目名 private-store-acceptance，与原商城 Compose 和本地 SQLite 分离。仅本机端口 18000/13306/16379/11435；独立 MySQL schema 为 private_store_acceptance。文件中的固定口令仅为回环隔离验收示例，不是生产配置。

## 启动服务和真实模型

```powershell
docker compose -f compose.acceptance.yml up -d mysql redis ollama
docker compose -f compose.acceptance.yml exec ollama ollama pull qwen2.5:1.5b
docker compose -f compose.acceptance.yml exec ollama ollama pull quentinz/bge-small-zh-v1.5
docker compose -f compose.acceptance.yml exec ollama ollama list
docker compose -f compose.acceptance.yml --profile api up -d --build api
```

模型下载需要网络，不能将下载命令执行视为模型已就绪。小模型若不能可靠选择工具，真实用例会失败；可更换支持工具调用的更大模型，并同步修改 Compose/API 与验收配置的模型名。不得降低断言或使用规则回复使其通过。

API 设置 STRICT_DEPENDENCIES、AGENT_REQUIRE_LLM、RAG_REQUIRE_VECTORS、ACCEPTANCE_ENVIRONMENT=true。/api/v1/ready 验证实际 MySQL SELECT 1 和 Redis PING；该就绪端点不调用收费聊天API，也不代替模型与Embedding的真实用例。

## 执行验收

在 backend 目录运行：

```powershell
.\.venv\Scripts\python.exe -m scripts.live_acceptance --env-file ../.env.acceptance.example --phase infrastructure --report data/acceptance/infrastructure.json
.\.venv\Scripts\python.exe -m scripts.live_acceptance --env-file ../.env.acceptance.example --phase full --restart-api --report data/acceptance/full.json
```

基础验收包含真实 MySQL 业务、真实 Redis 缓存与失效、权限/审计/限流和故障契约。完整验收追加真实模型五类工具、真实RAG三类问题、真实摘要、独立进程及API重启后的Redis会话恢复。缺少任何组不能全绿；报告按组记录失败，脚本退出码非零。请分别保留两份报告。

脚本只允许连接配置和实际 schema 都为 private_store_acceptance、且API显式声明验收环境的实例；每轮创建随机命名测试账号/店铺/商品和订单，不清空数据库。报告不保存登录令牌、完整订单号、凭据或收货资料。故障契约为独立 Pytest 子进程，明确区分模拟协议错误与真实不可达TCP端点，不停止现有服务。

报告中的 A05 使用“通过应用会话服务保存的真实模型压缩结果 + 独立进程恢复 + API重启后模型追问”验证持久性。压缩阈值测试由脚本构造长历史，不冒充真人完成十余轮自然对话。

中文Embedding选型依据与来源：[BAAI模型说明](https://huggingface.co/BAAI/bge-small-zh-v1.5)、[Ollama社区GGUF发布](https://ollama.com/quentinz/bge-small-zh-v1.5)。查询使用模型建议的中文检索前缀，文档按标题/段落切分并带标题输入；Chroma保存模型名和输入格式版本。nomic兼容配置使用[其任务前缀](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5)，实测未满足这组中文验收，未放宽首位来源断言。

## 不构建API镜像的本地方式

先启动独立 Compose 的 mysql/redis/ollama；在 backend 目录运行：

```powershell
.\.venv\Scripts\python.exe -m scripts.serve_acceptance --env-file ../.env.acceptance.example
```

该方式直接使用当前源码和本机虚拟环境，仍连接真实 MySQL/Redis/Ollama，适合基础联调。完整A05的 --restart-api 指向独立Compose的api服务，本地进程方式不能将另一进程读取冒充API重启通过。进行完整验收时使用容器API，避免同时占用18000。

也可由验收器启动并重启它自己创建的本地API进程，避开已有18000端口：

```powershell
.\.venv\Scripts\python.exe -m scripts.live_acceptance --env-file ../.env.acceptance.example --api-url http://127.0.0.1:18001 --phase full --manage-api --report data/acceptance/full.json
```

--manage-api 只允许显式本机端口，若端口已有服务则拒绝启动；只停止自己创建的进程树，验证结束后关闭该临时API。A05确实停止并重建API进程，再验证相同Redis会话与订单；不是仅在同一进程重新创建对象。

### 本轮CPU运行库复用

本轮从既有服务器只读复制已安装的官方 Ollama 0.40.4 CPU运行库和命令行程序，归档位于被Git忽略的 backend/data/acceptance/ollama-cpu/runtime.tgz。未复制模型API密钥或业务数据。deploy/Dockerfile.ollama-cpu 可将该归档放入独立容器，通过 OLLAMA_SHA256 检查命令行程序；本轮校验值为 `391486fad732fb98eba039aa74c345ece211290f89333637024577a9803280d7`。

本地标签 private-store-ollama-cpu:0.40.4 可通过 ACCEPTANCE_OLLAMA_IMAGE 环境变量替换默认镜像。此归档不是源码仓库交付物；其他机器仍可使用前述官方镜像方式，或自行准备经过校验的官方CPU运行库归档。

若本机代理把官方下载CDN解析为198.18.0.0/15假IP，Ollama重定向安全检查会拒绝下载。可先核实该CDN域名在独立公共DNS中的实际公网记录，再用仅本次容器的extra_hosts指定该域名公网地址；不要关闭重定向保护或TLS验证。地址有时效性，本机临时覆盖不提交为通用配置。

## 云端模型

更新：无Docker的真实MySQL/Redis/智谱Embedding全链路已按 [native-live.md](native-live.md) 跑通，旧WSL2阻塞不再阻止演示。旧失败报告保留，新的full-native.json七组全部通过；原Ollama路径仍可单独选择。

### 智谱配置

智谱使用 `.env.zhipu.example` 中的通用推理端点，当前默认glm-5.3-flash，CLOUD_MAX_TOKENS=4096。用户提供的赠送额度主要对应glm-5.3-flash与glm-5.3-flashx，因此不继续默认使用旧glm-4.7-flash。额度数量、截止时间以用户控制台为准，本应用未查询计费账单，也不保证请求一定扣赠送额度。

### 余额与额度自动切换

用户授权后已配置：glm-5.3-flash → glm-5.3-flashx → glm-5.3 → glm-4.7-flash。前两者对应用户提供的专项赠送额度，glm-5.3作为通用基础模型额度候选，glm-4.7-flash作为免费聊天模型兜底。不是“通用额度模型”这样的虚构模型编码，也不会把联网搜索模型发给chat/completions。搜索std/pro/quark/sogou是独立联网接口，本项目商品/订单查询和本店知识检索不使用它们，不会为消耗赠送次数自动发送外部搜索。

使用CLOUD_FALLBACK_MODELS配置有序候选，主模型计入后最多5个，去重。仅智谱明确业务错误码1113（账户欠费）、1308/1310（使用上限）触发换模型，同一请求每个候选至多尝试一轮。普通429限流/拥塞及503仍在原模型有界退避重试；认证、参数、内容安全错误和网络异常不换模型，不能借切换绕过安全检查。接口含义参见[官方错误码](https://docs.bigmodel.cn/cn/api/api-code)。

额度失败的模型在当前API进程中冷却300秒，后续会话和重新bind_tools创建的模型对象共享此状态，避免每轮重复请求已耗尽模型；到期后允许重新探测。状态以服务地址、API样式、密钥摘要和模型隔离，不保存明文密钥。多worker各自冷却，重启不保留冷却；不冒充实时余额台账。成功响应的response_metadata.model和仅含模型名称的服务日志可追踪实际选择，冒烟报告也记录actual_model。

重要限制：平台可能在某模型赠送包耗尽或到期后继续抵扣通用赠送包、甚至现金余额，且返回成功。这种情况下不会触发切换；当前实现不能承诺“只用免费额度”“按专项包剩余自动切换”或“余额零仍必然可用”。账户欠费也可能导致所有模型包括免费模型被拒绝，此时有界返回错误而非无限循环。要禁止现金消费，须由用户在智谱控制台设置可用的消费限制，并以控制台实际扣费记录核验。到期日期不硬编码为禁止模型使用，避免充值后仍误拒绝。

设置 `CLOUD_API_STYLE=zhipu` 后，GLM-5.3系列发送thinking.enabled、reasoning_effort=low、clear_thinking=false；较早模型保留thinking.disabled，不混用Qwen的enable_thinking字段。GLM-5.3不能关闭思考，不能只修改模型名而沿用旧参数。工具循环将模型返回的reasoning_content仅在进程内回传给后续模型请求，不展示到前端或写入协议测试报告。接口参考[官方API说明](https://docs.bigmodel.cn/cn/api/introduction)、[Flash/FlashX说明](https://docs.bigmodel.cn/cn/guide/models/vlm/glm-5.3-flash)、[5.3迁移说明](https://docs.bigmodel.cn/cn/guide/start/migrate-to-glm-new)。标准API密钥与Coding套餐密钥不应混用；如认证失败，先确认密钥类型，不自动改投第三方网关。

手动验证FlashX时，在当前PowerShell进程设置 `$env:CLOUD_MODEL='glm-5.3-flashx'` 后运行同一冒烟命令并另存报告，完成后 `Remove-Item Env:CLOUD_MODEL` 恢复文件中的Flash默认值。搜索次数额度用于智谱联网搜索，不是本项目的Chroma知识库检索额度；本轮不调用联网搜索，也不将其作为本店售后政策或订单数据来源。

本机backend/.env已配置 `CLOUD_API_KEY_FILE=D:/qiuzhao/API/zhipu_api.txt`；应用仅在发送请求前读取文件中的单行密钥，支持UTF-8 BOM与末尾换行，不复制文件内容到项目。环境变量CLOUD_API_KEY若有值则优先；切换来源时注意清除不再使用的环境变量。文件缺失、空白或多行时拒绝发送，错误不包含密钥或文件内容。其他机器须配置自己的外部路径，不能将此文件上传到前端或仓库。

该配置仅替换聊天模型，不替代MySQL、Redis、Embedding或Chroma，也不会启用本机虚拟化。已有API进程需正常重启才能加载新配置。从backend目录启动的服务读取backend/.env；根目录启动时需明确指定同一环境配置。

仅验证云模型连接和原生工具协议，可在backend目录运行：`.\.venv\Scripts\python.exe -m scripts.check_cloud_model --env-file .env --report data/acceptance/zhipu-smoke.json`。该脚本使用合成工具结果，不访问业务数据库或Chroma；报告明确标记范围，不得视作完整RAG验收。2026-10-19智谱真实对话、原生search_knowledge调用及工具结果回传生成回答已获得通过记录；首次尝试曾失败，复跑通过不代表可用性或准确率保证。

隔离完整验收可在启动脚本的进程环境中设置MODEL_PROVIDER=cloud、CLOUD_API_STYLE=zhipu、CLOUD_BASE_URL、CLOUD_MODEL、CLOUD_API_KEY_FILE，其余仍使用.env.acceptance.example的MySQL/Redis/BGE配置。待真实依赖恢复后运行full --manage-api，报告不能用仅模型协议冒烟代替。

当前保留 CloudChatModel 适配，可用独立本地环境文件设置 MODEL_PROVIDER=cloud、CLOUD_BASE_URL、CLOUD_MODEL、CLOUD_API_KEY。实际 API 配置与验收配置必须一致。云端模式仍需真实Ollama Embedding，除非后续另行实现Embedding适配器。报告标明cloud，不能写成Ollama推理。API Key只来自环境或外部私密文件，不提交、不打印。

也支持由外部密钥管理器向进程环境注入上述四个变量；Pydantic环境变量优先于示例文件，验收器创建的API子进程继承这些变量，无需把密钥写进示例文件。不要把密钥作为命令参数或粘贴进日志。运行时沿用 `--manage-api`，将报告另存为 `data/acceptance/full-cloud.json`，避免覆盖Ollama原始失败证据。

真实模型若在业务问题上未调用任何工具，最多允许一次模型纠正；再次未调用则严格失败，不由服务端偷偷执行规则工具冒充Function Calling。小模型是否能稳定遵循工具协议必须实测，不能只看模型能够输出自然语言。

## 重新启动后的环境预检

历史通过不代表电脑重启后依赖仍运行。先执行 `docker info` 和 `docker compose -f compose.acceptance.yml ps`；确认MySQL、Redis、Ollama运行，再启动托管验收。`/api/v1/ready`必须返回实际mysql/redis及严格模式标记。

2026-10-19本机WSL2报HCS_E_HYPERV_NOT_INSTALLED，Docker无法启动；只读检查显示HypervisorPresent=False，固件虚拟化=True。这是当前完整联调阻塞，不是业务代码通过证据。不要为运行本项目自动修改BCD、启用系统功能或重启Windows；由机器维护者恢复可用的WSL2/Docker环境后复跑，或在另一台具备Docker的隔离开发机上运行同一Compose。不要直接将验收配置指向生产数据库。

## 故障与停止

### Wireshark安装与最小验证

本机经用户明确授权安装Wireshark 4.6.9及Npcap 1.88，均校验官方签名有效；没有启用虚拟化或重启。Wireshark来自官方发布站，Npcap从同一已签名的Wireshark安装包提取，未绕过Npcap网站证书校验，也未安装USB抓包驱动。

在backend运行 `python -m scripts.check_packet_capture` 可复跑：脚本启动自己的127.0.0.1随机端口HTTP探针，使用Npcap回环接口，仅过滤该端口抓5秒；不捕获日常网络、登录令牌、模型密钥或业务订单。结束后停止自己创建的HTTP服务与抓包进程，保留pcapng及SHA256，报告data/acceptance/wireshark-installation.json。首次实测14个包、GET和HTTP200均通过，范围明确为真实抓包安装验证，不冒充项目业务排障成果。需要权限时直接失败，不自动请求提权或改驱动设置。

严格模型失败返回503，不回退后当作验收通过；严格向量建库/检索失败也拒绝；严格Redis断连就绪检查返回503，运行读写返回稳定503。开发非严格模式仍支持内存Redis、关键词检索及规则回复，接口显式报告模式。

```powershell
docker compose -f compose.acceptance.yml stop
```

此命令保留验收数据卷和模型。无需删除卷即可再次运行；不执行 down -v，不触碰原业务数据库。报告包含实际时间与模型配置，简历中不要添加未经测量的准确率或性能提升。

Windows若全量Pytest在会话结束清理系统临时目录时出现pytest-current的WinError 5，可在backend目录改用本项目独立临时目录：`.\.venv\Scripts\python.exe -m pytest -q --basetemp data/acceptance/pytest-local-独立批次名`。每轮使用新的批次名，不删除或修改其他项目的临时目录；不要把断言执行完毕但进程退出失败当作回归通过。
