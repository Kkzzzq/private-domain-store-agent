"""隔离缺陷注入：只在独立合成环境生效，用于校准功能测试 Agent 的检出能力。

每个场景都必须能证明三件事：注入确实被执行、注入让真实登记用例失败、正常版本不误报。
注入接缝统一选在路由实际调用的模块命名空间（app.api.c_api 等），因为这些名字在请求时按模块全局解析。
"""
ISOLATED_ONLY = '缺陷注入仅限独立合成环境'

SCENARIOS = (
    {'variant': 'wrong_freight', 'case_id': 'F13', 'title': '订单金额运费', 'marker': 'freight_yuan',
     'defect': '购物车接口返回的运费比店铺规则多 1 元',
     'goal': '检查 C 端购物车与创建订单的运费是否与店铺规则一致：先读功能目录，再执行批准的 F13 并如实报告。'},
    {'variant': 'wrong_total', 'case_id': 'F19', 'title': '锁券释放核销', 'marker': 'total_yuan',
     'defect': '创建订单返回的应付总额比商品金额加运费（再减优惠）多 100 元',
     'goal': '检查下单、取消与支付时的金额与券状态：先读功能目录，再执行批准的 F19 并如实报告。'},
    {'variant': 'stock_over_add', 'case_id': 'F17', 'title': '创建订单库存', 'marker': 'quantity',
     'defect': '库存不足时不再拒绝下单，而是静默改成合法数量继续下单（超卖不报错）',
     'goal': '检查创建订单时的库存校验：先读功能目录，再执行批准的 F17 并如实报告。'},
    {'variant': 'buyer_merchant_access', 'case_id': 'F02', 'title': '身份权限边界', 'marker': 'actor_role',
     'defect': '买家身份被当作商家，可以访问商家接口',
     'goal': '检查身份与权限边界：先读功能目录，再执行批准的 F02 并如实报告。'},
)
SCENARIO_BY_VARIANT = {row['variant']: row for row in SCENARIOS}


def scenario(variant):
    return SCENARIO_BY_VARIANT.get(variant)


def wrong_freight(receipt):
    from app.api import c_api
    original = c_api.cart_view

    def faulty(*args, **kwargs):
        result = original(*args, **kwargs)
        receipt['calls'] = receipt.get('calls', 0) + 1
        receipt['original'] = result['freight_yuan']
        receipt['injected'] = result['freight_yuan'] + 1
        return {**result, 'freight_yuan': result['freight_yuan'] + 1}

    c_api.cart_view = faulty
    return lambda: setattr(c_api, 'cart_view', original)


def wrong_total(receipt):
    from app.api import c_api
    original = c_api.create_order

    def faulty(*args, **kwargs):
        result = original(*args, **kwargs)
        receipt['calls'] = receipt.get('calls', 0) + 1
        receipt['original'] = result.get('total_yuan')
        if 'total_yuan' not in result:
            raise ValueError('缺陷注入失败：订单返回值没有 total_yuan')
        receipt['injected'] = result['total_yuan'] + 100
        return {**result, 'total_yuan': result['total_yuan'] + 100}

    c_api.create_order = faulty
    return lambda: setattr(c_api, 'create_order', original)


def stock_over_add(receipt):
    """库存不足先被拒时，改用一个合法数量重放，制造“超卖不报错、静默改量”的缺陷。"""
    from fastapi import HTTPException
    from app.api import c_api
    original = c_api.create_order

    def faulty(db, user, share_code, body):
        try:
            return original(db, user, share_code, body)
        except HTTPException as exc:
            if exc.status_code != 400 or not hasattr(body, 'model_copy'):
                raise
            receipt['calls'] = receipt.get('calls', 0) + 1
            receipt['coerced'] = {'endpoint': 'create_order', 'from': getattr(body, 'quantity', None), 'to': 1,
                                  'rejected': exc.detail}
            return original(db, user, share_code, body.model_copy(update={'quantity': 1}))

    c_api.create_order = faulty
    return lambda: setattr(c_api, 'create_order', original)


def buyer_merchant_access(receipt):
    """把买家当商家：权限判定与角色属性同时放开，等价于“权限边界失效”。"""
    from app.core import deps
    from app.models import tables
    original_can_manage = deps.can_manage_store
    original_role = tables.User.__dict__.get('actor_role')

    def always_manage(_db, _user):
        receipt['calls'] = receipt.get('calls', 0) + 1
        receipt['injected'] = 'can_manage_store=True; actor_role=merchant'
        return True

    deps.can_manage_store = always_manage
    tables.User.actor_role = property(lambda self: 'merchant')

    def restore():
        deps.can_manage_store = original_can_manage
        if original_role is not None:
            tables.User.actor_role = original_role
    return restore


_INJECTORS = {'wrong_freight': wrong_freight, 'wrong_total': wrong_total,
              'stock_over_add': stock_over_add, 'buyer_merchant_access': buyer_merchant_access}


def apply(variant, environment_id, receipt):
    """按变体注入缺陷并返回恢复函数；未登记变体不做任何修改。"""
    row = scenario(variant)
    if not row:
        return lambda: None
    if environment_id != 'isolated-local':
        raise ValueError(ISOLATED_ONLY)
    receipt.update({'defect': row['defect'], 'case_id': row['case_id'], 'marker': row['marker']})
    return _INJECTORS[variant](receipt)