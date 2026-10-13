from typing import Literal

from pydantic import BaseModel, Field


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


class ShopUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    notice: str | None = Field(default=None, max_length=500)
    status: Literal["open", "closed"] | None = None


class ShopOut(BaseModel):
    id: int
    name: str
    notice: str
    share_code: str
    status: str
    share_path: str


class StatusAction(BaseModel):
    action: Literal["on", "off", "ban", "unban"]


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class SkuIn(BaseModel):
    spec: str = Field(min_length=1, max_length=40)
    price_yuan: float = Field(gt=0, le=100000)
    stock: int = Field(ge=0, le=100000)


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    category: str = Field(default="家居", max_length=64)
    description: str = Field(default="", max_length=2000)
    image_url: str = Field(default="", max_length=500)
    skus: list[SkuIn] = Field(min_length=1, max_length=20)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    image_url: str | None = Field(default=None, max_length=500)
    sort_order: int | None = Field(default=None, ge=0, le=9999)


class SkuUpdate(BaseModel):
    spec: str | None = Field(default=None, min_length=1, max_length=40)
    price_yuan: float | None = Field(default=None, gt=0, le=100000)
    stock: int | None = Field(default=None, ge=0, le=100000)


class SkuOut(BaseModel):
    id: int
    spec: str
    price_yuan: float
    stock: int
    status: str
    purchasable: bool | None = None


class ProductOut(BaseModel):
    id: int
    shop_id: int
    name: str
    category: str
    description: str
    image_url: str
    status: str
    sort_order: int
    skus: list[SkuOut]


class OrderCreate(BaseModel):
    sku_id: int = Field(ge=1)
    quantity: int = Field(ge=1, le=20)
    address: str = Field(min_length=4, max_length=120)


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
    total_yuan: float
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
