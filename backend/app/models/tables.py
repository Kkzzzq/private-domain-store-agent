from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="customer")
    nickname: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    shop: Mapped["Shop | None"] = relationship(back_populates="merchant", uselist=False)
    orders: Mapped[list["Order"]] = relationship(back_populates="buyer")


class Shop(Base):
    """商家拥有一家店铺。C 端只通过分享码进入这家店。"""

    __tablename__ = "shops"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    notice: Mapped[str] = mapped_column(Text, default="")
    share_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    merchant: Mapped[User] = relationship(back_populates="shop")
    products: Mapped[list["Product"]] = relationship(back_populates="shop")
    orders: Mapped[list["Order"]] = relationship(back_populates="shop")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    category: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16), default="off")
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    shop: Mapped[Shop] = relationship(back_populates="products")
    skus: Mapped[list["Sku"]] = relationship(back_populates="product", cascade="all, delete-orphan")


class Sku(Base):
    __tablename__ = "skus"
    __table_args__ = (UniqueConstraint("product_id", "spec", name="uq_sku_spec"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    spec: Mapped[str] = mapped_column(String(64))
    price_cents: Mapped[int] = mapped_column()
    stock: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(16), default="on")

    product: Mapped[Product] = relationship(back_populates="skus")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    total_cents: Mapped[int] = mapped_column()
    address: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    shop: Mapped[Shop] = relationship(back_populates="orders")
    buyer: Mapped[User] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    """下单时记下商品和 SKU，同时保存当时的名称、规格和单价。"""

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"))
    product_name: Mapped[str] = mapped_column(String(128))
    sku_spec: Mapped[str] = mapped_column(String(64))
    price_cents: Mapped[int] = mapped_column()
    quantity: Mapped[int] = mapped_column()

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()
    sku: Mapped[Sku] = relationship()
