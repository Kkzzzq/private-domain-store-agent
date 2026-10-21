# 商城子域名

2026-10-20 按用户最新要求，新增 https://shop.kkzzzq.cyou/ ，主域名 https://kkzzzq.cyou/ 保持原页面，不跳转到 shop。

阿里云 DNS 新增 `shop` A 记录指向 `123.57.164.154`，默认线路、TTL 10 分钟。原有 `@` 记录未改。

Nginx 使用独立 `/etc/nginx/sites-available/private-store-shop` 配置，通过 sites-enabled 同名链接启用；后端仍为 `127.0.0.1:8001`。shop HTTP 跳转至其自身 HTTPS，证书位于 `/etc/letsencrypt/live/shop.kkzzzq.cyou/`，有效期至 2027-01-18，已有 certbot.timer 和 reload hook 会处理续期。主域名 Nginx 配置文件内容校验未变化。

`enable-shop-domain.py http` 配置签证书前的 ACME 入口；证书签发后运行 `enable-shop-domain.py https`。此操作只需管理 SSH，不随应用自动部署重复执行。主域和子域当前共用相同代码及 MySQL/Redis，GitHub main 的代码发布会同时更新两边。

主域已备案时，普通子域通常无需单独备案，参见阿里云 https://help.aliyun.com/zh/icp-filing/basic-icp-service/support/for-the-record-domain-faq/ 。用户提供的备案网站名为“看看制作周期”，实际商城名为“南枝手作”，已提示核对网站名称、内容与备案信息的一致性；本轮未代办或修改备案。
