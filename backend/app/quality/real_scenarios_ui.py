"""Playwright 实际生产页面操作，每条都保存真实截图。"""
import json
import os
from uuid import uuid4
from hashlib import sha256
from sqlalchemy import select
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.tables import CartItem


def run(ctx,cid):
    from playwright.sync_api import sync_playwright, expect
    call=ctx.call;check=ctx.e.check;root=settings.backend_root/'data'/'quality-artifacts';root.mkdir(parents=True,exist_ok=True)
    artifact=uuid4().hex+'.png'
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='msedge' if os.name=='nt' else None,headless=True,args=['--disable-gpu'])
        context=browser.new_context(viewport={'width':1440,'height':1000})
        key,token=('token_c',ctx.buyer) if cid in ('RE13','RE14') else ('token_b',ctx.merchant) if cid=='RE15' else ('token_op',ctx.op)
        context.add_init_script('sessionStorage.setItem('+json.dumps(key)+','+json.dumps(token)+');')
        page=context.new_page();page.set_default_timeout(15000);errors=[];server_errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('response',lambda r:server_errors.append(r.url.split('?')[0]) if '/api/v1/' in r.url and r.status>=500 else None)
        def tab(name):
            page.locator('nav [data-page="'+name+'"]').click()
            expect(page.locator('#content')).not_to_contain_text('正在读取')
        try:
            if cid.startswith('RE') and cid not in ('RE13','RE14','RE15'):
                page.goto(ctx.origin+'/op.html');expect(page.locator('#content .cards')).to_be_visible()
            if cid=='RE09':
                for name in ('overview','accounts','reviews','workspace-audits','shops','products','orders','shipments','after-sales','coupons','agent-logs','operation-logs','management-audits'):
                    tab(name)
                    if name in ('reviews','orders','shipments','after-sales','coupons'):
                        page.get_by_label('店铺选择' if name=='reviews' else '选择店铺',exact=True).select_option(str(ctx.shop_id))
                        page.get_by_role('button',name='查询',exact=True).click()
                        expect(page.locator('#content tbody tr').first).to_be_visible()
                        expect(page.locator('#content tbody')).not_to_contain_text('暂无')
                    check('管理tab实际打开 '+name,page.locator('#content').inner_text().strip()!='')
            elif cid=='RE10':
                tab('orders');expect(page.get_by_text('先定位小店，再查看订单',exact=True)).to_be_visible()
                page.get_by_label('选择店铺',exact=True).select_option(str(ctx.shop_id));page.get_by_role('button',name='查询',exact=True).click()
                expect(page.locator('#content tbody tr').first).to_be_visible();check('订单查询实际显示表格',page.locator('#content table').count()==1)
            elif cid=='RE11':
                tab('products')
                for state in ('on','off','draft','banned'):
                    page.get_by_label('状态筛选',exact=True).select_option(state)
                    with page.expect_response(lambda r:'/api/v1/op/records/products?' in r.url and 'status='+state in r.url) as response:page.get_by_role('button',name='查询',exact=True).click()
                    check('状态筛选请求成功 '+state,response.value.status==200)
                    check('筛选返回状态正确 '+state,all(r['status']==state for r in response.value.json()['items']))
            elif cid=='RE12':
                from app.models.tables import User
                with SessionLocal() as db:username=db.get(User,ctx.buyer_id).username
                tab('accounts');page.get_by_label('搜索关键词',exact=True).fill(username);page.get_by_role('button',name='查询',exact=True).click()
                page.get_by_role('button',name='买家资料',exact=True).click()
                for name in ('收货地址','购物车','已领优惠券','浏览记录','购买评价'):
                    page.locator('dialog').get_by_role('button',name=name,exact=True).click();expect(page.locator('dialog .customer-records table')).to_be_visible()
            elif cid=='RE13':
                p=ctx.fixture();cart=call('POST','/c/shops/nanzhi/cart',ctx.buyer,{'sku_id':p['skus'][0]['id'],'quantity':1});item=cart['items'][0]['id']
                page.goto(ctx.origin+'/c.html?code=nanzhi#/cart')
                expect(page.locator('.qty input').first).to_be_visible()
                with page.expect_response(lambda r:f'/c/cart/{item}' in r.url and r.request.method=='PATCH') as response:
                    page.locator('.qty').get_by_role('button',name='+',exact=True).click()
                check('UI数量修改请求200',response.value.status==200)
                with SessionLocal() as db:check('UI数量实际为2',db.get(CartItem,item).quantity==2)
                with page.expect_response(lambda r:f'/c/cart/{item}' in r.url and r.request.method=='DELETE') as response:page.get_by_role('button',name='删除',exact=True).click()
                check('UI删除请求200',response.value.status==200)
                with SessionLocal() as db:check('UI删除实际落库',db.get(CartItem,item) is None)
            elif cid=='RE14':
                ctx.order(ctx.fixture());page.goto(ctx.origin+'/c.html?code=nanzhi#/orders')
                for name in ('全部订单','待支付','待发货','待收货','已完成'):
                    page.get_by_role('button',name=name,exact=True).click();check('订单状态按钮可点击 '+name,page.locator('body').is_visible())
            elif cid=='RE15':
                p=ctx.fixture();page.goto(ctx.origin+'/b.html#/products');search=page.get_by_role('textbox',name='搜索商品名称或编号',exact=True)
                search.fill('绝无商品'+ctx.tag);expect(page.locator('#app')).not_to_contain_text(p['name'])
                search.fill(p['name']);expect(page.get_by_text(p['name'],exact=True).first).to_be_visible()
            elif cid=='RE16':
                p=ctx.fixture();pid=p['id']
                call('PATCH',f'/op/shops/{ctx.shop_id}/b/products/{pid}',ctx.op,{'description':'实测审计 '+ctx.tag})
                for action in ('ban','release'):call('POST',f'/op/products/{pid}/moderate',ctx.op,{'action':action,'reason':'实测页面审计 '+ctx.tag})
                tab('workspace-audits');expect(page.locator('#content')).to_contain_text('南枝实店自动化 '+ctx.tag)
                tab('operation-logs');expect(page.locator('#content')).to_contain_text('实测页面审计 '+ctx.tag)
            else:raise ValueError('未知扩展UI用例')
            check('真实UI无脚本错误',not errors,[],errors);check('真实页面接口无5xx',not server_errors,[],server_errors)
        finally:
            try:
                page.screenshot(path=str(root/artifact),full_page=True)
                ctx.e.artifacts=[{'id':artifact,'type':'image/png','sha256':sha256((root/artifact).read_bytes()).hexdigest()}]
            finally:browser.close()
