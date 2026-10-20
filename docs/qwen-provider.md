# 千问接入与密钥验收

## 当前检查结果

2026-10-20：用户指定的外部 qianwen_api.txt 文件只在服务端读取，未写入仓库或输出明文。格式为套餐专用前缀，使用百炼通用接口进行最小聊天和Embedding验证均得到HTTP401 invalid_api_key。尚未切换本地运行配置，不能宣称千问已联调成功。

官方区分套餐专用Key与通用百炼Key，二者地址与权限不互通。Coding Plan使用须知限制自动化脚本、自定义应用后端及非交互批量调用，因此不把该套餐Key搬到业务Agent或测试worker。

参考：https://help.aliyun.com/zh/model-studio/coding-plan

## 已实现的通用百炼适配

- 聊天沿用现有CloudChatModel的qwen/OpenAI兼容协议。
- Embedding新增QwenEmbedder，使用text-embedding-v4的兼容embeddings接口；最多10条一批，校验索引、维度、有限值和非零向量。
- EMBEDDING_PROVIDER支持qwen；保留Ollama和智谱适配。
- QA真实RAG场景按配置选择供应商，聊天和Embedding均计入预算。向量集合记录模型及输入版本，切模型必须新建集合，不能混用旧向量。

## 获得通用Key后

先最小验证聊天与Embedding均成功，再将本地忽略文件backend/.env配置为MODEL_PROVIDER=cloud、CLOUD_API_STYLE=qwen、CLOUD_API_KEY_FILE指向用户外部文件、CLOUD_BASE_URL为对应地域的通用兼容地址、CLOUD_MODEL=qwen-plus、EMBEDDING_PROVIDER=qwen、CLOUD_EMBEDDING_MODEL=text-embedding-v4。

地域以实际百炼控制台为准，不猜测空间ID。新的CHROMA_COLLECTION与重建索引只在确认后执行，保留旧知识集合方便回滚。重载API及QA worker前检查无活动测试，不能中断未知写任务。未经真实验证，规则/测试替身通过不计入真实模型或真实RAG门禁。
