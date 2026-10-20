# 登录与注册验收

## 已实现

- 商家 `/login`、买家登录弹窗、入口页登录门禁共用 `auth-ui.js`，支持注册、确认密码、密码遮罩、提交中禁用重复操作。统一登录入口为 `/account-login.html`；同一User同时持有B/C视角令牌，退出时撤销两端。旧角色接口保留兼容。
- 密码用带随机盐的 bcrypt 哈希存储，不保存明文。保留现有哈希兼容性；注册限制 UTF-8 编码最多72字节，避免中文长密码导致500或静默截断。登录错误统一提示，不区分用户名不存在与密码错误。
- JWT 固定 HS256，校验签名和必需的 sub / exp；新令牌增加 iat / 随机 jti。同账号连续登录得到不同令牌，权限以数据库身份为准，不能通过修改角色字段越权。
- `POST /api/v1/auth/logout` 将当前令牌 SHA-256 指纹写入 Redis 撤销列表，TTL 到令牌过期，不保存原始令牌。退出不影响同账号其他设备；B端切换账号/退出与C端店名旁退出均先调用此接口。注销账号仍由独立逻辑全身份停用。
- 普通接口和助手请求遇到401时，仅清除对应身份及上下文；403不退出，旧请求不会误删新登录令牌。网络故障导致服务端退出未确认时，保留登录并提示重试。
- 每来源IP登录默认60次/分钟，注册20次/15分钟，Redis原子计数，超出返回429与Retry-After。配置 `AUTH_LOGIN_LIMIT` / `AUTH_REGISTER_LIMIT`。未知用户名也执行密码校验，减少显著时间差。
- 重复用户名409；并发唯一键冲突回滚并返回409。已注销身份无法登录或继续使用旧令牌。

## 运行前提和边界

- 生产必须 HTTPS、足够随机的 JWT_SECRET（至少32字节）、真实 Redis 与严格依赖模式。内存 Redis 仅开发测试，重启会丢失撤销记录/限流；生产 Redis 需持久化和合适的淘汰策略。
- IP以ASGI可信客户端地址为准，反向代理只信任明确配置的代理，不能无条件信任外部X-Forwarded-For。共享出口用户会共用来源配额，可按实际流量调整。
- Token保存在sessionStorage，不是HttpOnly Cookie；同源XSS仍可能读取，需继续保持安全文本渲染、依赖更新和生产CSP。当前为访问令牌到期重新登录，尚无Refresh Token、短信/邮箱找回、MFA与设备管理，不宣称企业SSO完整实现。
- 参考官方 FastAPI 全栈模板的密码哈希、过期令牌、数据库身份验证方式；未直接复制其代码或引入整套框架：https://github.com/fastapi/full-stack-fastapi-template

## 回归命令

在backend目录运行：`.venv/Scripts/python.exe -m pytest tests/test_auth_security.py tests/test_account.py -q`。

在项目根目录运行：`node backend/scripts/test_auth_security.cjs`。

测试仅使用隔离SQLite与内存Redis；不修改实际账号密码，不注销实际用户，不连接大模型。
