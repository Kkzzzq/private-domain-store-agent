# 服务器 MySQL 数据迁移（2026-10-20）

来源为本机实际使用的 `127.0.0.1:13306/private_store_demo`，不是独立验收库。`backend/scripts/transfer_database.py` 在 MySQL REPEATABLE READ 事务中导出全部 24 张业务表，导入服务器空数据库前验证快照校验和，并在同一导入事务内逐表比较全部内容。目标非空或应用表集合不一致时拒绝导入。

快照包括 3 个用户、1 家店铺、35 件商品、58 个 SKU、4 个订单、4 条订单明细，以及地址、购物车、分类、标签、轮播、栏目、优惠券、评价和助手资料。已有 3 个同名用户保留服务器密码哈希，其他业务记录来自本地。服务器原 SQLite 不删除，旧服务的最终快照单独备份。

数据库导出文件位于已忽略的 `backend/data`，通过管理 SSH 上传到服务器 root 私有目录，不进入 GitHub。图片随源代码与本机上传目录一起迁移；后续正常自动部署保留线上上传目录。Redis 使用服务器新的 DB2 缓存命名空间，不迁移本机临时缓存和对话上下文。

迁移准备记录：`/root/private-store-migration-state.json`，其中记录目标库名、暂存目录和备份路径，不含密码。备份目录 `/root/private-store-backups/20261020-101158-before-mysql` 包含原配置、SQLite 快照及代码和图片。MySQL 仅监听本机，128MB InnoDB buffer pool、30 个最大连接，配置源 `deploy/mysql-small.cnf`。

切换程序 `deploy/cutover-mysql.py` 停止应用后再做最终旧库备份，更新代码与连接配置，启动并实际检查 MySQL/Redis readiness；失败恢复旧代码和配置。成功后立即验证一次 mysqldump 备份。MySQL 的后续备份使用 `deploy/backup-database.py`，由服务器接收脚本在每次部署前调用。

以后 commit/push main 只更新代码，不重复导入本机数据，也不覆盖服务器 `.env`、数据库和用户上传文件。表结构变化仍需适配迁移；不要在已有业务数据的线上库重新运行本次一次性导入。
