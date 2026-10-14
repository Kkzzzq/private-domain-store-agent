# 阿里云练手部署

服务器：123.57.164.154，Ubuntu 20.04。项目位于 `/opt/private-store`。

当前商城通过 SSH 转发在本机预览：`http://127.0.0.1:18081/`。该地址仅在建立转发的电脑上可用。

服务：`private-store.service`，使用独立 Python 3.12、SQLite 持久数据库、Redis 第 1 号库。助手使用规则检索。不会调用本地大模型，Chroma 和 LangChain 未安装。

应用监听 `127.0.0.1:8001`，Nginx 监听 `127.0.0.1:8081`。目前没有公开商城端口或修改 Cloudflare DNS。

部署后的账号密码保存在服务器 `/root/private-store-accounts.txt`，本机副本位于 `D:\qiuzhao\private-store-accounts.txt`。密钥和账号文件不放入代码仓库。

重新建立本机预览通道，在 PowerShell 执行：

```powershell
ssh -i C:\Users\Nanohana02\.ssh\kkzzzq_deploy -N -L 127.0.0.1:18081:127.0.0.1:8081 root@123.57.164.154
```

服务器上查看状态、日志、重启：

```bash
systemctl status private-store
journalctl -u private-store -n 50
systemctl restart private-store
```

备份时同时保存 `backend/data`、`backend/.env` 和 `web/covers/uploads`。SQLite 在运行时应通过 SQLite backup API 备份。

## 域名接入待办

阿里云检测提示当前 Cloudflare 注册商不符合备案条件。北京服务器公开域名网站前，需要解决域名注册商及 ICP 备案条件；或者另行部署到香港或海外服务器。

满足托管条件后，配置服务器 HTTPS 证书与 Nginx 443 入口、放行安全组 80/443，再在 Cloudflare 添加网站 A 记录指向服务器公网 IP，并配置 Full (strict)。保留已有 MX、TXT 和 cursor 隧道记录。当前没有执行这些公开接入步骤。

`setup-demo.sh` 是本次服务器初始化脚本，依赖 `/opt/store-python/bin/python3.12` 和已上传的项目；不替换系统 Python。首次初始化会更换所有种子账号密码。依赖版本快照保存在服务器 `/opt/private-store/requirements-demo.lock.txt`。
