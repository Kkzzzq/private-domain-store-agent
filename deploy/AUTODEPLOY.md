# GitHub 自动部署

仓库：https://github.com/Kkzzzq/private-domain-store-agent

本地 main 推送后，GitHub Actions 执行 Python 3.12 后端测试、前端语法检查，再将该提交的代码通过 SSH 发送到阿里云 123.57.164.154。服务器无需保存 GitHub 登录凭据。Actions 页面可查看部署结果，也可通过 workflow_dispatch 手动部署 main。

```powershell
git add .
git commit -m "描述本次修改"
git push origin main
```

GitHub Secrets：ALIYUN_DEPLOY_KEY、ALIYUN_KNOWN_HOSTS。部署密钥使用强制命令，只能调用服务器 /usr/local/sbin/private-store-receive；不允许 shell 或端口转发。原有管理密钥保留。

服务器保持 /opt/private-store 和 private-store.service，不改 Nginx、域名或备案状态。数据库 backend/data、backend/.env、web/covers/uploads 不在更新范围。助手继续使用 fallback 模式；服务器依赖列表为 backend/requirements-server.txt。

每次更新在 /root/private-store-backups/<时间>-<提交前缀> 保存代码、Python 环境和 SQLite 快照。更新期间服务会短暂停止；健康检查失败自动恢复原代码和依赖。数据库备份不会自动覆盖正在使用的数据。涉及表结构变更时必须单独设计迁移和回退，自动部署不等于自动数据库迁移。

已部署提交记录在 /opt/private-store/deployed-commit。查看日志：journalctl -u private-store -n 100。接收脚本由管理员单独安装，本仓库修改该脚本后需人工通过管理 SSH 更新 /usr/local/sbin/private-store-receive。

服务器保存备份会占用磁盘，应定期将旧备份归档到外部存储。
