from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.tables import Order, Product, Review, Shop, Sku, User
from app.models.support import AfterSale, Shipment
from scripts.seed_nanzhi_demo import BATCH, seed


def test_demo_seed_persists_consistent_data_and_is_idempotent(client):
    with SessionLocal() as db:
        shop = db.scalar(select(Shop).where(Shop.share_code == "nanzhi"))
        before = db.scalar(select(func.count()).select_from(Product))
        result = seed(db, shop.id)
        db.commit()
        assert result["products"] == 8 and result["customers"] == 6
        assert len(result["order_numbers"]) == 12
        for order in db.scalars(select(Order).where(Order.order_no.in_(result["order_numbers"]))):
            assert order.total_cents == sum(item.price_cents*item.quantity for item in order.items)+order.freight_cents
            for item in order.items:
                assert item.product_id == db.get(Sku,item.sku_id).spu_id
            shipment = db.scalar(select(Shipment).where(Shipment.order_id==order.id))
            assert bool(shipment) == (order.status in ("shipped","completed"))
        for review in db.scalars(select(Review).where(Review.user_id.in_(result["user_ids"]))):
            assert review.order_item.order.status == "completed"
        for row in db.scalars(select(AfterSale).where(AfterSale.order_id.in_(select(Order.id).where(Order.order_no.in_(result["order_numbers"]))))):
            assert db.get(Order,row.order_id).status in ("paid","shipped")
        again=seed(db,shop.id);db.commit()
        assert again["already_seeded"]
        assert db.scalar(select(func.count()).select_from(Product)) == before+8
        assert db.scalar(select(func.count()).select_from(User).where(User.username.startswith(BATCH))) == 6


def test_demo_seed_rejects_another_shop(client):
    import pytest
    with SessionLocal() as db:
        with pytest.raises(ValueError,match="nanzhi"):
            seed(db,-1)
