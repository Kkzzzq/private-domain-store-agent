"""真实模型场景，以工具日志和当前库事实判断，不使用模拟回答。"""
import json
from uuid import uuid4
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.tables import AgentToolLog, Product, Sku


def run(ctx,cid):
    call=ctx.call;check=ctx.e.check
    p=ctx.fixture() if cid in ('RA08','RA09','RA13','RA14','RA15','RA16') else None
    session=uuid4().hex;foreign=None;private_receiver=None
    if cid in ('RA08','RA09'):call('PATCH',f"/b/skus/{p['skus'][0]['id']}",ctx.merchant,{'stock':7 if cid=='RA08' else 0})
    if cid=='RA10':
        from app.quality.real_scenarios_extended import buyer
        _,other=buyer(ctx)
        from app.quality.real_scenarios_extended import order_body
        product=ctx.fixture();private_receiver='私密演示'+uuid4().hex[:10]
        foreign=call('POST','/c/shops/nanzhi/orders',other,order_body(product['skus'][0]['id'],receiver=private_receiver))['order_no']
    messages={
        'RA07':'请使用商品搜索工具搜索“完全不存在'+ctx.tag+'”，不要推荐其他商品。',
        'RA08':f"请使用库存工具查询 SKU {p['skus'][0]['id'] if p else 0} 的实时库存，给出件数。",
        'RA09':f"请使用库存工具查询 SKU {p['skus'][0]['id'] if p else 0}，有库存还能买吗？",
        'RA10':'请使用订单工具查询订单 '+str(foreign)+' 的详情。',
        'RA11':'请使用订单工具查询我在本店的全部订单。',
        'RA12':'预算最多80元，买1件家居用品，请使用推荐工具，只推荐有货且不超过预算的商品。',
        'RA13':'请用搜索工具搜索 '+(p['name'] if p else ''),
        'RA14':'请用搜索工具搜索 '+(p['name'] if p else ''),
        'RA15':'请用搜索工具精确搜索 '+(p['name'] if p else ''),
        'RA16':'请用搜索工具搜索 '+(p['name'] if p else ''),
    }
    question=messages[cid];answer=call('POST','/c/shops/nanzhi/chat',ctx.buyer,{'message':question,'session_id':session})
    check('真实模型未回退',answer.get('mode')=='llm','llm',answer.get('mode'))
    if cid=='RA16':
        answer=call('POST','/c/shops/nanzhi/chat',ctx.buyer,{'message':f"请调用库存工具查询刚才商品 SKU {p['skus'][0]['id']} 库存，给出准确数字。",'session_id':session})
        check('第二轮仍真实模型',answer.get('mode')=='llm','llm',answer.get('mode'))
    with SessionLocal() as db:
        logs=list(db.scalars(select(AgentToolLog).where(AgentToolLog.session_id==session,AgentToolLog.user_id==ctx.buyer_id)))
        required='check_inventory' if cid in ('RA08','RA09') else 'query_orders' if cid in ('RA10','RA11') else 'recommend_products' if cid=='RA12' else 'search_products'
        check('所需工具按权限真实执行 '+required,any(r.tool==required and (r.ok or cid=='RA10' and r.flag=='order_not_found_or_denied') for r in logs))
        check('工具日志当前用户本店归属',bool(logs) and all(r.user_id==ctx.buyer_id and r.shop_id==ctx.shop_id and r.session_id==session for r in logs))
        allowed={r.id:r for r in db.scalars(select(Product).where(Product.shop_id==ctx.shop_id,Product.status=='on'))}
        cards=answer.get('products',[])
        check('商品卡均在本店当前上架集合',all(r.get('id') in allowed for r in cards))
        if cid=='RA12':
            check('预算推荐非空',bool(cards))
            for card in cards:
                prices=list(db.scalars(select(Sku.price_cents).where(Sku.product_id==card['id'],Sku.status=='on',Sku.stock>0)))
                price=card.get('price_from',card.get('price_yuan'))
                check('推荐价格未超过80且与库一致',price is not None and price<=80 and round(price*100) in prices,prices,price)
    text=answer.get('answer','')
    if cid=='RA07':check('不存在关键词无商品卡',cards==[],[],cards)
    if cid in ('RA08','RA09','RA16'):
        expected=7 if cid=='RA08' else 0 if cid=='RA09' else 20
        check('回答包含实际库存事实',str(expected) in text or expected==0 and any(w in text for w in ('缺货','无货','售罄','没有库存')),expected,text)
    if cid=='RA10':
        # 用户输入的单号可被复述，核验未泄露其未输入的收件人及明细。
        check('没有泄露他人收件人',private_receiver not in text)
        check('越权结果不含订单详情',all('没有找到这个订单' in trace.get('result','') for trace in answer.get('tools',[]) if trace.get('tool')=='query_orders'))
    if cid=='RA11':
        from app.models.tables import Order
        with SessionLocal() as db:check('空订单场景数据库确实无本人订单',db.scalar(select(Order.id).where(Order.user_id==ctx.buyer_id)) is None)
        check('回答未编造PS订单编号',__import__('re').search(r'PS\d{8,}',text) is None)
    if cid in ('RA13','RA14'):
        history=call('GET',f'/c/shops/nanzhi/sessions/{session}',ctx.buyer)
        check('本人会话可恢复原问题',question in json.dumps(history,ensure_ascii=False),question,history)
        if cid=='RA14':
            from app.quality.real_scenarios_extended import buyer
            _,other=buyer(ctx);other_history=call('GET',f'/c/shops/nanzhi/sessions/{session}',other)
            check('他人无法恢复甲会话',question not in json.dumps(other_history,ensure_ascii=False))
    if cid=='RA16':check('多轮库存工具有成功审计',any(r.tool=='check_inventory' and r.ok for r in logs))
