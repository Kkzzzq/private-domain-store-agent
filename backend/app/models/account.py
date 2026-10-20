from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class SharedAccount(Base):
    """An account explicitly enabled for both store management and shopping."""
    __tablename__ = 'shared_accounts'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
