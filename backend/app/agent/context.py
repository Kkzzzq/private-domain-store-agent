from dataclasses import dataclass, field
from contextvars import ContextVar

from sqlalchemy.orm import Session


@dataclass
class Actor:
    user_id: int
    role: str
    username: str
    shop_id: int
    session_id: str = ""
    products: list[dict] = field(default_factory=list)


_ctx: ContextVar[tuple[Session, Actor] | None] = ContextVar("store_actor", default=None)


def set_actor(db: Session, actor: Actor):
    return _ctx.set((db, actor))


def reset_actor(token) -> None:
    _ctx.reset(token)


def current() -> tuple[Session, Actor]:
    value = _ctx.get()
    if value is None:
        raise RuntimeError("缺少用户上下文")
    return value
