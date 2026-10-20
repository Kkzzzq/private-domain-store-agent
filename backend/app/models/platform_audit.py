from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.models.tables import utcnow


class PlatformAudit(Base):
    __tablename__ = 'platform_management_audits'
    id: Mapped[int] = mapped_column(primary_key=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    target_type: Mapped[str] = mapped_column(String(24))
    target_id: Mapped[int] = mapped_column()
    action: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
