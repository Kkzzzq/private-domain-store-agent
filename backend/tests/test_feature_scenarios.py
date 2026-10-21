"""逐功能场景归类与状态：只承认人工核对过断言的归类，其余明确“待确认/暂不可测试”。"""
from pathlib import Path

import pytest

from app.quality.catalog import cases
from app.quality.feature_catalog import (REVIEWED_SCENARIOS, SCENARIO_KINDS, SCENARIO_LABELS,
                                         catalog, scenario_view)


def feature(snapshot, feature_id):
    return next(row for row in snapshot["features"] if row["id"] == feature_id)


def registered_functional():
    return {row["id"] for row in cases() if row["kind"] == "functional" and row["state"] == "active"}


def test_every_feature_declares_the_four_scenario_kinds_and_a_status():
    snapshot = catalog()
    statuses = set()
    for row in snapshot["features"]:
        scenes = row["scenarios"]
        assert set(scenes["coverage"]) == set(SCENARIO_KINDS) == set(SCENARIO_LABELS), row["id"]
        assert scenes["status"] in ("covered", "partial", "unconfirmed", "untestable"), row["id"]
        assert scenes["status_note"], row["id"]
        statuses.add(scenes["status"])
        tools = {tool["case_id"] for tool in row["tools"]}
        # 已核对归类必须只引用本域已登记用例；未核对的一律进待确认清单。
        assert set(scenes["reviewed"]) <= tools, row["id"]
        assert set(scenes["unconfirmed_case_ids"]) == tools - set(scenes["reviewed"]), row["id"]
        for kind, ids in scenes["coverage"].items():
            assert set(ids) <= set(scenes["reviewed"]), row["id"]
        assert (scenes["status"] == "untestable") == (not tools), row["id"]
        assert (scenes["status"] == "unconfirmed") == (bool(tools) and not scenes["reviewed"]), row["id"]
    assert {"untestable", "unconfirmed", "partial"} <= statuses, statuses


def test_reviewed_classification_is_anchored_to_real_assertions():
    registered = registered_functional()
    root = Path(__file__).resolve().parents[1]
    for case_id, entry in REVIEWED_SCENARIOS.items():
        assert case_id in registered, case_id
        assert entry["kinds"] and set(entry["kinds"]) <= set(SCENARIO_KINDS), case_id
        file_part, _, node = entry["evidence"].partition("::")
        source = (root / file_part).read_text(encoding="utf-8-sig")
        assert f"def {node}(" in source, entry["evidence"]                 # 出处必须真实存在
        assert entry["why"], case_id


def test_cart_auth_and_orders_show_reviewed_scenarios_others_are_pending():
    snapshot = catalog()
    cart = feature(snapshot, "cart")["scenarios"]
    assert cart["status"] == "partial"
    assert "F11" in cart["coverage"]["abnormal"] and "F11" in cart["coverage"]["boundary"]
    assert "F16" in cart["coverage"]["normal"]
    assert "F11" in cart["reviewed"] and "数量" in cart["reviewed"]["F11"]["why"]
    auth = feature(snapshot, "auth")["scenarios"]
    assert auth["coverage"]["permission"] == ["F02"] and auth["status"] == "partial"
    orders = feature(snapshot, "orders")["scenarios"]
    assert set(orders["coverage"]["normal"]) >= {"F17", "F19"} and "F17" in orders["coverage"]["boundary"]
    products = feature(snapshot, "products")["scenarios"]
    assert products["status"] == "unconfirmed" and products["unconfirmed_case_ids"] and "E02" in products["unconfirmed_case_ids"]
    uploads = feature(snapshot, "uploads")["scenarios"]
    assert uploads["status"] == "untestable" and "暂不可测试" in uploads["status_note"]


def test_scenario_view_marks_unreviewed_cases_instead_of_guessing():
    tools = [{"case_id": "F11", "channel": "api"}, {"case_id": "E01", "channel": "page"}]
    view = scenario_view(tools)
    assert view["coverage"]["abnormal"] == ["F11"] and view["coverage"]["permission"] == []
    assert view["unconfirmed_case_ids"] == ["E01"] and view["status"] == "partial"
    assert view["status_note"].startswith("只有部分场景类别")
    pending = scenario_view([{"case_id": "E01", "channel": "page"}])
    assert pending["status"] == "unconfirmed" and pending["status_note"].startswith("已登记工具存在")
    assert scenario_view([])["status"] == "untestable"
    assert "不编造步骤" in scenario_view([])["status_note"]


def test_planning_view_and_version_carry_scenarios():
    from app.quality.feature_catalog import planning_view

    plain = catalog()
    assert feature(planning_view(plain), "cart")["scenarios"]["coverage"]["boundary"] == ["F11"]
    moved = [dict(row) for row in cases()]
    target = next(row for row in moved if row["id"] == "F11")
    target["state"] = "candidate"                      # 已核对用例被下架后，归类不能继续算作覆盖
    changed = catalog(moved)
    assert changed["version"] != plain["version"]
    assert feature(changed, "cart")["scenarios"]["coverage"]["abnormal"] == []
    with pytest.raises(StopIteration):
        feature(plain, "no-such-feature")


def test_every_feature_declares_how_it_cleans_up():
    snapshot = catalog()
    for row in snapshot["features"]:
        cleanup = row["cleanup"]
        tools = row["tools"]
        assert cleanup["evidence"] and cleanup["note"], row["id"]
        assert "不等于用例通过" in cleanup["note"], row["id"]
        if not tools:
            assert cleanup["modes"] == [] and cleanup["steps"] == [] and cleanup["untestable_note"], row["id"]
            continue
        assert cleanup["modes"] and cleanup["steps"] and cleanup["untestable_note"] is None, row["id"]
        assert cleanup["environments"], row["id"]
        if "isolated-local" in cleanup["environments"]:
            assert any("独立子进程" in step for step in cleanup["steps"]), row["id"]
            assert any("销毁子进程与临时工作区" in step for step in cleanup["steps"]), row["id"]
        if any(tool["channel"] == "page" for tool in tools):
            assert any("关闭浏览器与隔离站点" in step for step in cleanup["steps"]), row["id"]


def test_cleanup_view_records_real_shop_archive_and_page_teardown():
    from app.quality.feature_catalog import cleanup_view

    real = cleanup_view([{"case_id": "RF01", "channel": "api", "environments": ["real-nanzhi"]}])
    assert real["modes"] == ["real_record_archive_only"]
    assert any("只写入本轮专属测试记录" in step for step in real["steps"])
    assert any("保留审计" in step for step in real["steps"])
    assert "不删除业务数据" in real["note"]
    native = cleanup_view([{"case_id": "F11", "channel": "api", "environments": ["native-local"]}])
    assert native["modes"] == ["independent_mysql_namespace"]
    assert any("最小权限临时用户" in step for step in native["steps"])
    page = cleanup_view([{"case_id": "E01", "channel": "page", "environments": ["isolated-local", "native-local"]}])
    assert page["modes"] == ["isolated_child_workspace", "independent_mysql_namespace"]
    assert any("临时截图工作区" in step for step in page["steps"])
    assert cleanup_view([])["untestable_note"].startswith("当前环境没有已登记执行工具")
    # 规划视图同样带上清理方式，且不能撑大规划提示
    import json

    from app.quality.feature_catalog import planning_view

    view = planning_view(catalog())
    assert feature(view, "cart")["cleanup"]["modes"]
    assert len(json.dumps(view, ensure_ascii=False).encode()) < 45000