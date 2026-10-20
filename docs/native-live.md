# 无虚拟化真实环境与验收

日期：2026-10-19；基线：prd-native-live.md。保留用户禁用虚拟化，不使用WSL2，不修改BCD、不安装系统数据库服务、不重启电脑。

## 实际运行组件

- Oracle MySQL Community 8.4.11官方Windows ZIP；mysqld.exe签名Oracle America, Inc.校验有效。ZIP：`https://cdn.mysql.com/Downloads/MySQL-8.4/mysql-8.4.11-winx64.zip`，SHA256 `a492371d687d2bab088b0062581144a0044b8964baefdf4faa579292b423d25c`。
- Redis 8.10.2社区Windows/Cygwin构建，不是Redis Ltd官方Windows发行，不是内存替代。来源：`https://github.com/redis-windows/redis-windows/releases/download/8.10.2/Redis-8.10.2-Windows-x64-cygwin.zip`，本轮ZIP SHA256 `6de5cc7f5adbf97b5928b13766383d4ad424626ef3d8b313ffff12d820ec6fc1`。该摘要记录下载产物，不冒充独立发布者签名。生产优先原Linux/Docker方案。
- 真实聊天模型：完整验收固定GLM-5.3-FlashX，不启用模型切换，避免实际模型不明。运行演示默认Flash并保留用户授权的额度切换。
- 真实Embedding：智谱Embedding-3，1024维；真实Chroma持久化。保留原Ollama适配及原BGE索引，不把云端链路写成Ollama运行。接口参考[智谱官方Embedding-3](https://docs.bigmodel.cn/cn/guide/models/embedding/embedding-3)。

所有数据库仅监听127.0.0.1。此为本机演示，样例数据库密码不可用于生产；Redis回环保护但未配置生产ACL/TLS，不对公网开放。

## 准备与启动

从backend目录执行以下命令。运行库和数据均在被Git忽略的data/acceptance/native，不进入源码仓库。

先将上述MySQL ZIP解压到 `data/acceptance/native/mysql-runtime/mysql-8.4.11-winx64`，Redis ZIP解压到 `data/acceptance/native/redis-runtime/Redis-8.10.2-Windows-x64-cygwin`。本机已完成下载与解压；其他机器自行下载并校验来源，不能依赖本机ignored产物。

```powershell
.\.venv\Scripts\python.exe -m scripts.native_services start
.\.venv\Scripts\python.exe -m scripts.native_services status
```

脚本首次仅初始化独立MySQL目录及private_store_acceptance，设置本地演示账号，Redis启用AOF与64MB内存上限。重复启动仅复用脚本明确拥有且占用预期端口的进程；发现其他进程占端口则拒绝，不接管或清空数据。MySQL Windows监控父进程与监听子进程通过父子关系、路径及创建时间核对。

## 完整真实验收

确认 `.env.acceptance.native.example` 的CLOUD_API_KEY_FILE指向自己的外部密钥文件。不要把密钥复制进仓库。

```powershell
.\.venv\Scripts\python.exe -m scripts.live_acceptance --env-file ../.env.acceptance.native.example --api-url http://127.0.0.1:18001 --phase full --manage-api --report data/acceptance/full-native.json
```

本轮full-native.json：passed=true，A01至A07七组全部通过。MySQL 8.4.11实际落库、真实Redis缓存/失效、权限/审计/限流、真实模型五类工具、三道原RAG问题的Embedding→Chroma首位来源→真实回答、真实摘要及API进程停止/重建后同一订单追问均通过。A07仍明确是确定性故障契约/不可达端点测试，不冒称所有故障都发生在真实云服务。

增强验收增加真实MySQL/Redis中的需求推荐：80元买两件37元马克杯→同会话把总预算降为70元且不改数量。必须先概览再筛选，首轮小计74元可购，追问无匹配且不放宽。首次增强试跑模型只看概览后心算无匹配，虽结论正确但跳过后端筛选，报告full-native-enhanced.json保持失败；已新增阶段完成校验与显式缺条件追问工具，再用full-native-enhanced-v2.json记录复跑，不把失败报告覆盖为成功。

最新full-native-enhanced-v2.json：passed=true，七组全部通过，A03包含需求推荐与真实Redis追问。全量代码回归161 passed，另有117条既有测试短JWT警告；不将故障契约/模拟协议测试当作真实模型样本。

验收记录了两个不同API进程PID，Redis会话TTL与真实模型摘要、来源与距离、工具结果及脱敏回答。数据库没有清空，测试仅创建随机账号/店铺/订单。旧full.json等失败报告保留，不覆盖为“历史一直通过”。

## 可使用的演示环境

演示库private_store_demo、Redis DB0与验收库private_store_acceptance、Redis DB1分开；旧SQLite文件原样保留，未迁移或删除。

```powershell
.\.venv\Scripts\python.exe -m scripts.native_services provision-demo
```

将 `.env.native-demo.example` 的本机配置放入backend/.env（本机已配置）。从backend启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

本机当前8000已启动，无需重复启动；日志data/demo-api.stdout.log、data/demo-api.stderr.log，启动进程回执data/demo-api-process.json。商家http://127.0.0.1:8000/b.html，买家http://127.0.0.1:8000/c.html?code=nanzhi。/api/v1/ready返回mysql/redis、严格模式、zhipu/embedding-3/1024维。本机已通过商家知识重建接口生成14块真实向量；其他机器首次需要商家登录后调用/b/knowledge/reindex，严格模式不会用关键词冒充成功。

此演示的支付是业务状态模拟，不是接入真实支付渠道；所有Agent工具仍只读，不自动下单或退款。

## 实际API抓包

Wireshark/Npcap已经用户授权安装。运行：

```powershell
.\.venv\Scripts\python.exe -m scripts.capture_acceptance --env-file ../.env.acceptance.native.example
```

该脚本临时启动自己的18003严格验收API，仅抓该回环端口的无认证GET /api/v1/ready，五秒结束，并停止自己创建的API。不使用日常8000端口，避免捕获浏览器登录令牌。本轮15个真实包、HTTP GET及200通过，pcapng及SHA256见data/acceptance/wireshark-api.json。这证明项目就绪接口的实际TCP/HTTP通信，不声称抓到了TLS加密模型正文或真实故障根因。

## 停服与安全边界

先正常结束使用这些数据库的演示API，再运行：

```powershell
.\.venv\Scripts\python.exe -m scripts.native_services stop
```

只在可执行路径、进程创建时间、监听端口及PID均对应自己记录时发送SHUTDOWN；不强杀其他进程，不删除数据目录。API自动托管验收结束时自行停止，常驻演示服务则有意保留供用户使用。若需要人工处理常驻后台进程，先核对data/demo-api-process.json与当前进程创建时间/命令行，不能直接使用历史PID杀进程。
