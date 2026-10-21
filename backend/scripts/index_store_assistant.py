import argparse
import json

from sqlalchemy import select

from app.agent.context import Actor
from app.db.session import SessionLocal
from app.models.tables import Product, Shop
from app.rag.product_images import search_product_images
from app.services.catalog import _product_query, serialize_product
from app.services.product_search import semantic_matches
from app.services.shelf import listed_on_c
from app.services.store_context import collect_records, ranked_ids


def main():
    parser = argparse.ArgumentParser(description="预热本店助手公开/商家知识与图片索引，不修改业务记录。私有买家数据只在本人查询时同步。")
    parser.add_argument("--shop-code", required=True)
    parser.add_argument("--images", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        shop = db.scalar(select(Shop).where(Shop.share_code == args.shop_code))
        if shop is None:
            raise SystemExit("没有找到店铺")
        result = []
        for role in ("customer", "merchant"):
            actor = Actor(shop.merchant_id, role, "indexer", shop.id)
            products = db.scalars(_product_query().where(Product.shop_id == shop.id)).unique().all()
            rows = [serialize_product(product, audience="b" if role == "merchant" else "c") for product in products if role == "merchant" or listed_on_c(product)]
            semantic_matches("商品", rows, db, actor)
            entry = {"role": role, "products": len(rows), "topics": {}}
            for topic in (("settings", "reviews", "coupons", "merchant_help") if role == "merchant" else ("settings", "reviews")):
                records = collect_records(db, actor, topic)
                ranked_ids(records, "", db, actor, topic, 5, build_only=True)
                entry["topics"][topic] = len(records)
            if args.images:
                _, status = search_product_images("", rows, db, actor)
                entry["images"] = status
            result.append(entry)
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
