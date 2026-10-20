from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_db, require_merchant
from app.models.tables import User
from app.agent.assistant import assistant
from app.agent.streaming import chat_stream
from app.agent.context import Actor, set_actor, reset_actor
from app.schemas.dto import ChatIn, ChatOut, SessionOut
from app.rag.knowledge import reindex_knowledge
from app.schemas.dto import (
    BannerIn,
    BannerOut,
    BannerUpdate,
    BatchShipIn,
    CategoryIn,
    CategoryOut,
    CategoryUpdate,
    OrderOut,
    ProductIn,
    ProductOut,
    ProductUpdate,
    ReindexOut,
    SectionIn,
    SectionOut,
    SectionUpdate,
    ShopOut,
    ShopUpdate,
    SkuIn,
    SkuUpdate,
    StatusAction,
    TagIn,
    TagOut,
    TagUpdate,
    TestimonialIn,
    TestimonialOut,
    TestimonialUpdate,
    UploadOut,
)
from app.services.home import (
    create_banner,
    create_section,
    create_testimonial,
    delete_banner,
    delete_section,
    delete_testimonial,
    list_banners,
    list_sections,
    list_testimonials,
    update_banner,
    update_section,
    update_testimonial,
)
from app.services.catalog import (
    change_product_status,
    change_sku_status,
    add_sku,
    create_product,
    dashboard,
    list_b_products,
    merchant_shop,
    serialize_shop,
    update_product,
    update_shop,
    update_sku,
    reorder_skus,
)
from app.services.orders import list_b_orders, ship_order, ship_orders
from app.services import categories as category_service
from app.services import tags as tag_service

router = APIRouter(prefix="/b", tags=["b"])

from app.schemas.decoration import DecorationDraft, SortOrderIn
from app.services import decoration as decoration_service


@router.get("/decoration")
def read_decoration(user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return decoration_service.decoration_snapshot(db, user)


@router.post("/decoration/preview")
def preview_decoration(body: DecorationDraft, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return decoration_service.preview_decoration(db, user, body)


@router.put("/decoration")
def save_decoration(body: DecorationDraft, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return decoration_service.save_decoration(db, user, body)


@router.post("/sort/{kind}")
def sort_rows(kind: str, body: SortOrderIn, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return decoration_service.reorder(db, user, kind, body.ordered_ids)

from app.services import coupons as coupon_service


@router.get("/coupons")
def list_coupons(user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return coupon_service.list_b(db, user)


@router.post("/coupons")
def create_coupon(body: coupon_service.CouponIn, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return coupon_service.create(db, user, body)


@router.patch("/coupons/{coupon_id}")
def toggle_coupon(coupon_id: int, body: coupon_service.CouponStatus, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return coupon_service.toggle(db, user, coupon_id, body)


@router.post("/chat/stream")
def stream_chat(body: ChatIn, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return chat_stream(user, merchant_shop(db, user).id, body)


@router.post("/chat", response_model=ChatOut)
def chat(body: ChatIn, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    shop = merchant_shop(db, user)
    token = set_actor(db, Actor(user.id, user.role, user.username, shop.id))
    try:
        return assistant.chat(user_id=user.id, shop_id=shop.id, session_id=body.session_id, message=body.message)
    finally:
        reset_actor(token)


@router.get("/sessions/{session_id}", response_model=SessionOut)
def read_agent_session(session_id: str, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return assistant.read_session(user.id, merchant_shop(db, user).id, session_id)


@router.get("/shop", response_model=ShopOut)
def read_shop(user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return serialize_shop(merchant_shop(db, user))


@router.patch("/shop", response_model=ShopOut)
def patch_shop(body: ShopUpdate, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return update_shop(db, user, body)


@router.get("/dashboard")
def read_dashboard(user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return dashboard(db, user)


@router.get("/products", response_model=list[ProductOut])
def read_products(
    keyword: str = "",
    status: str = "",
    user: User = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    return list_b_products(db, user, keyword=keyword, status=status)


@router.post("/products", response_model=ProductOut)
def add_product(body: ProductIn, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return create_product(db, user, body)


@router.patch("/products/{product_id}", response_model=ProductOut)
def patch_product(
    product_id: int,
    body: ProductUpdate,
    user: User = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    return update_product(db, user, product_id, body)


@router.post("/products/{product_id}/status", response_model=ProductOut)
def product_status(
    product_id: int,
    body: StatusAction,
    user: User = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    return change_product_status(db, user, product_id, body.action)


@router.post("/products/{product_id}/skus", response_model=ProductOut)
def create_sku(
    product_id: int,
    body: SkuIn,
    user: User = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    return add_sku(db, user, product_id, body)


@router.post("/products/{product_id}/skus/sort", response_model=ProductOut)
def sort_skus(product_id: int, body: SortOrderIn, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return reorder_skus(db, user, product_id, body.ordered_ids)


@router.patch("/skus/{sku_id}", response_model=ProductOut)
def patch_sku(
    sku_id: int,
    body: SkuUpdate,
    user: User = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    return update_sku(db, user, sku_id, body)


@router.post("/skus/{sku_id}/status", response_model=ProductOut)
def sku_status(
    sku_id: int,
    body: StatusAction,
    user: User = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    return change_sku_status(db, user, sku_id, body.action)


@router.get("/orders", response_model=list[OrderOut])
def read_orders(status: str = "", user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return list_b_orders(db, user, status)


@router.post("/orders/{order_no}/ship", response_model=OrderOut)
def ship(order_no: str, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return ship_order(db, user, order_no)


@router.post("/orders/ship-batch")
def ship_many(body: BatchShipIn, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return ship_orders(db, user, body.order_nos)


@router.post("/knowledge/reindex", response_model=ReindexOut)
def reindex(user: User = Depends(require_merchant)):
    del user
    return reindex_knowledge()


# ---------- 首页内容 ----------
@router.get("/banners", response_model=list[BannerOut])
def read_banners(user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return list_banners(db, user)


@router.post("/banners", response_model=BannerOut)
def add_banner(body: BannerIn, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return create_banner(db, user, body)


@router.patch("/banners/{banner_id}", response_model=BannerOut)
def patch_banner(
    banner_id: int,
    body: BannerUpdate,
    user: User = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    return update_banner(db, user, banner_id, body)


@router.delete("/banners/{banner_id}")
def remove_banner(banner_id: int, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    delete_banner(db, user, banner_id)
    return {"ok": True}


@router.get("/sections", response_model=list[SectionOut])
def read_sections(user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return list_sections(db, user)


@router.post("/sections", response_model=SectionOut)
def add_section(body: SectionIn, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return create_section(db, user, body)


@router.patch("/sections/{section_id}", response_model=SectionOut)
def patch_section(
    section_id: int,
    body: SectionUpdate,
    user: User = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    return update_section(db, user, section_id, body)


@router.delete("/sections/{section_id}")
def remove_section(section_id: int, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    delete_section(db, user, section_id)
    return {"ok": True}


@router.get("/testimonials", response_model=list[TestimonialOut])
def read_testimonials(user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return list_testimonials(db, user)


@router.post("/testimonials", response_model=TestimonialOut)
def add_testimonial(body: TestimonialIn, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return create_testimonial(db, user, body)


@router.patch("/testimonials/{row_id}", response_model=TestimonialOut)
def patch_testimonial(
    row_id: int,
    body: TestimonialUpdate,
    user: User = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    return update_testimonial(db, user, row_id, body)


@router.delete("/testimonials/{row_id}")
def remove_testimonial(row_id: int, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    delete_testimonial(db, user, row_id)
    return {"ok": True}


@router.get("/categories", response_model=list[CategoryOut])
def read_categories(user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    """商家自定义的分类标签，合集页左侧筛选项就是这套。"""
    return category_service.list_categories(db, user)


@router.post("/categories", response_model=CategoryOut)
def add_category(body: CategoryIn, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return category_service.create_category(db, user, body)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def patch_category(
    category_id: int,
    body: CategoryUpdate,
    user: User = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    return category_service.update_category(db, user, category_id, body)


@router.delete("/categories/{category_id}")
def remove_category(category_id: int, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    category_service.delete_category(db, user, category_id)
    return {"ok": True}


@router.get("/tags", response_model=list[TagOut])
def read_tags(user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    """商家自定义的商品标签，买家端卡片左上角显示的就是这套。"""
    return tag_service.list_tags(db, user)


@router.post("/tags", response_model=TagOut)
def add_tag(body: TagIn, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    return tag_service.create_tag(db, user, body)


@router.patch("/tags/{tag_id}", response_model=TagOut)
def patch_tag(
    tag_id: int,
    body: TagUpdate,
    user: User = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    return tag_service.update_tag(db, user, tag_id, body)


@router.delete("/tags/{tag_id}")
def remove_tag(tag_id: int, user: User = Depends(require_merchant), db: Session = Depends(get_db)):
    tag_service.delete_tag(db, user, tag_id)
    return {"ok": True}


@router.post("/uploads", response_model=UploadOut)
async def upload_image(
    file: UploadFile = File(...),
    user: User = Depends(require_merchant),
):
    """商家自己传图。存到 web/covers/uploads 下，返回可直接用的路径。"""
    del user
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        raise HTTPException(status_code=400, detail="只支持 jpg / png / webp / gif")
    folder = settings.web_dir / "covers" / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}{suffix}"
    target = folder / name
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片不要超过 5MB")
    target.write_bytes(content)
    return {"url": f"/covers/uploads/{name}"}
