"""Durable human support, fulfillment and after-sales records."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.models.tables import utcnow


class Conversation(Base):
    __tablename__ = 'support_conversations'
    __table_args__ = (UniqueConstraint('shop_id', 'customer_id', name='uq_support_customer_shop'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey('shops.id'), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    buyer_read: Mapped[int] = mapped_column(default=0)
    merchant_read: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Message(Base):
    __tablename__ = 'support_messages'
    __table_args__ = (UniqueConstraint('conversation_id', 'client_id', name='uq_support_message_retry'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey('support_conversations.id'), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    sender_role: Mapped[str] = mapped_column(String(16))
    client_id: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    order_no: Mapped[str] = mapped_column(String(32), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Shipment(Base):
    __tablename__ = 'order_shipments'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'), unique=True)
    carrier: Mapped[str] = mapped_column(String(40))
    tracking_number: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default='shipped')
    events: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AfterSale(Base):
    __tablename__ = 'after_sale_requests'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'), unique=True)
    kind: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(24), default='requested')
    return_carrier: Mapped[str] = mapped_column(String(40), default='')
    return_tracking: Mapped[str] = mapped_column(String(64), default='')
    events: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
