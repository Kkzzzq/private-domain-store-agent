"""OP navigation and mutation buttons in a disposable local database, never the live shop."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import httpx
from playwright.sync_api import sync_playwright, expect


def main():
    backend = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend))
    artifacts = backend / 'data/acceptance/op-buttons'
    artifacts.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    with tempfile.TemporaryDirectory(prefix='op-buttons-', dir=artifacts, ignore_cleanup_errors=True) as directory:
        workspace = Path(directory)
        shutil.copytree(backend.parent / 'web', workspace / 'web', ignore=shutil.ignore_patterns('uploads'))
        environment = dict(os.environ, DATABASE_URL='sqlite:///' + (workspace / 'test.db').as_posix(),
                           REDIS_URL='memory', STRICT_DEPENDENCIES='false', JWT_SECRET=uuid4().hex + uuid4().hex,
                           QA_CHILD_RUN=uuid4().hex, QA_CHILD_WORKSPACE=directory, QA_BROWSER_OP='1',
                           QA_REAL_SHOP_ENABLED='false', QA_NATIVE_ENABLED='false', AGENT_MODE='fallback',
                           AGENT_REQUIRE_LLM='false', RAG_REQUIRE_VECTORS='false',
                           CHROMA_PATH=(workspace / 'chroma').as_posix(), PYTHONIOENCODING='utf-8')
        with (artifacts / 'server.log').open('w', encoding='utf-8') as log:
            server = subprocess.Popen([sys.executable, '-m', 'app.quality.browser_server', '--port', str(port)],
                                      cwd=backend, env=environment, stdout=log, stderr=log,
                                      creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                      start_new_session=os.name != 'nt')
        try:
            for _ in range(160):
                try:
                    if httpx.get(origin + '/openapi.json', timeout=2).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.25)
            else:
                raise RuntimeError('Disposable server did not start')
            with httpx.Client(base_url=origin, timeout=30) as client:
                response = client.post('/api/v1/auth/login', json={'username': 'merchant', 'password': 'merchant123'})
                response.raise_for_status()
                token = response.json()['access_token']
                client.headers['Authorization'] = 'Bearer ' + token
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(channel='msedge' if os.name == 'nt' else None, headless=True)
                    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
                    context.add_init_script('sessionStorage.setItem("token_op", ' + json.dumps(token) + ');'
                                            'for(const name of ["prompt","confirm","alert"])window[name]=()=>{throw Error("Native dialog forbidden: "+name)};')
                    page = context.new_page()
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(origin + '/op.html')
                    expect(page.locator('nav [data-page]').first).to_be_visible()
                    routes = page.locator('nav [data-page]').evaluate_all('nodes => nodes.map(node => node.dataset.page)')

                    def navigate(route):
                        page.locator('nav [data-page="' + route + '"]').click()
                        page.wait_for_function("!/(正在读取|加载中)/.test(document.querySelector('#content').textContent)")
                        expect(page.locator('#content')).not_to_be_empty()
                        messages = page.locator('#content p.qa-error, #content p.error').all_text_contents()
                        messages = [message for message in messages if not message.startswith('会写入')]
                        assert not any(message.strip() for message in messages), (route, messages)

                    for route in routes:
                        navigate(route)
                        checks.append('navigation:' + route)
                    navigate('accounts')
                    page.locator('[data-create-account]').click()
                    detail = page.locator('.op-detail')
                    detail.get_by_label('登录账号', exact=True).fill('ui_buttons_user')
                    detail.get_by_label('昵称', exact=True).fill('隔离按钮账号')
                    detail.get_by_label('初始密码', exact=True).fill(uuid4().hex)
                    detail.get_by_label('操作原因', exact=True).fill('隔离创建账号验收')
                    with page.expect_response(lambda result: result.url.endswith('/governance/accounts') and result.request.method == 'POST') as pending:
                        detail.get_by_role('button', name='创建账号', exact=True).click()
                    assert pending.value.ok
                    expect(detail).to_have_count(0)
                    checks.append('account:create')
                    page.get_by_label('搜索关键词', exact=True).fill('ui_buttons_user')
                    page.locator('#content form').get_by_role('button', name='查询', exact=True).click()
                    expect(page.locator('#content tbody tr')).to_have_count(1)
                    for action in ['grant', 'revoke', 'disable', 'enable', 'grant_operator', 'revoke_operator']:
                        page.locator('[data-action="' + action + '"]').click()
                        page.locator('.op-action-dialog').get_by_label('操作原因').fill('隔离账号操作验收')
                        with page.expect_response(lambda result: '/accounts/' in result.url and result.request.method in ['POST', 'PATCH']) as pending:
                            page.locator('.op-action-dialog').get_by_role('button', name='确认提交').click()
                        assert pending.value.ok
                        expect(page.locator('.op-action-dialog')).to_have_count(0)
                        page.wait_for_timeout(100)
                        checks.append('account:' + action)
                    page.locator('[data-action="reset_password"]').click()
                    detail.get_by_label('新密码', exact=True).fill(uuid4().hex)
                    detail.get_by_label('操作原因', exact=True).fill('隔离重置密码验收')
                    with page.expect_response(lambda result: '/governance/accounts/' in result.url and result.request.method == 'POST') as pending:
                        detail.get_by_role('button', name='确认重置').click()
                    assert pending.value.ok
                    expect(detail).to_have_count(0)
                    checks.append('account:reset-password')
                    for action in ['account', 'customer-info']:
                        page.locator('[data-action="' + action + '"]').click()
                        expect(detail).to_be_visible()
                        if action == 'account':
                            detail.get_by_label('账号昵称', exact=True).fill('隔离已编辑账号')
                            detail.get_by_label('操作原因', exact=True).fill('隔离编辑昵称验收')
                            with page.expect_response(lambda result: '/platform/accounts/' in result.url and result.request.method == 'PATCH') as pending:
                                detail.get_by_role('button', name='保存修改').click()
                            assert pending.value.ok
                            expect(detail).to_have_count(0)
                        else:
                            detail.locator('.detail-close').click()
                        checks.append('account:' + action)
                    page.locator('[data-action="purchases"]').click()
                    expect(page.get_by_role('heading', name='购买订单', exact=True)).to_be_visible()
                    checks.append('account:purchases-navigation')
                    navigate('shops')
                    page.locator('[data-action="freeze"]').first.click()
                    modal = page.locator('.op-action-dialog')
                    expect(modal).to_be_visible()
                    modal.get_by_role('button', name='取消', exact=True).click()
                    expect(modal).to_have_count(0)
                    checks.append('freeze:cancel')
                    for action in ['freeze', 'unfreeze']:
                        page.locator('[data-action="' + action + '"]').first.click()
                        modal.get_by_label('操作原因').fill('隔离按钮功能验收')
                        with page.expect_response(lambda result: '/governance/' in result.url and result.request.method == 'POST') as pending:
                            modal.get_by_role('button', name='确认提交').click()
                        assert pending.value.ok, pending.value.status
                        expect(modal).to_have_count(0)
                        expect(page.locator('[data-action="' + ('unfreeze' if action == 'freeze' else 'freeze') + '"]').first).to_be_visible()
                        checks.append('shop:' + action)
                    page.locator('[data-action="shop"]').first.click()
                    detail.get_by_label('店铺名称', exact=True).fill('隔离维护小店')
                    detail.get_by_label('操作原因', exact=True).fill('隔离店铺编辑验收')
                    with page.expect_response(lambda result: '/platform/shops/' in result.url and result.request.method == 'PATCH') as pending:
                        detail.get_by_role('button', name='保存修改').click()
                    assert pending.value.ok
                    expect(detail).to_have_count(0)
                    checks.append('shop:edit')
                    page.locator('[data-action="full-workspace"]').first.click()
                    frame = page.frame_locator('.complete-workspace iframe')
                    expect(frame.locator('#op-scope-shop')).to_contain_text('隔离维护小店')
                    for name in ['经营概览', '商品管理', '分类标签', '商品标签', '优惠券管理', '订单管理', '首页装修', '店铺设置']:
                        frame.get_by_role('link', name=name, exact=True).click()
                        expect(frame.locator('h1')).to_have_text(name)
                        checks.append('workspace:' + name)
                    assert frame.locator('body').evaluate('() => Boolean(window.AssistantPresentation)')
                    page.locator('.complete-workspace .detail-close').click()
                    navigate('products')
                    for action in ['ban', 'release']:
                        page.locator('[data-action="' + action + '"]').first.click()
                        modal.get_by_label('操作原因').fill('隔离商品治理验收')
                        with page.expect_response(lambda result: '/moderate' in result.url and result.request.method == 'POST') as pending:
                            modal.get_by_role('button', name='确认提交').click()
                        assert pending.value.ok
                        expect(modal).to_have_count(0)
                        page.wait_for_timeout(200)
                        checks.append('product:' + action)
                    page.locator('[data-action="product"]').first.click()
                    expect(page.locator('.op-detail')).to_be_visible()
                    page.locator('[data-sku]').first.click()
                    expect(modal).to_be_visible()
                    modal.get_by_role('button', name='取消', exact=True).click()
                    expect(page.locator('.op-detail')).to_be_visible()
                    page.locator('.op-detail .detail-close').click()
                    checks.append('sku:reason-dialog-over-detail')
                    page.locator('[data-action="product"]').first.click()
                    expect(page.locator('.op-detail')).to_be_visible()
                    page.evaluate('window.OPDialogs.alert("弹窗中的错误也可关闭")')
                    nested_notice = page.locator('.op-detail [role="alert"]')
                    expect(nested_notice).to_contain_text('弹窗中的错误也可关闭')
                    nested_notice.get_by_role('button', name='关闭').click()
                    expect(nested_notice).to_have_count(0)
                    page.locator('.op-detail .detail-close').click()
                    checks.append('error:actionable-inside-modal')
                    page.evaluate('window.dialogResult="pending"; void window.OPDialogs.confirm("确认测试").then(value=>window.dialogResult=value)')
                    modal.get_by_role('button', name='取消', exact=True).click()
                    assert page.evaluate('window.dialogResult') is False
                    page.evaluate('window.dialogResult="pending"; void window.OPDialogs.confirm("确认测试").then(value=>window.dialogResult=value)')
                    modal.get_by_role('button', name='确认执行').click()
                    assert page.evaluate('window.dialogResult') is True
                    checks.append('confirmation:cancel-and-accept')
                    page.evaluate('window.dialogResult="pending"; void window.OPDialogs.prompt("原因").then(value=>window.dialogResult=value)')
                    modal.get_by_label('操作原因').fill(' ')
                    modal.get_by_role('button', name='确认提交').click()
                    expect(modal).to_be_visible()
                    page.keyboard.press('Escape')
                    assert page.evaluate('window.dialogResult') is None
                    checks.append('reason:validation-and-escape')
                    page.evaluate('window.dialogResult="pending"; void window.OPDialogs.prompt("原因").then(value=>window.dialogResult=value)')
                    page.evaluate('window.dispatchEvent(new Event("op-session-ended"))')
                    expect(modal).to_have_count(0)
                    assert page.evaluate('window.dialogResult') is None
                    checks.append('reason:session-ended')
                    page.evaluate('window.OPDialogs.alert("失败原因清楚显示")')
                    expect(page.get_by_role('alert')).to_contain_text('失败原因清楚显示')
                    page.get_by_role('alert').get_by_role('button', name='关闭').click()
                    checks.append('error:visible-dismissible')
                    for width in [1440, 390]:
                        page.set_viewport_size({'width': width, 'height': 1000})
                        page.evaluate('void window.OPDialogs.prompt("请填写操作原因")')
                        expect(modal).to_be_visible()
                        assert modal.evaluate('node => node.getBoundingClientRect().right <= innerWidth')
                        page.screenshot(path=str(artifacts / f'dialog-{width}.png'), full_page=True)
                        modal.get_by_role('button', name='取消', exact=True).click()
                        checks.append('dialog-width:' + str(width))
                    browser.close()
            assert not errors, errors
        finally:
            from app.quality.worker import stop_process
            stop_process(server)
            (artifacts / 'result.json').write_text(json.dumps({'checks': checks, 'errors': errors,
                                                             'live_shop_writes': False}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed_checks': len(checks), 'errors': errors, 'live_shop_writes': False}))


if __name__ == '__main__':
    main()
