# 统一账号与开店授权

登录后同一站点的门户、C端、B端及新标签页复用当前账号，密码不保存；令牌仍由服务端校验有效期与撤销状态。同源共享登录，localhost与线上域名不会共享凭据。

普通注册固定买家身份，即使提交role=merchant也不能自授商家权限。普通账号不建空店、不签发B端令牌；门户C入口进入南枝演示店，B卡置灰、不可点击。已有merchant角色属于既有授权；其他账号需由管理员显式授权后才创建自己的店铺。

在backend目录运行 `python scripts/manage_merchant_access.py 用户名` 授权，附加 `--revoke` 撤销。撤销后旧B令牌立即被服务端拒绝；保留已有店铺与业务数据。SharedAccount仅表示使用统一登录，不代表开店权限。

验收：test_unified_account.py覆盖普通注册防提权、授权前不建店、授权后双端、撤销旧令牌；test_shared_session.cjs覆盖新标签页及退出；隔离浏览器普通账号灰卡、另开C标签已登录。
