# 店铺满减券

本模块是适配当前 FastAPI + 原生 DOM 项目的独立实现。界面结构参考 [Vant Coupon](https://github.com/youzan/vant/blob/main/packages/vant/src/coupon/Coupon.tsx)（MIT），领取/订单校验流程参考 [mall UmsMemberCouponServiceImpl](https://github.com/macrozheng/mall/blob/master/mall-portal/src/main/java/com/macro/mall/portal/service/impl/UmsMemberCouponServiceImpl.java)（Apache-2.0）。未引入 Vue 或 Java 服务，未复制上述项目源码。

## 使用

- B 端「优惠券管理」设置名称、门槛、减免金额、总量、开始/结束时间，创建后 C 端详情页和结算页可领。已发券条款不可改，只能启用/停用，修改规则应新建券。
- 每账号每券限领 1 张；券仅限发券店铺，每单最多 1 张，不抵运费。折扣最多抵完商品金额。满减门槛与包邮均按优惠前商品金额判断。
- 领取计数使用条件更新、用户领取唯一约束；下单条件锁券，成功支付记已使用。取消/超时订单释放券；过期/停用券释放后仍不可用。
- C 端结算调用服务端报价，创建订单再次核验，金额一律整数分计算。B/C 订单返回相同优惠快照。停用不追溯更改已生成的待支付订单金额。
- 使用独立 coupons/user_coupons/coupon_orders 表，启动 create_all 创建；不改变既有订单表。金额快照独立保存，旧订单优惠为 0。
- 自动取消仍沿用现有 60 秒调度；支付已过期订单会被拒绝。

## 接口

- B：GET/POST `/api/v1/b/coupons`，PATCH `/api/v1/b/coupons/{id}`（enabled）。
- C：GET `/api/v1/c/shops/{code}/coupons`，POST `/coupons/{id}/claim`，POST `/coupon-quote`（items、user_coupon_id）。
- 直购与购物车结算均可传 user_coupon_id，未传不使用券。

## 结算交互（2026-10-20）

- 结算只保留一行优惠券入口，不再显示 select 下拉行。默认从已领取、有效且满足当前订单门槛的券中，选择实际抵扣最多的一张；同额优先低门槛，再按领取记录 ID 稳定排序。
- 自动选券后再次请求服务端报价，不在前端手算最终优惠金额。未领取的券不会被自动领取；用户在弹窗领取后重新选择当前最优已领券。
- 点击入口可换券或选择不使用。选中券卡右上角展示“使用中”；手动不使用后不自动重新勾选，除非主动领取新券或重新进入结算。
- 详情与结算没有有效可领取/已领可用券时，隐藏优惠券入口；不显示“暂无优惠券”占位。未满足门槛但仍有效的券可查看，不能选择使用。当前优惠券全店通用，没有伪造商品专属优惠范围。
- 报价进行中禁用提交和入口，报价失败不能提交，订单创建仍由后端校验归属、有效期和库存。金额为0时不显示优惠抵扣行。
- 验证：后端优惠券/业务17项通过；`node backend/scripts/test_coupon_selection.cjs` 验证自动选券、金额封顶、状态过滤、稳定排序及入口空态隐藏。真实8001浏览器109元订单自动减10为99元，弹窗右上角“使用中”，取消后109元，重新选择后99元；未提交订单或支付。截图 `docs/screenshots/coupon-using-auto.png`。
- 当前8000运行旧版本，OpenAPI没有 coupon-quote；8001已有完整券接口。此次仅前端改动无需重启8001，8000需正常更新/重启才能使用优惠券。没有绕过此前停止策略。

## 验证

`python -m pytest tests/test_coupons.py tests/test_bc_link.py -q`

大字号现价/原价采用本地 Geist Semibold/Regular、直立数字；参考 [Vercel Commerce](https://github.com/vercel/commerce/blob/main/app/layout.tsx)。标签中文继续微软雅黑，标签数字仍为 Roman。
