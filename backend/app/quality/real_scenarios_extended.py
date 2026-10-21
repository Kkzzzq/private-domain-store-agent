"""独立扩展场景；只修改 RealCase 创建的随机批次记录。"""
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select, func
from app.db.session import SessionLocal
from app.models.tables import (Address, CartItem, Coupon, CouponOrder, Order, OrderItem,
    Product, Review, Sku, UserCoupon, AgentToolLog, utcnow)
from app.models.support import AfterSale, Message, Shipment


def buyer(ctx):
    with SessionLocal() as db:return ctx.new_buyer(db)


def coupon(ctx, **changes):
    now=utcnow()
    body=dict(name='【实测】扩展券 '+ctx.tag,threshold_cents=0,amount_cents=100,total_count=5,
              starts_at=(now-timedelta(days=1)).isoformat(),ends_at=(now+timedelta(days=1)).isoformat())
    body.update(changes)
    row=ctx.call('POST','/b/coupons',ctx.merchant,body);ctx.coupons.append(row['id'])
    return row


def order_body(sku,**changes):
    body=dict(sku_id=sku,quantity=1,address='演示地址，请勿实际配送',receiver='实测收件人',phone='00000000000')
    body.update(changes);return body


def completed(ctx,p):
    row=ctx.order(p,True)
    ctx.call('PUT',f"/support/orders/{row['order_no']}/shipment",ctx.merchant,{'carrier':'演示物流','tracking_number':'DEMO-'+ctx.tag})
    ctx.call('POST',f"/c/orders/{row['order_no']}/confirm",ctx.buyer)
    with SessionLocal() as db:return db.scalar(select(OrderItem.id).join(Order).where(Order.order_no==row['order_no']))


def run(ctx,cid):
    if cid.startswith('RA'):
        from app.quality.real_scenarios_agent import run as agent
        return agent(ctx,cid)
    if cid.startswith('RE'):
        from app.quality.real_scenarios_ui import run as ui
        return ui(ctx,cid)
    call=ctx.call;check=ctx.e.check;b=ctx.buyer;m=ctx.merchant;op=ctx.op
    p=ctx.fixture(on=cid!='RF19');pid=p['id'];sku=p['skus'][0]['id']
    if cid=='RF13':
        call('PATCH',f'/b/skus/{sku}',m,{'stock':0})
        call('POST','/c/shops/nanzhi/orders',b,order_body(sku),status=(400,))
        with SessionLocal() as db:check('零库存拒绝且无订单',db.get(Sku,sku).stock==0 and not db.scalar(select(Order.id).where(Order.user_id==ctx.buyer_id)))
    elif cid=='RF14':
        call('PATCH',f'/b/skus/{sku}',m,{'stock':1})
        call('POST','/c/shops/nanzhi/cart',b,{'sku_id':sku,'quantity':2},status=(400,))
        with SessionLocal() as db:check('库存不足未写入购物车',not db.scalar(select(CartItem.id).where(CartItem.user_id==ctx.buyer_id)))
    elif cid=='RF15':
        call('PATCH',f'/b/products/{pid}',m,{'limit_per_user':1});o=ctx.order(p)
        call('POST','/c/shops/nanzhi/orders',b,order_body(sku),status=(400,))
        call('POST',f"/c/orders/{o['order_no']}/cancel",b);new=ctx.order(p);ctx.db_check_order(new,'pending')
    elif cid in ('RF16','RF17','RF18'):
        o=ctx.order(p,cid!='RF17');number=o['order_no']
        action={'RF16':'pay','RF17':'confirm','RF18':'cancel'}[cid]
        call('POST',f'/c/orders/{number}/{action}',b,status=(400,))
        ctx.db_check_order(o,'pending' if cid=='RF17' else 'paid')
        with SessionLocal() as db:check('重复或非法转换未重复扣库存',db.get(Sku,sku).stock==19,19,db.get(Sku,sku).stock)
    elif cid=='RF19':
        call('POST','/c/shops/nanzhi/orders',b,order_body(sku),status=(400,))
        call('POST',f'/op/products/{pid}/moderate',op,{'action':'ban','reason':'实测草稿禁售 '+ctx.tag})
        call('POST','/c/shops/nanzhi/orders',b,order_body(sku),status=(400,))
        with SessionLocal() as db:check('禁售草稿无订单',not db.scalar(select(Order.id).where(Order.user_id==ctx.buyer_id)))
        call('POST',f'/op/products/{pid}/moderate',op,{'action':'release','reason':'实测归档 '+ctx.tag})
    elif cid=='RF20':
        call('POST',f'/op/products/{pid}/moderate',op,{'action':'ban','reason':'实测禁售 '+ctx.tag})
        check('禁售后C列表隐藏',not any(x['id']==pid for x in call('GET','/c/shops/nanzhi/products')))
        result=call('POST',f'/op/products/{pid}/moderate',op,{'action':'release','reason':'实测解除 '+ctx.tag});check('解除为下架',result['status']=='off','off',result['status'])
        call('POST',f'/b/products/{pid}/status',m,{'action':'on'});check('重新上架C可见',call('GET',f'/c/shops/nanzhi/products/{pid}')['id']==pid)
        from app.models.operations import OperationLog
        with SessionLocal() as db:check('两条真实商品治理记录',set(db.scalars(select(OperationLog.action).where(OperationLog.product_id==pid)))=={'ban','release'})
    elif cid=='RF21':
        call('POST',f'/op/governance/skus/{sku}',op,{'action':'ban','reason':'实测规格禁售 '+ctx.tag})
        call('POST','/c/shops/nanzhi/orders',b,order_body(sku),status=(400,))
        call('POST',f'/op/governance/skus/{sku}',op,{'action':'unban','reason':'实测解除 '+ctx.tag})
        from app.models.platform_audit import PlatformAudit
        with SessionLocal() as db:
            check('解除规格为off',db.get(Sku,sku).status=='off')
            check('规格治理日志实际落库',db.scalar(select(func.count()).select_from(PlatformAudit).where(PlatformAudit.target_type=='sku',PlatformAudit.target_id==sku))==2)
    elif cid in ('RF22','RF23'):
        cart=call('POST','/c/shops/nanzhi/cart',b,{'sku_id':sku,'quantity':1});item=cart['items'][0]['id']
        if cid=='RF22':call('POST','/c/shops/nanzhi/cart',b,{'sku_id':sku,'quantity':2})
        else:
            _,other=buyer(ctx)
            call('PATCH',f'/c/cart/{item}',other,{'quantity':3},status=(404,));call('DELETE',f'/c/cart/{item}',other,status=(404,))
        with SessionLocal() as db:
            rows=list(db.scalars(select(CartItem).where(CartItem.user_id==ctx.buyer_id)))
            check('购物车仅一项且数量符合预期',len(rows)==1 and rows[0].quantity==(3 if cid=='RF22' else 1))
    elif cid in ('RF24','RF25'):
        body={'receiver':'演示收件人','phone':'00000000000','region':'演示地区','detail':'演示详细地址','is_default':True}
        first=call('POST','/c/addresses',b,body)
        if cid=='RF24':
            second=call('POST','/c/addresses',b,body)
            with SessionLocal() as db:check('默认地址唯一',db.scalar(select(func.count()).select_from(Address).where(Address.user_id==ctx.buyer_id,Address.is_default.is_(True)))==1)
            call('DELETE',f"/c/addresses/{second['id']}",b)
            with SessionLocal() as db:check('地址删除落库',db.get(Address,second['id']) is None)
        else:
            _,other=buyer(ctx);call('DELETE',f"/c/addresses/{first['id']}",other,status=(404,))
            with SessionLocal() as db:check('他人不可删除地址',db.get(Address,first['id']) is not None)
    elif cid=='RF26':
        rows=[coupon(ctx),coupon(ctx,starts_at=(utcnow()+timedelta(hours=1)).isoformat())]
        call('PATCH',f"/b/coupons/{rows[0]['id']}",m,{'enabled':False})
        for row in rows:
            call('POST',f"/c/shops/nanzhi/coupons/{row['id']}/claim",b,status=(400,))
            with SessionLocal() as db:check('不可领取券未消耗名额',db.get(Coupon,row['id']).claimed_count==0)
    elif cid=='RF27':
        row=coupon(ctx,total_count=1);call('POST',f"/c/shops/nanzhi/coupons/{row['id']}/claim",b)
        _,other=buyer(ctx);call('POST',f"/c/shops/nanzhi/coupons/{row['id']}/claim",other,status=(400,))
        with SessionLocal() as db:check('发行仅一张且计数一致',db.get(Coupon,row['id']).claimed_count==db.scalar(select(func.count()).select_from(UserCoupon).where(UserCoupon.coupon_id==row['id']))==1)
    elif cid in ('RF28','RF29','RF30'):
        row=coupon(ctx,threshold_cents=999999 if cid=='RF28' else 0)
        claim=call('POST',f"/c/shops/nanzhi/coupons/{row['id']}/claim",b);ucid=claim['user_coupon_id']
        if cid=='RF28':
            call('POST','/c/shops/nanzhi/coupon-quote',b,{'items':[{'sku_id':sku,'quantity':1}],'user_coupon_id':ucid},status=(400,))
            with SessionLocal() as db:check('报价失败无副作用',db.get(UserCoupon,ucid).status=='available' and not db.scalar(select(Order.id).where(Order.user_id==ctx.buyer_id)))
        else:
            o=call('POST','/c/shops/nanzhi/orders',b,order_body(sku,user_coupon_id=ucid));ctx.pending.append(o['order_no'])
            with SessionLocal() as db:
                record=db.scalar(select(Order).where(Order.order_no==o['order_no']));discount=db.scalar(select(CouponOrder).where(CouponOrder.order_id==record.id))
                check('券占用与订单金额正确',db.get(UserCoupon,ucid).status=='reserved' and record.total_cents==sum(i.price_cents*i.quantity for i in record.items)+record.freight_cents-discount.discount_cents)
            call('POST',f"/c/orders/{o['order_no']}/"+('cancel' if cid=='RF29' else 'pay'),b)
            with SessionLocal() as db:
                check('券状态转换落库',db.get(UserCoupon,ucid).status==('available' if cid=='RF29' else 'used'))
                check('订单券状态转换落库',db.scalar(select(CouponOrder.status).join(Order).where(Order.order_no==o['order_no']))==('released' if cid=='RF29' else 'used'))
            if cid=='RF30':call('POST','/c/shops/nanzhi/orders',b,order_body(sku,user_coupon_id=ucid),status=(400,))
    elif cid in ('RF31','RF32'):
        o=ctx.order(p,cid=='RF31');number=o['order_no'];body={'carrier':'演示物流','tracking_number':'DEMO-'+ctx.tag}
        call('PUT',f'/support/orders/{number}/shipment',m,body,status=(200,) if cid=='RF31' else (409,))
        if cid=='RF31':
            for state in ('transit','exception','delivered'):
                call('POST',f'/support/orders/{number}/shipment/events',m,{'status':state,'description':'【实测】'+state})
                check('C物流实时同步 '+state,call('GET',f'/support/orders/{number}/shipment',b)['status']==state)
            call('POST',f'/support/orders/{number}/shipment/events',m,{'status':'transit','description':'实测非法回退'},status=(409,))
            call('PUT',f'/support/orders/{number}/shipment',m,body,status=(409,))
        with SessionLocal() as db:
            saved=db.scalar(select(Shipment).join(Order).where(Order.order_no==number))
            check('物流数据库状态正确',(saved is None) if cid=='RF32' else saved.status=='delivered' and len(saved.events)==4)
    elif cid in ('RF33','RF34','RF35','RF36'):
        o=ctx.order(p,True);path=f"/support/orders/{o['order_no']}/after-sale";body={'kind':'exchange','reason':'【实测】多状态售后 '+ctx.tag}
        ticket=call('POST',path,b,body);tp=f"/support/after-sales/{ticket['id']}/process"
        if cid=='RF36':call('POST',path,b,body,status=(409,));expected='requested'
        elif cid=='RF33':
            call('POST',tp,m,{'action':'reject','note':'实测拒绝'});call('POST',tp,m,{'action':'accept','note':'实测重复'},status=(409,));expected='rejected'
        elif cid=='RF34':
            call('POST',tp,b,{'action':'accept','note':'实测越权'},status=(403,));call('POST',tp,b,{'action':'withdraw','note':'实测撤销'});expected='withdrawn'
        else:
            call('POST',tp,m,{'action':'accept','note':'实测受理'})
            result=call('POST',tp,b,{'action':'return_ship','note':'演示退回','carrier':'演示物流','tracking_number':'RETURN-'+ctx.tag})
            check('退回状态与运单正确',result['status']=='return_shipped' and result['return_tracking']=='RETURN-'+ctx.tag)
            call('POST',tp,m,{'action':'resolve','note':'实测解决'});expected='resolved'
        with SessionLocal() as db:check('售后实际状态正确',db.get(AfterSale,ticket['id']).status==expected,expected,db.get(AfterSale,ticket['id']).status)
    elif cid in ('RF37','RF38'):
        conv=call('POST','/support/shops/nanzhi/conversation',b);path=f"/support/conversations/{conv['id']}";body={'content':'【实测】消息 '+ctx.tag,'client_id':uuid4().hex}
        msg=call('POST',path+'/messages',b,body)
        if cid=='RF37':
            same=call('POST',path+'/messages',b,body);check('重复发送同一消息ID',same['id']==msg['id'])
            call('POST',path+'/read',m,{'message_id':msg['id']})
            convs=call('GET','/support/conversations',m);check('商家已读未读数0',next(x for x in convs if x['id']==conv['id'])['unread']==0)
            check('已读后无新增消息',call('GET',path+f"/messages?after={msg['id']}",b)==[])
        else:
            _,other=buyer(ctx);call('GET',path+'/messages',other,status=(404,));call('POST',path+'/messages',other,body,status=(404,))
        with SessionLocal() as db:check('消息实际仅一条',db.scalar(select(func.count()).select_from(Message).where(Message.conversation_id==conv['id']))==1)
    elif cid=='RF39':
        item=completed(ctx,p);body={'order_item_id':item,'rating':4,'content':'【实测】治理评价 '+ctx.tag}
        review=call('POST','/c/reviews',b,body);rid=review['id'];path=f'/c/shops/nanzhi/products/{pid}/reviews'
        for action,visible in [('hide',False),('show',True)]:
            call('POST',f'/op/governance/reviews/{rid}',op,{'action':action,'reason':'实测评价 '+ctx.tag})
            check('评价展示状态同步 '+action,any(x['id']==rid for x in call('GET',path))==visible)
        call('POST','/c/reviews',b,body,status=(400,409))
        with SessionLocal() as db:check('评价无重复',db.scalar(select(func.count()).select_from(Review).where(Review.order_item_id==item))==1)
    elif cid=='RF40':
        o=ctx.order(p);empty=call('GET','/op/platform/orders',op)
        check('OP默认不展示全量订单',empty['needs_filter'] and empty['items']==[])
        rows=call('GET',f"/op/platform/orders?shop_id={ctx.shop_id}&q={o['order_no']}&size=1",op)
        check('条件分页仅返回目标单',rows['total']==1 and len(rows['items'])==1 and rows['items'][0]['order_no']==o['order_no'])
        call('GET','/op/platform/accounts',b,status=(403,))
    else:raise ValueError('扩展接口用例缺少执行分支：'+cid)
