"""实店子进程中断后的归档；仅处理不可猜测批次标记所拥有的记录。"""
import json
import re
from pathlib import Path


def ledger_path(ledger_id):
    from app.core.config import settings
    if not re.fullmatch(r'[a-f0-9]{32}',ledger_id or ''):raise ValueError('实店台账编号非法')
    root=settings.backend_root/'data'/'quality-real-ledgers';root.mkdir(parents=True,exist_ok=True)
    return root/(ledger_id+'.json')


def recover(ledger_id):
    from sqlalchemy import select
    from app.db.session import SessionLocal
    from app.models.tables import Product,User,Order,CartItem,Coupon
    from app.services.orders import cancel_order
    from app.services.catalog import invalidate_catalog_cache
    path=ledger_path(ledger_id)
    if not path.exists():return {'ok':True,'records':0}
    data=json.loads(path.read_text(encoding='utf-8'));tag=data.get('tag','')
    if not re.fullmatch(r'[a-f0-9]{12}',tag):raise ValueError('实店批次标记非法')
    errors=[];count=0
    with SessionLocal() as db:
        users=list(db.scalars(select(User).where(User.username.startswith('qa_nz_'+tag+'_'))))
        ids=[u.id for u in users]
        for order in list(db.scalars(select(Order).where(Order.user_id.in_(ids),Order.shop_id==data['shop_id'],Order.status=='pending'))):
            try:
                user=db.get(User,order.user_id);user._actor_role='customer';cancel_order(db,user,order.order_no);count+=1
            except Exception as exc:db.rollback();errors.append(str(exc))
        for product in db.scalars(select(Product).where(Product.shop_id==data['shop_id'],Product.description.contains(tag))):
            # 描述可能在测试中修改，但必须保留本批tag；绝不使用外部传入的任意商品ID。
            if product.name.startswith('【实测】') and product.status=='on':product.status='off';count+=1
        for coupon in db.scalars(select(Coupon).where(Coupon.shop_id==data['shop_id'],Coupon.name.contains(tag))):
            if coupon.name.startswith('【实测】'):coupon.enabled=False
        for cart in db.scalars(select(CartItem).where(CartItem.user_id.in_(ids))):db.delete(cart)
        db.commit()
    invalidate_catalog_cache()
    if not errors:path.unlink(missing_ok=True)
    return {'ok':not errors,'records':count,'errors':errors}


def recover_stale():
    import time
    from app.core.config import settings
    if not settings.qa_real_shop_enabled:return
    root=settings.backend_root/'data'/'quality-real-ledgers'
    if not root.exists():return
    for path in list(root.glob('*.json'))[:100]:
        if time.time()-path.stat().st_mtime>600:recover(path.stem)
