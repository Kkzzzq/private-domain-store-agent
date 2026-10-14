# CPU Ollama

服务器为 2 vCPU、约 2 GiB 内存，无 GPU。使用官方 Qwen3 0.6B 量化模型，只适合小规模演示，需要实测响应时间和工具选择准确率。

Ollama 作为 systemd 服务运行，监听 127.0.0.1:11434。单并行、最多一个模型、默认 2048 上下文、内存上限 1200 MiB。无需新增公网端口。模型数据位于 ollama 用户的 /usr/share/ollama/.ollama。

商城 backend/.env 的配置（不提交实际环境文件）：

```dotenv
AGENT_MODE=auto
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:0.6b
OLLAMA_REASONING=false
OLLAMA_NUM_CTX=2048
OLLAMA_NUM_PREDICT=160
OLLAMA_TIMEOUT_SECONDS=45
```

关闭推理思考以缩短 CPU 响应时间，查询仍通过原有身份和权限检查。模型失败时保留规则兜底；接口响应 mode=llm 才表示实际使用模型，health 中 agent_mode=auto 只代表配置。

服务器依赖包含 langchain-core/langchain-ollama；知识库继续使用关键词检索。本次不安装 Chroma 或另一个 Embedding 模型，以限制小内存机器上的开销。

运维命令：systemctl status ollama；journalctl -u ollama -n 100；ollama list；ollama ps。若需停用模型，将 backend/.env 中 AGENT_MODE 改为 fallback 并重启 private-store，随后停止 ollama。

如果修改服务内存限制、上下文或模型，先测试再启用。不要在这台机器上直接拉取并运行原默认 7B 模型。
