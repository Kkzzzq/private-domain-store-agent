# 人工客服、物流和售后

## 使用入口

- 买家端右下角“联系商家”，商家端右下角“客户消息 / 售后”。与原有 AI 助手独立。
- 聊天支持离线留言、最近100条消息、加载更早记录、订单关联、未读数量。打开聊天时每3秒同步，关闭时每15秒检查未读；隐藏页面暂停轮询。消息在数据库持久保存，发送失败保留内容，重试去重。
- 商家在“订单物流”选择已付款订单，填写快递公司与运单号即发货；买家在同一入口查看。已有旧发货订单可以补录运单。支持商家追加运输、异常、签收记录；页面明确显示“商家更新”，尚未调用快递公司查询服务。
- 买家在“售后服务”选择已付款订单申请退货、换货、维修或其他处理；商家受理或拒绝并填写说明，受理后买家可提交退回运单，商家记录处理完成。双方均可从售后单“就此订单沟通”。待处理申请可由买家撤销。
- 售后完成仅记录处理结果，不修改原订单金额、库存或执行退款。暂不支持自动补发订单、客服消息图片和自动快递轨迹。

## 数据与权限

新增 `support_conversations`、`support_messages`、`order_shipments`、`after_sale_requests` 四张独立表；正常启动通过现有 `Base.metadata.create_all` 建表，不改变现有订单表列。

会话以店铺/买家唯一，发送消息时校验订单同时属于此店铺和该买家；商家只能访问自己店铺，买家只能访问自己的会话、运单和售后单。消息重试以会话/client_id唯一约束去重。已读游标只能单向推进。物流更新和售后流转加行锁；每单一份售后记录与物流单。

## 参考项目

此实现独立适配现有 Python/原生 JS 项目，未直接复制第三方源码或引入完整系统。

- [Chatwoot Conversation](https://github.com/chatwoot/chatwoot/blob/develop/app/models/conversation.rb)：借鉴会话归属、消息与已读管理的拆分。
- [Medusa Fulfillment](https://github.com/medusajs/medusa/blob/develop/packages/modules/fulfillment/src/models/fulfillment.ts)：借鉴物流履约记录独立于订单金额。
- [Medusa Return](https://github.com/medusajs/medusa/blob/develop/packages/modules/order/src/models/return.ts)：借鉴订单关联售后、状态流转与退回运单。

验证：`python -m pytest -q tests/test_support.py`。测试全部使用隔离数据库，涵盖真人双向消息/重试/未读/历史分页、跨买家与跨店隔离、订单关联、物流单及签收保护、售后受理/拒绝/撤销/退回/完成。
