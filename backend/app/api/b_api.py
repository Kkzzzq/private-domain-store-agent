from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_db, require_merchant
from app.models.tables import User
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
)
from app.services.orders import list_b_orders, ship_order, ship_orders
from app.services import categories as category_service
from app.services import tags as tag_service

router = APIRouter(prefix="/b", tags=["b"])


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
