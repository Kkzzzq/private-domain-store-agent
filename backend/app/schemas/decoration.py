from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.dto import BannerIn, PromiseItem, SectionIn, TestimonialIn
from app.schemas.storefront import StorefrontSettings


class AppearanceDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hero_height: int = Field(ge=320, le=760)
    strip_tint: bool
    promises: list[PromiseItem] = Field(max_length=6)
    storefront: StorefrontSettings


class BannerDraft(BannerIn):
    id: int


class SectionDraft(SectionIn):
    id: int


class TestimonialDraft(TestimonialIn):
    id: int


class DecorationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    appearance: AppearanceDraft
    banners: list[BannerDraft] = Field(max_length=30)
    sections: list[SectionDraft] = Field(max_length=30)
    testimonials: list[TestimonialDraft] = Field(max_length=100)

    @model_validator(mode="after")
    def unique_ids(self):
        for rows in (self.banners, self.sections, self.testimonials):
            ids = [row.id for row in rows]
            if 0 in ids or len(set(ids)) != len(ids):
                raise ValueError("装修内容ID不能为0或重复")
        return self


class SortOrderIn(BaseModel):
    ordered_ids: list[int] = Field(max_length=1000)

    @model_validator(mode="after")
    def unique_ids(self):
        if len(set(self.ordered_ids)) != len(self.ordered_ids):
            raise ValueError("排序ID不能重复")
        return self
