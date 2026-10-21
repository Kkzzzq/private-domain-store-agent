from app.core.config import settings
from app.quality.sandbox import Evidence


def test_a08_preparation_assertions_are_aggregated_and_distinct(client):
    from app.quality.scenarios import assistant_case
    keep = (settings.agent_mode, settings.agent_require_llm, settings.cloud_fallback_models, settings.cloud_max_tokens)
    evidence = Evidence()
    try:
        result = assistant_case("A08", evidence, "rules")
    finally:
        (settings.agent_mode, settings.agent_require_llm,
         settings.cloud_fallback_models, settings.cloud_max_tokens) = keep
    names = [row["name"] for row in evidence.assertions]
    # 下架准备原来按商品逐条记录，33 件商品会产生 33 条同名断言；现在汇总为一条。
    assert len(names) == len(set(names)), names
    assert len(evidence.assertions) <= 8, names
    assert all(row["passed"] for row in evidence.assertions), [row for row in evidence.assertions if not row["passed"]]
    login = [row for row in evidence.assertions if "登录成功" in row["name"]]
    assert {row["name"] for row in login} == {"合成测试身份 alice（买家）登录成功", "合成测试身份 merchant（商家）登录成功"}
    assert all(row["expected"]["expected_status"] == 200 and row["actual"] == 200 for row in login)
    offline = next(row for row in evidence.assertions if row["name"] == "仅隔离数据完成下架准备")
    assert offline["expected"]["商品数"] == offline["actual"]["下架成功"] > 0 and offline["actual"]["未成功"] == []
    assert "推荐热销商品" in [turn["input"] for turn in result["transcript"]]