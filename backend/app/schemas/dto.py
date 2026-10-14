from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=6, max_length=64)
    role: Literal["customer", "merchant"] = "customer"
    nickname: str = Field(default="", max_length=32)


class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    nickname: str


class PromiseItem(BaseModel):
    """首页最下面那条售后保障，商家自己写。"""

    title: str = Field(min_length=1, max_length=16)
    sub: str = Field(default="", max_length=40)


class ShopUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    notice: str | None = Field(default=None, max_length=500)
    logo_url: str | None = Field(default=None, max_length=500)
    theme_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    status: Literal["open", "closed"] | None = None
    hero_height: int | None = Field(default=None, ge=320, le=760)
    strip_tint: bool | None = None
    promises: list[PromiseItem] | None = Field(default=None, max_length=6)


class ShopOut(BaseModel):
    id: int
    name: str
    notice: str
    logo_url: str
    theme_color: str
    share_code: str
    status: str
    share_path: str
    hero_height: int
    strip_tint: bool
    promises: list[PromiseItem]


class StatusAction(BaseModel):
    action: Literal["on", "off", "ban", "unban"]


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class SkuIn(BaseModel):
    spec: str = Field(min_length=1, max_length=40)
    price_yuan: float = Field(gt=0, le=100000)
    market_price_yuan: float | None = Field(default=None, gt=0, le=100000)
    stock: int = Field(ge=0, le=100000)


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    category: str = Field(default="家居", max_length=64)
    description: str = Field(default="", max_length=2000)
    image_url: str = Field(default="", max_length=500)
    limit_per_user: int = Field(default=0, ge=0, le=99)
    tag_names: list[str] = Field(default_factory=list, max_length=4)
    skus: list[SkuIn] = Field(min_length=1, max_length=20)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    category: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    image_url: str | None = Field(default=None, max_length=500)
    sort_order: int | None = Field(default=None, ge=0, le=9999)
    limit_per_user: int | None = Field(default=None, ge=0, le=99)
    tag_names: list[str] | None = Field(default=None, max_length=4)


class SkuUpdate(BaseModel):
    spec: str | None = Field(default=None, min_length=1, max_length=40)
    price_yuan: float | None = Field(default=None, gt=0, le=100000)
    market_price_yuan: float | None = Field(default=None, gt=0, le=100000)
    stock: int | None = Field(default=None, ge=0, le=100000)


class SkuOut(BaseModel):
    id: int
    spec: str
    price_yuan: float
    market_price_yuan: float | None = None
    stock: int
    status: str
    purchasable: bool | None = None


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=16)
    color: str = Field(default="", max_length=16)


class TagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=16)
    color: str | None = Field(default=None, max_length=16)
    sort_order: int | None = Field(default=None, ge=0, le=9999)


class TagOut(BaseModel):
    id: int
    name: str
    color: str
    sort_order: int
    product_count: int


class TagRef(BaseModel):
    """挂在商品上的标签，买家端只关心名字和颜色。"""

    name: str
    color: str


class ProductOut(BaseModel):
    id: int
    shop_id: int
    name: str
    category: str
    description: str
    image_url: str
    status: str
    sort_order: int
    sales_count: int
    limit_per_user: int
    rating_avg: float | None = None
    review_count: int = 0
    favorited: bool = False
    price_from: float | None = None
    market_from: float | None = None
    tags: list[TagRef] = []
    skus: list[SkuOut]


class SavedProductOut(ProductOut):
    """收藏和浏览记录里的商品。跨店铺，下架的也保留，所以额外带店铺和状态信息。"""

    shop_name: str
    shop_share_code: str
    shelf_label: str
    available: bool


class OrderLine(BaseModel):
    sku_id: int = Field(ge=1)
    quantity: int = Field(ge=1, le=20)


class OrderCreate(BaseModel):
    sku_id: int | None = Field(default=None, ge=1)
    quantity: int = Field(default=1, ge=1, le=20)
    items: list[OrderLine] | None = None
    address: str = Field(min_length=4, max_length=120)
    receiver: str = Field(default="", max_length=32)
    phone: str = Field(default="", max_length=20)

    @model_validator(mode="after")
    def require_lines(self):
        if not self.items and self.sku_id is None:
            raise ValueError("请选择商品")
        return self


class CartAdd(BaseModel):
    sku_id: int = Field(ge=1)
    quantity: int = Field(default=1, ge=1, le=20)


class CartUpdate(BaseModel):
    quantity: int = Field(ge=1, le=20)


class CartCheckout(BaseModel):
    address: str = Field(min_length=4, max_length=120)
    receiver: str = Field(default="", max_length=32)
    phone: str = Field(default="", max_length=20)
    cart_item_ids: list[int] = Field(default_factory=list)


class AddressIn(BaseModel):
    receiver: str = Field(min_length=1, max_length=32)
    phone: str = Field(min_length=6, max_length=20)
    region: str = Field(min_length=2, max_length=80)
    detail: str = Field(min_length=2, max_length=120)
    is_default: bool = False


class AddressOut(BaseModel):
    id: int
    receiver: str
    phone: str
    region: str
    detail: str
    is_default: bool


class ReviewIn(BaseModel):
    order_item_id: int = Field(ge=1)
    rating: int = Field(ge=1, le=5)
    content: str = Field(default="", max_length=500)


class ReviewOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    rating: int
    content: str
    nickname: str
    created_at: str


class PendingReview(BaseModel):
    order_item_id: int
    order_no: str
    product_id: int
    product_name: str
    sku_spec: str


class BatchShipIn(BaseModel):
    order_nos: list[str] = Field(min_length=1, max_length=50)


class BannerIn(BaseModel):
    image_url: str = Field(min_length=1, max_length=500)
    title: str = Field(default="", max_length=64)
    subtitle: str = Field(default="", max_length=120)
    link_type: Literal["none", "product", "section"] = "none"
    link_value: str = Field(default="", max_length=64)
    enabled: bool = True


class BannerUpdate(BaseModel):
    image_url: str | None = Field(default=None, min_length=1, max_length=500)
    title: str | None = Field(default=None, max_length=64)
    subtitle: str | None = Field(default=None, max_length=120)
    link_type: Literal["none", "product", "section"] | None = None
    link_value: str | None = Field(default=None, max_length=64)
    sort_order: int | None = Field(default=None, ge=0, le=9999)
    enabled: bool | None = None


class BannerOut(BaseModel):
    id: int
    image_url: str
    title: str
    subtitle: str
    link_type: str
    link_value: str
    sort_order: int
    enabled: bool


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=32)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=32)
    sort_order: int | None = Field(default=None, ge=0, le=9999)


class CategoryOut(BaseModel):
    id: int
    name: str
    sort_order: int
    product_count: int


class SectionIn(BaseModel):
    title: str = Field(min_length=1, max_length=64)
    subtitle: str = Field(default="", max_length=120)
    source: Literal["manual", "sales"] = "manual"
    enabled: bool = True
    product_ids: list[int] = Field(default_factory=list, max_length=24)


class SectionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=64)
    subtitle: str | None = Field(default=None, max_length=120)
    source: Literal["manual", "sales"] | None = None
    sort_order: int | None = Field(default=None, ge=0, le=9999)
    enabled: bool | None = None
    product_ids: list[int] | None = Field(default=None, max_length=24)


class SectionOut(BaseModel):
    id: int
    title: str
    subtitle: str
    source: str
    sort_order: int
    enabled: bool
    product_ids: list[int]
    product_names: list[str]


class TestimonialIn(BaseModel):
    nickname: str = Field(min_length=1, max_length=32)
    content: str = Field(min_length=1, max_length=300)
    rating: int = Field(default=5, ge=1, le=5)
    enabled: bool = True


class TestimonialUpdate(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=32)
    content: str | None = Field(default=None, min_length=1, max_length=300)
    rating: int | None = Field(default=None, ge=1, le=5)
    sort_order: int | None = Field(default=None, ge=0, le=9999)
    enabled: bool | None = None


class TestimonialOut(BaseModel):
    id: int
    nickname: str
    content: str
    rating: int
    sort_order: int
    enabled: bool


class HomeSection(BaseModel):
    id: int
    title: str
    subtitle: str
    products: list[ProductOut]


class CollectionOut(BaseModel):
    key: str
    title: str
    subtitle: str
    source: str
    categories: list[str]
    category_counts: dict[str, int] = {}
    total: int
    products: list[ProductOut]


class HomeOut(BaseModel):
    banners: list[BannerOut]
    sections: list[HomeSection]
    testimonials: list[TestimonialOut]
    shop: ShopOut


class UploadOut(BaseModel):
    url: str


class OrderItemOut(BaseModel):
    product_id: int
    sku_id: int
    product_name: str
    sku_spec: str
    price_yuan: float
    quantity: int


class OrderOut(BaseModel):
    order_no: str
    shop_id: int
    shop_name: str
    status: str
    status_label: str
    goods_yuan: float
    freight_yuan: float
    total_yuan: float
    expires_in_seconds: int | None = None
    receiver: str = ""
    phone: str = ""
    address: str
    buyer_nickname: str | None = None
    buyer_username: str | None = None
    items: list[OrderItemOut]


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{8,64}$")


class ToolTrace(BaseModel):
    tool: str
    args: dict
    result: str


class ChatOut(BaseModel):
    session_id: str
    answer: str
    mode: str
    tools: list[ToolTrace]
    notices: list[str]


class SessionOut(BaseModel):
    session_id: str
    summary: str
    messages: list[dict]


class ReindexOut(BaseModel):
    chunks: int
    mode: str
    detail: str
