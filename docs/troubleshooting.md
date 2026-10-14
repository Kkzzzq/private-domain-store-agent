# 运行、验收与网络排障

## 本地运行

在 backend 目录安装 requirements.txt 后运行 `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`。FastAPI 同时提供前端：商家 `/b.html#/assistant`，买家 `/c.html?code=nanzhi`。已有本地 SQLite 数据会保留，新增审计表启动时自动创建。

无 MySQL 时默认 SQLite；Redis 不可用时内存降级，重启丢失会话、限流与缓存。生产运行应使用 MySQL 和 Redis，不能以 SQLite 回归测试替代生产数据库验证。

模型运行需要安装 Ollama，并执行 `ollama pull qwen2.5:7b` 和 `ollama pull nomic-embed-text`，通过 `/api/tags` 确认模型存在。AGENT_MODE=auto 时模型失败会返回 mode=fallback；AGENT_MODE=fallback 为主动规则演示。模型摘要使用相同模型，异常回退为事实摘要，预算包括摘要和历史。

## Docker

项目根目录执行 `docker compose up --build -d`，检查 MySQL/Redis/API 健康状态。宿主机 Ollama 需要能被容器通过 host.docker.internal:11434 访问。现有 Compose 使用示例凭据，部署前通过环境配置替换；Chroma 数据通过持久化卷保存。新建 MySQL 数据库由 SQLAlchemy 创建表，已有旧库字段变化需按当前模型迁移。

## 验收步骤

1. 买家登录后查询商品、SKU、预算推荐，核对卡片与详情价格；关闭店铺后推荐为空。
2. 查本人订单，再追问“这个订单发货了吗”；使用另一个买家同一订单号确认拒绝。
3. 商家登录后查看本店订单、经营概览、库存预警；另一商家查相同订单确认拒绝。
4. 超过 AGENT_RATE_LIMIT_PER_MINUTE 后返回 429；查看 agent_tool_logs，确认订单号脱敏、参数不含个人信息。
5. 商家调用 POST /api/v1/b/knowledge/reindex，mode=chroma 才代表真实向量生成成功；mode=keyword 代表降级。问售后问题确认来源与标题路径。
6. 运行 backend 下 `python -m pytest -q`。测试使用 SQLite/内存 Redis、模拟聊天模型，以及真实 Chroma 存储配确定性测试向量。模拟测试验证工具循环和安全边界，不能证明真实模型识别准确率。

## Wireshark 可复现排障

本节为操作步骤，不声称已经抓取或保存真实流量。Windows 选择 Npcap Loopback Adapter；Docker 选择对应虚拟网卡。使用演示账号和测试数据。

- `tcp.port == 8000 && http`：检查聊天请求是否到达、HTTP 状态与返回 mode。
- `tcp.port == 11434 && http`：检查 `/api/chat` 与 `/api/embed` 请求、响应及模型名。若没有 HTTP 解析，可对该 TCP 端口 Decode As HTTP。
- `tcp.port == 6379` 或 `tcp.port == 3306`：检查 Redis/MySQL TCP 握手、重传与连接重置。
- `tcp.analysis.retransmission`：定位重传；用 Follow TCP Stream 对照单个请求。HTTPS 不会直接展示明文业务内容。

复现模型离线：将 OLLAMA_BASE_URL 指向未监听的本地端口，在 auto 模式发送商品查询。预期网络连接失败，日志显示模型不可用，业务回复仍返回商品且 mode=fallback。恢复正确地址后再次查询，只有 mode=llm 并观察到模型请求才算真实模型验收。不要将这种预期流程写成已发生的实测案例。
