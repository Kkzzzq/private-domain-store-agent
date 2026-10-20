# DeepSeek 本地接入

2026-10-20 已按用户指定读取外部 deepseek_api.txt，密钥不入仓库、不输出。聊天使用 https://api.deepseek.com、deepseek-flash、非思考模式；工具调用保留原有LangChain工具与服务端权限边界，不发送千问专用enable_thinking字段。

真实验证：最小工具请求HTTP200并调用check_inventory；隔离业务A02库存、A03先目录再推荐、A05数量总预算、A09缺预算澄清全部通过，实际模型为deepseek-flash，报告位于backend/data/acceptance/quality-deepseek-switch.json。相关49项专项测试通过。这不是全部40条助手用例通过。

聊天与Embedding分别配置。CLOUD_API_KEY_FILE仅用于DeepSeek聊天。最新已按用户提供的embedding_api.txt切换千问qwen3.7-text-embedding-flash，1024维；独立端点与独立外部凭据。显式独立向量端点缺密钥时直接报错，绝不把DeepSeek密钥发送给Embedding供应商。新Chroma集合保留旧集合，真实RAG四场景已通过，详见three-agents-progress.md。

本地backend/.env已更新且保持忽略；未修改远端配置。OP用例显示已接入仅表示执行器存在，真实模型/向量验收结论仍以运行报告为准。

官方接口与工具调用参考：https://api-docs.deepseek.com/guides/tool_calls/
