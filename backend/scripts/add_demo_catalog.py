import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.demo_catalog import add_demo_catalog, expand_cup_skus
from app.services.catalog import invalidate_catalog_cache


def main():
    parser = argparse.ArgumentParser(description="为指定演示店铺补充带独立 SKU 图的商品；重复执行不覆盖已有商品")
    parser.add_argument("--shop", required=True)
    parser.add_argument("--expand-cup", action="store_true")
    args = parser.parse_args()
    web_root = Path(__file__).resolve().parents[2] / "web"
    with SessionLocal() as db:
        count = add_demo_catalog(db, args.shop, web_root)
        if args.expand_cup:
            print(f"新增 {expand_cup_skus(db, args.shop)} 个饮水杯组合规格")
    invalidate_catalog_cache()
    print(f"新增 {count} 件商品，商品缓存已刷新")


if __name__ == "__main__":
    main()
