from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class SharedAccount(Base):
    """An account using unified view sessions; this does not grant store permissions."""
    __tablename__ = 'shared_accounts'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)


class MerchantAccess(Base):
    """Explicit store-opening permission for accounts without a legacy merchant role."""
    __tablename__ = 'merchant_access'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=True)


def can_manage_store(db, user):
    access = db.get(MerchantAccess, user.id)
    return access.enabled if access else user.role == 'merchant'
