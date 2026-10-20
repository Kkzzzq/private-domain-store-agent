from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.models.tables import utcnow


class Operator(Base):
    __tablename__ = 'platform_operators'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)


class OperationLog(Base):
    __tablename__ = 'platform_operation_logs'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    action: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
