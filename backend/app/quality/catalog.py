from hashlib import sha256
import json
from app.quality.assistant_scenarios import ADDITIONAL_CASES, LIVE_CASES
from app.quality.rag_scenarios import RAG_CASES
from app.quality.browser import BROWSER_CASES


ASSISTANT_TITLES = [
    "本店商品搜索", "SKU库存事实", "推荐前了解目录", "单件预算推荐", "组合总预算", "用途材质要求", "无匹配商品", "不可售商品排除",
    "缺参数澄清", "第二个商品多轮指代", "修改预算", "订单多轮追问", "跨用户订单保护", "会话身份隔离", "真实RAG政策", "知识无命中",
    "提示注入", "异常有限重试", "提案确认边界", "模型切换降级", "拒绝加购", "选择SKU后加购", "旧卡实时价格", "多SKU价格库存",
    "付款退款边界", "双端能力菜单", "物流事实", "售后联系商家", "本店经营概览", "库存预警阈值", "多SKU提案参数", "提案缺字段追问",
    "跨店商品模板保护", "旧提案过期取消", "知识版本更新", "冲突政策", "口语错别字", "无关问题边界", "工具空结果", "长会话摘要",
]
FUNCTIONAL_TITLES = [
    "登录退出撤销", "身份权限边界", "显式商家授权", "用户店铺隔离", "草稿状态机", "禁售保护", "SKU字段同步", "SKU顺序同步",
    "合集可售价格排序", "禁售停业交易保护", "购物车数量校验", "跨SKU限购", "订单金额运费", "领券限量去重", "优惠券发行与适用",
    "结算适用券", "创建订单库存", "取消库存回补", "锁券释放核销", "订单号唯一性", "订单销量累计", "订单归属与统计",
    "分类标签配置", "装修草稿预览", "评价缓存失效", "真人会话隔离", "物流记录", "售后状态机", "提案确认幂等", "参数异常回滚",
]
FUNCTIONAL_TESTS = {
    "F02": "test_auth_security.py::test_invalid_tokens_and_database_role_are_authoritative",
    "F03": "test_unified_account.py::test_other_accounts_cannot_open_store_without_authorization",
    "F11": "test_quality_business.py::test_cart_quantity_validation_preserves_previous_value",
    "F13": "test_storefront_alignment.py::test_freight_quote_cart_and_created_order_use_same_shop_rules",
    "F17": "test_quality_business.py::test_order_reserves_exact_sku_stock_and_rejects_shortage",
    "F23": "test_quality_business.py::test_categories_and_tag_colors_sync_to_buyer",
    "F24": "test_decoration.py::test_preview_is_read_only_and_save_publishes_all",
    "F26": "test_support.py::test_support_isolated_by_user_shop_and_order",
    "F27": "test_support.py::test_shipping_is_shared_and_state_transitions_are_protected",
    "F28": "test_support.py::test_after_sale_lifecycle_without_funds_or_order_rewrite",
    "F01": "test_auth_security.py::test_logout_revokes_only_this_token",
    "F04": "test_bc_link.py::test_c_order_lands_on_b_and_cannot_cross_user_or_shop",
    "F05": "test_product_lifecycle.py::test_draft_only_initial_state_and_no_extra_draft_table",
    "F06": "test_product_lifecycle.py::test_banned_product_blocks_all_merchant_writes",
    "F07": "test_sku_images.py::test_merchant_can_set_a_sku_image",
    "F08": "test_product_lifecycle.py::test_sku_order_reaches_buyer_details_and_home",
    "F09": "test_bc_catalog_boundaries.py::test_collection_price_sort_ignores_hidden_skus",
    "F10": "test_bc_link.py::test_shelf_ban_and_shop_close_control_whether_c_can_buy",
    "F12": "test_bc_trade_boundaries.py::test_purchase_limit_accumulates_all_skus_before_reserving_stock",
    "F14": "test_coupons.py::test_duplicate_claim_does_not_consume_quota",
    "F15": "test_coupons.py::test_issuance_exhaustion_does_not_invalidate_claimed_coupon",
    "F16": "test_coupons.py::test_cart_checkout_uses_same_discount",
    "F18": "test_bc_trade_boundaries.py::test_stock_releases_do_not_overwrite_another_session",
    "F19": "test_coupons.py::test_coupon_full_order_cancel_and_pay",
    "F20": "test_bc_trade_boundaries.py::test_order_numbers_are_unique_before_any_commit",
    "F21": "test_bc_trade_boundaries.py::test_payments_do_not_overwrite_sales_from_another_session",
    "F22": "test_bc_link.py::test_dashboard_reports_low_stock_and_recent_orders",
    "F25": "test_bc_catalog_boundaries.py::test_review_refreshes_cached_catalog_rating_immediately",
    "F29": "test_agent_actions.py::test_proposal_preview_confirm_idempotent_and_not_visible_to_buyer",
    "F30": "test_agent_actions.py::test_confirmation_failure_rolls_back_product_and_claim",
}

FUNCTIONAL_TITLES += ['OP全部商家路由与越权保护', 'OP商品规格价格图片同步三端', 'OP店铺分类标签内容优惠券同步', 'OP装修预览发布与版本冲突', 'OP封店实时影响买家和商家', 'OP停用恢复重置密码撤销会话', 'OP物流售后与买家状态同步', 'OP评价隐藏恢复保留原文', 'OP买家详情权限与资源保护', 'OP规格禁售不可商家解除', 'OP上传校验和规格排序落盘', 'OP取消订单库存仅回补一次', 'OP创建账号及显式管理授权']
FUNCTIONAL_TESTS.update({'F31': 'test_op_complete.py::test_all_existing_routes_have_op_scope', 'F32': 'test_op_complete.py::test_full_product_sku_images_tags_and_scope', 'F33': 'test_op_complete.py::test_settings_categories_tags_content_and_coupons', 'F34': 'test_op_complete.py::test_decoration_revision_preview_save_and_sort', 'F35': 'test_op_complete.py::test_platform_freeze_blocks_cached_products_cart_and_merchant_reopen', 'F36': 'test_op_complete.py::test_account_disable_enable_reset_revokes_old_sessions', 'F37': 'test_op_complete.py::test_shipping_and_after_sales_share_existing_state_machine', 'F38': 'test_op_complete.py::test_review_moderation_updates_c_rating_without_editing_original', 'F39': 'test_op_complete.py::test_customer_details_are_explicit_and_op_only', 'F40': 'test_op_complete.py::test_sku_governance_is_platform_only', 'F41': 'test_op_complete.py::test_upload_validation_and_sku_sorting', 'F42': 'test_op_complete.py::test_platform_cancel_restores_stock_once', 'F43': 'test_op_complete.py::test_create_account_and_explicit_operator_grant'})

ASSISTANT_CASES = {"A01", "A02", "A04", "A07", "A08", "A13", "A14", "A29", "A30", "A38", "A39"}
ASSISTANT_CASES |= ADDITIONAL_CASES
ASSISTANT_CASES |= RAG_CASES | {"A20"}
LIVE_CASES |= RAG_CASES | {"A20"}
CAPABILITIES = {"qa.view", "qa.assistant.run", "qa.functional.run", "qa.approve"}
ENVIRONMENT = {"id": "isolated-local", "name": "独立合成数据 / SQLite + 内存Redis", "production": False,
               "description": "每个用例独立子进程；不连接现有店铺库。真实MySQL/Redis联调档尚未启用。"}
NATIVE_ENVIRONMENT = {"id": "native-local", "name": "独立合成数据 / 真实MySQL + Redis", "production": False,
                      "description": "本地归属校验后创建独立数据库、最小权限临时用户与Redis命名空间，执行后清理。"}


def environments():
    from app.core.config import settings
    return [ENVIRONMENT, NATIVE_ENVIRONMENT] if settings.qa_native_enabled else [ENVIRONMENT]


def cases():
    rows = []
    for kind, titles, prefix in (("assistant", ASSISTANT_TITLES, "A"), ("functional", FUNCTIONAL_TITLES, "F")):
        for index, title in enumerate(titles, 1):
            case_id = f"{prefix}{index:02}"
            active = case_id in (ASSISTANT_CASES if kind == "assistant" else FUNCTIONAL_TESTS)
            rows.append({"id": case_id, "title": title, "kind": kind, "version": 1,
                         "state": "active" if active else "candidate", "modes": ["live"] if case_id in LIVE_CASES else ["rules", "live"] if kind == "assistant" else ["rules"],
                         "adapter": "isolated_assistant_api" if kind == "assistant" else "registered_pytest",
                         "critical": True})
    rows.extend({"id": case_id, "title": title, "kind": "functional", "version": 1, "state": "active", "modes": ["rules"], "adapter": "registered_browser", "critical": True,
                 "environments": ["isolated-local"] if case_id == "E04" else ["isolated-local", "native-local"]} for case_id, title in BROWSER_CASES.items())
    return rows


def case_by_id(case_id):
    return next((row for row in cases() if row["id"] == case_id), None)


def content_digest(payload):
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


CATALOG_VERSION = content_digest(cases())
