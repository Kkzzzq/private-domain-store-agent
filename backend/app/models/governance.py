from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.models.tables import utcnow


class ShopRestriction(Base):
    __tablename__ = 'platform_shop_restrictions'
    shop_id: Mapped[int] = mapped_column(ForeignKey('shops.id'), primary_key=True)
    blocked: Mapped[bool] = mapped_column(default=False)
    reason: Mapped[str] = mapped_column(String(200), default='')


class AccountRestriction(Base):
    __tablename__ = 'platform_account_restrictions'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    disabled: Mapped[bool] = mapped_column(default=False)
    revoke_before: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoke_before_us: Mapped[int] = mapped_column(BigInteger, default=0)
    reason: Mapped[str] = mapped_column(String(200), default='')


class ReviewRestriction(Base):
    __tablename__ = 'platform_review_restrictions'
    review_id: Mapped[int] = mapped_column(ForeignKey('reviews.id'), primary_key=True)
    hidden: Mapped[bool] = mapped_column(default=False)
    reason: Mapped[str] = mapped_column(String(200), default='')


class WorkspaceAction(Base):
    __tablename__ = 'platform_workspace_actions'
    id: Mapped[int] = mapped_column(primary_key=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    shop_id: Mapped[int] = mapped_column(ForeignKey('shops.id'))
    method: Mapped[str] = mapped_column(String(8))
    resource: Mapped[str] = mapped_column(String(300))
    reason: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default='pending')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
