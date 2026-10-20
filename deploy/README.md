# 阿里云商城部署

服务器：123.57.164.154，Ubuntu 20.04。项目位于 `/opt/private-store`。

正式入口：https://kkzzzq.cyou/ 。买家端 `/c.html?code=nanzhi`，商家端 `/b.html`。

服务：`private-store.service`，使用独立 Python 3.12、SQLite 持久数据库、Redis 第 1 号库。2026-10-20 健康接口实测 SQLite/Redis 正常、agent_mode=auto；助手实际模型能力需另行验收。

应用监听 `127.0.0.1:8001`，Nginx 对外提供 80/443，HTTP 自动跳转 HTTPS；保留 `127.0.0.1:8081` 预览入口。公网 80/443 已从客户端实际连接成功。

部署后的账号密码保存在服务器 `/root/private-store-accounts.txt`，本机副本位于 `D:\qiuzhao\other\私有配置\private-store-accounts.txt`。密钥和账号文件不放入代码仓库。

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

## 域名与 HTTPS（2026-10-20）

使用域名 `kkzzzq.cyou`，用户提供备案号 `陕ICP备2026029472号-1`。阿里云 DNS 主域名 A 记录已解析至 `123.57.164.154`；当前 www 无 A 记录，因此证书与站点仅绑定主域名。

Let's Encrypt 证书已签发，有效期至 2027-01-18。证书位于 `/etc/letsencrypt/live/kkzzzq.cyou/`，启用 `certbot.timer` 自动续期，成功后 hook 检查并 reload Nginx。账户未配置通知邮箱。

首页、买家端、商家端通过 `web/site-registration.js` 显示备案链接，独立于店铺装修。Nginx 关闭代理缓冲并使用 300 秒读超时，以支持助手响应。上线前配置及 HTML 备份位于 `/root/private-store-backups/20261020-100331-domain`。

`enable-domain.py` 供已有服务器在证书签发后运行，备份 HTML 和 Nginx 配置后启用域名；先上传 `web/site-registration.js`。它不会部署全部业务代码、迁移数据库或修改 DNS。此次仅接入域名并更新备案信息，服务器业务仍为原部署版本，本地正在开发的业务改动未整体上传。

如需 www，先在阿里云 DNS 添加 `www` A 记录至服务器，确认生效后扩展证书和 Nginx；不要仅添加解析而遗漏 HTTPS 证书。

`setup-demo.sh` 是本次服务器初始化脚本，依赖 `/opt/store-python/bin/python3.12` 和已上传的项目；不替换系统 Python。首次初始化会更换所有种子账号密码。依赖版本快照保存在服务器 `/opt/private-store/requirements-demo.lock.txt`。
