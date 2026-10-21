import json
from pathlib import Path

import pytest

from app.agent.answer_presentation import user_facing_answer


CASES = json.loads((Path(__file__).parent / "fixtures/answer_presentation.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES)
def test_no_citations_in_user_facing_answers(case):
    assert user_facing_answer(case["input"]) == case["expected"]


def test_history_is_cleaned_without_altering_user_input_or_stored_evidence(client):
    from app.services.session import SessionService
    from app.db.redis_client import get_redis
    service = SessionService()
    messages = [{"role": "user", "content": "after_sales.md是什么意思？"},
                {"role": "assistant", "content": CASES[0]["input"], "products": [{"id": 1}]}]
    for role in ("customer", "merchant"):
        service.save(42, 1, "old-source", {"summary": "", "messages": messages}, role)
        get_redis().set_json(f"chat-recent:{role}:42:1", {"session_id": "old-source", "messages": messages})
        for result in (service.load(42, 1, "old-source", role), service.recent(42, 1, role)):
            assert result["messages"][0] == messages[0]
            assert result["messages"][1]["content"] == CASES[0]["expected"]
            assert result["messages"][1]["products"] == [{"id": 1}]
        original = get_redis().get_json(service._key(42, 1, "old-source", role))
        assert original["messages"][1]["content"] == CASES[0]["input"]
