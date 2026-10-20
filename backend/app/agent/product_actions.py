"""Merchant product proposals: model prepares, authenticated UI confirms."""
from datetime import datetime, timedelta
from uuid import uuid4
import json
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import DateTime, ForeignKey, JSON, String, select, update
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.models.tables import Product, User, utcnow
from app.schemas.dto import ProductIn, SkuIn
from app.services.catalog import merchant_shop, serialize_product, _sku_row, invalidate_catalog_cache
from app.agent.context import current


class ProductProposal(Base):
    __tablename__ = "agent_product_proposals"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)
    session_id: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)


class PrepareProductArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_product_id: int | None = Field(default=None, ge=1, description="可选：仅以本店商品为模板复制新草稿，不修改原商品")
    name: str | None = Field(default=None, min_length=1, max_length=128)
    category: str | None = Field(default=None, max_length=15)
    description: str | None = Field(default=None, max_length=2000)
    image_url: str | None = Field(default=None, max_length=500)
    limit_per_user: int | None = Field(default=None, ge=0, le=99)
    skus: list[SkuIn] | None = Field(default=None, min_length=1, max_length=20,
        description="新建时必填，必须使用用户明确提供的规格、售价与库存，不推测价格和库存")

    @field_validator("name")
    @classmethod
    def nonblank(cls, value):
        if value is not None and not value.strip():
            raise ValueError("商品名称不能为空")
        return value.strip() if value is not None else None


def prepare_product_draft(**kwargs):
    db, actor = current()
    if actor.role != "merchant":
        raise HTTPException(403, "仅商家可配置商品")
    data = PrepareProductArgs.model_validate(kwargs)
    payload = {}
    if data.source_product_id:
        source = db.scalar(select(Product).where(Product.id == data.source_product_id, Product.shop_id == actor.shop_id))
        if source is None:
            raise HTTPException(404, "未找到本店模板商品")
        serialized = serialize_product(source, audience="b")
        payload = {k: serialized[k] for k in ("name", "category", "description", "image_url", "limit_per_user")}
        payload["skus"] = [{k: row[k] for k in ("spec", "price_yuan", "stock", "image_url", "market_price_yuan", "parameters")} for row in serialized["skus"]]
    payload.update(data.model_dump(exclude_none=True, exclude={"source_product_id"}))
    if not payload.get("name") or not payload.get("skus"):
        return "请先向商家确认商品名称、规格、售价和库存，或提供本店模板商品编号；尚未生成提案。"
    body = ProductIn.model_validate({**payload, "status": "draft"})
    proposal = ProductProposal(id=uuid4().hex, user_id=actor.user_id, shop_id=actor.shop_id,
        session_id=actor.session_id, payload=body.model_dump(), expires_at=utcnow() + timedelta(minutes=15))
    db.add(proposal)
    db.commit()
    return json.dumps({"type": "product_draft_proposal", "proposal_id": proposal.id,
        "name": body.name, "status": "pending", "message": "待商家点击预览并确认，仅保存草稿，不自动上架"}, ensure_ascii=False)


def owned_proposal(db, user, proposal_id):
    shop = merchant_shop(db, user)
    proposal = db.scalar(select(ProductProposal).where(ProductProposal.id == proposal_id,
        ProductProposal.user_id == user.id, ProductProposal.shop_id == shop.id))
    if proposal is None:
        raise HTTPException(404, "未找到该配置提案")
    return proposal


def snapshot(proposal):
    return {"id": proposal.id, "payload": proposal.payload, "status": proposal.status,
        "expires_at": proposal.expires_at.isoformat() + "Z", "product_id": proposal.product_id}


def confirm_proposal(db, user, proposal_id):
    proposal = owned_proposal(db, user, proposal_id)
    if proposal.status == "completed":
        return snapshot(proposal)
    now = utcnow()
    # Conditional UPDATE claims atomically; transaction also contains the product INSERT.
    claimed = db.execute(update(ProductProposal).where(ProductProposal.id == proposal_id,
        ProductProposal.status == "pending", ProductProposal.expires_at > now)
        .values(status="executing"), execution_options={"synchronize_session": False})
    if claimed.rowcount != 1:
        db.rollback()
        proposal = owned_proposal(db, user, proposal_id)
        if proposal.status == "completed":
            return snapshot(proposal)
        raise HTTPException(409, "提案已过期、已取消或正在处理，请重新生成或查询结果")
    try:
        body = ProductIn.model_validate(proposal.payload)
        product = Product(shop_id=proposal.shop_id, name=body.name.strip(), category=body.category.strip(),
            description=body.description.strip(), image_url=body.image_url.strip(),
            status="draft", sort_order=0, limit_per_user=body.limit_per_user)
        for index, sku in enumerate(body.skus):
            row = _sku_row(sku)
            row.sort_order = index + 1
            product.skus.append(row)
        db.add(product)
        db.flush()
        proposal.status = "completed"
        proposal.product_id = product.id
        db.commit()
    except Exception:
        db.rollback()
        raise
    invalidate_catalog_cache()
    return snapshot(proposal)
