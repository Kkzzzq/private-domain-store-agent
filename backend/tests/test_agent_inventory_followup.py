import importlib
from sqlalchemy import select
from app.agent.context import Actor,set_actor,reset_actor
from app.agent.intent import classify
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.tables import User,Shop


def test_negative_recommendation_word_does_not_override_explicit_search():
    assert classify('请搜索不存在的商品，不要推荐其他商品')=='product_search'
    assert classify('请搜索刚才商品的库存，不要推荐')=='inventory'


def test_inventory_followup_keeps_current_question_and_historical_product_clue(client,monkeypatch):
    module=importlib.import_module('app.agent.assistant')
    monkeypatch.setattr(settings,'agent_mode','llm')
    captured=[]
    def loop(history,summary,query,**kwargs):
        captured.append(query);return '当前库存7件',[{'tool':'check_inventory','args':{'sku_id':1},'result':'库存7件'}]
    monkeypatch.setattr(module,'run_tool_loop',loop)
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.username=='alice'));shop=db.scalar(select(Shop).where(Shop.share_code=='nanzhi'))
        token=set_actor(db,Actor(user.id,'customer',user.username,shop.id))
        try:
            session='inventory-followup-regression'
            # Session save signatures vary with role-isolation enhancement; customer is default in both.
            module.assistant.sessions.save(user.id,shop.id,session,{'summary':'','messages':[{'role':'user','content':'搜索亚麻抱枕'}]})
            question='刚才商品 SKU 1 库存还有多少？'
            result=module.assistant.chat(user_id=user.id,shop_id=shop.id,session_id=session,message=question,llm=object())
            assert result['mode']=='llm'
            assert question in captured[0] and '搜索亚麻抱枕' in captured[0]
            assert classify(captured[0])=='inventory'
        finally:reset_actor(token)
