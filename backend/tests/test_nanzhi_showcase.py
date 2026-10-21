from sqlalchemy import select,func
from app.db.session import SessionLocal
from app.models.tables import Shop,Order,Product,Coupon,UserCoupon,CouponOrder
from app.models.support import AfterSale,Shipment
from scripts.seed_nanzhi_showcase import seed,BATCH,ORDER_PREFIX


def test_showcase_is_idempotent_relational_and_has_complete_business_states(client):
    with SessionLocal() as db:
        shop=db.scalar(select(Shop).where(Shop.share_code=='nanzhi'));original=shop.status
        first=seed(db,shop.id);db.commit();second=seed(db,shop.id);db.commit()
        assert first==second and len(first['product_ids'])==12 and len(first['user_ids'])==12 and first['orders']==24
        assert db.get(Shop,shop.id).status==original
        orders=list(db.scalars(select(Order).where(Order.order_no.startswith(ORDER_PREFIX))))
        assert {o.status for o in orders}=={'pending','paid','shipped','completed','cancelled'}
        for o in orders:
            coupon=db.scalar(select(CouponOrder).where(CouponOrder.order_id==o.id))
            assert o.total_cents==sum(i.price_cents*i.quantity for i in o.items)+o.freight_cents-(coupon.discount_cents if coupon else 0)
        assert set(db.scalars(select(AfterSale.status).where(AfterSale.order_id.in_([o.id for o in orders]))))=={'requested','accepted','rejected','return_shipped','resolved','withdrawn'}
        assert set(db.scalars(select(Shipment.status).where(Shipment.order_id.in_([o.id for o in orders]))))=={'shipped','transit','exception','delivered'}
        for c in db.scalars(select(Coupon).where(Coupon.name.startswith('【演示】'))):
            assert c.claimed_count==db.scalar(select(func.count()).select_from(UserCoupon).where(UserCoupon.coupon_id==c.id))
        assert db.scalar(select(func.count()).select_from(Product).where(Product.description.contains(BATCH)))==12
        for product in db.scalars(select(Product).where(Product.description.contains(BATCH),Product.limit_per_user>0)):
            quantities={}
            for o in orders:
                if o.status!='cancelled':quantities[o.user_id]=quantities.get(o.user_id,0)+sum(i.quantity for i in o.items if i.product_id==product.id)
            assert all(value<=product.limit_per_user for value in quantities.values())
