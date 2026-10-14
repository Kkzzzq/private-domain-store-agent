# PRD：店内 Agent 能力补强

> 目标：让简历里描述的**全部能力**都落到可演示、可测试、经得起面试追问的代码上。
> 本文以 Agent 补强为主线（§3 功能需求），并在 §8 给出覆盖简历全量的交付清单；不重构现有商品 / 订单业务。

## 0. 背景

项目当前已具备 Agent 主体能力：

- LangChain 工具调用（`app/agent/assistant.py` `run_tool_loop`）
- 业务工具封装（`app/agent/tools.py`，pydantic 参数校验）
- RAG 检索（`app/rag/knowledge.py`，Chroma + Ollama Embedding，含关键词兜底）
- 多轮会话（`app/services/session.py`，Redis，7 天 TTL）
- 工具调用安全（`app/agent/guard.py` 参数校验 + 重试，跨用户订单隔离）

但以下简历表述**强于代码现状**，需要补实：

| 简历表述 | 现状 | 差距 |
| --- | --- | --- |
| 设计意图识别…流程 | 靠 LLM 选工具隐式完成 + 关键词兜底 | 无显式意图识别层 |
| 智能推荐 | 只有关键词搜索 `search_products` | 无个性化 / 相似 / 预算推荐 |
| 文档清洗和分块 | 定长 500 字符 + 80 重叠切片 | 无结构感知、无标题元数据 |
| 历史消息截断与摘要机制 | 拼接前 80 字 | 非真正的摘要 |
| 工具调用安全与异常处理 | 校验 + 重试 + 越权拦截 | 无审计日志、无限流 |

## 1. 范围与决策记录

| 决策项 | 结论 |
| --- | --- |
| 实现范围 | 全量：P0 + P1 + P2 |
| 推荐策略 | `viewed` / `hot` / `related` / `budget` 四种 reason 全做 |
| 前端展示 | 对话区增加商品卡片（改 `web/c.js` + `web/mall.css`） |
| PRD 定位 | 覆盖简历全量：§8 交付清单 + §9 可观测性（Wireshark） |
| PRD 落盘 | 本文件 |

## 2. 需求清单

| 编号 | 需求 | 优先级 | 对应简历 |
| --- | --- | --- | --- |
| FR-1 | 显式意图识别 + 工具路由 | P0 | 设计意图识别…流程 |
| FR-2 | 智能推荐工具（4 种 reason） | P0 | 智能推荐 |
| FR-3 | 结构化 RAG 清洗与分块 | P1 | 文档清洗和分块 |
| FR-4 | LLM 摘要式上下文压缩 | P1 | 历史消息截断与摘要机制 |
| FR-5 | 工具调用审计 + 限流 | P2 | 工具调用安全与异常处理 |
| FR-6 | Agent 测试补齐 | P0 | 技术栈 Pytest |
| FR-7 | 推荐结果前端卡片 | P0 | C 端智能助手 |
| FR-8 | 可观测性与排障（Wireshark） | P2 | 技术栈 Wireshark |

## 3. 功能需求与验收标准

### FR-1 显式意图识别 + 工具路由

- 新增 `app/agent/intent.py`，输出 `{intent, confidence, slots, source}`。
- 两级识别：
  - **L1 规则快匹配**：复用 `fallback.py` 词表，命中且高置信直接路由（省一次 LLM 调用，降延迟）。
  - **L2 LLM 结构化分类**：未命中时调用 LLM 输出 JSON（`with_structured_output` 或 JSON 约束）。
- 路由：intent → 允许的工具子集，只对子集 `bind_tools`；`SMALLTALK / UNCLEAR` 不调工具。
- 集成点：`run_tool_loop` 构造消息前插入识别，`traces` 首项记录 intent 与 source。
- **验收**：
  - 预制 query 集意图分类准确率 ≥ 90%（进 `pytest`）。
  - 「今天天气不错」不触发任何业务工具。
  - 日志 / 响应 trace 可见 intent。

### FR-2 智能推荐工具（4 种 reason）

- 新增 `app/services/recommend.py`，新增工具 `recommend_products(reason, product_id=None, budget_yuan=None, limit=3)`，注册进 `tools.py` 的 `SPECS / IMPL / DESCRIPTIONS`。
- reason 语义与数据来源：
  - `viewed`：`engagement._recent_ids(user_id)` 取最近浏览 → 同类目 / 同店热销。
  - `hot`：`Product.sales_count` top N。
  - `related`：同 `category` 排除自身，按销量。
  - `budget`：筛 `price_from <= budget_yuan`。
- **硬约束**：一律限定 `shop_id` + `listed_on_c`，只推当前店在售商品。
- **验收**：
  - 看过「亚麻抱枕套」后问「再推荐几个」→ 返回同类目在售商品。
  - 不串别家店商品（沿用 `test_bc_link.py` 跨店隔离思路加断言）。

### FR-3 结构化 RAG 清洗与分块

- 新增 `app/rag/cleaner.py`：
  - `clean(text)`：去 HTML 注释 / 多余空行 / 重复段落（hash 去重）、全半角统一，保留 Markdown 标题层级。
  - `split_by_headings(text)`：以 `# / ## / ###` 为边界切；超长段再定长 + overlap 二次切。
  - 每块带 `heading_path`（如 `售后政策 > 退货 > 时效`）。
- `KnowledgeBase.load_chunks` 改走 cleaner，Chroma metadata 增加 `heading_path`，检索时拼进上下文。
- **验收**：`POST /api/v1/b/knowledge/reindex` 后每块有 `source + heading_path`；同段落不重复入库；问答可显示来源。

### FR-4 LLM 摘要式上下文压缩

- 新增 `app/agent/summarizer.py`：`summarize(head_messages, prev_summary, llm) -> str`，保留用户诉求 / 已确认的商品或订单号 / 未决问题。
- `compact_messages` 用 token 预算（`len/4` 或 tiktoken）替代字符阈值；超预算时调摘要器，**异常回退到现有拼接逻辑**。
- **验收**：10 轮以上长对话后仍能记住早前说过的订单号。

### FR-5 工具调用审计 + 限流

- 新增表 `AgentToolLog`：`user_id / shop_id / session_id / tool / args(脱敏) / ok / latency_ms / flag`，越权尝试单独打标。
- `guard.execute_tool` 落审计；`chat` 接口加 per-user 每分钟限流（Redis 计数），超频返回 429。
- **验收**：跨用户查询留下审计记录；超频返回 429。

### FR-6 Agent 测试补齐

- `test_agent_intent.py`、`test_agent_guard.py`、`test_agent_recommend.py`、`test_agent_context.py`。
- 现有 `test_bc_link.py` 的 agent 用例必须保持通过。

### FR-7 推荐结果前端卡片

- `ChatOut` 增加 `products: list[ChatProductCard]`（默认空），由 Agent 在调用推荐 / 搜索工具时回填。
- `web/c.js` 的 `renderChat`：当响应带 `products` 时，在气泡下方渲染卡片（图 + 名称 + 价格），点击进商品详情。
- `web/mall.css` 增加卡片样式（沿用现有商品卡的视觉语言）。
- **验收**：助手推荐后卡片可点击进详情页；无推荐时不渲染空容器。

## 4. 实现路径（任务分解）

### 阶段一：P0

- [ ] T1.1 新增 `app/agent/intent.py`（Intent 枚举 + 路由表 + 两级 classify）
- [ ] T1.2 `assistant.run_tool_loop` 接入意图路由，traces 记录 intent
- [ ] T1.3 `settings` 增加 `agent_intent_enabled` 开关
- [ ] T2.1 新增 `app/services/recommend.py`（4 种 reason）
- [ ] T2.2 `tools.py` 注册 `recommend_products`
- [ ] T2.3 `prompts.py` 补充推荐场景说明
- [ ] T7.1 `dto.py` 增加 `ChatProductCard`，`ChatOut` 加 `products`
- [ ] T7.2 Agent 执行结果回填结构化商品（供卡片）
- [ ] T7.3 `web/c.js` + `web/mall.css` 渲染卡片
- [ ] T6.1 新增 `test_agent_intent.py` / `test_agent_guard.py` / `test_agent_recommend.py`

### 阶段二：P1

- [ ] T3.1 新增 `app/rag/cleaner.py`
- [ ] T3.2 `knowledge.load_chunks` 走 cleaner，写 `heading_path`
- [ ] T3.3 reindex 验证（chunk 数、元数据、去重）
- [ ] T4.1 新增 `app/agent/summarizer.py`
- [ ] T4.2 `session.compact_messages` 接入摘要器 + 异常回退
- [ ] T6.2 新增 `test_agent_context.py`

### 阶段三：P2

- [ ] T5.1 `models/tables.py` 新增 `AgentToolLog`
- [ ] T5.2 `guard.execute_tool` 写审计（含越权打标）
- [ ] T5.3 `c_api.chat` 加限流
- [ ] T9.1 新增 `docs/troubleshooting.md`（Wireshark 抓包排障步骤 + 真实案例）

## 5. 技术设计

### 5.1 文件改动图

| 动作 | 文件 | 说明 |
| --- | --- | --- |
| 新增 | `backend/app/agent/intent.py` | 意图枚举 + 两级识别 + 路由表 |
| 新增 | `backend/app/agent/summarizer.py` | LLM 摘要（FR-4） |
| 新增 | `backend/app/services/recommend.py` | 推荐数据逻辑 |
| 新增 | `backend/app/rag/cleaner.py` | 清洗 + 标题结构化分块 |
| 修改 | `backend/app/agent/tools.py` | 注册 `recommend_products` |
| 修改 | `backend/app/agent/assistant.py` | 接入意图路由 + 回填推荐商品 |
| 修改 | `backend/app/agent/prompts.py` | 推荐场景说明 |
| 修改 | `backend/app/agent/guard.py` | 写审计日志 |
| 修改 | `backend/app/rag/knowledge.py` | `load_chunks` 走 cleaner |
| 修改 | `backend/app/services/session.py` | 接入摘要器 |
| 修改 | `backend/app/models/tables.py` | 新增 `AgentToolLog` |
| 修改 | `backend/app/schemas/dto.py` | `ChatProductCard` + `ChatOut.products` |
| 修改 | `backend/app/api/c_api.py` | `chat` 限流 |
| 修改 | `backend/app/core/config.py` | 能力开关 |
| 修改 | `web/c.js` / `web/mall.css` | 商品卡片 |
| 新增 | `backend/tests/test_agent_*.py` | FR-6 |
| 新增 | `docs/troubleshooting.md` | Wireshark 抓包排障（FR-8） |

### 5.2 核心数据结构（提案）

```python
# app/agent/intent.py
class Intent(str, Enum):
    PRODUCT_SEARCH = "product_search"
    INVENTORY = "inventory"
    ORDER = "order"
    POLICY = "policy"
    RECOMMEND = "recommend"
    SMALLTALK = "smalltalk"
    UNCLEAR = "unclear"

INTENT_TOOLS = {
    Intent.PRODUCT_SEARCH: ["search_products"],
    Intent.INVENTORY: ["check_inventory"],
    Intent.ORDER: ["query_orders"],
    Intent.POLICY: ["search_knowledge"],
    Intent.RECOMMEND: ["recommend_products"],
    Intent.SMALLTALK: [],
    Intent.UNCLEAR: [],
}

@dataclass
class IntentResult:
    intent: Intent
    confidence: float
    slots: dict
    source: str  # "rule" | "llm"

def classify(message: str, history: list[dict], llm=None) -> IntentResult: ...
```

```python
# app/services/recommend.py
def recommend_for_user(db, shop_id: int, user_id: int, limit: int = 3) -> list[dict]: ...
def recommend_related(db, shop_id: int, product_id: int, limit: int = 3) -> list[dict]: ...
def recommend_hot(db, shop_id: int, limit: int = 3) -> list[dict]: ...
def recommend_within_budget(db, shop_id: int, budget_yuan: float, limit: int = 3) -> list[dict]: ...
```

```python
# app/schemas/dto.py
class ChatProductCard(BaseModel):
    id: int
    name: str
    image_url: str
    category: str
    price_from: float | None = None
    market_from: float | None = None
    sales_count: int = 0

class ChatOut(BaseModel):
    session_id: str
    answer: str
    mode: str
    tools: list[ToolTrace]
    notices: list[str]
    products: list[ChatProductCard] = []   # 新增
```

```python
# app/models/tables.py
class AgentToolLog(Base):
    __tablename__ = "agent_tool_logs"
    id = ...
    user_id = Column(Integer, index=True)
    shop_id = Column(Integer, index=True)
    session_id = Column(String(64))
    tool = Column(String(64))
    args = Column(Text, default="")          # 脱敏
    ok = Column(Boolean, default=True)
    latency_ms = Column(Integer, default=0)
    flag = Column(String(32), default="")    # 如 cross_user_attempt
    created_at = Column(DateTime, default=utcnow)
```

### 5.3 集成方式（不破坏现有链路）

`run_tool_loop`（`assistant.py`）在构造 `messages` 前插入：

```text
intent = classify(user_text, history, llm)
if intent.intent in (SMALLTALK, UNCLEAR):
    直接返回追问 / 闲聊，不 bind_tools
else:
    tools = filter(langchain_tools(), INTENT_TOOLS[intent.intent])
    llm = llm.bind_tools(tools)
traces 首项记 {"intent": ..., "source": ...}
```

- `agent_mode == "fallback"` 分支保持不动（`fallback.py` 关键词层即 FR-1 的 L1，天然复用）。
- 推荐商品回填：工具返回结果时，`recommend_products` / `search_products` 额外产出结构化列表，由 `Assistant.chat` 汇总进 `products`。

### 5.4 开关与兼容

`settings` 新增（默认关 → 开，便于回归与降级演示）：

| 配置 | 默认 | 作用 |
| --- | --- | --- |
| `agent_intent_enabled` | `true` | 显式意图路由 |
| `agent_recommend_enabled` | `true` | 推荐工具 |
| `agent_summary_enabled` | `true` | LLM 摘要 |
| `agent_audit_enabled` | `true` | 工具审计 |
| `agent_rate_limit_per_minute` | `30` | 每用户限流 |

- FR-4 摘要器必须捕获异常并回退到现有拼接逻辑。
- 向量模型 / LLM 不可用时，全链路沿用现有兜底（关键词检索 + 规则回复）。

## 6. 验收与测试策略

| 层 | 内容 |
| --- | --- |
| 单元 | `intent.classify`、`recommend_*`、`cleaner.split_by_headings`、`summarize` |
| 接口 | `POST /api/v1/c/shops/{code}/chat`：意图路由、推荐、越权、兜底、限流 |
| 回归 | 现有 `test_bc_link.py` agent 用例保持通过；全量 `pytest` 绿 |
| 演示 | 问商品 → 追问库存 → 查本人订单 → 查他人订单被拒 → 售后政策 → 推荐（带卡片） |

## 7. 风险与对策

| 风险 | 对策 |
| --- | --- |
| 意图误判导致路由错工具 | 两级识别 + `UNCLEAR` 追问；提供全工具兜底开关 |
| 前端卡片改动引入回归 | 无 `products` 时不渲染；复用现有商品卡样式 |
| LLM 摘要不可用 | 异常回退到现有拼接逻辑 |
| Chroma 重建影响数据 | reindex 幂等（已有 `delete_collection` 重建） |
| 限流误伤正常用户 | 阈值可配，默认 30/min |

## 8. 完整交付清单（对齐简历全量）

> 本节把简历里提到的**全部**能力逐项列出，标注「已实现」或「本次补强」，确保 PRD 与简历逐字对齐。

### 8.1 系统组成

| 简历表述 | 交付 | 状态 |
| --- | --- | --- |
| 商家管理后台 | `web/b.js` + `app/api/b_api.py` + `app/services/*` | ✅ 已实现 |
| C 端商品交易模块 | `web/c.js` + `app/api/c_api.py` + `services/catalog|orders|trade.py` | ✅ 已实现 |
| AI Agent 智能助手 | `app/agent/*` + `app/rag/*` | ✅ 已实现 + 本次补强 |

### 8.2 后端业务开发

| 简历表述 | 交付 | 状态 |
| --- | --- | --- |
| FastAPI + SQLAlchemy 商品/用户/订单接口 | `app/api/*` + `app/models/tables.py` | ✅ 已实现 |
| 商品上下架、SKU 管理 | `services/shelf.py` + `services/catalog.py` | ✅ 已实现 |
| 订单查询、权限校验 | `services/orders.py` + `core/deps.py` | ✅ 已实现 |
| MySQL 存储业务数据 | `docker-compose.yml`（MySQL 8.4） | ✅ 已实现 |
| Redis 热点数据与用户会话 | `db/redis_client.py` + `services/session.py` + 商品列表缓存 | ✅ 已实现 |

### 8.3 Agent 能力（本次补强重点）

| 简历表述 | 交付 | 状态 |
| --- | --- | --- |
| LangChain 构建电商助手 | `agent/assistant.py` | ✅ 已实现 |
| 意图识别 | `agent/intent.py` | 🚧 FR-1 补强 |
| 工具选择 / 参数提取 / 结果返回 | `run_tool_loop` + pydantic `args_schema` | ✅ 已实现 |
| 封装商品搜索/库存/订单工具 | `agent/tools.py` | ✅ 已实现 |
| Function Calling | `bind_tools` + `ToolMessage` | ✅ 已实现 |
| 智能推荐 | `services/recommend.py` + 工具 | 🚧 FR-2 补强 |

### 8.4 RAG 知识库

| 简历表述 | 交付 | 状态 |
| --- | --- | --- |
| 商品说明/平台规则/售后政策文档 | `knowledge/product_care.md`、`platform_rules.md`、`after_sales.md` | ✅ 已实现 |
| 清洗和分块 | `rag/cleaner.py` | 🚧 FR-3 补强 |
| Embedding 生成向量存入 Chroma | `rag/knowledge.py`（OllamaEmbeddings + chromadb） | ✅ 已实现 |
| 语义相似度检索 | `semantic_search`（cosine） | ✅ 已实现 |

### 8.5 多轮对话与上下文

| 简历表述 | 交付 | 状态 |
| --- | --- | --- |
| Redis 维护会话上下文 | `services/session.py` | ✅ 已实现 |
| 历史消息截断与摘要机制 | `agent/summarizer.py` | 🚧 FR-4 补强 |
| 控制上下文长度 | token 预算（`compact_messages`） | 🚧 FR-4 补强 |
| 结合用户身份/订单的多轮交互 | `agent/context.py` + 工具 | ✅ 已实现 |

### 8.6 工具调用安全与异常处理

| 简历表述 | 交付 | 状态 |
| --- | --- | --- |
| 参数校验 | `agent/guard.py` + pydantic | ✅ 已实现 |
| 用户身份认证 | `core/deps.py` `require_customer` | ✅ 已实现 |
| 权限控制、限制跨用户订单访问 | `describe_my_orders` 隔离 | ✅ 已实现 |
| 工具调用失败/参数缺失的重试 | `guard` 2 次重试 | ✅ 已实现 |
| 模型输出异常与兜底回复 | `ModelOutputError` + `fallback.py` | ✅ 已实现 |
| 审计与限流 | `AgentToolLog` + `chat` 限流 | 🚧 FR-5 补强 |

### 8.7 技术栈

| 技术 | 交付 | 状态 |
| --- | --- | --- |
| Python / FastAPI | 后端主体 | ✅ 已实现 |
| MySQL | `docker-compose.yml` | ✅ 已实现 |
| Redis | 缓存 / 会话 / 浏览记录 | ✅ 已实现 |
| LangChain | `langchain-core` / `langchain-ollama` | ✅ 已实现 |
| Ollama | `qwen2.5:7b` + `nomic-embed-text` | ✅ 已实现 |
| Pytest | `tests/` | ✅ 已实现，🚧 FR-6 补齐 Agent 用例 |
| Docker | `Dockerfile` + `docker-compose.yml` | ✅ 已实现 |
| Wireshark | 抓包排障，见 §9 | 🚧 本次补充说明 |

## 9. 可观测性与排障（Wireshark）

> 简历技术栈含 Wireshark，本节明确它在项目中的**真实用途**，保证面试可被追问。

### 9.1 用途定位

Wireshark 用于**网络层排障**，不参与业务逻辑：

1. **验证 Agent ↔ Ollama 通信**：本项目 LLM 与 Embedding 都走本机 Ollama 的 HTTP 接口（`127.0.0.1:11434`）。抓回环网卡可观察 `/api/chat`、`/api/embed` 的请求与响应，确认模型确实被调用、响应是否卡顿。
2. **定位接口时延**：过滤 `tcp.port == 8000`，对比 `chat` 接口整体耗时与其中 Ollama 调用耗时，区分「后端慢」还是「模型慢」。
3. **排查连接问题**：Docker 部署时确认容器到 `host.docker.internal:11434` 的连通性；Redis/MySQL 连接异常时看 TCP 握手。
4. **明文 HTTP 分析**：本地为明文 HTTP，可直接用 `http` 过滤查看；HTTPS 需配置 `SSLKEYLOGFILE` 才能解密。

### 9.2 推荐过滤表达式

| 场景 | 过滤器 |
| --- | --- |
| 只看 Ollama 调用 | `tcp.port == 11434 && http` |
| 只看后端 API | `tcp.port == 8000 && http` |
| 排除健康检查 | `http && !(http.request.uri contains "/health")` |
| 只看 Redis | `tcp.port == 6379` |

### 9.3 交付物

- [ ] T9.1 新增 `docs/troubleshooting.md`：记录上述抓包步骤 + 一次真实排障案例（如模型未启动时的超时表现）。

## 10. 附录：简历条目 → PRD / 代码对照

| 简历条目 | 对应交付 |
| --- | --- |
| 后端业务开发 | §8.2（已实现） |
| Agent 架构设计 | FR-1 `intent.py` + §8.3 |
| RAG 知识库构建 | FR-3 `cleaner.py` + §8.4 |
| 多轮对话与上下文管理 | FR-4 `summarizer.py` + §8.5 |
| 工具调用安全与异常处理 | FR-5 `AgentToolLog` + §8.6 |
| 技术栈 Wireshark | FR-8 / §9 |
