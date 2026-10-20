import argparse
import json
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description="只读核对演示店铺B/C公开数据，不修改商品、设置或订单")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    checks = []
    def check(name, passed, detail=""):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        auth = client.post("/api/v1/auth/login", json={"username": "merchant", "password": "merchant123"})
        auth.raise_for_status()
        headers = {"Authorization": "Bearer " + auth.json()["access_token"]}
        def get(path, merchant=False):
            response = client.get(path, headers=headers if merchant else {})
            response.raise_for_status()
            return response.json()
        business = get("/api/v1/b/shop", True)
        prefix = f"/api/v1/c/shops/{business['share_code']}"
        public = get(prefix)
        fields = ["name", "notice", "theme_color", "logo_url", "hero_height", "strip_tint", "assistant_name", "promises", "social_accounts"]
        check("店铺配置B/C一致", all(business.get(key) == public.get(key) for key in fields))
        check("新增全店配置接口已加载", "storefront" in business and business.get("storefront") == public.get("storefront"),
              "缺少storefront说明进程仍需正常重启加载最新代码")
        products = get("/api/v1/b/products", True)
        catalog = get(prefix + "/products")
        by_id = {item["id"]: item for item in products}
        expected = {item["id"] for item in products if item["status"] == "on" and business["status"] == "open"}
        check("SPU上下架可见范围", expected == {item["id"] for item in catalog})
        mismatches = []
        for product in catalog:
            source = by_id[product["id"]]
            for field in ("name", "category", "description", "image_url", "sort_order", "limit_per_user", "tags"):
                if source[field] != product[field]:
                    mismatches.append(f"SPU{product['id']}:{field}")
            source_skus = {sku["id"]: sku for sku in source["skus"] if sku["status"] == "on"}
            if set(source_skus) != {sku["id"] for sku in product["skus"]}:
                mismatches.append(f"SPU{product['id']}:SKU可见范围")
            for sku in product["skus"]:
                original = source_skus.get(sku["id"], {})
                for field in ("spec", "image_url", "price_yuan", "market_price_yuan", "stock", "parameters"):
                    if original.get(field) != sku.get(field):
                        mismatches.append(f"SKU{sku['id']}:{field}")
        check("SPU/SKU字段逐项对齐", not mismatches, "；".join(mismatches))
        price_mismatches = []
        for product in catalog:
            first = min(product["skus"], key=lambda item: (item["price_yuan"], item["id"]), default=None)
            if first and (product["price_from"] != first["price_yuan"] or product["market_from"] != first["market_price_yuan"]):
                price_mismatches.append(str(product["id"]))
        check("卡片现价原价属于同一SKU", not price_mismatches, "异常SPU：" + ",".join(price_mismatches))
        home = get(prefix + "/home")
        check("首页与店铺接口一致", home["shop"] == public)
        banners = get("/api/v1/b/banners", True)
        check("轮播启停对齐", {item["id"] for item in home["banners"]} == {item["id"] for item in banners if item["enabled"]})
        sections = {item["id"]: item for item in get("/api/v1/b/sections", True)}
        check("首页栏目与商品范围", all(section["id"] in sections and sections[section["id"]]["enabled"]
              and sections[section["id"]]["title"] == section["title"]
              and all(product["id"] in expected for product in section["products"]) for section in home["sections"]))
        coupons = {item["id"]: item for item in get("/api/v1/b/coupons", True)}
        public_coupons = get(prefix + "/coupons")
        check("优惠券条款对齐", all(item["id"] in coupons and all(item[field] == coupons[item["id"]][field]
              for field in ("name", "amount_cents", "threshold_cents", "starts_at", "ends_at", "enabled")) for item in public_coupons),
              f"核对{len(public_coupons)}张可见券；无券样本不代表已验证实际券条款")
    report = {"base_url": args.base_url, "read_only_business_data": True, "checks": checks,
              "passed": sum(item["passed"] for item in checks), "total": len(checks)}
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in checks:
        print(("PASS " if item["passed"] else "FAIL ") + item["name"] + (" " + item["detail"] if not item["passed"] else ""))
    if report["passed"] != report["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
