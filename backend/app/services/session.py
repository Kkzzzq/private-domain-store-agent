from app.db.redis_client import get_redis


def compact_messages(state: dict, max_chars: int) -> tuple[dict, str | None]:
    messages = list(state.get("messages") or [])
    summary = (state.get("summary") or "").strip()
    total = sum(len(item.get("content") or "") for item in messages)
    if total <= max_chars or len(messages) <= 1:
        return {"summary": summary, "messages": messages}, None
    keep = 4 if len(messages) > 4 else 1
    head, tail = messages[:-keep], messages[-keep:]
    piece = "；".join(
        item["content"].strip()[:80]
        for item in head
        if item.get("role") == "user" and item.get("content")
    )
    merged = "；".join(part for part in (summary, piece) if part)
    return {"summary": merged[:400], "messages": tail}, "较早的对话已压缩为摘要"


class SessionService:
    def __init__(self) -> None:
        self.redis = get_redis()

    def _key(self, user_id: int, shop_id: int, session_id: str) -> str:
        return f"session:{user_id}:{shop_id}:{session_id}"

    def load(self, user_id: int, shop_id: int, session_id: str) -> dict:
        state = self.redis.get_json(self._key(user_id, shop_id, session_id))
        if not isinstance(state, dict):
            return {"summary": "", "messages": []}
        state.setdefault("summary", "")
        state.setdefault("messages", [])
        return state

    def save(self, user_id: int, shop_id: int, session_id: str, state: dict) -> None:
        self.redis.set_json(self._key(user_id, shop_id, session_id), state, ex=7 * 24 * 3600)
