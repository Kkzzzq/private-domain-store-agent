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
    logo_url: Mapped[str] = mapped_column(String(500), default="")
    theme_color: Mapped[str] = mapped_column(String(16), default="#ff5000")
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
    sales_count: Mapped[int] = mapped_column(default=0)
    limit_per_user: Mapped[int] = mapped_column(default=0)
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
    freight_cents: Mapped[int] = mapped_column(default=0)
    receiver: Mapped[str] = mapped_column(String(32), default="")
    phone: Mapped[str] = mapped_column(String(20), default="")
    address: Mapped[str] = mapped_column(String(200))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("user_id", "sku_id", name="uq_cart_user_sku"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"))
    quantity: Mapped[int] = mapped_column(default=1)

    sku: Mapped[Sku] = relationship()
    shop: Mapped[Shop] = relationship()


class Address(Base):
    __tablename__ = "addresses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    receiver: Mapped[str] = mapped_column(String(32))
    phone: Mapped[str] = mapped_column(String(20))
    region: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str] = mapped_column(String(120))
    is_default: Mapped[bool] = mapped_column(default=False)


class Favorite(Base):
    """买家收藏商品。同一用户同一商品只留一条。"""

    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_favorite_user_product"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    product: Mapped[Product] = relationship()
    shop: Mapped[Shop] = relationship()


class Review(Base):
    """确认收货后可以评价。一条订单明细只能评一次。"""

    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("order_item_id", name="uq_review_order_item"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    order_item_id: Mapped[int] = mapped_column(ForeignKey("order_items.id"))
    rating: Mapped[int] = mapped_column(default=5)
    content: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship()
    product: Mapped[Product] = relationship()
    order_item: Mapped["OrderItem"] = relationship()
