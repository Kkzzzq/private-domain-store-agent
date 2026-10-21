"""Code-derived B/C capabilities. Discovery and scenario coverage are deliberately distinct."""
import ast
from hashlib import sha256
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ('auth', 'b_api', 'c_api', 'support', 'agent_actions')
# Reviewed scenario associations, not a claim that each endpoint/branch is covered.
DOMAINS = {
    'auth': ('账号与身份', ['F01','F02','F03','RF11'], '登录令牌、退出撤销和商家授权按当前身份生效'),
    'products': ('商品与规格', ['F05','F06','F07','F08','F09','F10','E02','RF01','RF02','RF10','RE05','RE06'], '商品状态、规格顺序、图片和可售范围在 B/C 一致'),
    'cart': ('购物车与结算', ['F11','F12','F13','F16','E01','RF05','RE04','RE08'], '数量合法、价格运费优惠一致，拒绝后原状态不变'),
    'orders': ('订单与库存', ['F04','F17','F18','F19','F20','F21','F22','RF06','RF07'], '归属隔离、金额正确，库存扣减与取消回补不可重复'),
    'coupons': ('优惠券', ['F14','F15','F16','F19','E01','RF04'], '领券去重、限量、适用规则与结算核销一致'),
    'decoration': ('店铺装修', ['F24'], '预览无写入、发布内容一致、版本冲突明确'),
    'categories': ('分类', ['F23'], '改名与商品分类同步'),
    'tags': ('标签', ['F23'], '名称与独立颜色同步买家'),
    'reviews': ('买家评价', ['F25'], '评价资格合法、统计与缓存同步'),
    'support': ('联系商家与售后物流', ['F26','F27','F28','RF08','RF09'], '会话按店铺和用户隔离、物流售后状态合法'),
    'proposals': ('商家商品提案', ['F29','F30'], '提案确认需本人、幂等且失败回滚'),
    'chat': ('业务助手与会话', [], '角色、会话归属与 B/C 能力边界；Agent质量另行评测'),
    'addresses': ('收货地址', [], '地址归属本人、默认地址及删除状态正确'),
    'history': ('浏览历史', [], '本人历史与清空隔离'),
    'uploads': ('图片上传', [], '真实文件类型、大小和资源范围校验'),
    'home': ('首页与内容', [], '已发布内容、合集、轮播和排序正确'),
    'settings': ('店铺设置与经营', ['F13','F22'], '本店配置与经营统计基于授权数据'),
}


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',',':')).encode()).hexdigest()


def domain_for(path, source):
    if source == 'auth': return 'auth'
    if source == 'support': return 'support'
    if source == 'agent_actions': return 'proposals'
    if any(word in path for word in ('chat','sessions','knowledge')): return 'chat'
    if 'coupon' in path: return 'coupons'
    for key in ('cart','orders','coupons','decoration','categories','tags','reviews','addresses','history','uploads','products'):
        if key in path: return key
    if any(word in path for word in ('banners','sections','testimonials','home','collections','sort/')): return 'home'
    return 'settings'


def discover():
    entries = []
    for source in SOURCES:
        file = ROOT / 'app' / 'api' / (source + '.py')
        tree = ast.parse(file.read_text(encoding='utf-8-sig'))
        prefix = ''
        for item in tree.body:
            if isinstance(item, ast.Assign) and isinstance(item.value, ast.Call) and ast.unparse(item.value.func) == 'APIRouter':
                prefix = next((ast.literal_eval(k.value) for k in item.value.keywords if k.arg == 'prefix'), '')
        for fn in tree.body:
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)): continue
            for dec in fn.decorator_list:
                if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute) or ast.unparse(dec.func.value) != 'router': continue
                method = dec.func.attr.upper()
                if method not in {'GET','POST','PUT','PATCH','DELETE'} or not dec.args: continue
                path = '/api/v1' + prefix + ast.literal_eval(dec.args[0])
                domain = domain_for(path, source)
                deps = [ast.unparse(x) for x in fn.args.defaults if isinstance(x, ast.Call) and ast.unparse(x.func) == 'Depends']
                entries.append({'id': method+' '+path, 'method': method, 'path': path, 'domain': domain,
                    'sides': ['B','C'] if source in ('support','auth') else ['B'] if prefix.startswith('/b') else ['C'],
                    'handler': fn.name, 'source': f'backend/app/api/{source}.py', 'line': fn.lineno,
                    'source_hash': sha256(ast.get_source_segment(file.read_text(encoding='utf-8-sig'), fn).encode()).hexdigest(),
                    'dependencies': deps, 'description':ast.get_docstring(fn) or fn.name,
                    'implementation':ast.get_source_segment(file.read_text(encoding='utf-8-sig'),fn),
                    'parameters': [{ 'name': a.arg, 'type': ast.unparse(a.annotation) if a.annotation else ''} for a in fn.args.args if a.arg not in ('db','user')],
                    'writes': method != 'GET', 'contract_status': 'code_discovered'})
    return sorted(entries, key=lambda x:x['id'])


def channel_of(row):
    """接口覆盖与页面覆盖必须分开记录：浏览器适配器与点击工具都算页面测试。"""
    adapter = str(row.get('adapter', ''))
    return 'page' if ('browser' in adapter or 'ui_action' in adapter) else 'api'


CHANNEL_NOTE = {
    'api': '仅已登记接口/业务断言场景；接口调用成功只证明链路成功，不代表页面可用，也不代表本域全部接口与异常分支已覆盖',
    'page': '仅已登记页面场景；页面功能必须实际操作页面，接口通过不能替代页面验证，也不代表本域全部页面与交互已覆盖',
}

# 已人工核对测试断言的场景归类（不是按用例标题猜的）。每个条目都记录断言出处，便于复核与更新。
# 未列入的已登记用例一律记为“待确认”，只有完全没有执行工具的功能域才是“暂不可测试”。
REVIEWED_SCENARIOS = {
    'F02': {'kinds': ('permission',), 'evidence': 'tests/test_auth_security.py::test_invalid_tokens_and_database_role_are_authoritative',
            'why': '伪造商家角色的买家令牌访问商家接口必须 403；过期/缺失/篡改令牌必须 401'},
    'F11': {'kinds': ('abnormal', 'boundary'), 'evidence': 'tests/test_quality_business.py::test_cart_quantity_validation_preserves_previous_value',
            'why': '数量 0/-1/21 等非法与边界值必须被拒，且拒绝后购物车与之前完全一致'},
    'F13': {'kinds': ('normal',), 'evidence': 'tests/test_storefront_alignment.py::test_freight_quote_cart_and_created_order_use_same_shop_rules',
            'why': '运费报价、购物车与创建订单按同一店铺规则计算，店铺改价后新报价随之变化'},
    'F16': {'kinds': ('normal',), 'evidence': 'tests/test_coupons.py::test_cart_checkout_uses_same_discount',
            'why': '购物车结算使用与报价一致的优惠抵扣，结算后购物车清空'},
    'F17': {'kinds': ('normal', 'boundary'), 'evidence': 'tests/test_quality_business.py::test_order_reserves_exact_sku_stock_and_rejects_shortage',
            'why': '下单精确扣减目标 SKU 库存且不影响其它 SKU；库存不足（stock+1）必须拒绝'},
    'F19': {'kinds': ('normal',), 'evidence': 'tests/test_coupons.py::test_coupon_full_order_cancel_and_pay',
            'why': '下单/取消/支付的券状态与金额一致，总额等于商品加运费再减优惠，且券不可重复使用'},
}
SCENARIO_KINDS = ('normal', 'abnormal', 'permission', 'boundary')
SCENARIO_LABELS = {'normal': '正常流程', 'abnormal': '异常分支', 'permission': '权限/越权', 'boundary': '边界值'}

# 每类环境的测试数据要求与清理方式（与执行器实际行为一致：隔离档用独立子进程与工作区，实店只归档本轮记录）。
CLEANUP_MODES = {
    'isolated-local': {'mode': 'isolated_child_workspace',
                       'steps': ['每条用例在独立子进程内执行，使用独立 SQLite 与内存 Redis 命名空间',
                                 '用例结束后销毁子进程与临时工作区（含上传/页面资源副本），报告记录 cleanup_ok']},
    'native-local': {'mode': 'independent_mysql_namespace',
                     'steps': ['使用独立 MySQL 库、最小权限临时用户与独立 Redis 前缀',
                               '执行结束回收临时账号、库与命名空间，报告记录 cleanup_ok']},
    'real-nanzhi': {'mode': 'real_record_archive_only',
                    'steps': ['只写入本轮专属测试记录（不触碰既有业务数据）',
                              '结束后归档本轮记录并核对台账，保留审计，报告记录 cleanup_ok']},
}
CLEANUP_PAGE_STEP = '页面用例还会关闭浏览器与隔离站点，并清理临时截图工作区'
TEST_STATUS_NOTE = {
    'covered': '正常、异常、权限、边界四类都有已核对断言的用例；仍不代表本域全部分支',
    'partial': '只有部分场景类别有已核对断言的用例，其余类别待补充',
    'unconfirmed': '已登记工具存在，但场景归类尚未人工核对断言，按“待确认”处理，不计入覆盖',
    'untestable': '当前环境没有已登记执行工具，标记为“暂不可测试”，不编造步骤',
}


def cleanup_view(tool_rows):
    """逐功能说明测试数据要求与清理方式；清理成功不等于用例通过，实店不删业务数据。"""
    environments = sorted({env for row in tool_rows for env in (row.get('environments') or ('isolated-local', 'native-local'))})
    modes = [CLEANUP_MODES[env] for env in environments if env in CLEANUP_MODES]
    page = any(row['channel'] == 'page' for row in tool_rows)
    steps = [step for mode in modes for step in mode['steps']]
    if page:
        steps.append(CLEANUP_PAGE_STEP)
    return {'environments': environments, 'modes': [mode['mode'] for mode in modes], 'steps': steps,
            'evidence': '运行结果 result.cleanup_ok 与运行报告中的清理记录；失败或中断同样要求清理确认',
            'note': '清理成功只表示释放测试资源，不等于用例通过；实店执行只归档本轮记录，不删除业务数据',
            'untestable_note': None if tool_rows else '当前环境没有已登记执行工具，暂不可测试，也没有清理依据'}


def scenario_view(tool_rows):
    """按已核对归类输出四类场景；未核对的一律进待确认，不按标题猜测。"""
    registered = [row['case_id'] for row in tool_rows]
    reviewed = {case_id: REVIEWED_SCENARIOS[case_id] for case_id in registered if case_id in REVIEWED_SCENARIOS}
    coverage = {kind: sorted(case_id for case_id, entry in reviewed.items() if kind in entry['kinds']) for kind in SCENARIO_KINDS}
    unconfirmed = sorted(case_id for case_id in registered if case_id not in REVIEWED_SCENARIOS)
    if not registered:
        status = 'untestable'
    elif not reviewed:
        status = 'unconfirmed'
    else:
        status = 'covered' if all(coverage.values()) else 'partial'
    return {'kinds': SCENARIO_KINDS, 'labels': SCENARIO_LABELS, 'coverage': coverage,
            'reviewed': {case_id: {'kinds': list(entry['kinds']), 'evidence': entry['evidence'], 'why': entry['why']}
                         for case_id, entry in sorted(reviewed.items())},
            'unconfirmed_case_ids': unconfirmed, 'status': status, 'status_note': TEST_STATUS_NOTE[status]}


def split_channels(tools):
    return {channel: [row['case_id'] for row in tools if row['channel'] == channel] for channel in ('api', 'page')}


def catalog(case_rows=None):
    if case_rows is None:
        from app.quality.catalog import cases
        case_rows = cases()
    active = {r['id']:r for r in case_rows if r['kind']=='functional' and r['state']=='active'}
    endpoints = discover()
    features = []
    for key,(name,ids,rule) in DOMAINS.items():
        routes = [r for r in endpoints if r['domain']==key]
        if not routes: continue
        tools = [active[i] for i in ids if i in active]
        # 可复用点击工具已经是登记用例，按所属功能域并入本域工具清单（页面通道）。
        tools.extend(row for row in active.values()
                     if (row.get('ui_action') or row.get('ui_flow')) and row.get('feature') == key)
        tool_rows = [{'case_id':r['id'],'title':r['title'],'adapter':r.get('adapter'),'channel':channel_of(r),
                      'ui_action':r.get('ui_action'),
                      'environments':r.get('environments',[])} for r in tools]
        split = split_channels(tool_rows)
        features.append({'id':key,'name':name,'sides':sorted({s for r in routes for s in r['sides']}),
            'pages': [('/b.html' if s=='B' else '/c.html') for s in sorted({s for r in routes for s in r['sides']})],
            'rule':rule,'preconditions':['匹配用户/店铺/角色','使用当前环境的合成或本轮专属测试记录'],
            'verification':['核对实际请求、响应与业务状态','页面能力需浏览器场景独立验证'],
            'endpoints':routes,'tools':tool_rows,
            'coverage':'partial_registered' if tools else 'uncovered',
            'coverage_split':{channel:{'status':'partial_registered' if case_ids else 'uncovered',
                                       'case_ids':case_ids,'note':CHANNEL_NOTE[channel]}
                              for channel,case_ids in split.items()},
            'scenarios':scenario_view(tool_rows),
            'cleanup':cleanup_view(tool_rows),
            'ui_actions':ui_actions_view(key),
            'coverage_note':'接口覆盖与页面覆盖分别记录；两者都只统计已登记场景，不代表本域全部分支或页面已覆盖'})
    frontend=[]
    for side in ('b','c'):
        file=ROOT.parent/'web'/(side+'.js')
        source=file.read_text(encoding='utf-8-sig')
        frontend.append({'side':side.upper(),'source':'web/'+side+'.js','sha256':sha256(file.read_bytes()).hexdigest(),
                         'route_literals':sorted(set(re.findall(r'["\x27`]([^"\x27`\n]*#/[^"\x27`\n]*)["\x27`]',source))),
                         'note':'前端静态入口与模板，不等于这些交互已经浏览器验收'})
    body={'schema':'bc-features-v1','features':features,'endpoint_count':len(endpoints),'frontend':frontend,
          'ui_actions':ui_actions_view(None) if False else _all_ui_actions()}
    return {**body,'version':digest(body)}


def _all_ui_actions():
    from app.quality.ui_actions import public_view
    view = public_view()
    return {'counts': view['counts'], 'note': view['note'],
            'actions': [{key: row.get(key) for key in ('id', 'name', 'side', 'feature', 'status', 'entry', 'params', 'risk', 'steps', 'verify', 'cross_check', 'evidence', 'precondition')}
                        for row in view['actions']]}


def bind_plan(payload):
    """Called before approval digest; never silently upgrade an already approved plan."""
    if payload['kind'] not in ('functional','joint'): return
    snapshot = catalog(payload.get('case_snapshots'))
    payload['feature_catalog'] = snapshot
    if payload.get('functional_driver'):
        from app.core.config import settings
        payload['functional_model_profile']={'model':settings.qa_chat_model,'endpoint':settings.qa_chat_base_url,'style':settings.qa_chat_api_style}
    mapped = {t['case_id'] for f in snapshot['features'] for t in f['tools']}
    payload['unmapped_cases'] = [r['id'] for r in payload['case_snapshots'] if r['kind']=='functional' and r['id'] not in mapped]


def compact_cleanup(cleanup):
    """规划视图只带清理模式与边界说明；逐步清理步骤留在完整目录，避免撑大规划提示。"""
    return {'modes': cleanup['modes'], 'note': cleanup['note'], 'untestable_note': cleanup['untestable_note']}


def compact_coverage(split):
    """规划视图只带通道→用例；通道说明与待确认清单留在完整目录，避免撑大规划提示。"""
    return {channel: list(split[channel]['case_ids']) for channel in ('api', 'page')}


def compact_scenarios(scenarios):
    return {'status': scenarios['status'], 'coverage': scenarios['coverage']}


def ui_actions_view(feature_id):
    """本功能域可用的可复用点击工具（只有 ready 的可被 Agent 调用），并给出登记用例号。"""
    from app.quality.ui_actions import ACTIONS, catalog_rows
    registered = {row['ui_action']: row['id'] for row in catalog_rows() if row.get('ui_action')}
    rows = [{'id': row['id'], 'case_id': registered.get(row['id']), 'name': row['name'], 'side': row['side'],
             'status': row['status'], 'entry': row['entry'], 'params': row['params'], 'risk': row['risk'],
             'precondition': row.get('precondition')} for row in ACTIONS if row['feature'] == feature_id]
    return {'ready': [row['id'] for row in rows if row['status'] == 'ready'], 'actions': rows}


def planning_view(snapshot):
    if not snapshot:return None
    # All capabilities remain visible, but source implementations are fetched only for execution.
    features=[]
    for feature in snapshot['features']:
        row={key:value for key,value in feature.items() if key not in ('endpoints','pages','scenarios','coverage_split','cleanup','ui_actions')}
        row['entry_points']=[{'id':r['id'],'handler':r['handler'],'dependencies':r['dependencies'],'parameters':r['parameters']} for r in feature['endpoints']]
        row['coverage_split']=compact_coverage(feature['coverage_split'])
        row['scenarios']=compact_scenarios(feature['scenarios'])
        row['cleanup']=compact_cleanup(feature['cleanup'])
        # 点击工具已作为登记用例出现在 tools 里（带 ui_action 字段），不再单独下发清单以守住提示预算。
        features.append(row)
    return {'version':snapshot['version'],'endpoint_count':snapshot['endpoint_count'],'features':features}


def validate_bound(payload):
    old = payload.get('feature_catalog')
    if old and old['version'] != catalog(payload.get('case_snapshots'))['version']:
        raise ValueError('B/C功能目录已变化，请重新生成并批准计划')
    if payload.get('functional_model_profile'):
        from app.core.config import settings
        actual={'model':settings.qa_chat_model,'endpoint':settings.qa_chat_base_url,'style':settings.qa_chat_api_style}
        if actual!=payload['functional_model_profile']:raise ValueError('功能测试模型配置已变化，请重新审批计划')
