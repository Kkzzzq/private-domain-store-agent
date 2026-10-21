# 南枝全页展示数据与扩展实店用例

目标站点：https://shop.kkzzzq.cyou。实际主体为 share_code=nanzhi 的已有店铺，界面名称为南枝手作。

## 数据范围

`backend/scripts/seed_nanzhi_showcase.py` 使用批次 `nanzhi-showcase-v2-20261021`，追加12个标明演示的账号、12件商品/36个SKU、24笔演示订单、6张优惠券、11份物流、6张售后申请及评价、地址和客服会话。原有第一批数据保留。

- 订单：pending / paid / shipped / completed / cancelled。
- 物流：shipped / transit / exception / delivered。
- 售后：requested / accepted / rejected / return_shipped / resolved / withdrawn；类型含退货、换货、维修、其他。
- 优惠券发行：active / scheduled / expired / disabled / exhausted；领取关联包含 available / reserved / used，订单券关联包含 reserved / used / released。
- 商品：on / off / draft / banned，规格含on/off/banned、零库存、低库存、多规格和限购。
- 账号：正常、禁用、注销、可开店；真实管理员原账号保留。
- 评价：多评分、展示中与隐藏。
- 店铺：南枝主店保持营业；另外两家明确标明演示的样例店分别展示停业和平台封店，不承载实店测试订单。
- 维护审计：通过真实OP接口执行成功维护和被业务规则拒绝的维护，形成 succeeded / failed；不伪造未完成pending意图。
- 治理和平台记录：真实执行商品禁售/解除、单规格禁售、隐藏评价、禁用本批账号、封禁本批演示样例店。
- 助手审计：真实模型测试留下成功工具调用及权限拒绝等失败标记，不直接插入伪造调用日志。

所有展示订单均为明确标识的模拟业务状态，不调用外部支付、退款或快递。所有已付款金额均为展示统计，不能当作真实资金成交。展示待付款订单允许无到期时间，避免自动测试归档把展示状态清空；可由平台正常取消。

工具默认只预览。实际运行须同时匹配数据库名称、已有店铺ID和有效OP身份。批次重复运行不新增；中断后可重跑补足治理步骤。`verify()`直接核验24订单金额/优惠抵扣、SKU归属、所有物流/售后状态以及领券计数。

## 页面修复

物流筛选改查真实Shipment状态，售后筛选改查真实AfterSale状态，并显示相应中文状态，不再误用订单状态。优惠券新增按店铺和5种发行状态分页查询，显示未用、锁定、核销数量及真实有效期。订单、物流、售后仍须先选店铺或关键词，不默认全量展示。

## 72条实店测试

目录为40条接口、16条Agent、16条UI；新增46条，保留原26条。`real_cases_extended.py`保存中文步骤/预期，`real_scenarios_extended.py`、`real_scenarios_agent.py`、`real_scenarios_ui.py`分别执行真实HTTP/数据库、真实模型、真实Playwright页面操作。

扩展覆盖库存不足/限购/非法状态转换/禁售治理/购物车幂等与越权/地址默认唯一/券窗口和名额/报价无副作用/锁券核销释放/物流终态/售后拒绝撤销退回/消息幂等已读/评价治理/订单条件分页，以及模型隐私、实时库存、空搜索、会话隔离、多轮对话和全部管理页导航。

每次执行使用随机测试身份、商品和订单，保留审计/交易证据；结束取消自己未付款订单、归档自己测试商品并关闭测试券，不删除展示批次或修改原商品。子进程中断使用现有台账恢复。真正的UI测试保存真实截图。

Agent隐私用例允许复述用户输入的单号，要求拒绝越权工具结果，且不能泄露用户未输入的私密标记收件人。拒绝审计的ok=false是预期，不把真实权限拒绝误当执行器错误。未找到记录与系统错误仍在实际证据中展示。

本轮首轮线上扩展执行43/46通过、3条失败，原始结果已导入OP并保留（不是重放业务或伪造通过）。其中发现并修复：库存追问被历史搜索替换；否定词“不要推荐”误触推荐意图。另修正了隐私测试的判据。

回归命令：从backend运行 `python -m pytest tests/test_real_shop_runner.py tests/test_nanzhi_showcase.py tests/test_op_business_states.py tests/test_agent_inventory_followup.py tests/test_real_extended_catalog.py`。Windows使用项目data下独立`--basetemp`。生产实店执行须通过现有计划、批准、队列、worker和报告链路；严禁把pytest清库夹具指向实际数据库。
