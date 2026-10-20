# 统一账号与店铺入口

- 访问 `/` 时先验证已有会话。未登录或登录失效，跳转到 `/account-login.html`；不会先展示南枝页面。
- 演示登录页通过 `/api/v1/auth/demo-login` 获取预填凭据。该接口按用户要求公开演示账号，响应禁止缓存。配置 `DEMO_LOGIN_ENABLED`、`DEMO_LOGIN_USERNAME`、`DEMO_LOGIN_PASSWORD`；本地默认为种子演示账号，服务器值仅存环境文件，不入仓库。切换账号进入空表单。
- 登录、注册统一使用 `/auth/portal-login`、`/auth/portal-register`。同一 User 同时取得 B/C 视角令牌，保存在当前标签页 sessionStorage；不复制出另一份用户或改变原始用户角色。
- `shared_accounts` 记录已启用统一能力的账号。认证依照数据库账号及此记录校验签名后的角色视角，`User.actor_role` 只影响当前请求。旧的分角色登录接口保留兼容。
- 当前账号名下没有店铺时，首次进入统一账号流程创建其自己的空店铺；有店铺则沿用。南枝账号继续对应 nanzhi；其他账号的两个入口都对应自己的店铺，不复制南枝商品、订单或装修记录。入口页忽略 URL 中试图指定其他店铺的 code。
- 买家与商家视角下 IM 按消息方向管理未读，订单/售后/助手按正确视角校验。退出统一会话时两枚令牌都撤销；其他设备不受影响。
- 店铺名称、Logo、入口品牌文案继续由该店铺后台设置。认证加固沿用登录验收文档。

回归：`python -m pytest -q tests/test_unified_account.py tests/test_auth_security.py tests/test_support.py`，以及根目录 `node backend/scripts/test_auth_security.cjs`。
