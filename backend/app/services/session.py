from app.db.redis_client import get_redis
from app.agent.summarizer import summarize


def compact_messages(state: dict, max_chars: int, llm=None) -> tuple[dict, str | None]:
    messages = list(state.get("messages") or [])
    summary = (state.get("summary") or "").strip()
    total = len(summary) + sum(len(item.get("content") or "") for item in messages)
    if total <= max_chars:
        return {"summary": summary, "messages": messages}, None
    summary_budget = min(600, max_chars // 3)
    tail = []
    remaining = max_chars - summary_budget
    for item in reversed(messages):
        content = item.get("content") or ""
        if len(content) > remaining:
            break
        tail.insert(0, item)
        remaining -= len(content)
        if len(tail) >= 4:
            break
    head = messages[:len(messages) - len(tail)]
    merged = summarize(head, summary, llm, max_chars=summary_budget)
    return {"summary": merged, "messages": tail}, "较早的对话已压缩为摘要"


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
