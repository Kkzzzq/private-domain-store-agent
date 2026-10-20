from typing import Literal
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DetailSection(BaseModel):
    title: str = Field(min_length=1, max_length=40)
    body: str = Field(min_length=1, max_length=2000)


class StorefrontSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    background_color: str = Field(default="#faf7f2", pattern=r"^#[0-9a-fA-F]{6}$")
    surface_color: str = Field(default="#fffcf7", pattern=r"^#[0-9a-fA-F]{6}$")
    text_color: str = Field(default="#38332e", pattern=r"^#[0-9a-fA-F]{6}$")
    muted_color: str = Field(default="#756b62", pattern=r"^#[0-9a-fA-F]{6}$")
    product_image_ratio: Literal["1/1", "4/5", "3/4"] = "4/5"
    rail_columns: Literal["3", "3.5", "4"] = "3.5"
    hero_enabled: bool = True
    promises_enabled: bool = True
    assistant_enabled: bool = True
    merchant_title: str = Field(default="商家工作台", min_length=1, max_length=32)
    brand_slogan: str = Field(default="器物有温度，日常有心意", max_length=60)
    portal_title: str = Field(default="让喜欢的好物，走进日常。", max_length=60)
    portal_description: str = Field(default="逛逛小店，发现一件心仪之物。也让每一份用心经营，都有条不紊。", max_length=200)
    product_subtitle: str = Field(default="店主直发 · 小批量手作", max_length=100)
    footer_about: str = Field(default="私域独立店铺 · 分享码进店", max_length=200)
    footer_service: str = Field(default="有问题点右下角问店内助手", max_length=200)
    dispatch_text: str = Field(default="付款后48小时内发货", max_length=120)
    return_text: str = Field(default="7天无理由退货，定制品和已使用商品除外", max_length=200)
    free_shipping_yuan: float = Field(default=99, ge=0, le=100000)
    base_freight_yuan: float = Field(default=8, ge=0, le=10000)
    assistant_welcome: str = Field(default="可以推荐商品、查询库存和你自己的订单，也能检索售后和养护说明哦。", max_length=500)
    quick_questions: list[str] = Field(default_factory=lambda: ["抱枕还有货吗", "我的订单到哪了", "定制品能退吗"], max_length=6)
    testimonial_title: str = Field(default="买家反馈", max_length=40)
    testimonial_subtitle: str = Field(default="店铺展示的买家反馈", max_length=100)
    detail_sections: list[DetailSection] = Field(default_factory=list, max_length=6)

    @field_validator("free_shipping_yuan", "base_freight_yuan")
    @classmethod
    def validate_money(cls, value):
        amount = Decimal(str(value))
        if amount != amount.quantize(Decimal("0.01")):
            raise ValueError("运费和门槛最多保留两位小数")
        return value

    @field_validator("quick_questions")
    @classmethod
    def validate_questions(cls, values):
        if any(not item.strip() or len(item) > 80 for item in values):
            raise ValueError("快捷问题须为1至80字")
        return [item.strip() for item in values]
