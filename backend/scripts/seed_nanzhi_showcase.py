"""追加全管理页多状态演示记录。默认只预览；不清库，不调用资金/快递服务。

所有商品、买家、地址、单号都明确标注演示。治理日志由真实 HTTP 操作产生，
不直接伪造审计。主店营业状态及原账号权限不变。重复运行可补做未完成治理操作。
"""
import argparse
import json
import secrets
from datetime import timedelta
from urllib.parse import quote
from sqlalchemy import select,func

BATCH='nanzhi-showcase-v2-20261021'
ORDER_PREFIX='NZSHOW20261021'


def seed(db,shop_id):
    from app.core.security import hash_password
    from app.models.tables import (User,Shop,Product,Sku,Order,OrderItem,Address,Coupon,UserCoupon,CouponOrder,Review,AccountClosure,utcnow)
    from app.models.account import MerchantAccess
    from app.models.support import Shipment,AfterSale,Conversation,Message
    shop=db.get(Shop,shop_id)
    if not shop or shop.share_code!='nanzhi':raise ValueError('目标必须是已有南枝店')
    marker=db.scalar(select(User).where(User.username==BATCH+'-01'))
    if marker:
        if db.scalar(select(func.count()).select_from(Order).where(Order.order_no.startswith(ORDER_PREFIX)))!=24:raise ValueError('批次不完整，停止追加')
        return summary(db,shop_id)
    now=utcnow();users=[]
    for i in range(12):
        u=User(username=f'{BATCH}-{i+1:02}',nickname=f'【演示】南枝买家{i+1:02}',role='customer',password_hash=hash_password(secrets.token_urlsafe(32)))
        db.add(u);db.flush();users.append(u)
        db.add(Address(user_id=u.id,receiver='演示收件人',phone='00000000000',region='演示地区',detail='多状态展示数据，请勿实际配送',is_default=True))
    db.add(AccountClosure(user_id=users[9].id))
    for index,status in [(10,'closed'),(11,'open')]:
        db.add(MerchantAccess(user_id=users[index].id,enabled=True))
        db.add(Shop(merchant_id=users[index].id,name='【演示】南枝'+('停业样例店' if index==10 else '封店样例店'),share_code=f'nanzhi-demo-v2-{index}',status=status,notice='多状态演示店，无实际营业；主店仍为nanzhi'))
    image=db.scalar(select(Product.image_url).where(Product.shop_id==shop_id,Product.image_url!='').limit(1)) or ''
    products=[];skus=[]
    for i in range(12):
        title=['日常抱枕','双色餐垫','手作陶杯','香氛套装','便携收纳','黄铜书签','售罄茶罐','低库存花器','季节下架款','待审核草稿','禁售样例','解除禁售样例'][i]
        p=Product(shop_id=shop_id,name='【演示】'+title,description='全管理页多状态演示，非真实交易；'+BATCH,status='on' if i<8 else 'off' if i!=9 else 'draft',category='演示家居',image_url=image,limit_per_user=5 if i==4 else 0,sort_order=950+i)
        db.add(p);db.flush();products.append(p)
        for v in range(3):
            s=Sku(spu_id=p.id,spec=['标准装','礼盒装','停售规格'][v],price_cents=2900+i*500+v*300,stock=0 if i==6 else 2 if i==7 else 100,status='off' if v==2 else 'on',image_url=image,sort_order=v)
            db.add(s);db.flush();skus.append(s)
    coupons=[]
    for name,start,end,enabled,count in [('可领取满减',-1,60,True,100),('即将开始',3,60,True,100),('历史过期',-30,-1,True,100),('主动停用',-1,60,False,100),('名额已领完',-1,60,True,2),('订单核销与释放',-1,60,True,100)]:
        c=Coupon(shop_id=shop_id,name='【演示】'+name,threshold_cents=1000,amount_cents=300,total_count=count,starts_at=now+timedelta(days=start),ends_at=now+timedelta(days=end),enabled=enabled)
        db.add(c);db.flush();coupons.append(c)
    statuses=['pending','paid','shipped','completed','cancelled']*4+['shipped','shipped','completed','paid']
    sale_states=['requested','accepted','rejected','return_shipped','resolved','withdrawn']
    for i,status in enumerate(statuses):
        u=users[i%6];p=products[i%6];s=skus[(i%6)*3];qty=1+i%2
        o=Order(order_no=f'{ORDER_PREFIX}{i+1:04}',shop_id=shop_id,user_id=u.id,status=status,total_cents=s.price_cents*qty,freight_cents=0,receiver=u.nickname,phone='00000000000',address='【演示】数据库展示订单，请勿实际配送',created_at=now-timedelta(hours=i*5),expires_at=None)
        db.add(o);db.flush();item=OrderItem(order_id=o.id,product_id=p.id,sku_id=s.id,product_name=p.name,sku_spec=s.spec,price_cents=s.price_cents,quantity=qty);db.add(item);db.flush()
        if status!='cancelled':s.stock-=qty
        if status in ('paid','shipped','completed'):p.sales_count+=qty
        if status in ('shipped','completed'):
            shipstate='delivered' if status=='completed' else ['shipped','transit','exception'][i%3]
            db.add(Shipment(order_id=o.id,carrier='演示物流（未接快递）',tracking_number=f'SHOW-NZ-{i+1:06}',status=shipstate,events=[dict(at=now.isoformat()+'Z',role='merchant',text='【演示】已填写展示运单'),dict(at=now.isoformat()+'Z',role='merchant',text='【演示】'+shipstate)]))
        if status=='completed':db.add(Review(user_id=u.id,product_id=p.id,order_item_id=item.id,rating=1+i%5,content=f'【演示】多评分评价样例{i+1}，不代表真实用户反馈。'))
        if i in (1,2,3,6,7,8):
            idx=[1,2,3,6,7,8].index(i);state=sale_states[idx]
            db.add(AfterSale(order_id=o.id,kind='exchange' if state=='return_shipped' else ['return','exchange','repair','other'][idx%4],reason='【演示】售后状态展示，不执行资金退款',status=state,return_carrier='演示退货物流' if state in ('return_shipped','resolved') else '',return_tracking='SHOW-RETURN-'+str(i) if state in ('return_shipped','resolved') else '',events=[dict(at=now.isoformat()+'Z',role='customer',text='【演示】售后申请'),dict(at=now.isoformat()+'Z',role='merchant',text='【演示】当前状态 '+state)]))
        if i in (0,1,4):
            uc=UserCoupon(coupon_id=coupons[5].id,user_id=u.id,status='reserved' if i==0 else 'used' if i==1 else 'available');db.add(uc);db.flush();coupons[5].claimed_count+=1
            db.add(CouponOrder(order_id=o.id,user_coupon_id=uc.id,name=coupons[5].name,discount_cents=300,status='reserved' if i==0 else 'used' if i==1 else 'released'));o.total_cents-=300
    for index,u in enumerate(users[:8]):
        for c in ([coupons[0]] if index>=2 else [coupons[0],coupons[4]]):db.add(UserCoupon(coupon_id=c.id,user_id=u.id));c.claimed_count+=1
        conv=Conversation(shop_id=shop_id,customer_id=u.id);db.add(conv);db.flush()
        db.add(Message(conversation_id=conv.id,sender_id=u.id,sender_role='customer',client_id=f'show-v2-{index}',content='【演示】咨询规格、库存、物流或售后状态'))
        if index%2:db.add(Message(conversation_id=conv.id,sender_id=shop.merchant_id,sender_role='merchant',client_id=f'show-reply-{index}',content='【演示】已核查订单信息，后续请关注站内处理记录。'))
    db.flush();return summary(db,shop_id)


def summary(db,shop_id):
    from app.models.tables import User,Product,Order
    return dict(batch=BATCH,shop_id=shop_id,user_ids=list(db.scalars(select(User.id).where(User.username.startswith(BATCH)).order_by(User.id))),product_ids=list(db.scalars(select(Product.id).where(Product.shop_id==shop_id,Product.description.contains(BATCH)).order_by(Product.id))),orders=db.scalar(select(func.count()).select_from(Order).where(Order.order_no.startswith(ORDER_PREFIX))))


def verify(db,shop_id):
    """可重复的只读批次验收；订单、券及SKU明细直接对照数据库。"""
    from app.models.tables import Order,CouponOrder,Product,Sku,Coupon,UserCoupon
    from app.models.support import Shipment,AfterSale
    info=summary(db,shop_id)
    assert len(info['user_ids'])==12 and len(info['product_ids'])==12 and info['orders']==24,'全页演示批次不完整'
    orders=list(db.scalars(select(Order).where(Order.order_no.startswith(ORDER_PREFIX))))
    assert {o.status for o in orders}=={'pending','paid','shipped','completed','cancelled'},'订单状态缺失'
    for o in orders:
        discount=db.scalar(select(CouponOrder.discount_cents).where(CouponOrder.order_id==o.id)) or 0
        assert o.shop_id==shop_id and o.total_cents==sum(i.price_cents*i.quantity for i in o.items)+o.freight_cents-discount,'订单金额或店铺不一致'
        assert all(db.get(Sku,i.sku_id).spu_id==i.product_id and db.get(Product,i.product_id).shop_id==shop_id for i in o.items),'订单规格归属不一致'
    ids=[o.id for o in orders]
    shipments=dict(db.execute(select(Shipment.status,func.count()).where(Shipment.order_id.in_(ids)).group_by(Shipment.status)).all())
    sales=dict(db.execute(select(AfterSale.status,func.count()).where(AfterSale.order_id.in_(ids)).group_by(AfterSale.status)).all())
    assert set(shipments)=={'shipped','transit','exception','delivered'},'物流状态缺失'
    assert set(sales)=={'requested','accepted','rejected','return_shipped','resolved','withdrawn'},'售后状态缺失'
    for c in db.scalars(select(Coupon).where(Coupon.shop_id==shop_id,Coupon.id.in_(select(UserCoupon.coupon_id).where(UserCoupon.user_id.in_(info['user_ids']))))):
        assert c.claimed_count==db.scalar(select(func.count()).select_from(UserCoupon).where(UserCoupon.coupon_id==c.id)),'券发行计数不一致'
    return dict(batch=BATCH,orders=len(orders),shipments=shipments,after_sales=sales,amounts_and_ownership=True)


def govern(info,operator_id,origin):
    import httpx
    from app.core.security import create_access_token,revoke_access_token
    from app.db.session import SessionLocal
    from app.models.tables import User,Review,Product,Shop,Sku
    from app.models.operations import Operator
    from app.models.governance import AccountRestriction,ReviewRestriction,ShopRestriction,WorkspaceAction
    with SessionLocal() as db:
        actor=db.get(User,operator_id)
        if not actor or not db.get(Operator,operator_id):raise ValueError('缺少有效OP身份')
        token=create_access_token(user_id=actor.id,username=actor.username,role=actor.role)
    def post(path,body,method='POST',statuses=(200,201)):
        r=client.request(method,'/api/v1'+path,json=body)
        if r.status_code not in statuses:raise RuntimeError(f'{method} {path}: {r.status_code} {r.text[:200]}')
        return r.json()
    try:
        with httpx.Client(base_url=origin,headers={'Authorization':'Bearer '+token,'X-OP-Reason':quote('【演示】全页状态补齐 '+BATCH)},timeout=30,trust_env=False) as client:
            # 只治理本批次对象；每步可重入，所有日志均来自正式接口。
            with SessionLocal() as db:limit=db.get(Product,info['product_ids'][4]).limit_per_user
            if limit!=5:post(f"/op/shops/{info['shop_id']}/b/products/{info['product_ids'][4]}",{'limit_per_user':5},'PATCH')
            uid=info['user_ids'][8]
            with SessionLocal() as db:r=db.get(AccountRestriction,uid);disabled=bool(r and r.disabled)
            if not disabled:post(f'/op/governance/accounts/{uid}',{'action':'disable','reason':'【演示】禁用样例 '+BATCH})
            with SessionLocal() as db:
                sku=db.scalar(select(Sku).where(Sku.spu_id==info['product_ids'][7]).order_by(Sku.id.desc()));sku_id=sku.id;sku_banned=sku.status=='banned'
            if not sku_banned:post(f'/op/governance/skus/{sku_id}',{'action':'ban','reason':'【演示】单规格禁售样例 '+BATCH})
            pid=info['product_ids'][10]
            with SessionLocal() as db:banned=db.get(Product,pid).status=='banned'
            if not banned:post(f'/op/products/{pid}/moderate',{'action':'ban','reason':'【演示】保留禁售样例 '+BATCH})
            pid=info['product_ids'][11]
            from app.models.operations import OperationLog
            with SessionLocal() as db:done=db.scalar(select(OperationLog.id).where(OperationLog.product_id==pid,OperationLog.action=='release'))
            if not done:
                post(f'/op/products/{pid}/moderate',{'action':'ban','reason':'【演示】整改流程 '+BATCH});post(f'/op/products/{pid}/moderate',{'action':'release','reason':'【演示】整改完成 '+BATCH})
            with SessionLocal() as db:
                review=db.scalar(select(Review).where(Review.product_id.in_(info['product_ids'])).order_by(Review.id));rid=review.id
                hidden=db.get(ReviewRestriction,rid);done=bool(hidden and hidden.hidden)
            if not done:post(f'/op/governance/reviews/{rid}',{'action':'hide','reason':'【演示】隐藏样例评价 '+BATCH})
            with SessionLocal() as db:
                demo=db.scalar(select(Shop).where(Shop.share_code=='nanzhi-demo-v2-11'));sid=demo.id
                blocked=db.get(ShopRestriction,sid);done=bool(blocked and blocked.blocked)
            if not done:post(f'/op/governance/shops/{sid}',{'action':'freeze','reason':'【演示】封店样例，非南枝主店 '+BATCH})
            with SessionLocal() as db:statuses=set(db.scalars(select(WorkspaceAction.status).where(WorkspaceAction.reason=='【演示】全页状态补齐 '+BATCH)))
            if 'succeeded' not in statuses:post(f"/op/shops/{info['shop_id']}/b/products/{info['product_ids'][0]}",{'description':'全管理页多状态演示，非真实交易；'+BATCH},'PATCH')
            if 'failed' not in statuses:
                # 本批禁售商品尝试上架，业务校验真实拒绝，生成真实失败维护记录。
                post(f"/op/shops/{info['shop_id']}/b/products/{info['product_ids'][10]}/status",{'action':'on'},statuses=(400,403,409))
    finally:revoke_access_token(token)


def main():
    from app.core.config import settings
    from app.db.session import SessionLocal
    from app.models.tables import Shop
    from sqlalchemy.engine import make_url
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');parser.add_argument('--expected-database');parser.add_argument('--shop-id',type=int);parser.add_argument('--operator-id',type=int);args=parser.parse_args()
    database=make_url(settings.database_url).database
    with SessionLocal() as db:
        shop=db.scalar(select(Shop).where(Shop.share_code=='nanzhi'))
        if not args.apply:print(json.dumps(dict(preview=True,database=database,shop_id=shop.id,batch=BATCH),ensure_ascii=False));return
        if args.expected_database!=database or args.shop_id!=shop.id or not args.operator_id:raise SystemExit('必须匹配数据库、店铺ID并指定OP身份')
        if settings.qa_real_shop_origin.rstrip('/')!='https://shop.kkzzzq.cyou':raise SystemExit('仅支持已授权站点')
        info=seed(db,shop.id);db.commit()
    govern(info,args.operator_id,settings.qa_real_shop_origin)
    from app.services.catalog import invalidate_catalog_cache
    invalidate_catalog_cache()
    with SessionLocal() as db:info['verification']=verify(db,info['shop_id'])
    print(json.dumps(info,ensure_ascii=False))


if __name__=='__main__':main()
