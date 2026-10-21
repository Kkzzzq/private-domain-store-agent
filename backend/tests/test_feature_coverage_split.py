"""接口覆盖与页面覆盖必须分开记录：页面覆盖只看浏览器用例，接口覆盖不冒充页面验证。"""
import pytest

from app.quality.feature_catalog import catalog, channel_of, split_channels


def feature(snapshot, feature_id):
    return next(row for row in snapshot["features"] if row["id"] == feature_id)


def test_every_feature_records_api_and_page_coverage_separately():
    snapshot = catalog()
    assert snapshot["features"], "功能目录不应为空"
    for row in snapshot["features"]:
        split = row["coverage_split"]
        assert set(split) == {"api", "page"}, row["id"]
        for channel, entry in split.items():
            assert entry["status"] in ("partial_registered", "uncovered"), entry
            assert isinstance(entry["case_ids"], list) and entry["note"], entry
            assert (entry["status"] == "partial_registered") == bool(entry["case_ids"]), entry
        # 通道统计必须与 tools 的 channel 字段一致，不能靠用例编号前缀猜。
        assert {channel: sorted(entry["case_ids"]) for channel, entry in split.items()} == {
            channel: sorted(ids) for channel, ids in split_channels(row["tools"]).items()}
        assert all(tool["channel"] in ("api", "page") for tool in row["tools"])
        assert all(tool["channel"] == channel_of(tool) for tool in row["tools"])
        assert "分别记录" in row["coverage_note"]


def test_page_channel_only_contains_browser_or_click_tool_cases():
    snapshot = catalog()
    page_cases = [tool for row in snapshot["features"] for tool in row["tools"] if tool["channel"] == "page"]
    assert page_cases, "至少应有已登记的页面用例"
    allowed = {"registered_browser", "real_shop_browser", "registered_ui_action"}
    assert {tool["adapter"] for tool in page_cases} <= allowed, page_cases
    assert all(str(tool["adapter"]).endswith("browser") or tool["adapter"] == "registered_ui_action" for tool in page_cases)
    assert {"registered_browser", "registered_ui_action"} <= {tool["adapter"] for tool in page_cases}


def test_cart_split_shows_both_channels_and_uncovered_domain_shows_page_gap():
    snapshot = catalog()
    cart = feature(snapshot, "cart")
    assert cart["coverage_split"]["api"]["status"] == "partial_registered"
    assert "F11" in cart["coverage_split"]["api"]["case_ids"]
    assert cart["coverage_split"]["page"]["status"] == "partial_registered"
    assert "E01" in cart["coverage_split"]["page"]["case_ids"]
    assert any(case_id.startswith("U") for case_id in cart["coverage_split"]["page"]["case_ids"])   # 点击工具也在页面通道
    assert all(case_id.startswith(("E", "U")) for case_id in cart["coverage_split"]["page"]["case_ids"])
    assert "接口通过不能替代" in cart["coverage_split"]["page"]["note"]
    # 只有接口用例的功能域，页面覆盖必须明确记为未覆盖，不能混算成“已覆盖”。
    decoration = feature(snapshot, "decoration")
    assert decoration["coverage_split"]["api"]["status"] == "partial_registered"
    assert decoration["coverage_split"]["page"] == {"status": "uncovered", "case_ids": [], "note": decoration["coverage_split"]["page"]["note"]}


def test_channel_classification_and_split_helpers():
    assert channel_of({"adapter": "registered_browser"}) == "page"
    assert channel_of({"adapter": "real_shop_browser"}) == "page"
    assert channel_of({"adapter": "registered_pytest"}) == "api"
    assert channel_of({"adapter": "real_shop_api"}) == "api"
    assert channel_of({"adapter": "declarative_functional"}) == "api"
    assert channel_of({}) == "api"
    assert split_channels([{"case_id": "F11", "channel": "api"}, {"case_id": "E01", "channel": "page"}]) == {"api": ["F11"], "page": ["E01"]}


def test_planning_view_still_carries_the_split_without_endpoint_sources():
    from app.quality.feature_catalog import planning_view

    view = planning_view(catalog())
    cart = feature(view, "cart")
    assert "E01" in cart["coverage_split"]["page"], cart["coverage_split"]      # 紧凑投影只保留通道→用例
    assert any(case_id.startswith("U") for case_id in cart["coverage_split"]["page"])
    assert "endpoints" not in cart and "pages" not in cart
    assert "entry_points" in cart


def test_catalog_version_changes_with_channel_membership():
    from app.quality.catalog import cases

    plain = catalog(cases())
    moved = [dict(row) for row in cases()]
    target = next(row for row in moved if row["id"] == "F11")
    target["adapter"] = "registered_browser"          # 同一个用例改走页面通道，目录版本必须变化
    assert catalog(moved)["version"] != plain["version"]
    with pytest.raises(StopIteration):
        feature(plain, "not-a-feature")