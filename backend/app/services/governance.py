from datetime import timezone
from sqlalchemy.orm import object_session
from app.models.governance import AccountRestriction, ShopRestriction


def shop_blocked(shop):
    db = object_session(shop)
    restriction = db.get(ShopRestriction, shop.id) if db and shop.id else None
    return bool(restriction and restriction.blocked)


def shop_open(shop):
    return shop.status == 'open' and not shop_blocked(shop)


def account_allowed(db, user, payload=None):
    row = db.get(AccountRestriction, user.id)
    if not row:
        return True
    if row.disabled:
        return False
    if payload is not None and row.revoke_before:
        issued = payload.get('issued_at_us', float(payload.get('iat', 0)) * 1_000_000)
        cutoff = row.revoke_before_us or row.revoke_before.replace(tzinfo=timezone.utc).timestamp() * 1_000_000
        return issued >= cutoff
    return True
